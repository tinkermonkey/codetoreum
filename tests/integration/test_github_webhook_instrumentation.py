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
from unittest.mock import AsyncMock, MagicMock, patch

from codetoreum.adapters.primary.github_webhook_adapter import (
    GitHubWebhookAdapter,
    WebhookEvent,
)


@pytest.fixture
def tracer_provider():
    """Provide a test tracer with in-memory span exporter.

    Yields the InMemorySpanExporter which has get_finished_spans() method.
    Uses monkeypatch to avoid OpenTelemetry's provider override protection.
    """
    # Create a new tracer provider for each test
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)

    # Monkeypatch trace module to return our provider
    with patch('opentelemetry.trace.get_tracer_provider', return_value=provider):
        yield exporter

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
        return_value=MagicMock(
            github=MagicMock(org="org", repo="repo"),
            pipelines=[
                MagicMock(
                    name="main-pipeline",
                    board_name="main",
                    workflow="main-workflow",
                )
            ]
        )
    )
    mock_dependencies["config"].load_github_state = AsyncMock(
        return_value={
            "boards": {
                "main": {"columns": {"in-progress": 456}}
            }
        }
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
        return_value=MagicMock(
            github=MagicMock(org="acme", repo="platform"),
            pipelines=[
                MagicMock(
                    name="main-pipeline",
                    board_name="main",
                    workflow="main-workflow",
                )
            ]
        )
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


