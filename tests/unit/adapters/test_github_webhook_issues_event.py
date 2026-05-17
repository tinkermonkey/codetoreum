"""Tests for GitHub webhook adapter issues event handling

Tests that the webhook adapter properly delegates issue intake to the input port.
"""

from datetime import UTC, datetime

import pytest

from codetoreum.adapters.primary.github_webhook_adapter import (
    GitHubWebhookAdapter,
    WebhookEvent,
)
from codetoreum.ports.input.issue_intake import IssueIntakeResult


class MockWorkflowCommandPort:
    """Mock workflow command port."""

    async def start_workflow(self, command):
        return type("Result", (), {"workflow_run_id": "run-1"})()


class MockEventBus:
    """Mock event bus."""

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


class MockLogger:
    """Mock logger."""

    def warning(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass


class MockIssueIntakePort:
    """Mock issue intake port."""

    def __init__(self):
        self.commands_received = []

    async def on_issue_opened(self, command):
        self.commands_received.append(command)
        return IssueIntakeResult(
            success=True,
            work_item_id=command.issue_number,
            message=f"Issue {command.issue_number} placed on board",
        )


@pytest.mark.asyncio
async def test_handle_issues_event_opened_calls_issue_intake_port():
    """Test that opened issues event delegates to issue intake port."""
    workflow_port = MockWorkflowCommandPort()
    event_bus = MockEventBus()
    config_service = MockConfigService()
    logger = MockLogger()
    issue_intake_port = MockIssueIntakePort()

    adapter = GitHubWebhookAdapter(
        workflow_command_port=workflow_port,
        event_bus=event_bus,
        config_service=config_service,
        logger=logger,
        issue_intake_port=issue_intake_port,
    )

    event = WebhookEvent(
        delivery_id="delivery-1",
        event_type="issues",
        payload={
            "action": "opened",
            "issue": {
                "number": 42,
                "title": "Test Issue",
                "html_url": "https://github.com/test-org/test-repo/issues/42",
            },
        },
        signature="sha256=test",
        timestamp=datetime.now(UTC),
        repository="test-org/test-repo",
    )

    result = await adapter._handle_issues_event(event, "proj-1")

    assert result == ["42"]
    assert len(issue_intake_port.commands_received) == 1
    command = issue_intake_port.commands_received[0]
    assert command.project_id == "proj-1"
    assert command.issue_number == "42"
    assert command.issue_title == "Test Issue"
    assert command.issue_url == "https://github.com/test-org/test-repo/issues/42"


@pytest.mark.asyncio
async def test_handle_issues_event_opened_without_issue_intake_port():
    """Test that opened issues event returns empty list if issue intake port not available."""
    workflow_port = MockWorkflowCommandPort()
    event_bus = MockEventBus()
    config_service = MockConfigService()
    logger = MockLogger()

    adapter = GitHubWebhookAdapter(
        workflow_command_port=workflow_port,
        event_bus=event_bus,
        config_service=config_service,
        logger=logger,
        issue_intake_port=None,  # No issue intake port
    )

    event = WebhookEvent(
        delivery_id="delivery-1",
        event_type="issues",
        payload={
            "action": "opened",
            "issue": {
                "number": 42,
                "title": "Test Issue",
            },
        },
        signature="sha256=test",
        timestamp=datetime.now(UTC),
        repository="test-org/test-repo",
    )

    result = await adapter._handle_issues_event(event, "proj-1")

    assert result == []


@pytest.mark.asyncio
async def test_handle_issues_event_closed_action_ignored():
    """Test that issues event with 'closed' action is ignored."""
    workflow_port = MockWorkflowCommandPort()
    event_bus = MockEventBus()
    config_service = MockConfigService()
    logger = MockLogger()
    issue_intake_port = MockIssueIntakePort()

    adapter = GitHubWebhookAdapter(
        workflow_command_port=workflow_port,
        event_bus=event_bus,
        config_service=config_service,
        logger=logger,
        issue_intake_port=issue_intake_port,
    )

    event = WebhookEvent(
        delivery_id="delivery-1",
        event_type="issues",
        payload={
            "action": "closed",  # Different action
            "issue": {
                "number": 42,
            },
        },
        signature="sha256=test",
        timestamp=datetime.now(UTC),
        repository="test-org/test-repo",
    )

    result = await adapter._handle_issues_event(event, "proj-1")

    assert result == []
    assert len(issue_intake_port.commands_received) == 0


@pytest.mark.asyncio
async def test_handle_issues_event_intake_failure():
    """Test that failed issue intake returns empty list."""

    class FailingIssueIntakePort:
        async def on_issue_opened(self, command):
            return IssueIntakeResult(
                success=False,
                work_item_id=command.issue_number,
                message="Failed to place issue on board",
                errors=["Board service unavailable"],
            )

    workflow_port = MockWorkflowCommandPort()
    event_bus = MockEventBus()
    config_service = MockConfigService()
    logger = MockLogger()
    issue_intake_port = FailingIssueIntakePort()

    adapter = GitHubWebhookAdapter(
        workflow_command_port=workflow_port,
        event_bus=event_bus,
        config_service=config_service,
        logger=logger,
        issue_intake_port=issue_intake_port,
    )

    event = WebhookEvent(
        delivery_id="delivery-1",
        event_type="issues",
        payload={
            "action": "opened",
            "issue": {
                "number": 42,
            },
        },
        signature="sha256=test",
        timestamp=datetime.now(UTC),
        repository="test-org/test-repo",
    )

    result = await adapter._handle_issues_event(event, "proj-1")

    assert result == []
