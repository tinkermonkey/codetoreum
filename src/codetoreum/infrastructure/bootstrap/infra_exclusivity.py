"""
Infrastructure exclusivity checks (INV-21).

Verifies that production bootstrap has exclusive access to required infrastructure:
- Elasticsearch cluster/index prefix
- Redis instance/key prefix
- Docker daemon capacity
- GitHub credentials and rate limits

Exit codes:
- 70: Elasticsearch is shared with another service
- 71: Redis is shared with another service
- 72: Docker daemon lacks capacity headroom
- 73: GitHub token is invalid or rate-limited

The CODETOREUM_INFRA_EXCLUSIVITY=skip flag bypasses checks for local dev/tests only.
Must not be used in CI or production-shaped environments.
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Exit codes for each check
EXIT_CODE_ES_SHARED = 70
EXIT_CODE_REDIS_SHARED = 71
EXIT_CODE_DOCKER_CAPACITY = 72
EXIT_CODE_GITHUB_RATE_LIMIT = 73


@dataclass
class InfraExclusivityCheckResult:
    """Result of an infra exclusivity check."""

    check_name: str
    passed: bool
    error_message: Optional[str] = None
    exit_code: Optional[int] = None


def _should_skip_checks() -> bool:
    """
    Determine if infra-exclusivity checks should be skipped.

    Checks only if:
    1. CODETOREUM_INFRA_EXCLUSIVITY=skip is set
    2. Not in CI environment (CI_ENVIRONMENT check)

    Returns True only if skip flag is set AND not in CI.
    """
    skip_flag = os.environ.get("CODETOREUM_INFRA_EXCLUSIVITY", "").lower() == "skip"
    in_ci = os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI_ENVIRONMENT")

    if skip_flag and in_ci:
        logger.warning(
            "CODETOREUM_INFRA_EXCLUSIVITY=skip is set but CI environment detected. "
            "Checks will NOT be skipped in CI."
        )
        return False

    return skip_flag


async def check_elasticsearch_exclusivity(es_url: str) -> InfraExclusivityCheckResult:
    """
    Check if Elasticsearch cluster is exclusively used by Codetoreum.

    Verifies:
    1. Elasticsearch is accessible at es_url
    2. Index prefix "codetoreum-" exists and is the only prefix in the cluster

    Args:
        es_url: Elasticsearch URL (from ELASTICSEARCH_URL env var)

    Returns:
        InfraExclusivityCheckResult with pass/fail and error details
    """
    try:
        from elasticsearch import AsyncElasticsearch
    except ImportError:
        return InfraExclusivityCheckResult(
            check_name="elasticsearch",
            passed=False,
            error_message="elasticsearch package not installed",
            exit_code=EXIT_CODE_ES_SHARED,
        )

    es_client = AsyncElasticsearch([es_url])
    try:
        # List all indices to check for contention
        indices_response = await es_client.indices.get(index="*")
        indices = list(indices_response.keys())

        # Check for codetoreum indices
        codetoreum_indices = [i for i in indices if i.startswith("codetoreum-")]
        non_codetoreum_indices = [i for i in indices if not i.startswith("codetoreum-")]

        if non_codetoreum_indices:
            return InfraExclusivityCheckResult(
                check_name="elasticsearch",
                passed=False,
                error_message=(
                    f"Elasticsearch cluster is shared with other services. "
                    f"Found {len(non_codetoreum_indices)} non-Codetoreum indices: "
                    f"{', '.join(non_codetoreum_indices[:5])}"
                    f"{'...' if len(non_codetoreum_indices) > 5 else ''}"
                ),
                exit_code=EXIT_CODE_ES_SHARED,
            )

        logger.info(f"Elasticsearch cluster is exclusive (found {len(codetoreum_indices)} Codetoreum indices)")
        return InfraExclusivityCheckResult(check_name="elasticsearch", passed=True)

    except Exception as e:
        return InfraExclusivityCheckResult(
            check_name="elasticsearch",
            passed=False,
            error_message=f"Failed to verify Elasticsearch exclusivity: {e}",
            exit_code=EXIT_CODE_ES_SHARED,
        )
    finally:
        await es_client.close()


async def check_redis_exclusivity(redis_url: str, key_prefix: str = "codetoreum:") -> InfraExclusivityCheckResult:
    """
    Check if Redis instance is exclusively used by Codetoreum.

    Verifies:
    1. Redis is accessible at redis_url
    2. All keys in the database start with the key_prefix

    Args:
        redis_url: Redis URL (from REDIS_URL env var)
        key_prefix: Expected key prefix (default: "codetoreum:")

    Returns:
        InfraExclusivityCheckResult with pass/fail and error details
    """
    try:
        import redis.asyncio as aioredis
    except ImportError:
        return InfraExclusivityCheckResult(
            check_name="redis",
            passed=False,
            error_message="redis package not installed",
            exit_code=EXIT_CODE_REDIS_SHARED,
        )

    redis_client = None
    try:
        redis_client = await aioredis.from_url(redis_url)

        # Get all keys in the database
        all_keys = await redis_client.keys("*")

        # Check for non-Codetoreum keys
        non_codetoreum_keys = [k for k in all_keys if not k.startswith(key_prefix)]

        if non_codetoreum_keys:
            return InfraExclusivityCheckResult(
                check_name="redis",
                passed=False,
                error_message=(
                    f"Redis instance is shared with other services. "
                    f"Found {len(non_codetoreum_keys)} non-Codetoreum keys: "
                    f"{', '.join(str(k)[:40] for k in non_codetoreum_keys[:5])}"
                    f"{'...' if len(non_codetoreum_keys) > 5 else ''}"
                ),
                exit_code=EXIT_CODE_REDIS_SHARED,
            )

        logger.info(f"Redis instance is exclusive ({len(all_keys)} Codetoreum keys)")
        return InfraExclusivityCheckResult(check_name="redis", passed=True)

    except Exception as e:
        return InfraExclusivityCheckResult(
            check_name="redis",
            passed=False,
            error_message=f"Failed to verify Redis exclusivity: {e}",
            exit_code=EXIT_CODE_REDIS_SHARED,
        )
    finally:
        if redis_client:
            await redis_client.close()


def check_docker_capacity(agent_count: int = 1, max_parallel_work_items: int = 5) -> InfraExclusivityCheckResult:
    """
    Check if Docker daemon has sufficient capacity headroom.

    Verifies that available container capacity can accommodate:
    agent_count × max_parallel_work_items + 20% headroom

    Args:
        agent_count: Number of configured agents (default: 1)
        max_parallel_work_items: Max work items per agent (default: 5)

    Returns:
        InfraExclusivityCheckResult with pass/fail and error details
    """
    try:
        import docker
    except ImportError:
        return InfraExclusivityCheckResult(
            check_name="docker",
            passed=False,
            error_message="docker package not installed",
            exit_code=EXIT_CODE_DOCKER_CAPACITY,
        )

    try:
        docker_client = docker.from_env()
        containers = docker_client.containers.list(all=True)
        running_containers = docker_client.containers.list()

        required_capacity = agent_count * max_parallel_work_items
        headroom_factor = 1.2  # 20% headroom
        required_with_headroom = int(required_capacity * headroom_factor)

        # Approximate max containers (typically 256 on most systems)
        max_container_count = 256
        available_capacity = max_container_count - len(containers)

        if available_capacity < required_with_headroom:
            return InfraExclusivityCheckResult(
                check_name="docker",
                passed=False,
                error_message=(
                    f"Docker daemon lacks capacity headroom. "
                    f"Current containers: {len(containers)}, running: {len(running_containers)}. "
                    f"Required capacity with headroom: {required_with_headroom}. "
                    f"Available: {available_capacity}. "
                    f"Reduce container count or increase Docker max-containers limit."
                ),
                exit_code=EXIT_CODE_DOCKER_CAPACITY,
            )

        logger.info(
            f"Docker daemon has sufficient capacity "
            f"(using {len(containers)} of ~{max_container_count}, "
            f"required {required_with_headroom} for bootstrap)"
        )
        return InfraExclusivityCheckResult(check_name="docker", passed=True)

    except Exception as e:
        return InfraExclusivityCheckResult(
            check_name="docker",
            passed=False,
            error_message=f"Failed to verify Docker capacity: {e}",
            exit_code=EXIT_CODE_DOCKER_CAPACITY,
        )


async def check_github_rate_limit(github_token: str) -> InfraExclusivityCheckResult:
    """
    Check if GitHub API credentials are valid and have rate-limit headroom.

    Verifies:
    1. GitHub token is valid
    2. Rate limit headroom is >= 1000 requests

    Args:
        github_token: GitHub API token (from GITHUB_TOKEN env var)

    Returns:
        InfraExclusivityCheckResult with pass/fail and error details
    """
    if not github_token:
        return InfraExclusivityCheckResult(
            check_name="github",
            passed=False,
            error_message="GITHUB_TOKEN not set",
            exit_code=EXIT_CODE_GITHUB_RATE_LIMIT,
        )

    try:
        from codetoreum.infrastructure.http.github_graphql_client import (
            GitHubGraphQLClient,
            GitHubGraphQLConfig,
        )
    except ImportError:
        return InfraExclusivityCheckResult(
            check_name="github",
            passed=False,
            error_message="GitHub client not available",
            exit_code=EXIT_CODE_GITHUB_RATE_LIMIT,
        )

    try:
        config = GitHubGraphQLConfig(token=github_token)
        client = GitHubGraphQLClient(config)

        # Query rate limit
        rate_limit_query = """
        query {
            viewer {
                login
            }
            rateLimit {
                limit
                remaining
                resetAt
            }
        }
        """

        result = await client.execute(rate_limit_query)

        if "errors" in result:
            error_msg = result.get("errors", [{}])[0].get("message", "Unknown error")
            return InfraExclusivityCheckResult(
                check_name="github",
                passed=False,
                error_message=f"GitHub API error: {error_msg}",
                exit_code=EXIT_CODE_GITHUB_RATE_LIMIT,
            )

        remaining = result.get("data", {}).get("rateLimit", {}).get("remaining", 0)
        limit = result.get("data", {}).get("rateLimit", {}).get("limit", 0)

        if remaining < 1000:
            return InfraExclusivityCheckResult(
                check_name="github",
                passed=False,
                error_message=(
                    f"GitHub rate limit headroom insufficient. "
                    f"Remaining: {remaining}/{limit} (need >= 1000)"
                ),
                exit_code=EXIT_CODE_GITHUB_RATE_LIMIT,
            )

        login = result.get("data", {}).get("viewer", {}).get("login", "unknown")
        logger.info(f"GitHub token valid for user {login} ({remaining}/{limit} requests remaining)")
        return InfraExclusivityCheckResult(check_name="github", passed=True)

    except Exception as e:
        return InfraExclusivityCheckResult(
            check_name="github",
            passed=False,
            error_message=f"Failed to verify GitHub credentials: {e}",
            exit_code=EXIT_CODE_GITHUB_RATE_LIMIT,
        )


async def verify_infra_exclusivity(
    elasticsearch_url: str,
    redis_url: str,
    github_token: str,
    agent_count: int = 1,
    max_parallel_work_items: int = 5,
) -> None:
    """
    Run all infra-exclusivity checks and exit on failure.

    This is the main entry point for infra-exclusivity verification.
    Called from bootstrap/register_project.py and ProductionApplicationBootstrap.setup().

    If CODETOREUM_INFRA_EXCLUSIVITY=skip is set and not in CI, skips all checks.

    Args:
        elasticsearch_url: Elasticsearch URL (from ELASTICSEARCH_URL env var)
        redis_url: Redis URL (from REDIS_URL env var)
        github_token: GitHub API token (from GITHUB_TOKEN env var)
        agent_count: Number of agents to verify Docker capacity for
        max_parallel_work_items: Max parallel work items per agent

    Exits with code 70-73 if any check fails.
    """
    if _should_skip_checks():
        logger.info("CODETOREUM_INFRA_EXCLUSIVITY=skip: skipping infra-exclusivity checks")
        return

    logger.info("Starting infra-exclusivity checks...")

    # Run async checks concurrently
    es_result, redis_result, github_result = await asyncio.gather(
        check_elasticsearch_exclusivity(elasticsearch_url),
        check_redis_exclusivity(redis_url),
        check_github_rate_limit(github_token),
    )

    # Run sync Docker check
    docker_result = check_docker_capacity(agent_count, max_parallel_work_items)

    # Collect results
    results = [es_result, redis_result, docker_result, github_result]
    failures = [r for r in results if not r.passed]

    if failures:
        logger.error(f"Infra-exclusivity check(s) failed ({len(failures)}/{len(results)})")
        for result in failures:
            logger.error(f"  {result.check_name}: {result.error_message}")

        # Exit with the first failure's exit code
        sys.exit(failures[0].exit_code or 1)

    logger.info(f"All infra-exclusivity checks passed ({len(results)}/{len(results)})")
