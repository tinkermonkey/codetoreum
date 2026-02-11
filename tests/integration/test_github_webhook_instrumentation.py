"""Integration tests for GitHub webhook adapter instrumentation.

Verifies that GitHubWebhookAdapter webhook processing methods emit
OpenTelemetry spans with proper GitHub-specific metadata.
"""

import pytest
from datetime import datetime
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from unittest.mock import AsyncMock, MagicMock

from codetoreum.adapters.primary.github_webhook_adapter import (
    GitHubWebhookAdapter,
    WebhookEvent,
)


@pytest.fixture
def tracer_provider():
    """Provide a test tracer with in-memory span exporter."""
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    yield provider
    provider.force_flush()


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for GitHubWebhookAdapter."""
    return {
        "workflow_port": AsyncMock(),
        "event_bus": MagicMock(),
        "config": AsyncMock(),
        "logger": MagicMock(),
    }


@pytest.fixture
def webhook_adapter(mock_dependencies):
    """Create a GitHubWebhookAdapter instance with mocks."""
    return GitHubWebhookAdapter(
        workflow_command_port=mock_dependencies["workflow_port"],
        event_bus=mock_dependencies["event_bus"],
        config_service=mock_dependencies["config"],
        logger=mock_dependencies["logger"],
    )


# ============================================================================
# Webhook Processing Tests
# ============================================================================


@pytest.mark.asyncio
async def test_github_webhook_process_event_project_card(
    tracer_provider, webhook_adapter, mock_dependencies
):
    """Verify GitHubWebhookAdapter._process_event captures webhook metadata."""
    # Setup mocks
    mock_dependencies["config"].list_projects = AsyncMock(
        return_value=["test-project"]
    )
    mock_dependencies["config"].get_project_config = AsyncMock(
        return_value=MagicMock(github=MagicMock(org="org", repo="repo"))
    )
    mock_dependencies["workflow_port"].start_workflow = AsyncMock(
        return_value=MagicMock(workflow_run_id="run-001")
    )

    # Create webhook event
    event = WebhookEvent(
        delivery_id="delivery-123",
        event_type="project_card",
        payload={
            "action": "moved",
            "repository": {"full_name": "org/repo"},
            "project_card": {
                "id": 1,
                "content_url": "https://api.github.com/repos/org/repo/issues/123",
                "column_id": 456,
            },
            "changes": {"column_id": {"from": 789}},
        },
        signature="sha256=test",
        timestamp=datetime.utcnow(),
        repository="org/repo",
    )

    # Execute
    result = await webhook_adapter._process_event(event)

    # Assert span was created with correct attributes
    spans = tracer_provider.get_finished_spans()
    process_span = next(
        (s for s in spans if s.name == "github.webhook.process_event"),
        None,
    )

    assert process_span is not None
    assert process_span.attributes["service"] == "github_webhook"
    assert process_span.attributes["github.event_type"] == "project_card"
    assert process_span.attributes["github.delivery_id"] == "delivery-123"
    assert process_span.attributes["github.repository"] == "org/repo"


@pytest.mark.asyncio
async def test_github_webhook_handle_project_card_event(
    tracer_provider, webhook_adapter, mock_dependencies
):
    """Verify GitHubWebhookAdapter._handle_project_card_event captures context."""
    # Setup mocks
    mock_dependencies["config"].load_github_state = AsyncMock(
        return_value={
            "boards": {
                "main": {"columns": {"backlog": 789, "in-progress": 456}}
            }
        }
    )
    mock_dependencies["config"].get_project_config = AsyncMock(
        return_value=MagicMock(
            pipelines=[
                MagicMock(
                    name="main-pipeline",
                    board_name="main",
                    workflow="main-workflow",
                )
            ]
        )
    )
    mock_dependencies["config"].get_workflow_template = AsyncMock(
        return_value=MagicMock(
            columns=[
                MagicMock(
                    name="in-progress",
                    agent="dev-agent",
                )
            ]
        )
    )
    mock_dependencies["workflow_port"].start_workflow = AsyncMock(
        return_value=MagicMock(workflow_run_id="run-002")
    )

    # Create webhook event
    event = WebhookEvent(
        delivery_id="delivery-456",
        event_type="project_card",
        payload={
            "action": "moved",
            "repository": {"full_name": "org/repo"},
            "project_card": {
                "id": 1,
                "content_url": "https://api.github.com/repos/org/repo/issues/123",
                "column_id": 456,
            },
            "changes": {"column_id": {"from": 789}},
        },
        signature="sha256=test",
        timestamp=datetime.utcnow(),
        repository="org/repo",
    )

    # Execute
    result = await webhook_adapter._handle_project_card_event(
        event, "test-project"
    )

    # Assert span was created with GitHub context
    spans = tracer_provider.get_finished_spans()
    card_span = next(
        (s for s in spans if s.name == "github.webhook.handle_project_card"),
        None,
    )

    assert card_span is not None
    assert card_span.attributes["service"] == "github_webhook"
    assert card_span.attributes["event_type"] == "project_card"
    assert card_span.attributes["github.project"] == "test-project"
    assert card_span.attributes["github.action"] == "moved"


@pytest.mark.asyncio
async def test_github_webhook_handle_issue_comment_event(
    tracer_provider, webhook_adapter
):
    """Verify GitHubWebhookAdapter._handle_issue_comment_event captures comment context."""
    # Create webhook event
    event = WebhookEvent(
        delivery_id="delivery-789",
        event_type="issue_comment",
        payload={
            "action": "created",
            "repository": {"full_name": "org/repo"},
            "issue": {"number": 42, "id": 999},
            "comment": {"id": 555, "body": "LGTM"},
        },
        signature="sha256=test",
        timestamp=datetime.utcnow(),
        repository="org/repo",
    )

    # Execute
    result = await webhook_adapter._handle_issue_comment_event(event, "test-project")

    # Assert span was created with comment context
    spans = tracer_provider.get_finished_spans()
    comment_span = next(
        (s for s in spans if s.name == "github.webhook.handle_issue_comment"),
        None,
    )

    assert comment_span is not None
    assert comment_span.attributes["service"] == "github_webhook"
    assert comment_span.attributes["event_type"] == "issue_comment"
    assert comment_span.attributes["github.project"] == "test-project"
    assert comment_span.attributes["github.action"] == "created"
    assert comment_span.attributes["github.issue_number"] == 42
    assert comment_span.attributes["github.comment_id"] == 555


@pytest.mark.asyncio
async def test_github_webhook_handle_pull_request_event(
    tracer_provider, webhook_adapter
):
    """Verify GitHubWebhookAdapter._handle_pull_request_event captures PR context."""
    # Create webhook event
    event = WebhookEvent(
        delivery_id="delivery-pr-001",
        event_type="pull_request",
        payload={
            "action": "opened",
            "repository": {"full_name": "org/repo"},
            "number": 99,
            "pull_request": {"id": 777},
        },
        signature="sha256=test",
        timestamp=datetime.utcnow(),
        repository="org/repo",
    )

    # Execute
    result = await webhook_adapter._handle_pull_request_event(event, "test-project")

    # Assert span was created with PR context
    spans = tracer_provider.get_finished_spans()
    pr_span = next(
        (s for s in spans if s.name == "github.webhook.handle_pull_request"),
        None,
    )

    assert pr_span is not None
    assert pr_span.attributes["service"] == "github_webhook"
    assert pr_span.attributes["event_type"] == "pull_request"
    assert pr_span.attributes["github.project"] == "test-project"
    assert pr_span.attributes["github.action"] == "opened"
    assert pr_span.attributes["github.pr_number"] == 99


@pytest.mark.asyncio
async def test_github_webhook_handle_issues_event(tracer_provider, webhook_adapter):
    """Verify GitHubWebhookAdapter._handle_issues_event captures issue context."""
    # Create webhook event
    event = WebhookEvent(
        delivery_id="delivery-issue-001",
        event_type="issues",
        payload={
            "action": "opened",
            "repository": {"full_name": "org/repo"},
            "issue": {"id": 123, "number": 1},
        },
        signature="sha256=test",
        timestamp=datetime.utcnow(),
        repository="org/repo",
    )

    # Execute
    result = await webhook_adapter._handle_issues_event(event, "test-project")

    # Assert span was created with issue context
    spans = tracer_provider.get_finished_spans()
    issue_span = next(
        (s for s in spans if s.name == "github.webhook.handle_issues"),
        None,
    )

    assert issue_span is not None
    assert issue_span.attributes["service"] == "github_webhook"
    assert issue_span.attributes["event_type"] == "issues"
    assert issue_span.attributes["github.project"] == "test-project"
    assert issue_span.attributes["github.action"] == "opened"


@pytest.mark.asyncio
async def test_github_webhook_handle_discussion_event(
    tracer_provider, webhook_adapter
):
    """Verify GitHubWebhookAdapter._handle_discussion_event captures context."""
    # Create webhook event
    event = WebhookEvent(
        delivery_id="delivery-disc-001",
        event_type="discussion",
        payload={
            "action": "created",
            "repository": {"full_name": "org/repo"},
            "discussion": {"id": 888},
        },
        signature="sha256=test",
        timestamp=datetime.utcnow(),
        repository="org/repo",
    )

    # Execute
    result = await webhook_adapter._handle_discussion_event(event, "test-project")

    # Assert span was created with discussion context
    spans = tracer_provider.get_finished_spans()
    disc_span = next(
        (s for s in spans if s.name == "github.webhook.handle_discussion"),
        None,
    )

    assert disc_span is not None
    assert disc_span.attributes["service"] == "github_webhook"
    assert disc_span.attributes["event_type"] == "discussion"
    assert disc_span.attributes["github.project"] == "test-project"
    assert disc_span.attributes["github.action"] == "created"


# ============================================================================
# Comprehensive Context Tests
# ============================================================================


@pytest.mark.asyncio
async def test_github_webhook_complete_trace_chain(
    tracer_provider, webhook_adapter, mock_dependencies
):
    """Verify webhook spans include complete business context for tracing."""
    # Setup mocks
    mock_dependencies["config"].list_projects = AsyncMock(
        return_value=["test-project"]
    )
    mock_dependencies["config"].get_project_config = AsyncMock(
        return_value=MagicMock(github=MagicMock(org="acme", repo="platform"))
    )
    mock_dependencies["config"].load_github_state = AsyncMock(
        return_value={
            "boards": {"main": {"columns": {"ready": 123}}}
        }
    )
    mock_dependencies["config"].get_workflow_template = AsyncMock(
        return_value=MagicMock(
            columns=[MagicMock(name="ready", agent="scheduler")]
        )
    )
    mock_dependencies["workflow_port"].start_workflow = AsyncMock(
        return_value=MagicMock(workflow_run_id="run-comprehensive")
    )

    # Create webhook event with full metadata
    event = WebhookEvent(
        delivery_id="delivery-comprehensive",
        event_type="project_card",
        payload={
            "action": "moved",
            "repository": {"full_name": "acme/platform"},
            "project_card": {
                "id": 1,
                "content_url": "https://api.github.com/repos/acme/platform/issues/555",
                "column_id": 123,
            },
            "changes": {"column_id": {"from": 456}},
        },
        signature="sha256=comprehensive",
        timestamp=datetime.utcnow(),
        repository="acme/platform",
    )

    # Execute
    result = await webhook_adapter._process_event(event)

    # Assert all expected spans with complete context
    spans = tracer_provider.get_finished_spans()
    process_span = next(
        (s for s in spans if s.name == "github.webhook.process_event"),
        None,
    )

    # Verify core attributes present
    expected_attributes = [
        "service",
        "github.event_type",
        "github.delivery_id",
        "github.repository",
    ]

    for attr in expected_attributes:
        assert (
            attr in process_span.attributes
        ), f"Missing attribute: {attr}"

    # Verify values
    assert process_span.attributes["github.event_type"] == "project_card"
    assert (
        process_span.attributes["github.delivery_id"]
        == "delivery-comprehensive"
    )
    assert process_span.attributes["github.repository"] == "acme/platform"


@pytest.mark.asyncio
async def test_github_webhook_missing_optional_fields(
    tracer_provider, webhook_adapter
):
    """Verify webhook instrumentation handles missing optional payload fields gracefully."""
    # Create webhook event with minimal payload
    event = WebhookEvent(
        delivery_id="delivery-minimal",
        event_type="issue_comment",
        payload={
            "action": "created",
            "repository": {"full_name": "org/repo"},
            "issue": {"number": 10},
            "comment": {"id": 20},
        },
        signature="sha256=test",
        timestamp=datetime.utcnow(),
        repository="org/repo",
    )

    # Execute - should not raise exception even with minimal fields
    result = await webhook_adapter._handle_issue_comment_event(
        event, "test-project"
    )

    # Assert span was still created with available context
    spans = tracer_provider.get_finished_spans()
    comment_span = next(
        (s for s in spans if s.name == "github.webhook.handle_issue_comment"),
        None,
    )

    assert comment_span is not None
    # Core attributes should be present
    assert comment_span.attributes["service"] == "github_webhook"
    assert comment_span.attributes["github.issue_number"] == 10
    assert comment_span.attributes["github.comment_id"] == 20
