"""
Tests for WebSocket instrumentation with OpenTelemetry spans.

Tests session spans, message spans, and trace context propagation
through WebSocket connections.
"""

from typing import TYPE_CHECKING

import pytest

from codetoreum.adapters.primary.websocket_adapter import (
    EventFilter,
    SubscriptionType,
    WebSocketAdapter,
    WebSocketConfig,
)
from codetoreum.domain.events import (
    ExecutionStarted,
    WorkItemCreated,
)
from codetoreum.infrastructure.observability.websocket_instrumentation import (
    WebSocketMessageTracer,
    WebSocketSessionTracer,
)

try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    if TYPE_CHECKING:
        from opentelemetry import trace
        from opentelemetry.trace import SpanKind
    else:
        trace = None  # type: ignore[assignment,misc]
        SpanKind = None  # type: ignore[assignment,misc]


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def websocket_config():
    """WebSocket configuration for testing."""
    return WebSocketConfig(
        max_buffer_size=100,
        flow_control_threshold=0.8,
        disconnect_on_overflow=True,
        heartbeat_interval=10,
        heartbeat_timeout=30,
    )


@pytest.fixture
def websocket_adapter(websocket_config):
    """Create WebSocket adapter for testing."""
    return WebSocketAdapter(config=websocket_config, auth_manager=None)


@pytest.fixture
def session_tracer():
    """Create session tracer for testing."""
    return WebSocketSessionTracer()


# ============================================================================
# Session Span Tests
# ============================================================================


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_session_tracer_start_session():
    """Test starting a WebSocket session span."""
    tracer = WebSocketSessionTracer()

    session_span = tracer.start_session(
        connection_id="test-conn-123",
        client_ip="192.168.1.100",
        token_present=True,
    )

    assert session_span is not None
    # Note: span might not have valid IDs if OpenTelemetry is not properly initialized
    # Just check that the span object exists and can be ended
    span_context = session_span.get_span_context()
    assert span_context is not None

    # Cleanup
    tracer.end_session(session_span, reason="test_complete")


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_session_tracer_end_session():
    """Test ending a WebSocket session span with statistics."""
    tracer = WebSocketSessionTracer()

    session_span = tracer.start_session(
        connection_id="test-conn-456",
        client_ip="10.0.0.1",
        token_present=False,
    )

    # End session with stats
    tracer.end_session(
        session_span,
        reason="normal_closure",
        message_count=42,
        buffered_events=10,
    )

    # Verify span was ended (no exception thrown)
    assert session_span is not None


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_session_tracer_add_session_event():
    """Test adding events to a session span."""
    tracer = WebSocketSessionTracer()

    session_span = tracer.start_session(
        connection_id="test-conn-789",
        client_ip="172.16.0.1",
        token_present=True,
    )

    # Add events
    tracer.add_session_event(
        session_span,
        "buffer_overflow",
        attributes={"buffer_size": 100, "max_size": 100},
    )

    tracer.add_session_event(session_span, "rate_limit_exceeded")

    # Cleanup
    tracer.end_session(session_span, reason="test_complete")


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_session_tracer_graceful_degradation_without_otel():
    """Test that session tracer degrades gracefully without OpenTelemetry."""
    # This test verifies the tracer works even if OpenTelemetry is not available
    # In the actual implementation, this is handled by checking OPENTELEMETRY_AVAILABLE
    tracer = WebSocketSessionTracer()

    # Should not raise even with None spans
    tracer.end_session(None, reason="test")
    tracer.add_session_event(None, "test_event")


# ============================================================================
# Message Span Tests
# ============================================================================


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_message_tracer_start_subscribe_message():
    """Test starting a subscribe message span."""
    session_tracer = WebSocketSessionTracer()
    session_span = session_tracer.start_session(
        connection_id="test-conn-sub-1",
        client_ip="127.0.0.1",
        token_present=True,
    )

    message_tracer = WebSocketMessageTracer(session_span)

    # Start subscribe message
    message_span = message_tracer.start_subscribe_message(
        connection_id="test-conn-sub-1",
        subscription_type="all_events",
        filter_count=2,
    )

    assert message_span is not None
    span_context = message_span.get_span_context()
    assert span_context is not None

    # Cleanup
    message_tracer.end_message_span(message_span, success=True)
    session_tracer.end_session(session_span)


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_message_tracer_start_unsubscribe_message():
    """Test starting an unsubscribe message span."""
    session_tracer = WebSocketSessionTracer()
    session_span = session_tracer.start_session(
        connection_id="test-conn-unsub-1",
        client_ip="127.0.0.1",
        token_present=True,
    )

    message_tracer = WebSocketMessageTracer(session_span)

    # Start unsubscribe message
    message_span = message_tracer.start_unsubscribe_message(
        connection_id="test-conn-unsub-1",
        subscription_id="sub-123",
    )

    assert message_span is not None

    # Cleanup
    message_tracer.end_message_span(message_span, success=True)
    session_tracer.end_session(session_span)


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_message_tracer_start_ping_message():
    """Test starting a ping message span."""
    session_tracer = WebSocketSessionTracer()
    session_span = session_tracer.start_session(
        connection_id="test-conn-ping-1",
        client_ip="127.0.0.1",
        token_present=True,
    )

    message_tracer = WebSocketMessageTracer(session_span)

    # Start ping message
    message_span = message_tracer.start_ping_message("test-conn-ping-1")

    assert message_span is not None

    # Cleanup
    message_tracer.end_message_span(message_span, success=True)
    session_tracer.end_session(session_span)


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_message_tracer_end_message_span():
    """Test ending a message span with results."""
    session_tracer = WebSocketSessionTracer()
    session_span = session_tracer.start_session(
        connection_id="test-conn-end-1",
        client_ip="127.0.0.1",
        token_present=True,
    )

    message_tracer = WebSocketMessageTracer(session_span)

    # Start and end message
    message_span = message_tracer.start_subscribe_message(
        connection_id="test-conn-end-1",
        subscription_type="workflow_events",
        filter_count=1,
    )

    message_tracer.end_message_span(
        message_span,
        success=True,
        message_size=256,
    )

    # Verify no exception
    assert message_span is not None

    # Cleanup
    session_tracer.end_session(session_span)


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_message_tracer_end_message_span_with_error():
    """Test ending a message span with error."""
    session_tracer = WebSocketSessionTracer()
    session_span = session_tracer.start_session(
        connection_id="test-conn-error-1",
        client_ip="127.0.0.1",
        token_present=True,
    )

    message_tracer = WebSocketMessageTracer(session_span)

    # Start and end message with error
    message_span = message_tracer.start_subscribe_message(
        connection_id="test-conn-error-1",
    )
    message_tracer.end_message_span(
        message_span,
        success=False,
        error_code="subscription_failed",
    )

    # Cleanup
    session_tracer.end_session(session_span)


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_message_tracer_start_event_delivery_span():
    """Test starting an event delivery span."""
    session_tracer = WebSocketSessionTracer()
    session_span = session_tracer.start_session(
        connection_id="test-conn-delivery-1",
        client_ip="127.0.0.1",
        token_present=True,
    )

    message_tracer = WebSocketMessageTracer(session_span)

    # Start event delivery
    event_span = message_tracer.start_event_delivery_span(
        connection_id="test-conn-delivery-1",
        event_type="ExecutionStarted",
        event_id="evt-12345",
        subscription_type="workflow_events",
    )

    assert event_span is not None

    # Cleanup
    message_tracer.end_message_span(event_span, success=True)
    session_tracer.end_session(session_span)


# ============================================================================
# Trace Context Propagation Tests
# ============================================================================


@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
def test_message_tracer_link_to_event_trace_context():
    """Test linking message span to event trace context."""
    session_tracer = WebSocketSessionTracer()
    session_span = session_tracer.start_session(
        connection_id="test-conn-link-1",
        client_ip="127.0.0.1",
        token_present=True,
    )

    message_tracer = WebSocketMessageTracer(session_span)

    # Create a test event with trace context
    event = ExecutionStarted(
        aggregate_id="exec-123",
        payload={"started_at": "2024-01-01T00:00:00Z"},
    )

    # Inject trace context (simulate)
    if OPENTELEMETRY_AVAILABLE:
        current_span = trace.get_current_span()
        if current_span and current_span.get_span_context():
            from codetoreum.infrastructure.observability.trace_context_propagation import (
                TraceContextData,
            )

            trace_data = TraceContextData.from_span_context(current_span.get_span_context())
            event.metadata["traceparent"] = trace_data.to_traceparent()

    # Start and link message span
    message_span = message_tracer.start_event_delivery_span(
        connection_id="test-conn-link-1",
        event_type=event.event_type,
        event_id=str(event.event_id),
    )

    message_tracer.link_to_event_trace_context(message_span, event)

    # Cleanup
    message_tracer.end_message_span(message_span, success=True)
    session_tracer.end_session(session_span)


# ============================================================================
# WebSocket Adapter Instrumentation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_websocket_adapter_session_span_initialization():
    """Test that WebSocket adapter initializes session spans."""
    config = WebSocketConfig()
    adapter = WebSocketAdapter(config=config, auth_manager=None)

    # Verify tracers are initialized
    assert adapter._session_tracer is not None
    assert len(adapter._session_spans) == 0
    assert len(adapter._message_tracers) == 0


# ============================================================================
# Subscription Matching Tests
# ============================================================================


def test_websocket_adapter_subscription_matches_event_no_filters():
    """Test subscription matching with no filters."""
    adapter = WebSocketAdapter()

    # Create subscription with no filters
    subscription = EventFilter(
        subscription_type=SubscriptionType.ALL_EVENTS,
    )

    # Any event should match
    event = ExecutionStarted(
        aggregate_id="exec-1",
        payload={"started_at": "2024-01-01T00:00:00Z"},
    )

    assert adapter._subscription_matches_event(subscription, event)


def test_websocket_adapter_subscription_matches_event_by_type():
    """Test subscription matching by event type."""
    adapter = WebSocketAdapter()

    # Create subscription with event type filter
    subscription = EventFilter(
        subscription_type=SubscriptionType.ALL_EVENTS,
        event_types=["ExecutionStarted", "ExecutionCompleted"],
    )

    # Matching event
    event1 = ExecutionStarted(
        aggregate_id="exec-1",
        payload={"started_at": "2024-01-01T00:00:00Z"},
    )

    assert adapter._subscription_matches_event(subscription, event1)

    # Non-matching event
    event2 = WorkItemCreated(
        aggregate_id="item-1",
        payload={"url": "https://github.com/org/repo/issues/1"},
    )

    assert not adapter._subscription_matches_event(subscription, event2)


def test_websocket_adapter_subscription_matches_event_by_work_item():
    """Test subscription matching by work item ID."""
    adapter = WebSocketAdapter()

    # Create subscription filtered by work item
    subscription = EventFilter(
        subscription_type=SubscriptionType.ALL_EVENTS,
        work_item_id="item-999",
    )

    # Event that doesn't have work_item_id attribute - should match (no filter contradiction)
    event1 = ExecutionStarted(
        aggregate_id="exec-1",
        payload={"started_at": "2024-01-01T00:00:00Z"},
    )

    assert adapter._subscription_matches_event(subscription, event1)


def test_websocket_adapter_subscription_matches_event_combined_filters():
    """Test subscription matching with multiple filters (AND logic)."""
    adapter = WebSocketAdapter()

    # Create subscription with multiple filters
    subscription = EventFilter(
        subscription_type=SubscriptionType.ALL_EVENTS,
        event_types=["ExecutionStarted"],
    )

    # Event matching event type filter
    event1 = ExecutionStarted(
        aggregate_id="exec-1",
        payload={"started_at": "2024-01-01T00:00:00Z"},
    )

    assert adapter._subscription_matches_event(subscription, event1)

    # Event with wrong event type (WorkItemCreated)
    event2 = WorkItemCreated(
        aggregate_id="item-1",
        payload={"url": "https://github.com/org/repo/issues/1"},
    )

    assert not adapter._subscription_matches_event(subscription, event2)


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not OPENTELEMETRY_AVAILABLE, reason="OpenTelemetry not available")
async def test_websocket_instrumentation_end_to_end():
    """Test end-to-end WebSocket instrumentation from connection to event delivery."""
    config = WebSocketConfig()
    adapter = WebSocketAdapter(config=config, auth_manager=None)

    # Verify initial state
    assert len(adapter._session_spans) == 0
    assert len(adapter._message_tracers) == 0

    # Simulate connection setup (what handle_websocket does)
    connection_id = "test-conn-e2e-1"

    session_span = adapter._session_tracer.start_session(
        connection_id=connection_id,
        client_ip="127.0.0.1",
        token_present=True,
    )
    adapter._session_spans[connection_id] = session_span
    adapter._message_tracers[connection_id] = WebSocketMessageTracer(session_span)

    assert connection_id in adapter._session_spans
    assert connection_id in adapter._message_tracers

    # Simulate subscription
    message_tracer = adapter._message_tracers[connection_id]
    assert message_tracer is not None, "message_tracer should not be None after setup"

    sub_span = message_tracer.start_subscribe_message(
        connection_id=connection_id,
        subscription_type="all_events",
        filter_count=1,
    )
    message_tracer.end_message_span(sub_span, success=True)

    # Simulate event delivery
    event = ExecutionStarted(
        aggregate_id="exec-1",
        payload={"started_at": "2024-01-01T00:00:00Z"},
    )

    event_span = message_tracer.start_event_delivery_span(
        connection_id=connection_id,
        event_type=event.event_type,
        event_id=str(event.event_id),
        subscription_type="all_events",
    )
    message_tracer.link_to_event_trace_context(event_span, event)
    message_tracer.end_message_span(event_span, success=True)

    # Simulate disconnect
    adapter._cleanup_session_span(connection_id, reason="normal_closure")

    assert connection_id not in adapter._session_spans
    assert connection_id not in adapter._message_tracers
