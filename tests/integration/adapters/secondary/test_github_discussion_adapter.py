"""Integration tests for GitHub discussion adapter.

Tests webhook handling, polling, event emission, and GitHub API integration.
Uses mock HTTP responses for deterministic testing without external services.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codetoreum.adapters.secondary.github_discussion_adapter import (
    GitHubDiscussionAdapter,
    GitHubDiscussionConfig,
)
from codetoreum.domain.events.discussion_events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    CommentPostedEvent,
)
from codetoreum.ports.output.discussion_adapter import DiscussionMonitoringConfig
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)


class MockIdentityService:
    """Mock identity service for testing."""

    def __init__(self, bot_usernames: Optional[List[str]] = None):
        self.bot_usernames = bot_usernames or ["dependabot", "renovate", "codetoreum-bot"]
        self.configured_bot = "codetoreum-bot"

    def is_bot_user(self, username: str) -> bool:
        return username in self.bot_usernames

    def get_bot_username(self) -> str:
        return self.configured_bot

    def get_human_users(self, usernames: List[str]) -> List[str]:
        return [u for u in usernames if not self.is_bot_user(u)]

    def configure(self, config):
        pass


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
            column_name="Review",
            agent_assignment="agent-1",
        )

    async def test_webhook_created_action_emits_event(self, adapter, monitoring_config):
        """Webhook for comment.created emits comment.needs_response for human comments."""
        # Setup
        adapter.start_monitoring("123", monitoring_config)
        events = []
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
        assert event.comment.body == "This needs review"
        assert event.comment.author == "alice"
        assert event.comment.is_bot is False
        assert event.work_item_id == "123"
        assert event.project_id == "proj-1"

    async def test_webhook_skips_bot_comments(self, adapter, monitoring_config):
        """Webhook for bot comments does not emit events."""
        # Setup
        adapter.start_monitoring("123", monitoring_config)
        events = []
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

    async def test_webhook_ignores_unmonitored_issues(self, adapter):
        """Webhook for unmonitored issues is ignored."""
        events = []
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

    async def test_webhook_ignores_deleted_action(self, adapter, monitoring_config):
        """Webhook for deleted/modified comments is ignored."""
        adapter.start_monitoring("123", monitoring_config)
        events = []
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

    async def test_webhook_invalid_payload_raises_error(self, adapter, monitoring_config):
        """Webhook with invalid payload raises ValidationError."""
        adapter.start_monitoring("123", monitoring_config)

        payload = {
            "action": "created",
            # Missing issue and comment
        }

        with pytest.raises(ValidationError):
            await adapter.handle_webhook(payload)

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
            column_name="Review",
            agent_assignment="agent-1",
        )

    @pytest.mark.asyncio
    async def test_polling_detects_new_comments(self, polling_adapter, monitoring_config):
        """Polling detects new human comments and emits events."""
        polling_adapter.start_monitoring("123", monitoring_config)

        # Mock the get_thread method to return comments
        from codetoreum.ports.output.discussion_adapter import DiscussionThread

        original_get_thread = polling_adapter.get_thread

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

        polling_adapter.get_thread = mock_get_thread

        # Subscribe to events
        events = []
        polling_adapter.on("comment.needs_response", events.append)

        # Wait for first poll
        await asyncio.sleep(1.5)

        # Should have detected new comment (charlie's comment)
        assert len(events) >= 1
        assert any(e.comment.author == "charlie" for e in events)

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
        start_time = datetime.now(timezone.utc)

        async def mock_get_thread(work_item_id: str):
            from codetoreum.ports.output.discussion_adapter import DiscussionThread

            call_times.append(datetime.now(timezone.utc))
            return DiscussionThread(
                id=f"thread-{work_item_id}",
                work_item_id=work_item_id,
                comments=[],
                thread_type="flat",
            )

        adapter.get_thread = mock_get_thread

        # Wait for 5 seconds to see multiple polls
        await asyncio.sleep(5)

        adapter.stop_monitoring("123")

        # Should have at least 2 calls with roughly 2-second intervals
        if len(call_times) >= 2:
            interval = (call_times[1] - call_times[0]).total_seconds()
            assert 1.5 < interval < 3.0  # Allow some variance

    def test_polling_task_cancelled_on_stop_monitoring(self, polling_adapter, monitoring_config):
        """Polling task is cancelled when monitoring stops."""
        polling_adapter.start_monitoring("123", monitoring_config)

        # Verify task is running
        assert "123" in polling_adapter._polling_tasks
        task = polling_adapter._polling_tasks["123"]

        polling_adapter.stop_monitoring("123")

        # Verify task is cancelled
        assert "123" not in polling_adapter._polling_tasks
        assert task.cancelled() or task.done()


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
    async def test_get_thread_handles_pagination(self, adapter):
        """get_thread handles paginated responses."""
        # Mock responses for two pages
        responses = [
            Mock(
                status_code=200,
                json=Mock(
                    return_value=[
                        {
                            "id": i,
                            "user": {"login": f"user{i}"},
                            "body": f"Comment {i}",
                            "created_at": f"2025-01-08T10:{i:02d}:00Z",
                        }
                        for i in range(100)
                    ]
                ),
            ),
            Mock(
                status_code=200,
                json=Mock(
                    return_value=[
                        {
                            "id": 100,
                            "user": {"login": "user100"},
                            "body": "Comment 100",
                            "created_at": "2025-01-08T11:40:00Z",
                        }
                    ]
                ),
            ),
        ]

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.side_effect = responses
            mock_get_client.return_value = mock_client

            thread = await adapter.get_thread("123")

            # Should have fetched both pages
            assert len(thread.comments) == 101

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
            column_name="Review",
            agent_assignment="agent-1",
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

        events = []
        adapter.on("comment.posted", events.append)

        with patch.object(adapter, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            comment = await adapter.add_comment("123", "This looks good!")

            assert comment.body == "This looks good!"
            assert comment.author == "codetoreum-bot"
            assert len(events) == 1
            assert events[0].comment.body == "This looks good!"

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
            column_name="Review",
            agent_assignment="agent-1",
        )

    def test_start_monitoring_initializes_state(self, adapter, monitoring_config):
        """start_monitoring initializes monitoring state."""
        adapter.start_monitoring("123", monitoring_config)

        assert "123" in adapter._monitoring
        assert adapter._monitoring["123"] == monitoring_config
        assert "123" in adapter._last_processed

    def test_start_monitoring_starts_polling(self, adapter, monitoring_config):
        """start_monitoring starts polling task when webhook disabled."""
        adapter.start_monitoring("123", monitoring_config)

        assert "123" in adapter._polling_tasks
        assert not adapter._polling_tasks["123"].done()

    def test_stop_monitoring_cleans_up_state(self, adapter, monitoring_config):
        """stop_monitoring cleans up all state."""
        adapter.start_monitoring("123", monitoring_config)
        adapter.stop_monitoring("123")

        assert "123" not in adapter._monitoring
        assert "123" not in adapter._polling_tasks

    def test_stop_monitoring_not_monitoring_raises_error(self, adapter):
        """stop_monitoring raises error if not currently monitoring."""
        with pytest.raises(ResourceNotFoundError):
            adapter.stop_monitoring("999")

    def test_start_monitoring_validation(self, adapter):
        """start_monitoring validates parameters."""
        config = DiscussionMonitoringConfig(
            project_id="proj-1",
            column_name="Review",
            agent_assignment="agent-1",
        )

        with pytest.raises(ValidationError):
            adapter.start_monitoring("", config)

        with pytest.raises(ValidationError):
            adapter.start_monitoring("123", DiscussionMonitoringConfig(
                project_id="",
                column_name="Review",
                agent_assignment="agent-1",
            ))


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
            work_item_id="123",
            project_id="proj-1",
            comment=Comment("1", "alice", "test", "2025-01-08T10:00:00Z"),
            context=CommentContext(),
            timestamp="2025-01-08T10:00:00Z",
            source="github",
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
