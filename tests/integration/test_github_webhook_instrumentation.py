"""Integration tests for GitHub webhook adapter instrumentation.

Verifies that GitHubWebhookAdapter webhook processing methods emit
OpenTelemetry spans with proper GitHub-specific metadata.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

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
    with patch("opentelemetry.trace.get_tracer_provider", return_value=provider):
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
async def test_github_webhook_process_event_project_card(tracer_provider, webhook_adapter, mock_dependencies):
    """Verify GitHubWebhookAdapter._process_event captures webhook metadata for project_card events."""
    # Setup mocks - config must return ProjectConfig with metadata containing board column mappings
    from types import MappingProxyType

    mock_project_config = MagicMock()
    mock_project_config.metadata = MappingProxyType({"board_columns": {"456": "In Progress", "789": "Backlog"}})

    mock_dependencies["config"].list_projects = AsyncMock(return_value=["test-project"])
    mock_dependencies["config"].get_project_config = AsyncMock(return_value=mock_project_config)

    # Mock event_bus.publish to track event emission
    mock_dependencies["event_bus"].publish = AsyncMock()

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
        timestamp=datetime.now(UTC),
        repository="org/repo",
    )

    # Execute
    result = await webhook_adapter._process_event(event, "test-project")

    # Assert event was published
    mock_dependencies["event_bus"].publish.assert_called_once()
    published_event = mock_dependencies["event_bus"].publish.call_args[0][0]

    # Verify it's a WorkItemColumnChangedEvent with correct data
    assert published_event.event_type == "WorkItemColumnChangedEvent"
    assert published_event.work_item_id == "123"
    assert published_event.to_column == "In Progress"
    assert published_event.from_column == "Backlog"

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
async def test_github_webhook_complete_trace_chain(tracer_provider, webhook_adapter, mock_dependencies):
    """Verify webhook spans include complete business context for tracing."""
    # Setup mocks - config must return ProjectConfig with board column mappings
    from types import MappingProxyType

    mock_project_config = MagicMock()
    mock_project_config.metadata = MappingProxyType({"board_columns": {"123": "Ready", "456": "Todo"}})

    mock_dependencies["config"].list_projects = AsyncMock(return_value=["test-project"])
    mock_dependencies["config"].get_project_config = AsyncMock(return_value=mock_project_config)

    # Mock event_bus.publish
    mock_dependencies["event_bus"].publish = AsyncMock()

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
        timestamp=datetime.now(UTC),
        repository="acme/platform",
    )

    # Execute
    result = await webhook_adapter._process_event(event, "test-project")

    # Assert event was published
    mock_dependencies["event_bus"].publish.assert_called_once()
    published_event = mock_dependencies["event_bus"].publish.call_args[0][0]
    assert published_event.work_item_id == "555"
    assert published_event.to_column == "Ready"

    # Assert all expected spans with complete context
    spans = tracer_provider.get_finished_spans()
    process_span = next(
        (s for s in spans if s.name == "github.webhook.process_event"),
        None,
    )

    # Verify span was created
    assert process_span is not None

    # Verify core attributes present
    expected_attributes = [
        "service",
        "github.event_type",
        "github.delivery_id",
        "github.repository",
    ]

    for attr in expected_attributes:
        assert attr in process_span.attributes, f"Missing attribute: {attr}"

    # Verify values
    assert process_span.attributes["github.event_type"] == "project_card"
    assert process_span.attributes["github.delivery_id"] == "delivery-comprehensive"
    assert process_span.attributes["github.repository"] == "acme/platform"


# ============================================================================
# Column Resolution Failure Tests
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_column_id_to_name_column_not_in_mapping(webhook_adapter, mock_dependencies):
    """Verify _resolve_column_id_to_name returns None when column_id not in mapping."""
    from types import MappingProxyType

    # Setup config with board_columns that doesn't include the requested column_id
    mock_project_config = MagicMock()
    mock_project_config.metadata = MappingProxyType({"board_columns": {"456": "In Progress", "789": "Backlog"}})
    mock_dependencies["config"].get_project_config = AsyncMock(return_value=mock_project_config)

    # Execute - request a column_id that's not in the mapping
    result = await webhook_adapter._resolve_column_id_to_name("test-project", "999")

    # Assert returns None and logs warning
    assert result is None
    mock_dependencies["logger"].warning.assert_called()


@pytest.mark.asyncio
async def test_resolve_column_id_to_name_project_config_not_found(webhook_adapter, mock_dependencies):
    """Verify _resolve_column_id_to_name returns None when project config not found."""
    # Setup config to return None
    mock_dependencies["config"].get_project_config = AsyncMock(return_value=None)

    # Execute
    result = await webhook_adapter._resolve_column_id_to_name("missing-project", "456")

    # Assert returns None and logs warning
    assert result is None
    mock_dependencies["logger"].warning.assert_called()


@pytest.mark.asyncio
async def test_resolve_column_id_to_name_exception_during_resolution(webhook_adapter, mock_dependencies):
    """Verify _resolve_column_id_to_name returns None on exception during resolution."""
    # Setup config to raise exception
    mock_dependencies["config"].get_project_config = AsyncMock(side_effect=Exception("Config service error"))

    # Execute
    result = await webhook_adapter._resolve_column_id_to_name("test-project", "456")

    # Assert returns None and logs error with exc_info
    assert result is None
    mock_dependencies["logger"].error.assert_called()


@pytest.mark.asyncio
async def test_project_card_event_handler_exits_on_column_resolution_failure(webhook_adapter, mock_dependencies):
    """Verify project_card handler exits without publishing event when column resolution fails."""
    from types import MappingProxyType

    # Setup config with empty board_columns mapping
    mock_project_config = MagicMock()
    mock_project_config.metadata = MappingProxyType({"board_columns": {}})
    mock_dependencies["config"].get_project_config = AsyncMock(return_value=mock_project_config)

    # Mock event_bus.publish
    mock_dependencies["event_bus"].publish = AsyncMock()

    # Create webhook event with column_id not in mapping
    event = WebhookEvent(
        delivery_id="delivery-failure",
        event_type="project_card",
        payload={
            "action": "moved",
            "repository": {"full_name": "org/repo"},
            "project_card": {
                "id": 1,
                "content_url": "https://api.github.com/repos/org/repo/issues/123",
                "column_id": 999,  # Not in mapping
            },
        },
        signature="sha256=test",
        timestamp=datetime.now(UTC),
        repository="org/repo",
    )

    # Execute
    result = await webhook_adapter._handle_project_card_event(event, "test-project")

    # Assert handler returns empty list and does not publish event
    assert result == []
    mock_dependencies["event_bus"].publish.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_column_id_to_name_with_zero_column_id(webhook_adapter, mock_dependencies):
    """Verify _resolve_column_id_to_name correctly handles column_id=0 as valid."""
    from types import MappingProxyType

    # Setup config with board_columns that includes column_id 0
    mock_project_config = MagicMock()
    mock_project_config.metadata = MappingProxyType({"board_columns": {"0": "Todo", "1": "In Progress"}})
    mock_dependencies["config"].get_project_config = AsyncMock(return_value=mock_project_config)

    # Execute - column_id=0 should be treated as a valid ID, not as None/missing
    result = await webhook_adapter._resolve_column_id_to_name("test-project", 0)

    # Assert returns the column name for ID 0
    assert result == "Todo"
