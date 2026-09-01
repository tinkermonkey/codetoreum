"""Integration tests for GitHub discussion adapter.

Tests webhook handling, polling, event emission, and GitHub API integration.
Uses mock HTTP responses for deterministic testing without external services.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codetoreum.adapters.secondary.github_discussion_adapter import (
    GitHubDiscussionAdapter,
    GitHubDiscussionConfig,
)
from codetoreum.adapters.secondary.github_ticket_adapter import GitHubTicketAdapter
from codetoreum.domain.events.discussion_events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    CommentPostedEvent,
)
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.discussion_adapter import DiscussionMonitoringConfig
from tests.conftest import wait_for_polling_cycle

from .conftest import MockIdentityService


class TestGitHubDiscussionAdapterWebhook:
    """Tests for webhook handling functionality."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with mock identity service."""
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="test-repo",
            webhook_enabled=True,
        )
        identity = MockIdentityService()
        return GitHubDiscussionAdapter(config, identity)

    @pytest.fixture
    def monitoring_config(self):
        """Create monitoring configuration."""
        return DiscussionMonitoringConfig(
            project_id="proj-1",
        )

    @pytest.mark.asyncio
    async def test_webhook_created_action_emits_event(self, adapter, monitoring_config):
        """Webhook for comment.created emits comment.needs_response for human comments."""
        # Setup
        adapter.start_monitoring("123", monitoring_config)
        events: list[CommentNeedsResponseEvent] = []
        adapter.on("comment.needs_response", events.append)

        # Payload for human comment
        payload = {
            "action": "created",
            "issue": {"number": 123},
            "comment": {
                "id": 456,
                "user": {"login": "alice"},
                "body": "This needs review",
                "created_at": "2025-01-08T10:00:00Z",
            },
        }

        # Act
        await adapter.handle_webhook(payload)

        # Assert
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, CommentNeedsResponseEvent)
        comment = event.comment
        assert comment is not None
        assert comment.body == "This needs review"
        assert comment.author == "alice"
        assert comment.is_bot is False
        assert event.work_item_id == "123"
        assert event.project_id == "proj-1"

    @pytest.mark.asyncio
    async def test_webhook_skips_bot_comments(self, adapter, monitoring_config):
        """Webhook for bot comments does not emit events."""
        # Setup
        adapter.start_monitoring("123", monitoring_config)
        events: list[CommentNeedsResponseEvent] = []
        adapter.on("comment.needs_response", events.append)

        # Payload for bot comment
        payload = {
            "action": "created",
            "issue": {"number": 123},
            "comment": {
                "id": 456,
                "user": {"login": "dependabot"},
                "body": "Dependencies updated",
                "created_at": "2025-01-08T10:00:00Z",
            },
        }

        # Act
        await adapter.handle_webhook(payload)

        # Assert
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_webhook_ignores_unmonitored_issues(self, adapter):
        """Webhook for unmonitored issues is ignored."""
        events: list[CommentNeedsResponseEvent] = []
        adapter.on("comment.needs_response", events.append)

        payload = {
            "action": "created",
            "issue": {"number": 999},  # Not monitored
            "comment": {
                "id": 456,
                "user": {"login": "alice"},
                "body": "Comment on unmonitored issue",
                "created_at": "2025-01-08T10:00:00Z",
            },
        }

        await adapter.handle_webhook(payload)

        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_webhook_ignores_deleted_action(self, adapter, monitoring_config):
        """Webhook for deleted/modified comments is ignored."""
        adapter.start_monitoring("123", monitoring_config)
        events: list[CommentNeedsResponseEvent] = []
        adapter.on("comment.needs_response", events.append)

        payload = {
            "action": "deleted",
            "issue": {"number": 123},
            "comment": {
                "id": 456,
                "user": {"login": "alice"},
                "body": "Deleted comment",
                "created_at": "2025-01-08T10:00:00Z",
            },
        }

        await adapter.handle_webhook(payload)

        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_webhook_invalid_payload_raises_error(self, adapter, monitoring_config):
        """Webhook with invalid payload raises ValidationError."""
        adapter.start_monitoring("123", monitoring_config)

        payload = {
            "action": "created",
            # Missing issue and comment
        }

        with pytest.raises(ValidationError):
            await adapter.handle_webhook(payload)

    @pytest.mark.asyncio
    async def test_webhook_tracks_last_processed_comment(self, adapter, monitoring_config):
        """Webhook updates last_processed_comment_id."""
        adapter.start_monitoring("123", monitoring_config)

        payload = {
            "action": "created",
            "issue": {"number": 123},
            "comment": {
                "id": 456,
                "user": {"login": "alice"},
                "body": "First comment",
                "created_at": "2025-01-08T10:00:00Z",
            },
        }

        await adapter.handle_webhook(payload)

        # Verify last_processed is updated
        assert adapter._last_processed["123"] == "456"


class TestGitHubDiscussionAdapterPolling:
    """Tests for polling-based detection."""

    @pytest.fixture
    def polling_adapter(self):
        """Create adapter with polling enabled."""
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="test-repo",
            webhook_enabled=False,  # Enable polling
            polling_interval_seconds=1,  # Short interval for testing
        )
        identity = MockIdentityService()
        return GitHubDiscussionAdapter(config, identity)

    @pytest.fixture
    def monitoring_config(self):
        return DiscussionMonitoringConfig(
            project_id="proj-1",
        )

    @pytest.mark.asyncio
    async def test_polling_detects_new_comments(self, polling_adapter, monitoring_config):
        """Polling detects new human comments and emits events."""
        polling_adapter.start_monitoring("123", monitoring_config)

        # Mock the get_thread method to return comments
        from codetoreum.ports.output.discussion_adapter import DiscussionThread

        call_count = [0]
        comments_to_return = [
            [
                Comment("1", "alice", "First comment", "2025-01-08T10:00:00Z"),
                Comment("2", "bob", "Second comment", "2025-01-08T10:01:00Z"),
            ],
            [
                Comment("1", "alice", "First comment", "2025-01-08T10:00:00Z"),
                Comment("2", "bob", "Second comment", "2025-01-08T10:01:00Z"),
                Comment("3", "charlie", "Third comment", "2025-01-08T10:02:00Z"),
            ],
        ]

        async def mock_get_thread(work_item_id: str) -> DiscussionThread:
            result = DiscussionThread(
                id=f"thread-{work_item_id}",
                work_item_id=work_item_id,
                comments=comments_to_return[min(call_count[0], 1)],
                thread_type="flat",
            )
            call_count[0] += 1
            return result

        with patch.object(polling_adapter, "get_thread", new=mock_get_thread):
            # Subscribe to events
            events: list[CommentNeedsResponseEvent] = []
            polling_adapter.on("comment.needs_response", events.append)

            # Wait for 3 events total: alice, bob (first cycle) + charlie (second cycle)
            # The first polling cycle will return alice and bob (2 events)
            # The second polling cycle will return charlie (1 new event)
            await wait_for_polling_cycle(events, expected_count=3, timeout=10.0)

            # Should have detected all comments including charlie's
            assert len(events) >= 3
            assert all(e.comment is not None for e in events)
            assert any(e.comment and e.comment.author == "charlie" for e in events)

        polling_adapter.stop_monitoring("123")

    @pytest.mark.asyncio
    async def test_polling_respects_interval(self, polling_adapter, monitoring_config):
        """Polling respects configured interval."""
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="test-repo",
            webhook_enabled=False,
            polling_interval_seconds=2,
        )
        identity = MockIdentityService()
        adapter = GitHubDiscussionAdapter(config, identity)

        adapter.start_monitoring("123", monitoring_config)

        call_times = []
        start_time = datetime.now(UTC)

        async def mock_get_thread(work_item_id: str):
            from codetoreum.ports.output.discussion_adapter import DiscussionThread

            call_times.append(datetime.now(UTC))
            return DiscussionThread(
                id=f"thread-{work_item_id}",
                work_item_id=work_item_id,
                comments=[],
                thread_type="flat",
            )

        with patch.object(adapter, "get_thread", new=mock_get_thread):
            # Wait for at least 2 polling calls
            await wait_for_polling_cycle(call_times, expected_count=2, timeout=15.0)

            adapter.stop_monitoring("123")

            # Should have at least 2 calls with roughly 2-second intervals
            if len(call_times) >= 2:
                interval = (call_times[1] - call_times[0]).total_seconds()
                assert 1.5 < interval < 3.0  # Allow some variance


class TestGitHubDiscussionAdapterQueries:
    """Tests for query operations via REST API."""

    @pytest.fixture
    def adapter(self):
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="test-repo",
        )
        identity = MockIdentityService()
        return GitHubDiscussionAdapter(config, identity)

    @pytest.mark.asyncio
    async def test_get_thread_returns_all_comments(self, adapter):
        """get_thread retrieves all comments from GitHub API."""
        # Mock httpx client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 1,
                "user": {"login": "alice"},
                "body": "First comment",
                "created_at": "2025-01-08T10:00:00Z",
            },
            {
                "id": 2,
                "user": {"login": "dependabot"},
                "body": "Dependencies updated",
                "created_at": "2025-01-08T10:01:00Z",
            },
        ]

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            # Act
            thread = await adapter.get_thread("123")

            # Assert
            assert thread.work_item_id == "123"
            assert len(thread.comments) == 2
            assert thread.comments[0].author == "alice"
            assert thread.comments[1].author == "dependabot"
            assert thread.comments[1].is_bot is True

    @pytest.mark.asyncio
    async def test_get_thread_invalid_work_item_raises_error(self, adapter):
        """get_thread raises ValidationError for invalid work_item_id."""
        with pytest.raises(ValidationError):
            await adapter.get_thread("not-a-number")

    @pytest.mark.asyncio
    async def test_get_thread_issue_not_found_raises_error(self, adapter):
        """get_thread raises ResourceNotFoundError for non-existent issues."""
        mock_response = Mock(status_code=404)

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            with pytest.raises(ResourceNotFoundError):
                await adapter.get_thread("999")

    @pytest.mark.asyncio
    async def test_get_thread_authentication_error(self, adapter):
        """get_thread raises AuthenticationError for auth failures."""
        mock_response = Mock(status_code=401)

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            with pytest.raises(AuthenticationError):
                await adapter.get_thread("123")


class TestGitHubDiscussionAdapterCommands:
    """Tests for command operations via REST API."""

    @pytest.fixture
    def adapter(self):
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="test-repo",
        )
        identity = MockIdentityService()
        return GitHubDiscussionAdapter(config, identity)

    @pytest.fixture
    def monitoring_config(self):
        return DiscussionMonitoringConfig(
            project_id="proj-1",
        )

    @pytest.mark.asyncio
    async def test_add_comment_posts_and_emits_event(self, adapter, monitoring_config):
        """add_comment posts to GitHub and emits comment.posted event."""
        adapter.start_monitoring("123", monitoring_config)

        mock_response = Mock(
            status_code=201,
            json=Mock(
                return_value={
                    "id": 789,
                    "user": {"login": "codetoreum-bot"},
                    "body": "This looks good!",
                    "created_at": "2025-01-08T10:00:00Z",
                }
            ),
        )

        events: list[CommentPostedEvent] = []
        adapter.on("comment.posted", events.append)

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            comment = await adapter.add_comment("123", "This looks good!")

            assert comment.body == "This looks good!"
            assert comment.author == "codetoreum-bot"
            assert len(events) == 1
            event_comment = events[0].comment
            assert event_comment is not None
            assert event_comment.body == "This looks good!"

    @pytest.mark.asyncio
    async def test_add_comment_validation(self, adapter):
        """add_comment validates input."""
        with pytest.raises(ValidationError):
            await adapter.add_comment("invalid", "content")

        with pytest.raises(ValidationError):
            await adapter.add_comment("123", "")

        # Test content length validation
        with pytest.raises(ValidationError):
            await adapter.add_comment("123", "x" * 70000)

    @pytest.mark.asyncio
    async def test_add_comment_issue_not_found(self, adapter):
        """add_comment raises ResourceNotFoundError for non-existent issues."""
        mock_response = Mock(status_code=404)

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            with pytest.raises(ResourceNotFoundError):
                await adapter.add_comment("999", "test")


class TestGitHubDiscussionAdapterMonitoring:
    """Tests for monitoring lifecycle."""

    @pytest.fixture
    def adapter(self):
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="test-repo",
            webhook_enabled=False,
        )
        identity = MockIdentityService()
        return GitHubDiscussionAdapter(config, identity)

    @pytest.fixture
    def monitoring_config(self):
        return DiscussionMonitoringConfig(
            project_id="proj-1",
        )

    @pytest.mark.asyncio
    async def test_start_monitoring_initializes_state(self, adapter, monitoring_config):
        """start_monitoring initializes monitoring state."""
        adapter.start_monitoring("123", monitoring_config)

        assert "123" in adapter._monitoring
        assert adapter._monitoring["123"] == monitoring_config
        assert "123" in adapter._last_processed

    @pytest.mark.asyncio
    async def test_start_monitoring_starts_polling(self, adapter, monitoring_config):
        """start_monitoring starts polling task when webhook disabled."""
        adapter.start_monitoring("123", monitoring_config)

        assert "123" in adapter._polling_tasks
        assert not adapter._polling_tasks["123"].done()

        # Cleanup
        adapter.stop_monitoring("123")

    @pytest.mark.asyncio
    async def test_stop_monitoring_cleans_up_state(self, adapter, monitoring_config):
        """stop_monitoring cleans up all state."""
        adapter.start_monitoring("123", monitoring_config)
        adapter.stop_monitoring("123")

        assert "123" not in adapter._monitoring
        assert "123" not in adapter._polling_tasks

    def test_stop_monitoring_not_monitoring_raises_error(self, adapter):
        """stop_monitoring raises error if not currently monitoring."""
        with pytest.raises(ResourceNotFoundError):
            adapter.stop_monitoring("999")

    def test_start_monitoring_validation(self, adapter, monitoring_config):
        """start_monitoring validates parameters."""
        # Test that empty work_item_id raises ValidationError
        with pytest.raises(ValidationError):
            adapter.start_monitoring("", monitoring_config)

        # Test that invalid project_id in config raises ValueError (from dataclass constructor)
        with pytest.raises(ValueError):
            DiscussionMonitoringConfig(
                project_id="",
            )


class TestGitHubDiscussionAdapterEventEmission:
    """Tests for event emitter functionality."""

    @pytest.fixture
    def adapter(self):
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="test-repo",
        )
        identity = MockIdentityService()
        return GitHubDiscussionAdapter(config, identity)

    def test_on_subscribes_to_events(self, adapter):
        """on() subscribes to event types."""
        handler = Mock()
        adapter.on("comment.needs_response", handler)

        assert "comment.needs_response" in adapter._event_handlers

    def test_off_unsubscribes_from_events(self, adapter):
        """off() unsubscribes from events."""
        handler = Mock()
        adapter.on("comment.needs_response", handler)
        adapter.off("comment.needs_response", handler)

        assert len(adapter._event_handlers.get("comment.needs_response", [])) == 0

    def test_emit_calls_all_handlers(self, adapter):
        """emit() calls all registered handlers."""
        handler1 = Mock()
        handler2 = Mock()
        adapter.on("comment.needs_response", handler1)
        adapter.on("comment.needs_response", handler2)

        event = CommentNeedsResponseEvent(
            type="comment.needs_response",
            timestamp="2025-01-08T10:00:00Z",
            source="github",
            work_item_id="123",
            project_id="proj-1",
            comment=Comment("1", "alice", "test", "2025-01-08T10:00:00Z"),
            context=CommentContext(),
        )

        adapter.emit(event)

        handler1.assert_called_once_with(event)
        handler2.assert_called_once_with(event)

    def test_on_validation(self, adapter):
        """on() validates parameters."""
        with pytest.raises(ValueError):
            adapter.on("", Mock())

        with pytest.raises(ValueError):
            adapter.on("test", "not callable")

    def test_emit_validation(self, adapter):
        """emit() validates event type."""
        with pytest.raises(ValueError):
            adapter.emit({"invalid": "object"})


class TestGitHubDiscussionAdapterDiscussionNodeId:
    """Tests for D_... Discussion node ID routing in add_comment and get_thread."""

    @pytest.fixture
    def graphql_client(self):
        return AsyncMock()

    @pytest.fixture
    def adapter(self, graphql_client):
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="test-repo",
            graphql_client=graphql_client,
        )
        identity = MockIdentityService()
        return GitHubDiscussionAdapter(config, identity)

    @pytest.fixture
    def adapter_no_graphql(self):
        """Adapter without a GraphQL client configured."""
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="test-repo",
        )
        identity = MockIdentityService()
        return GitHubDiscussionAdapter(config, identity)

    @pytest.fixture
    def monitoring_config(self):
        return DiscussionMonitoringConfig(project_id="proj-1")

    # -------------------------------------------------------------------------
    # add_comment — D_ routing
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_add_comment_discussion_id_calls_graphql(self, adapter, graphql_client):
        """add_comment with D_... ID uses the addDiscussionComment GraphQL mutation."""
        graphql_client.execute.return_value = {
            "addDiscussionComment": {
                "comment": {
                    "id": "DC_abc123",
                    "body": "Great point!",
                    "author": {"login": "alice"},
                    "createdAt": "2025-01-08T10:00:00Z",
                }
            }
        }

        comment = await adapter.add_comment("D_kwDOABC123", "Great point!")

        graphql_client.execute.assert_called_once()
        call_args = graphql_client.execute.call_args
        variables = call_args[0][1]
        assert variables["discussionId"] == "D_kwDOABC123"
        assert variables["body"] == "Great point!"
        assert comment.id == "DC_abc123"
        assert comment.body == "Great point!"
        assert comment.author == "alice"
        assert comment.created_at == "2025-01-08T10:00:00Z"

    @pytest.mark.asyncio
    async def test_add_comment_discussion_emits_posted_event_when_monitoring(
        self, adapter, graphql_client, monitoring_config
    ):
        """add_comment on a monitored Discussion emits comment.posted."""
        adapter.start_monitoring("D_kwDOABC123", monitoring_config)
        graphql_client.execute.return_value = {
            "addDiscussionComment": {
                "comment": {
                    "id": "DC_new",
                    "body": "Hello",
                    "author": {"login": "bot"},
                    "createdAt": "2025-01-08T10:00:00Z",
                }
            }
        }

        events: list[CommentPostedEvent] = []
        adapter.on("comment.posted", events.append)

        await adapter.add_comment("D_kwDOABC123", "Hello")

        assert len(events) == 1
        assert events[0].work_item_id == "D_kwDOABC123"
        assert events[0].comment.id == "DC_new"

    @pytest.mark.asyncio
    async def test_add_comment_discussion_no_graphql_client_raises(self, adapter_no_graphql):
        """add_comment with D_... ID raises ExternalServiceError when no GraphQL client."""
        from codetoreum.ports.exceptions import ExternalServiceError

        with pytest.raises(ExternalServiceError, match="GraphQL client required"):
            await adapter_no_graphql.add_comment("D_kwDOABC123", "test")

    @pytest.mark.asyncio
    async def test_add_comment_discussion_not_found_raises_resource_not_found(self, adapter, graphql_client):
        """add_comment raises ResourceNotFoundError when GraphQL says the discussion is not found."""
        from codetoreum.ports.exceptions import ExternalServiceError

        graphql_client.execute.side_effect = ExternalServiceError(
            service="GitHub", message="GraphQL errors: Could not resolve to a node with the global id of 'D_invalid'"
        )

        with pytest.raises(ResourceNotFoundError):
            await adapter.add_comment("D_invalid", "test")

    @pytest.mark.asyncio
    async def test_add_comment_invalid_id_clear_error_message(self, adapter):
        """add_comment with an unrecognised ID format includes guidance in the error."""
        with pytest.raises(ValidationError, match="D_\\.\\.\\."):
            await adapter.add_comment("d_lowercase", "content")

    # -------------------------------------------------------------------------
    # get_thread — D_ routing
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_thread_discussion_id_fetches_via_graphql(self, adapter, graphql_client):
        """get_thread with D_... ID uses the GetDiscussionComments GraphQL query."""
        graphql_client.execute.return_value = {
            "node": {
                "comments": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {
                            "id": "DC_1",
                            "body": "First comment",
                            "author": {"login": "alice"},
                            "createdAt": "2025-01-08T10:00:00Z",
                        },
                        {
                            "id": "DC_2",
                            "body": "Second comment",
                            "author": {"login": "bob"},
                            "createdAt": "2025-01-08T10:01:00Z",
                        },
                    ],
                }
            }
        }

        thread = await adapter.get_thread("D_kwDOABC123")

        assert thread.work_item_id == "D_kwDOABC123"
        assert len(thread.comments) == 2
        assert thread.comments[0].id == "DC_1"
        assert thread.comments[0].author == "alice"
        assert thread.comments[1].id == "DC_2"

    @pytest.mark.asyncio
    async def test_get_thread_discussion_paginates(self, adapter, graphql_client):
        """get_thread follows hasNextPage to retrieve all Discussion comments."""
        page1 = {
            "node": {
                "comments": {
                    "pageInfo": {"hasNextPage": True, "endCursor": "cursor_abc"},
                    "nodes": [
                        {"id": "DC_1", "body": "p1", "author": {"login": "a"}, "createdAt": "2025-01-08T10:00:00Z"}
                    ],
                }
            }
        }
        page2 = {
            "node": {
                "comments": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {"id": "DC_2", "body": "p2", "author": {"login": "b"}, "createdAt": "2025-01-08T10:01:00Z"}
                    ],
                }
            }
        }
        graphql_client.execute.side_effect = [page1, page2]

        thread = await adapter.get_thread("D_kwDOABC123")

        assert len(thread.comments) == 2
        assert graphql_client.execute.call_count == 2
        # Second call should pass the cursor
        second_call_vars = graphql_client.execute.call_args_list[1][0][1]
        assert second_call_vars["after"] == "cursor_abc"

    @pytest.mark.asyncio
    async def test_get_thread_discussion_not_found_raises_resource_not_found(self, adapter, graphql_client):
        """get_thread raises ResourceNotFoundError when node is None (discussion not found)."""
        graphql_client.execute.return_value = {"node": None}

        with pytest.raises(ResourceNotFoundError):
            await adapter.get_thread("D_invalid")

    @pytest.mark.asyncio
    async def test_get_thread_discussion_no_graphql_client_raises(self, adapter_no_graphql):
        """get_thread with D_... ID raises ExternalServiceError when no GraphQL client."""
        from codetoreum.ports.exceptions import ExternalServiceError

        with pytest.raises(ExternalServiceError, match="GraphQL client required"):
            await adapter_no_graphql.get_thread("D_kwDOABC123")

    @pytest.mark.asyncio
    async def test_get_thread_invalid_id_clear_error_message(self, adapter):
        """get_thread with an unrecognised ID format includes guidance in the error."""
        with pytest.raises(ValidationError, match="D_\\.\\.\\."):
            await adapter.get_thread("not-a-valid-id")


class TestGitHubDiscussionAdapterMultiProject:
    """Tests for multi-project repo resolution via ticket_adapter."""

    @pytest.fixture
    def monitoring_config(self):
        """Create monitoring configuration."""
        return DiscussionMonitoringConfig(
            project_id="proj-multi-1",
        )

    @pytest.mark.asyncio
    async def test_resolve_repository_with_ticket_adapter(self, monitoring_config):
        """Repository resolution uses ticket_adapter._get_repo when supplied."""
        # Setup
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="",  # No default repository
        )

        # Mock ticket adapter that resolves repos per project
        mock_ticket_adapter = Mock(spec=GitHubTicketAdapter)
        mock_ticket_adapter._get_repo = Mock(return_value="resolved-repo")

        identity = MockIdentityService()
        adapter = GitHubDiscussionAdapter(config, identity, ticket_adapter=mock_ticket_adapter)

        # Start monitoring with a project ID
        adapter.start_monitoring("123", monitoring_config)

        # Act - resolve repository for the work item
        repo = adapter._resolve_repository("123")

        # Assert
        assert repo == "resolved-repo"
        mock_ticket_adapter._get_repo.assert_called_once_with("proj-multi-1")

    @pytest.mark.asyncio
    async def test_resolve_repository_fallback_to_config(self, monitoring_config):
        """Repository resolution falls back to config.repository when ticket_adapter not supplied."""
        # Setup
        from codetoreum.adapters.secondary.github_discussion_adapter import (
            GitHubDiscussionAdapter,
            GitHubDiscussionConfig,
        )

        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="fallback-repo",  # Fallback repository
        )

        identity = MockIdentityService()
        adapter = GitHubDiscussionAdapter(config, identity, ticket_adapter=None)

        # Start monitoring
        adapter.start_monitoring("456", monitoring_config)

        # Act
        repo = adapter._resolve_repository("456")

        # Assert
        assert repo == "fallback-repo"

    @pytest.mark.asyncio
    async def test_resolve_repository_fallback_when_project_not_registered(self, monitoring_config):
        """Repository resolution falls back to config when project_id not registered in ticket_adapter."""
        # Setup
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="fallback-repo",
        )

        # Mock ticket adapter that raises ConfigurationError for unknown project
        mock_ticket_adapter = Mock(spec=GitHubTicketAdapter)
        mock_ticket_adapter._get_repo = Mock(side_effect=ConfigurationError("Project not found"))

        identity = MockIdentityService()
        adapter = GitHubDiscussionAdapter(config, identity, ticket_adapter=mock_ticket_adapter)

        # Start monitoring
        adapter.start_monitoring("789", monitoring_config)

        # Act
        repo = adapter._resolve_repository("789")

        # Assert - falls back to config.repository
        assert repo == "fallback-repo"

    @pytest.mark.asyncio
    async def test_resolve_repository_raises_when_no_repo_available(self, monitoring_config):
        """Repository resolution raises ConfigurationError when no repo is available."""
        # Setup
        from codetoreum.adapters.secondary.github_discussion_adapter import (
            GitHubDiscussionAdapter,
            GitHubDiscussionConfig,
        )

        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="",  # No default repository
        )

        identity = MockIdentityService()
        adapter = GitHubDiscussionAdapter(config, identity, ticket_adapter=None)

        # Start monitoring
        adapter.start_monitoring("999", monitoring_config)

        # Act & Assert
        from codetoreum.ports.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="Unable to determine GitHub repository"):
            adapter._resolve_repository("999")

    @pytest.mark.asyncio
    async def test_get_thread_uses_resolved_repository(self, monitoring_config):
        """get_thread uses the resolved repository when fetching comments."""
        # Setup
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="",
        )

        mock_ticket_adapter = Mock(spec=GitHubTicketAdapter)
        mock_ticket_adapter._get_repo = Mock(return_value="resolved-repo")

        identity = MockIdentityService()
        adapter = GitHubDiscussionAdapter(config, identity, ticket_adapter=mock_ticket_adapter)

        # Start monitoring
        adapter.start_monitoring("123", monitoring_config)

        # Mock the HTTP client to capture the URL being called
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=[
            {
                "id": 1,
                "user": {"login": "alice"},
                "body": "Test comment",
                "created_at": "2025-01-08T10:00:00Z",
            }
        ])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            # Act
            thread = await adapter.get_thread("123")

            # Assert
            assert len(thread.comments) == 1
            # Verify that the API call was made with the resolved repository
            call_args = mock_client.get.call_args
            assert "resolved-repo" in call_args[0][0]
            assert "test-org" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_comment_uses_resolved_repository(self, monitoring_config):
        """add_comment uses the resolved repository when posting comments."""
        # Setup
        config = GitHubDiscussionConfig(
            token="test-token",
            organization="test-org",
            repository="",
        )

        mock_ticket_adapter = Mock(spec=GitHubTicketAdapter)
        mock_ticket_adapter._get_repo = Mock(return_value="resolved-repo")

        identity = MockIdentityService()
        adapter = GitHubDiscussionAdapter(config, identity, ticket_adapter=mock_ticket_adapter)

        # Start monitoring
        adapter.start_monitoring("456", monitoring_config)

        # Mock the HTTP client to capture the URL being called
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json = Mock(return_value={
            "id": 999,
            "user": {"login": "bot"},
            "body": "Response comment",
            "created_at": "2025-01-08T11:00:00Z",
        })

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(adapter, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            # Act
            comment = await adapter.add_comment("456", "Response comment")

            # Assert
            assert comment.body == "Response comment"
            # Verify that the API call was made with the resolved repository
            call_args = mock_client.post.call_args
            assert "resolved-repo" in call_args[0][0]
            assert "test-org" in call_args[0][0]
