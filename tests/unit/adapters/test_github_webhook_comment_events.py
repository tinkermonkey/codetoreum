"""Tests for GitHub webhook adapter comment and review event handling

Tests that the webhook adapter properly emits CommentNeedsResponseEvent
and ReviewStatusChangedEvent for issue comments, PR events, and discussions.
"""

from datetime import UTC, datetime

import pytest

from codetoreum.adapters.primary.github_webhook_adapter import (
    GitHubWebhookAdapter,
    WebhookEvent,
)


class MockEventBus:
    """Mock event bus that captures published events."""

    def __init__(self):
        self.published_events = []

    async def publish(self, event):
        self.published_events.append(event)

    def subscribe(self, event_type, handler):
        pass


class MockConfigService:
    """Mock config service."""

    async def get_project_config(self, project_id):
        return type("Config", (), {"metadata": {"webhook_secret": "secret"}})()

    async def list_projects(self):
        return [
            type(
                "Project",
                (),
                {
                    "id": "proj-1",
                    "github_org": "test-org",
                    "github_repo": "test-repo",
                },
            )()
        ]


class MockWorkflowCommandPort:
    """Mock workflow command port."""

    async def start_workflow(self, command):
        return type("Result", (), {"workflow_run_id": "run-1"})()


class MockLogger:
    """Mock logger."""

    def __init__(self):
        self.warnings = []
        self.infos = []
        self.errors = []

    def warning(self, *args, **kwargs):
        self.warnings.append(args)

    def info(self, *args, **kwargs):
        self.infos.append(args)

    def error(self, *args, **kwargs):
        self.errors.append(args)

    def debug(self, *args, **kwargs):
        pass


class TestIssueCommentEventHandling:
    """Tests for issue_comment webhook event handling."""

    @pytest.fixture
    def adapter(self):
        """Create a GitHubWebhookAdapter with mock dependencies."""
        workflow_port = MockWorkflowCommandPort()
        event_bus = MockEventBus()
        config_service = MockConfigService()
        logger = MockLogger()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=workflow_port,
            event_bus=event_bus,
            config_service=config_service,
            logger=logger,
        )
        return adapter

    @pytest.mark.asyncio
    async def test_issue_comment_created_emits_event(self, adapter):
        """Test that created issue comment emits CommentNeedsResponseEvent."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="issue_comment",
            payload={
                "action": "created",
                "issue": {
                    "number": 42,
                    "title": "Test Issue",
                    "state": "open",
                },
                "comment": {
                    "id": 123456,
                    "user": {"login": "test-user", "type": "User"},
                    "body": "This looks good to me!",
                    "created_at": "2025-01-14T10:30:00Z",
                },
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_issue_comment_event(event, "proj-1")

        assert len(result) == 1
        assert len(adapter.event_bus.published_events) == 1

        published_event = adapter.event_bus.published_events[0]
        assert published_event.type == "comment.needs_response"
        assert published_event.work_item_id == "42"
        assert published_event.project_id == "proj-1"
        assert published_event.comment is not None
        assert published_event.comment.author == "test-user"
        assert published_event.comment.body == "This looks good to me!"
        assert published_event.comment.is_bot is False

    @pytest.mark.asyncio
    async def test_issue_comment_edited_action_ignored(self, adapter):
        """Test that edited issue comment is ignored."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="issue_comment",
            payload={
                "action": "edited",
                "issue": {
                    "number": 42,
                },
                "comment": {
                    "id": 123456,
                    "user": {"login": "test-user"},
                    "body": "Modified comment",
                    "created_at": "2025-01-14T10:30:00Z",
                },
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_issue_comment_event(event, "proj-1")

        assert result == []
        assert len(adapter.event_bus.published_events) == 0

    @pytest.mark.asyncio
    async def test_issue_comment_bot_is_marked(self, adapter):
        """Test that bot comments are marked correctly."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="issue_comment",
            payload={
                "action": "created",
                "issue": {
                    "number": 42,
                },
                "comment": {
                    "id": 123456,
                    "user": {"login": "my-bot[bot]", "type": "Bot"},
                    "body": "Automated check passed",
                    "created_at": "2025-01-14T10:30:00Z",
                },
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_issue_comment_event(event, "proj-1")

        assert len(result) == 1
        published_event = adapter.event_bus.published_events[0]
        assert published_event.comment.is_bot is True


class TestPullRequestEventHandling:
    """Tests for pull_request webhook event handling."""

    @pytest.fixture
    def adapter(self):
        """Create a GitHubWebhookAdapter with mock dependencies."""
        workflow_port = MockWorkflowCommandPort()
        event_bus = MockEventBus()
        config_service = MockConfigService()
        logger = MockLogger()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=workflow_port,
            event_bus=event_bus,
            config_service=config_service,
            logger=logger,
        )
        return adapter

    @pytest.mark.asyncio
    async def test_pull_request_opened_emits_event(self, adapter):
        """Test that opened PR emits ReviewStatusChangedEvent."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="pull_request",
            payload={
                "action": "opened",
                "number": 42,
                "pull_request": {
                    "number": 42,
                    "state": "open",
                    "merged": False,
                    "title": "Add feature X",
                    "user": {"login": "developer-1"},
                },
                "sender": {"login": "developer-1"},
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_pull_request_event(event, "proj-1")

        assert len(result) == 1
        assert len(adapter.event_bus.published_events) == 1

        published_event = adapter.event_bus.published_events[0]
        assert published_event.type == "review.status_changed"
        assert published_event.review_id == "42"
        assert published_event.project_id == "proj-1"
        assert published_event.new_status == "open"
        assert published_event.previous_status == "open"
        assert published_event.reviewer is None

    @pytest.mark.asyncio
    async def test_pull_request_closed_emits_event(self, adapter):
        """Test that closed PR emits ReviewStatusChangedEvent."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="pull_request",
            payload={
                "action": "closed",
                "number": 42,
                "pull_request": {
                    "number": 42,
                    "state": "closed",
                    "merged": False,
                    "title": "Add feature X",
                    "user": {"login": "developer-1"},
                },
                "sender": {"login": "reviewer-user"},
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_pull_request_event(event, "proj-1")

        assert len(result) == 1
        published_event = adapter.event_bus.published_events[0]
        assert published_event.new_status == "closed"
        assert published_event.previous_status == "open"
        assert published_event.reviewer == "reviewer-user"

    @pytest.mark.asyncio
    async def test_pull_request_merged_emits_event(self, adapter):
        """Test that merged PR emits ReviewStatusChangedEvent with merged status."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="pull_request",
            payload={
                "action": "closed",
                "number": 42,
                "pull_request": {
                    "number": 42,
                    "state": "closed",
                    "merged": True,
                    "title": "Add feature X",
                    "user": {"login": "developer-1"},
                },
                "sender": {"login": "merger-user"},
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_pull_request_event(event, "proj-1")

        assert len(result) == 1
        published_event = adapter.event_bus.published_events[0]
        assert published_event.new_status == "merged"
        assert published_event.previous_status == "open"
        assert published_event.reviewer == "merger-user"

    @pytest.mark.asyncio
    async def test_pull_request_reopened_emits_event(self, adapter):
        """Test that reopened PR emits ReviewStatusChangedEvent with correct previous_status."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="pull_request",
            payload={
                "action": "reopened",
                "number": 42,
                "pull_request": {
                    "number": 42,
                    "state": "open",
                    "merged": False,
                    "title": "Add feature X",
                    "user": {"login": "developer-1"},
                },
                "sender": {"login": "reopener-user"},
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_pull_request_event(event, "proj-1")

        assert len(result) == 1
        published_event = adapter.event_bus.published_events[0]
        assert published_event.new_status == "open"
        assert published_event.previous_status == "closed"
        assert published_event.reviewer == "reopener-user"

    @pytest.mark.asyncio
    async def test_pull_request_synchronize_action_ignored(self, adapter):
        """Test that synchronize action (new commits) is ignored."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="pull_request",
            payload={
                "action": "synchronize",
                "number": 42,
                "pull_request": {
                    "number": 42,
                    "state": "open",
                    "merged": False,
                },
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_pull_request_event(event, "proj-1")

        assert result == []
        assert len(adapter.event_bus.published_events) == 0


class TestDiscussionEventHandling:
    """Tests for discussion webhook event handling."""

    @pytest.fixture
    def adapter(self):
        """Create a GitHubWebhookAdapter with mock dependencies."""
        workflow_port = MockWorkflowCommandPort()
        event_bus = MockEventBus()
        config_service = MockConfigService()
        logger = MockLogger()

        adapter = GitHubWebhookAdapter(
            workflow_command_port=workflow_port,
            event_bus=event_bus,
            config_service=config_service,
            logger=logger,
        )
        return adapter

    @pytest.mark.asyncio
    async def test_discussion_comment_created_emits_event(self, adapter):
        """Test that created discussion comment emits CommentNeedsResponseEvent."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="discussion_comment",
            payload={
                "action": "created",
                "discussion": {
                    "number": 10,
                    "title": "Discussion about feature",
                    "state": "open",
                },
                "comment": {
                    "id": 789012,
                    "user": {"login": "community-member", "type": "User"},
                    "body": "What's the timeline for this?",
                    "created_at": "2025-01-14T11:00:00Z",
                },
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_discussion_event(event, "proj-1")

        assert len(result) == 1
        assert len(adapter.event_bus.published_events) == 1

        published_event = adapter.event_bus.published_events[0]
        assert published_event.type == "comment.needs_response"
        assert published_event.work_item_id == "10"
        assert published_event.project_id == "proj-1"
        assert published_event.comment is not None
        assert published_event.comment.author == "community-member"
        assert published_event.comment.body == "What's the timeline for this?"

    @pytest.mark.asyncio
    async def test_discussion_created_without_comment_ignored(self, adapter):
        """Test that discussion creation (without comment) is ignored."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="discussion_comment",
            payload={
                "action": "created",
                "discussion": {
                    "number": 10,
                    "title": "New Discussion",
                    "state": "open",
                },
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_discussion_event(event, "proj-1")

        assert result == []
        assert len(adapter.event_bus.published_events) == 0

    @pytest.mark.asyncio
    async def test_discussion_labeled_action_ignored(self, adapter):
        """Test that labeled action is ignored."""
        event = WebhookEvent(
            delivery_id="delivery-1",
            event_type="discussion_comment",
            payload={
                "action": "labeled",
                "discussion": {
                    "number": 10,
                },
                "repository": {
                    "full_name": "test-org/test-repo",
                },
            },
            signature="sha256=test",
            timestamp=datetime.now(UTC),
            repository="test-org/test-repo",
        )

        result = await adapter._handle_discussion_event(event, "proj-1")

        assert result == []
        assert len(adapter.event_bus.published_events) == 0
