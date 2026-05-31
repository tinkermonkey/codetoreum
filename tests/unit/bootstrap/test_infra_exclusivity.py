"""Tests for infrastructure exclusivity checks (INV-21)."""

import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from codetoreum.infrastructure.bootstrap.infra_exclusivity import (
    EXIT_CODE_DOCKER_CAPACITY,
    EXIT_CODE_ES_SHARED,
    EXIT_CODE_GITHUB_RATE_LIMIT,
    EXIT_CODE_REDIS_SHARED,
    InfraExclusivityError,
    check_docker_capacity,
    check_elasticsearch_exclusivity,
    check_github_rate_limit,
    check_redis_exclusivity,
    verify_infra_exclusivity,
)


class TestElasticsearchExclusivity:
    """Tests for Elasticsearch exclusivity check."""

    @pytest.mark.asyncio
    async def test_es_exclusive_cluster_passes(self) -> None:
        """Verify Elasticsearch exclusivity check passes with only codetoreum indices."""
        mock_es = AsyncMock()
        mock_es.indices.get.return_value = {
            "codetoreum-events": {},
            "codetoreum-config": {},
        }
        mock_es.close = AsyncMock()

        with patch("elasticsearch.AsyncElasticsearch", return_value=mock_es):
            result = await check_elasticsearch_exclusivity("http://localhost:9200")

        assert result.passed is True
        assert result.error_message is None
        assert result.exit_code is None

    @pytest.mark.asyncio
    async def test_es_shared_cluster_fails(self) -> None:
        """Verify Elasticsearch exclusivity check fails when other indices exist."""
        mock_es = AsyncMock()
        mock_es.indices.get.return_value = {
            "codetoreum-events": {},
            "switchyard-data": {},  # Non-Codetoreum index
            "logstash-2024": {},  # Another non-Codetoreum index
        }
        mock_es.close = AsyncMock()

        with patch("elasticsearch.AsyncElasticsearch", return_value=mock_es):
            result = await check_elasticsearch_exclusivity("http://localhost:9200")

        assert result.passed is False
        assert result.check_name == "elasticsearch"
        assert result.exit_code == EXIT_CODE_ES_SHARED
        assert "shared with other services" in result.error_message

    @pytest.mark.asyncio
    async def test_es_empty_cluster_passes(self) -> None:
        """Verify Elasticsearch exclusivity check passes with no indices."""
        mock_es = AsyncMock()
        mock_es.indices.get.return_value = {}
        mock_es.close = AsyncMock()

        with patch("elasticsearch.AsyncElasticsearch", return_value=mock_es):
            result = await check_elasticsearch_exclusivity("http://localhost:9200")

        assert result.passed is True

    @pytest.mark.asyncio
    async def test_es_connection_error_fails(self) -> None:
        """Verify Elasticsearch exclusivity check fails on connection error."""
        mock_es = AsyncMock()
        mock_es.indices.get.side_effect = ConnectionError("Cannot connect to Elasticsearch")
        mock_es.close = AsyncMock()

        with patch("elasticsearch.AsyncElasticsearch", return_value=mock_es):
            result = await check_elasticsearch_exclusivity("http://localhost:9200")

        assert result.passed is False
        assert result.exit_code == EXIT_CODE_ES_SHARED
        assert "Failed to verify Elasticsearch exclusivity" in result.error_message


class TestRedisExclusivity:
    """Tests for Redis exclusivity check."""

    @pytest.mark.asyncio
    async def test_redis_exclusive_instance_passes(self) -> None:
        """Verify Redis exclusivity check passes with only codetoreum: keys."""
        mock_redis = AsyncMock()
        mock_redis.keys.return_value = ["codetoreum:lock:1", "codetoreum:event:2"]
        mock_redis.close = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            result = await check_redis_exclusivity("redis://localhost:6379/0")

        assert result.passed is True
        assert result.error_message is None
        assert result.exit_code is None

    @pytest.mark.asyncio
    async def test_redis_shared_instance_fails(self) -> None:
        """Verify Redis exclusivity check fails when other keys exist."""
        mock_redis = AsyncMock()
        mock_redis.keys.return_value = [
            "codetoreum:lock:1",
            "switchyard:queue:1",  # Non-Codetoreum key
            "cache:data:2",  # Another non-Codetoreum key
        ]
        mock_redis.close = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            result = await check_redis_exclusivity("redis://localhost:6379/0")

        assert result.passed is False
        assert result.check_name == "redis"
        assert result.exit_code == EXIT_CODE_REDIS_SHARED
        assert "shared with other services" in result.error_message
        assert "2 non-Codetoreum keys" in result.error_message

    @pytest.mark.asyncio
    async def test_redis_empty_instance_passes(self) -> None:
        """Verify Redis exclusivity check passes with no keys."""
        mock_redis = AsyncMock()
        mock_redis.keys.return_value = []
        mock_redis.close = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            result = await check_redis_exclusivity("redis://localhost:6379/0")

        assert result.passed is True

    @pytest.mark.asyncio
    async def test_redis_custom_prefix_passes(self) -> None:
        """Verify Redis exclusivity check respects custom key prefix."""
        mock_redis = AsyncMock()
        mock_redis.keys.return_value = ["custom:key:1", "custom:key:2"]
        mock_redis.close = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            result = await check_redis_exclusivity("redis://localhost:6379/0", key_prefix="custom:")

        assert result.passed is True

    @pytest.mark.asyncio
    async def test_redis_connection_error_fails(self) -> None:
        """Verify Redis exclusivity check fails on connection error."""
        with patch("redis.asyncio.from_url", side_effect=ConnectionError("Cannot connect to Redis")):
            result = await check_redis_exclusivity("redis://localhost:6379/0")

        assert result.passed is False
        assert result.exit_code == EXIT_CODE_REDIS_SHARED
        assert "Failed to verify Redis exclusivity" in result.error_message


class TestDockerCapacity:
    """Tests for Docker daemon capacity check."""

    def test_docker_sufficient_capacity_passes(self) -> None:
        """Verify Docker capacity check passes with sufficient headroom."""
        mock_docker = Mock()
        mock_containers = Mock()

        # 10 existing containers, need 6 (1 agent × 5 work items) + 20% = 7.2
        # Available: 256 - 10 = 246 > 7.2 ✓
        mock_containers.list.side_effect = [
            [Mock() for _ in range(10)],  # all containers
            [Mock() for _ in range(3)],   # running containers
        ]
        mock_docker.containers = mock_containers

        with patch("docker.from_env", return_value=mock_docker):
            result = check_docker_capacity(agent_count=1, max_parallel_work_items=5)

        assert result.passed is True
        assert result.error_message is None
        assert result.exit_code is None

    def test_docker_insufficient_capacity_fails(self) -> None:
        """Verify Docker capacity check fails when not enough headroom."""
        mock_docker = Mock()
        mock_containers = Mock()

        # 250 existing containers, need 12 (2 agents × 5 work items) + 20% = 14.4
        # Available: 256 - 250 = 6 < 14.4 ✗
        mock_containers.list.side_effect = [
            [Mock() for _ in range(250)],  # all containers
            [Mock() for _ in range(100)],  # running containers
        ]
        mock_docker.containers = mock_containers

        with patch("docker.from_env", return_value=mock_docker):
            result = check_docker_capacity(agent_count=2, max_parallel_work_items=5)

        assert result.passed is False
        assert result.exit_code == EXIT_CODE_DOCKER_CAPACITY
        assert "lacks capacity headroom" in result.error_message

    def test_docker_connection_error_fails(self) -> None:
        """Verify Docker capacity check fails on connection error."""
        with patch("docker.from_env", side_effect=ConnectionError("Cannot connect to Docker")):
            result = check_docker_capacity()

        assert result.passed is False
        assert result.exit_code == EXIT_CODE_DOCKER_CAPACITY
        assert "Failed to verify Docker capacity" in result.error_message

    def test_docker_default_parameters(self) -> None:
        """Verify Docker capacity check uses sensible defaults."""
        mock_docker = Mock()
        mock_containers = Mock()
        mock_containers.list.side_effect = [
            [Mock() for _ in range(10)],
            [Mock() for _ in range(3)],
        ]
        mock_docker.containers = mock_containers

        with patch("docker.from_env", return_value=mock_docker):
            # Call without parameters
            result = check_docker_capacity()

        assert result.passed is True
        # Verify the default calls were made
        assert mock_containers.list.call_count == 2


class TestGitHubRateLimit:
    """Tests for GitHub rate-limit check."""

    @pytest.mark.asyncio
    async def test_github_valid_token_with_headroom_passes(self) -> None:
        """Verify GitHub rate-limit check passes with sufficient headroom."""
        mock_client = AsyncMock()
        mock_client.execute.return_value = {
            "data": {
                "viewer": {"login": "test-user"},
                "rateLimit": {
                    "limit": 5000,
                    "remaining": 4500,  # 4500 > 1000 ✓
                    "resetAt": "2026-05-31T23:00:00Z",
                },
            }
        }

        with patch(
            "codetoreum.infrastructure.http.github_graphql_client.GitHubGraphQLClient",
            return_value=mock_client,
        ):
            result = await check_github_rate_limit("valid-token")

        assert result.passed is True
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_github_rate_limit_exhausted_fails(self) -> None:
        """Verify GitHub rate-limit check fails when headroom below 1000."""
        mock_client = AsyncMock()
        mock_client.execute.return_value = {
            "data": {
                "viewer": {"login": "test-user"},
                "rateLimit": {
                    "limit": 5000,
                    "remaining": 500,  # 500 < 1000 ✗
                    "resetAt": "2026-05-31T23:00:00Z",
                },
            }
        }

        with patch(
            "codetoreum.infrastructure.http.github_graphql_client.GitHubGraphQLClient",
            return_value=mock_client,
        ):
            result = await check_github_rate_limit("valid-token")

        assert result.passed is False
        assert result.exit_code == EXIT_CODE_GITHUB_RATE_LIMIT
        assert "rate limit headroom insufficient" in result.error_message

    @pytest.mark.asyncio
    async def test_github_missing_token_fails(self) -> None:
        """Verify GitHub rate-limit check fails when token is missing."""
        result = await check_github_rate_limit("")

        assert result.passed is False
        assert result.exit_code == EXIT_CODE_GITHUB_RATE_LIMIT
        assert "GITHUB_TOKEN not set" in result.error_message

    @pytest.mark.asyncio
    async def test_github_api_error_fails(self) -> None:
        """Verify GitHub rate-limit check fails on API error."""
        mock_client = AsyncMock()
        mock_client.execute.return_value = {
            "errors": [{"message": "Bad credentials"}]
        }

        with patch(
            "codetoreum.infrastructure.http.github_graphql_client.GitHubGraphQLClient",
            return_value=mock_client,
        ):
            result = await check_github_rate_limit("invalid-token")

        assert result.passed is False
        assert result.exit_code == EXIT_CODE_GITHUB_RATE_LIMIT
        assert "GitHub API error" in result.error_message
        assert "Bad credentials" in result.error_message

    @pytest.mark.asyncio
    async def test_github_connection_error_fails(self) -> None:
        """Verify GitHub rate-limit check fails on connection error."""
        mock_client = AsyncMock()
        mock_client.execute.side_effect = ConnectionError("Cannot connect to GitHub")

        with patch(
            "codetoreum.infrastructure.http.github_graphql_client.GitHubGraphQLClient",
            return_value=mock_client,
        ):
            result = await check_github_rate_limit("valid-token")

        assert result.passed is False
        assert result.exit_code == EXIT_CODE_GITHUB_RATE_LIMIT
        assert "Failed to verify GitHub credentials" in result.error_message


class TestSkipFlag:
    """Tests for CODETOREUM_INFRA_EXCLUSIVITY=skip flag."""

    def test_skip_flag_not_set_returns_false(self) -> None:
        """Verify skip flag detection returns False when not set."""
        with patch.dict(os.environ, {}, clear=True):
            from codetoreum.infrastructure.bootstrap.infra_exclusivity import _should_skip_checks
            assert _should_skip_checks() is False

    def test_skip_flag_set_returns_true_not_in_ci(self) -> None:
        """Verify skip flag is respected when set and not in CI."""
        with patch.dict(os.environ, {"CODETOREUM_INFRA_EXCLUSIVITY": "skip"}, clear=True):
            from codetoreum.infrastructure.bootstrap.infra_exclusivity import _should_skip_checks
            assert _should_skip_checks() is True

    def test_skip_flag_ignored_in_github_actions(self) -> None:
        """Verify skip flag is ignored when GITHUB_ACTIONS is set."""
        with patch.dict(os.environ, {
            "CODETOREUM_INFRA_EXCLUSIVITY": "skip",
            "GITHUB_ACTIONS": "true",
        }, clear=True):
            from codetoreum.infrastructure.bootstrap.infra_exclusivity import _should_skip_checks
            assert _should_skip_checks() is False

    def test_skip_flag_ignored_in_ci_environment(self) -> None:
        """Verify skip flag is ignored when CI_ENVIRONMENT is set."""
        with patch.dict(os.environ, {
            "CODETOREUM_INFRA_EXCLUSIVITY": "skip",
            "CI_ENVIRONMENT": "github-actions",
        }, clear=True):
            from codetoreum.infrastructure.bootstrap.infra_exclusivity import _should_skip_checks
            assert _should_skip_checks() is False

    def test_skip_flag_case_insensitive(self) -> None:
        """Verify skip flag is case-insensitive."""
        with patch.dict(os.environ, {"CODETOREUM_INFRA_EXCLUSIVITY": "SKIP"}, clear=True):
            from codetoreum.infrastructure.bootstrap.infra_exclusivity import _should_skip_checks
            assert _should_skip_checks() is True

        with patch.dict(os.environ, {"CODETOREUM_INFRA_EXCLUSIVITY": "Skip"}, clear=True):
            from codetoreum.infrastructure.bootstrap.infra_exclusivity import _should_skip_checks
            assert _should_skip_checks() is True


class TestExitCodes:
    """Tests for exit code constants."""

    def test_exit_codes_are_distinct(self) -> None:
        """Verify all exit codes are unique."""
        codes = [
            EXIT_CODE_ES_SHARED,
            EXIT_CODE_REDIS_SHARED,
            EXIT_CODE_DOCKER_CAPACITY,
            EXIT_CODE_GITHUB_RATE_LIMIT,
        ]
        assert len(codes) == len(set(codes)), "Exit codes must be unique"

    def test_exit_codes_in_valid_range(self) -> None:
        """Verify exit codes are in valid range (64-113 for custom usage)."""
        codes = [
            EXIT_CODE_ES_SHARED,
            EXIT_CODE_REDIS_SHARED,
            EXIT_CODE_DOCKER_CAPACITY,
            EXIT_CODE_GITHUB_RATE_LIMIT,
        ]
        # Standard BSD convention: 64-113 for custom exit codes
        assert all(64 <= code <= 113 for code in codes), "Exit codes should be in valid range"

    def test_exit_code_values(self) -> None:
        """Verify exit code values match specification."""
        assert EXIT_CODE_ES_SHARED == 70
        assert EXIT_CODE_REDIS_SHARED == 71
        assert EXIT_CODE_DOCKER_CAPACITY == 72
        assert EXIT_CODE_GITHUB_RATE_LIMIT == 73


class TestVerifyInfraExclusivity:
    """Tests for verify_infra_exclusivity orchestrator function."""

    @pytest.mark.asyncio
    async def test_all_checks_pass_returns_successfully(self) -> None:
        """Verify verify_infra_exclusivity returns without error when all checks pass."""
        mock_es = AsyncMock()
        mock_es.indices.get.return_value = {"codetoreum-events": {}}
        mock_es.close = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.keys.return_value = ["codetoreum:lock:1"]
        mock_redis.close = AsyncMock()

        mock_github_client = AsyncMock()
        mock_github_client.execute.return_value = {
            "data": {
                "viewer": {"login": "test-user"},
                "rateLimit": {
                    "limit": 5000,
                    "remaining": 4500,
                    "resetAt": "2026-05-31T23:00:00Z",
                },
            }
        }

        mock_docker = Mock()
        mock_containers = Mock()
        mock_containers.list.side_effect = [[Mock()], [Mock()]]
        mock_docker.containers = mock_containers

        with patch("elasticsearch.AsyncElasticsearch", return_value=mock_es):
            with patch("redis.asyncio.from_url", return_value=mock_redis):
                with patch(
                    "codetoreum.infrastructure.http.github_graphql_client.GitHubGraphQLClient",
                    return_value=mock_github_client,
                ):
                    with patch("docker.from_env", return_value=mock_docker):
                        # Should not raise
                        await verify_infra_exclusivity(
                            "http://localhost:9200",
                            "redis://localhost:6379/0",
                            "valid-token",
                        )

    @pytest.mark.asyncio
    async def test_elasticsearch_failure_raises_error(self) -> None:
        """Verify verify_infra_exclusivity raises InfraExclusivityError on Elasticsearch failure."""
        mock_es = AsyncMock()
        mock_es.indices.get.return_value = {
            "codetoreum-events": {},
            "other-service-index": {},
        }
        mock_es.close = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.keys.return_value = ["codetoreum:lock:1"]
        mock_redis.close = AsyncMock()

        mock_github_client = AsyncMock()
        mock_github_client.execute.return_value = {
            "data": {
                "viewer": {"login": "test-user"},
                "rateLimit": {
                    "limit": 5000,
                    "remaining": 4500,
                    "resetAt": "2026-05-31T23:00:00Z",
                },
            }
        }

        mock_docker = Mock()
        mock_containers = Mock()
        mock_containers.list.side_effect = [[Mock()], [Mock()]]
        mock_docker.containers = mock_containers

        with patch("elasticsearch.AsyncElasticsearch", return_value=mock_es):
            with patch("redis.asyncio.from_url", return_value=mock_redis):
                with patch(
                    "codetoreum.infrastructure.http.github_graphql_client.GitHubGraphQLClient",
                    return_value=mock_github_client,
                ):
                    with patch("docker.from_env", return_value=mock_docker):
                        with pytest.raises(InfraExclusivityError) as exc_info:
                            await verify_infra_exclusivity(
                                "http://localhost:9200",
                                "redis://localhost:6379/0",
                                "valid-token",
                            )

        assert exc_info.value.exit_code == EXIT_CODE_ES_SHARED

    @pytest.mark.asyncio
    async def test_redis_failure_raises_error(self) -> None:
        """Verify verify_infra_exclusivity raises InfraExclusivityError on Redis failure."""
        mock_es = AsyncMock()
        mock_es.indices.get.return_value = {"codetoreum-events": {}}
        mock_es.close = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.keys.return_value = ["codetoreum:lock:1", "other-service:key:1"]
        mock_redis.close = AsyncMock()

        mock_github_client = AsyncMock()
        mock_github_client.execute.return_value = {
            "data": {
                "viewer": {"login": "test-user"},
                "rateLimit": {
                    "limit": 5000,
                    "remaining": 4500,
                    "resetAt": "2026-05-31T23:00:00Z",
                },
            }
        }

        mock_docker = Mock()
        mock_containers = Mock()
        mock_containers.list.side_effect = [[Mock()], [Mock()]]
        mock_docker.containers = mock_containers

        with patch("elasticsearch.AsyncElasticsearch", return_value=mock_es):
            with patch("redis.asyncio.from_url", return_value=mock_redis):
                with patch(
                    "codetoreum.infrastructure.http.github_graphql_client.GitHubGraphQLClient",
                    return_value=mock_github_client,
                ):
                    with patch("docker.from_env", return_value=mock_docker):
                        with pytest.raises(InfraExclusivityError) as exc_info:
                            await verify_infra_exclusivity(
                                "http://localhost:9200",
                                "redis://localhost:6379/0",
                                "valid-token",
                            )

        assert exc_info.value.exit_code == EXIT_CODE_REDIS_SHARED

    @pytest.mark.asyncio
    async def test_skip_flag_bypasses_checks(self) -> None:
        """Verify verify_infra_exclusivity respects skip flag and doesn't run checks."""
        with patch.dict(os.environ, {"CODETOREUM_INFRA_EXCLUSIVITY": "skip"}, clear=True):
            # Should return without making any calls
            with patch("codetoreum.infrastructure.bootstrap.infra_exclusivity.check_elasticsearch_exclusivity") as mock_es:
                with patch("codetoreum.infrastructure.bootstrap.infra_exclusivity.check_redis_exclusivity") as mock_redis:
                    with patch("codetoreum.infrastructure.bootstrap.infra_exclusivity.check_github_rate_limit") as mock_github:
                        with patch("codetoreum.infrastructure.bootstrap.infra_exclusivity.check_docker_capacity") as mock_docker:
                            await verify_infra_exclusivity(
                                "http://localhost:9200",
                                "redis://localhost:6379/0",
                                "valid-token",
                            )

                            # Verify no checks were called
                            mock_es.assert_not_called()
                            mock_redis.assert_not_called()
                            mock_github.assert_not_called()
                            mock_docker.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_failure_determines_exit_code(self) -> None:
        """Verify verify_infra_exclusivity raises with first failure's exit code."""
        mock_es = AsyncMock()
        mock_es.indices.get.return_value = {
            "codetoreum-events": {},
            "other-service-index": {},  # ES fails
        }
        mock_es.close = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.keys.return_value = [b"other-service:key:1"]  # Redis also fails
        mock_redis.close = AsyncMock()

        mock_github_client = AsyncMock()
        mock_github_client.execute.return_value = {
            "errors": [{"message": "Bad credentials"}]  # GitHub also fails
        }

        mock_docker = Mock()
        mock_containers = Mock()
        mock_containers.list.side_effect = [
            [Mock() for _ in range(250)],  # Docker capacity fails
            [Mock() for _ in range(100)],
        ]
        mock_docker.containers = mock_containers

        with patch("elasticsearch.AsyncElasticsearch", return_value=mock_es):
            with patch("redis.asyncio.from_url", return_value=mock_redis):
                with patch(
                    "codetoreum.infrastructure.http.github_graphql_client.GitHubGraphQLClient",
                    return_value=mock_github_client,
                ):
                    with patch("docker.from_env", return_value=mock_docker):
                        with pytest.raises(InfraExclusivityError) as exc_info:
                            await verify_infra_exclusivity(
                                "http://localhost:9200",
                                "redis://localhost:6379/0",
                                "invalid-token",
                                agent_count=2,
                                max_parallel_work_items=5,
                            )

        # Should be ES exit code since ES check runs first
        assert exc_info.value.exit_code == EXIT_CODE_ES_SHARED
