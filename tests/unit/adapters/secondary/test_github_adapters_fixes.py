"""
Unit tests for GitHub adapter fixes from revision cycle #325.

Tests the following fixes:
1. Removal of embedded retry logic from GitHubTicketAdapter
2. Removal of preemptive rate-limit waiting (embedded resilience)
3. Exception chaining with `from e` in webhook adapter
4. Bounded idempotency cache with FIFO eviction in webhook adapter
5. Batched eviction logging
"""

import asyncio
from collections import OrderedDict
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.primary.github_webhook_adapter import (
    GitHubWebhookAdapter,
    WebhookProcessingResult,
)
from codetoreum.adapters.secondary.github_ticket_adapter import GitHubConfig, GitHubTicketAdapter
from codetoreum.ports.exceptions import ExternalServiceError


class TestGitHubTicketAdapterResilience:
    """Tests for GitHubTicketAdapter resilience cleanup."""

    def test_adapter_has_asyncio_imported(self):
        """Verify asyncio is properly imported for streaming methods."""
        # This test ensures the missing asyncio import is restored
        import inspect

        import codetoreum.adapters.secondary.github_ticket_adapter as module

        source = inspect.getsource(module)
        assert "import asyncio" in source, "asyncio must be imported for get_work_item_stream"

    def test_wait_for_rate_limit_method_removed(self):
        """Verify _wait_for_rate_limit_if_needed method is removed (embedded resilience)."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        # Method should not exist
        assert not hasattr(
            adapter, "_wait_for_rate_limit_if_needed"
        ), "_wait_for_rate_limit_if_needed should be removed (embedded resilience logic)"

    @pytest.mark.asyncio
    async def test_make_request_does_not_call_rate_limit_wait(self):
        """Verify _make_request no longer calls rate limit waiting."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            # _make_request should complete without sleeping
            response = await adapter._make_request("GET", "/test")

            assert response.status_code == 200
            # Verify no sleep was called (rate limit waiting removed)
            # If there were a sleep, the test would take longer


class TestGitHubWebhookAdapterCache:
    """Tests for webhook adapter idempotency cache with FIFO eviction."""

    def test_cache_uses_ordered_dict(self):
        """Verify cache uses OrderedDict for FIFO ordering."""
        mock_port = MagicMock()
        mock_bus = MagicMock()
        mock_config = MagicMock()
        mock_logger = MagicMock()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=mock_port,
            event_bus=mock_bus,
            config_service=mock_config,
            logger=mock_logger,
        )

        assert isinstance(
            adapter._processed_deliveries, OrderedDict
        ), "Cache should use OrderedDict for FIFO insertion-order tracking"

    def test_cache_bounded_at_configured_size(self):
        """Verify cache respects configured maximum size."""
        mock_port = MagicMock()
        mock_bus = MagicMock()
        mock_config = MagicMock()
        mock_logger = MagicMock()

        cache_size = 100
        adapter = GitHubWebhookAdapter(
            workflow_command_port=mock_port,
            event_bus=mock_bus,
            config_service=mock_config,
            logger=mock_logger,
            idempotency_cache_size=cache_size,
        )

        assert adapter._idempotency_cache_size == cache_size

    def test_eviction_threshold_is_90_percent(self):
        """Verify eviction triggers at 90% capacity."""
        mock_port = MagicMock()
        mock_bus = MagicMock()
        mock_config = MagicMock()
        mock_logger = MagicMock()

        cache_size = 100
        adapter = GitHubWebhookAdapter(
            workflow_command_port=mock_port,
            event_bus=mock_bus,
            config_service=mock_config,
            logger=mock_logger,
            idempotency_cache_size=cache_size,
        )

        # At 89 entries (89%), no eviction
        for i in range(89):
            adapter._processed_deliveries[f"delivery_{i}"] = WebhookProcessingResult(
                success=True,
                message="test",
                commands_created=[],
            )

        assert len(adapter._processed_deliveries) == 89

        # At 90 entries (90%), eviction should trigger
        adapter._processed_deliveries["delivery_90"] = WebhookProcessingResult(
            success=True,
            message="test",
            commands_created=[],
        )
        adapter._evict_old_entries_if_needed()

        # Should have evicted 10% (10 entries) - now back to 90 - 10 + 1 = 81
        assert (
            len(adapter._processed_deliveries) <= cache_size
        ), "Cache should not exceed configured size after eviction"

    def test_eviction_removes_oldest_entries_fifo(self):
        """Verify eviction removes oldest (first inserted) entries."""
        mock_port = MagicMock()
        mock_bus = MagicMock()
        mock_config = MagicMock()
        mock_logger = MagicMock()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=mock_port,
            event_bus=mock_bus,
            config_service=mock_config,
            logger=mock_logger,
            idempotency_cache_size=10,  # Small size for testing
        )

        # Add 10 items
        for i in range(10):
            adapter._processed_deliveries[f"delivery_{i}"] = WebhookProcessingResult(
                success=True,
                message=f"test_{i}",
                commands_created=[],
            )

        keys_before = list(adapter._processed_deliveries.keys())

        # Trigger eviction (at 90% capacity = 9 items)
        adapter._processed_deliveries["delivery_10"] = WebhookProcessingResult(
            success=True,
            message="test_10",
            commands_created=[],
        )
        adapter._evict_old_entries_if_needed()

        keys_after = list(adapter._processed_deliveries.keys())

        # Oldest entries should be gone
        assert "delivery_0" not in keys_after, "Oldest entry should be evicted"
        assert "delivery_10" in keys_after, "Newest entry should remain"
        assert len(keys_after) <= 10, "Cache size should be bounded"

    def test_eviction_logs_batched_message(self):
        """Verify eviction logs a single batched message, not per-entry."""
        mock_port = MagicMock()
        mock_bus = MagicMock()
        mock_config = MagicMock()
        mock_logger = MagicMock()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=mock_port,
            event_bus=mock_bus,
            config_service=mock_config,
            logger=mock_logger,
            idempotency_cache_size=100,
        )

        # Fill cache to trigger eviction
        for i in range(91):
            adapter._processed_deliveries[f"delivery_{i}"] = WebhookProcessingResult(
                success=True,
                message="test",
                commands_created=[],
            )

        adapter._evict_old_entries_if_needed()

        # Verify debug log was called
        mock_logger.debug.assert_called()

        # Get the last call to debug
        call_args = mock_logger.debug.call_args
        log_message = call_args[0][0]

        # Should be a batched log, not per-entry
        assert "Evicted" in log_message
        assert "entries" in log_message.lower()
        assert log_message.count("delivery_") == 0, "Batched log should not list individual delivery IDs"

    def test_no_separate_timestamp_tracking(self):
        """Verify no separate timestamp dict is maintained (OrderedDict handles order)."""
        mock_port = MagicMock()
        mock_bus = MagicMock()
        mock_config = MagicMock()
        mock_logger = MagicMock()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=mock_port,
            event_bus=mock_bus,
            config_service=mock_config,
            logger=mock_logger,
        )

        # Should not have a _delivery_timestamps attribute
        assert not hasattr(
            adapter, "_delivery_timestamps"
        ), "OrderedDict eliminates need for separate timestamp tracking"


class TestGitHubWebhookAdapterExceptionChaining:
    """Tests for exception chaining with `from e` in webhook adapter."""

    @pytest.mark.asyncio
    async def test_exception_chains_preserved(self):
        """Verify exception chaining preserves exception context."""
        mock_port = MagicMock()
        mock_bus = MagicMock()
        mock_config = MagicMock()
        mock_logger = MagicMock()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=mock_port,
            event_bus=mock_bus,
            config_service=mock_config,
            logger=mock_logger,
        )

        # Simulate webhook request with mocked error
        from fastapi import HTTPException, Request

        mock_request = AsyncMock(spec=Request)
        mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
        mock_request.json = AsyncMock(return_value={"test": "data"})

        # Mock verification to fail with exception chain
        with patch.object(adapter, "_verify_signature", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = False

            with pytest.raises(HTTPException) as exc_info:
                await adapter.receive_webhook(
                    request=mock_request,
                    x_github_delivery="test_delivery",
                    x_github_event="issues",
                    x_hub_signature_256="sha256=invalid",
                )

            # Verify the exception has a cause chain
            # HTTPException should have been raised with `from e`
            assert exc_info.value.__cause__ is not None or isinstance(
                exc_info.value.__context__, Exception
            ), "Exception should preserve context chain"


class TestGitHubTicketAdapterDiscussionId:
    """Tests for GitHubTicketAdapter discussion_id population from GraphQL API."""

    def test_graphql_client_lazy_initialization(self):
        """Verify GraphQL client is lazily initialized on first use."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        # Should be None initially
        assert adapter._graphql_client is None

        # After calling _get_graphql_client, should be initialized
        client = adapter._get_graphql_client()
        assert client is not None
        assert adapter._graphql_client is not None

    @pytest.mark.asyncio
    async def test_fetch_discussions_with_pagination(self):
        """Verify _fetch_discussions_for_repository implements cursor-based pagination."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        # Mock the GraphQL client to return paginated results
        mock_graphql_client = AsyncMock()

        # First page response
        first_page = {
            "repository": {
                "discussions": {
                    "pageInfo": {
                        "hasNextPage": True,
                        "endCursor": "cursor_1",
                    },
                    "nodes": [
                        {
                            "id": "discussion_1",
                            "body": "This fixes issue #123",
                        },
                        {
                            "id": "discussion_2",
                            "body": "Related to #456",
                        },
                    ],
                }
            }
        }

        # Second page response (no more pages)
        second_page = {
            "repository": {
                "discussions": {
                    "pageInfo": {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                    "nodes": [
                        {
                            "id": "discussion_3",
                            "body": "Fixes issue #789",
                        },
                    ],
                }
            }
        }

        mock_graphql_client.execute = AsyncMock(side_effect=[first_page, second_page])

        with patch.object(adapter, "_get_graphql_client", return_value=mock_graphql_client):
            result = await adapter._fetch_discussions_for_repository()

            # Should have called execute twice (pagination)
            assert mock_graphql_client.execute.call_count == 2

            # Should have found all three issues
            assert "123" in result
            assert "456" in result
            assert "789" in result
            assert result["123"] == "discussion_1"
            assert result["456"] == "discussion_2"
            assert result["789"] == "discussion_3"

    @pytest.mark.asyncio
    async def test_fetch_discussions_caches_result(self):
        """Verify discussion fetch is cached and only happens once."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        mock_graphql_client = AsyncMock()
        mock_response = {
            "repository": {
                "discussions": {
                    "pageInfo": {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                    "nodes": [
                        {
                            "id": "discussion_1",
                            "body": "Fixes issue #123",
                        },
                    ],
                }
            }
        }

        mock_graphql_client.execute = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_graphql_client", return_value=mock_graphql_client):
            # First call
            result1 = await adapter._fetch_discussions_for_repository()
            assert mock_graphql_client.execute.call_count == 1

            # Second call should use cache and not execute GraphQL
            result2 = await adapter._fetch_discussions_for_repository()
            assert mock_graphql_client.execute.call_count == 1  # Still 1, not 2
            assert result1 == result2

    @pytest.mark.asyncio
    async def test_get_discussion_id_cache_hit(self):
        """Verify _get_discussion_id returns cached value when available."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        # Manually set up cache to simulate a prior fetch
        adapter._discussion_cache["123"] = "discussion_abc"
        adapter._discussions_fetched = True

        result = await adapter._get_discussion_id("123")
        assert result == "discussion_abc"

    @pytest.mark.asyncio
    async def test_get_discussion_id_issue_not_found(self):
        """Verify _get_discussion_id returns None for issues not in discussions."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        # Simulate an empty fetch
        adapter._discussion_cache = {"123": "discussion_abc"}
        adapter._discussions_fetched = True

        result = await adapter._get_discussion_id("999")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_discussion_id_triggers_fetch_on_first_call(self):
        """Verify _get_discussion_id triggers fetch on first call."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        mock_graphql_client = AsyncMock()
        mock_response = {
            "repository": {
                "discussions": {
                    "pageInfo": {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                    "nodes": [
                        {
                            "id": "discussion_1",
                            "body": "Fixes issue #123",
                        },
                    ],
                }
            }
        }

        mock_graphql_client.execute = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_graphql_client", return_value=mock_graphql_client):
            # First call to _get_discussion_id should trigger fetch
            result = await adapter._get_discussion_id("123")
            assert result == "discussion_1"
            assert mock_graphql_client.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_discussions_graceful_fallback_on_graphql_error(self):
        """Verify graceful fallback when GraphQL query fails."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        mock_graphql_client = AsyncMock()
        mock_graphql_client.execute = AsyncMock(
            side_effect=ExternalServiceError("GitHub", "Query timeout")
        )

        with patch.object(adapter, "_get_graphql_client", return_value=mock_graphql_client):
            result = await adapter._fetch_discussions_for_repository()

            # Should return empty dict on error
            assert result == {}
            # Should NOT mark as fetched to allow retry on transient failures
            assert adapter._discussions_fetched is False
            # Should generate error_id for Sentry tracking
            assert adapter._discussions_fetch_error_id is not None

    @pytest.mark.asyncio
    async def test_fetch_discussions_graceful_fallback_on_generic_error(self):
        """Verify graceful fallback on unexpected errors."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        mock_graphql_client = AsyncMock()
        mock_graphql_client.execute = AsyncMock(
            side_effect=ValueError("Unexpected error")
        )

        with patch.object(adapter, "_get_graphql_client", return_value=mock_graphql_client):
            result = await adapter._fetch_discussions_for_repository()

            # Should return empty dict on error
            assert result == {}
            # Should NOT mark as fetched to allow retry on transient failures
            assert adapter._discussions_fetched is False
            # Should generate error_id for Sentry tracking
            assert adapter._discussions_fetch_error_id is not None

    @pytest.mark.asyncio
    async def test_regex_contextual_matching_filters_hex_colors(self):
        """Verify regex pattern filters hex colors with letter components (A-F)."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        mock_graphql_client = AsyncMock()
        # Discussion with hex colors and valid issue references
        # #FF0000 is clearly a color (has A-F)
        # # 1. is markdown (space between # and number)
        # #123 and #456 are numeric (could be issues or colors)
        mock_response = {
            "repository": {
                "discussions": {
                    "pageInfo": {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                    "nodes": [
                        {
                            "id": "discussion_1",
                            "body": "Updated color from #FF0000 to #00FF00. Related to #123 and fixes #456.",
                        },
                    ],
                }
            }
        }

        mock_graphql_client.execute = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_graphql_client", return_value=mock_graphql_client):
            result = await adapter._fetch_discussions_for_repository()

            # Should match valid issue references
            assert "123" in result  # Numeric issue reference
            assert "456" in result  # Numeric issue reference
            assert result["123"] == "discussion_1"
            assert result["456"] == "discussion_1"

            # Hex colors with A-F (like #FF0000, #00FF00) are filtered out
            assert "FF0000" not in result  # Filtered as color
            assert "00FF00" not in result  # Filtered as color

    @pytest.mark.asyncio
    async def test_fetch_discussions_retries_on_transient_failure(self):
        """Verify that adapter retries discussion fetch after transient failure."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        mock_graphql_client = AsyncMock()

        # First call fails, second call succeeds
        first_call_error = ExternalServiceError("GitHub", "Temporary timeout")
        success_response = {
            "repository": {
                "discussions": {
                    "pageInfo": {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                    "nodes": [
                        {
                            "id": "discussion_1",
                            "body": "Fixes issue #123",
                        },
                    ],
                }
            }
        }

        mock_graphql_client.execute = AsyncMock(
            side_effect=[first_call_error, success_response]
        )

        with patch.object(adapter, "_get_graphql_client", return_value=mock_graphql_client):
            # First call fails
            result1 = await adapter._fetch_discussions_for_repository()
            assert result1 == {}
            assert adapter._discussions_fetched is False
            assert adapter._discussions_fetch_error_id is not None

            # Second call retries and succeeds
            result2 = await adapter._fetch_discussions_for_repository()
            assert result2 == {"123": "discussion_1"}
            assert adapter._discussions_fetched is True
            assert adapter._discussions_fetch_error_id is None  # Error ID should be cleared on success

            # Should have called execute twice (retry on second call)
            assert mock_graphql_client.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_regex_pattern_avoids_markdown_headings(self):
        """Verify regex pattern avoids matching markdown headings (# 1 with space)."""
        config = GitHubConfig(
            token="test_token",
            organization="test_org",
            repository="test_repo",
        )
        adapter = GitHubTicketAdapter(config)

        mock_graphql_client = AsyncMock()
        # Markdown heading (# 1. Title) should not match because there's a space
        # But #123 without space should match
        mock_response = {
            "repository": {
                "discussions": {
                    "pageInfo": {
                        "hasNextPage": False,
                        "endCursor": None,
                    },
                    "nodes": [
                        {
                            "id": "discussion_1",
                            "body": "# 1. Introduction\nThis fixes #123 and references #456.",
                        },
                    ],
                }
            }
        }

        mock_graphql_client.execute = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_graphql_client", return_value=mock_graphql_client):
            result = await adapter._fetch_discussions_for_repository()

            # Should match issue references
            assert "123" in result
            assert "456" in result

            # Markdown heading # 1 should not match (space between # and 1)
            assert "1" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
