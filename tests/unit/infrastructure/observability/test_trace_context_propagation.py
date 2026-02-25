"""Tests for W3C Trace Context propagation in event bus.

Tests cover:
- TraceContextData parsing and serialization (W3C traceparent format)
- Trace context injection into events
- Trace context extraction from events
- Span context activation during event handling
- Integration with event bus publishing and handling
"""

from unittest.mock import Mock, patch

import pytest

# Test imports with optional OpenTelemetry
try:
    from opentelemetry import context, trace
    from opentelemetry.trace import SpanContext, TraceFlags

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.observability.trace_context_propagation import (
    EventBusTraceContext,
    TraceContextData,
    TraceContextPropagator,
    extract_and_activate_trace_context,
    inject_current_trace_context_into_event,
)


class TestTraceContextData:
    """Tests for TraceContextData serialization and parsing."""

    def test_to_traceparent_format(self):
        """Test serialization to W3C traceparent format."""
        trace_data = TraceContextData(
            version="00",
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b9c7c989f97918e1",
            trace_flags="01",
        )

        traceparent = trace_data.to_traceparent()
        assert (
            traceparent
            == "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"
        )

    def test_from_traceparent_valid(self):
        """Test parsing valid W3C traceparent header."""
        traceparent = "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"
        trace_data = TraceContextData.from_traceparent(traceparent)

        assert trace_data is not None
        assert trace_data.version == "00"
        assert trace_data.trace_id == "0af7651916cd43dd8448eb211c80319c"
        assert trace_data.span_id == "b9c7c989f97918e1"
        assert trace_data.trace_flags == "01"

    def test_from_traceparent_invalid_format(self):
        """Test parsing invalid traceparent format."""
        invalid_traceparents = [
            "invalid",  # Too short
            "00-invalid-span-01",  # Invalid hex
            "00-0af7651916cd43dd8448eb211c80319c",  # Incomplete
            "00-0af7651916cd43dd8448eb211c80319x-b9c7c989f97918e1-01",  # Invalid hex char
        ]

        for traceparent in invalid_traceparents:
            trace_data = TraceContextData.from_traceparent(traceparent)
            assert trace_data is None

    def test_traceparent_roundtrip(self):
        """Test that parse -> serialize -> parse is idempotent."""
        original = "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"
        trace_data = TraceContextData.from_traceparent(original)
        assert trace_data is not None

        serialized = trace_data.to_traceparent()
        reparsed = TraceContextData.from_traceparent(serialized)

        assert trace_data == reparsed
        assert serialized == original

    @pytest.mark.skipif(not OTEL_AVAILABLE, reason="OpenTelemetry not available")
    def test_from_span_context(self):
        """Test creation from OpenTelemetry SpanContext."""
        span_context = SpanContext(
            trace_id=0x0AF7651916CD43DD8448EB211C80319C,
            span_id=0xB9C7C989F97918E1,
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )

        trace_data = TraceContextData.from_span_context(span_context)

        assert trace_data.version == "00"
        assert trace_data.trace_id == "0af7651916cd43dd8448eb211c80319c"
        assert trace_data.span_id == "b9c7c989f97918e1"
        assert trace_data.trace_flags == "01"

    @pytest.mark.skipif(not OTEL_AVAILABLE, reason="OpenTelemetry not available")
    def test_from_span_context_not_sampled(self):
        """Test trace flags are set correctly when not sampled."""
        span_context = SpanContext(
            trace_id=0x0AF7651916CD43DD8448EB211C80319C,
            span_id=0xB9C7C989F97918E1,
            is_remote=False,
            trace_flags=TraceFlags(0x00),
        )

        trace_data = TraceContextData.from_span_context(span_context)
        assert trace_data.trace_flags == "00"


class TestTraceContextPropagator:
    """Tests for trace context injection and extraction."""

    def test_inject_trace_context_into_event(self):
        """Test injecting trace context into event metadata."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        # Mock span context
        mock_span_context = Mock()
        mock_span_context.is_valid = True
        mock_span_context.trace_id = 0x0AF7651916CD43DD8448EB211C80319C
        mock_span_context.span_id = 0xB9C7C989F97918E1
        mock_span_context.trace_flags = TraceFlags(0x01)

        TraceContextPropagator.inject_trace_context(event, mock_span_context)

        # Verify trace context injected into metadata
        assert "traceparent" in event.metadata
        traceparent = event.metadata["traceparent"]
        assert traceparent.startswith("00-")
        assert "0af7651916cd43dd8448eb211c80319c" in traceparent
        assert "b9c7c989f97918e1" in traceparent

    def test_inject_trace_context_with_invalid_span(self):
        """Test that injection is skipped for invalid span context."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        mock_span_context = Mock()
        mock_span_context.is_valid = False

        TraceContextPropagator.inject_trace_context(event, mock_span_context)

        # No trace context should be injected
        assert "traceparent" not in event.metadata

    def test_extract_trace_context_from_event(self):
        """Test extracting trace context from event metadata."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )
        event.metadata["traceparent"] = "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"

        trace_data = TraceContextPropagator.extract_trace_context(event)

        assert trace_data is not None
        assert trace_data.trace_id == "0af7651916cd43dd8448eb211c80319c"
        assert trace_data.span_id == "b9c7c989f97918e1"

    def test_extract_trace_context_not_present(self):
        """Test that None is returned when trace context not present."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        trace_data = TraceContextPropagator.extract_trace_context(event)
        assert trace_data is None

    def test_extract_trace_context_with_empty_metadata(self):
        """Test that None is returned when metadata is empty."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )
        event.metadata = {}

        trace_data = TraceContextPropagator.extract_trace_context(event)
        assert trace_data is None

    @pytest.mark.skipif(not OTEL_AVAILABLE, reason="OpenTelemetry not available")
    def test_activate_trace_context(self):
        """Test activating trace context in execution context."""
        trace_data = TraceContextData(
            version="00",
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b9c7c989f97918e1",
            trace_flags="01",
        )

        ctx = TraceContextPropagator.activate_trace_context(trace_data)

        assert ctx is not None

    def test_activate_trace_context_opentelemetry_unavailable(self):
        """Test graceful handling when OpenTelemetry unavailable."""
        # This test passes when OTEL is available since we return a context
        # But doesn't fail when OTEL is unavailable
        trace_data = TraceContextData(
            version="00",
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b9c7c989f97918e1",
            trace_flags="01",
        )

        ctx = TraceContextPropagator.activate_trace_context(trace_data)

        if OTEL_AVAILABLE:
            assert ctx is not None
        else:
            assert ctx is None

    def test_activate_trace_context_invalid_hex(self):
        """Test handling of invalid trace context data."""
        # Create invalid trace data (this would normally fail in from_traceparent)
        # but we can test the activation with manually created invalid data
        trace_data = Mock()
        trace_data.trace_id = "not_hex"
        trace_data.span_id = "not_hex"
        trace_data.trace_flags = "01"

        ctx = TraceContextPropagator.activate_trace_context(trace_data)
        assert ctx is None


class TestEventBusTraceContext:
    """Tests for EventBusTraceContext helper class."""

    def test_from_event_with_trace_context(self):
        """Test creating EventBusTraceContext from event with trace context."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )
        event.metadata["traceparent"] = "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"

        trace_ctx = EventBusTraceContext.from_event(event)

        assert trace_ctx.has_trace_context()
        assert trace_ctx.get_traceparent() == "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"

    def test_from_event_without_trace_context(self):
        """Test creating EventBusTraceContext from event without trace context."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        trace_ctx = EventBusTraceContext.from_event(event)

        assert not trace_ctx.has_trace_context()
        assert trace_ctx.get_traceparent() is None

    @pytest.mark.skipif(not OTEL_AVAILABLE, reason="OpenTelemetry not available")
    def test_activate_with_trace_context(self):
        """Test activating EventBusTraceContext."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )
        event.metadata["traceparent"] = "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"

        trace_ctx = EventBusTraceContext.from_event(event)
        ctx = trace_ctx.activate()

        assert ctx is not None

    def test_activate_without_trace_context(self):
        """Test activate returns None when no trace context."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        trace_ctx = EventBusTraceContext.from_event(event)
        ctx = trace_ctx.activate()

        assert ctx is None


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_inject_current_trace_context_into_event(self):
        """Test convenience function for injecting trace context."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        # Mock the injector to verify it's called
        with patch.object(
            TraceContextPropagator, "inject_trace_context"
        ) as mock_inject:
            inject_current_trace_context_into_event(event)
            mock_inject.assert_called_once_with(event)

    def test_extract_and_activate_trace_context_with_context(self):
        """Test convenience function for extracting and activating."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )
        event.metadata["traceparent"] = "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"

        ctx = extract_and_activate_trace_context(event)

        if OTEL_AVAILABLE:
            assert ctx is not None
        else:
            assert ctx is None

    def test_extract_and_activate_trace_context_without_context(self):
        """Test convenience function when no trace context."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        ctx = extract_and_activate_trace_context(event)
        assert ctx is None
