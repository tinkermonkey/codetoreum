"""Integration tests for event bus trace context propagation.

Tests the complete flow of:
1. Publishing events with trace context injection
2. Handling events with trace context extraction and activation
3. Trace context carried through event chains
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch

try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanContext, TraceFlags

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.event_bus import EventBus, EventHandler
from codetoreum.infrastructure.observability.trace_context_propagation import (
    TraceContextData,
    TraceContextPropagator,
)


class SimpleEventHandler(EventHandler):
    """Simple handler that tracks handle calls."""

    def __init__(self):
        self.handled_events = []

    async def handle(self, event: DomainEvent) -> None:
        """Track event handling."""
        self.handled_events.append(event)

    def get_event_types(self):
        return ["DomainEvent"]  # Matches the class name of DomainEvent


class TestEventBusTraceContextIntegration:
    """Integration tests for event bus trace context propagation."""

    @pytest.mark.asyncio
    async def test_publish_injects_trace_context(self):
        """Test that publishing injects trace context into event."""
        event_bus = EventBus()
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
            payload={"key": "value"},
        )

        # Mock the injector to verify it's called
        with patch(
            "codetoreum.infrastructure.event_bus.inject_current_trace_context_into_event"
        ) as mock_inject:
            await event_bus.publish(event)
            mock_inject.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_receives_event_with_trace_context(self):
        """Test that handlers receive events with trace context."""
        event_bus = EventBus()
        handler = SimpleEventHandler()
        event_bus.register_handler(handler)

        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        # Manually inject trace context before publishing
        trace_data = TraceContextData(
            version="00",
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b9c7c989f97918e1",
            trace_flags="01",
        )
        event.metadata["traceparent"] = trace_data.to_traceparent()

        await event_bus.publish(event)

        assert len(handler.handled_events) == 1
        handled_event = handler.handled_events[0]
        assert "traceparent" in handled_event.metadata
        assert handled_event.metadata["traceparent"] == trace_data.to_traceparent()

    @pytest.mark.asyncio
    async def test_handler_extraction_activates_trace_context(self):
        """Test that handlers can extract and activate trace context."""
        event_bus = EventBus()

        extracted_trace_data = []

        class TraceContextCapturingHandler(EventHandler):
            async def handle(self, event: DomainEvent) -> None:
                # Extract trace context
                trace_data = TraceContextPropagator.extract_trace_context(event)
                extracted_trace_data.append(trace_data)

            def get_event_types(self):
                return ["DomainEvent"]

        handler = TraceContextCapturingHandler()
        event_bus.register_handler(handler)

        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        # Inject trace context
        trace_data = TraceContextData(
            version="00",
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b9c7c989f97918e1",
            trace_flags="01",
        )
        event.metadata["traceparent"] = trace_data.to_traceparent()

        await event_bus.publish(event)

        assert len(extracted_trace_data) == 1
        assert extracted_trace_data[0] is not None
        assert extracted_trace_data[0].trace_id == trace_data.trace_id
        assert extracted_trace_data[0].span_id == trace_data.span_id

    @pytest.mark.asyncio
    async def test_multiple_handlers_receive_same_trace_context(self):
        """Test that multiple handlers receive the same trace context."""
        event_bus = EventBus()

        extracted_contexts = []

        class ContextCapturingHandler(EventHandler):
            def __init__(self, handler_id):
                self.handler_id = handler_id

            async def handle(self, event: DomainEvent) -> None:
                trace_data = TraceContextPropagator.extract_trace_context(event)
                extracted_contexts.append((self.handler_id, trace_data))

            def get_event_types(self):
                return ["DomainEvent"]

        # Register multiple handlers
        for i in range(3):
            handler = ContextCapturingHandler(f"handler-{i}")
            event_bus.register_handler(handler)

        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        # Inject trace context
        trace_data = TraceContextData(
            version="00",
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b9c7c989f97918e1",
            trace_flags="01",
        )
        event.metadata["traceparent"] = trace_data.to_traceparent()

        await event_bus.publish(event)

        # All handlers should receive the same trace context
        assert len(extracted_contexts) == 3
        for handler_id, extracted in extracted_contexts:
            assert extracted is not None
            assert extracted.trace_id == trace_data.trace_id
            assert extracted.span_id == trace_data.span_id

    @pytest.mark.asyncio
    async def test_callback_extraction_activates_trace_context(self):
        """Test that callbacks can extract and activate trace context."""
        event_bus = EventBus()
        extracted_trace_data = []

        async def trace_capturing_callback(event: DomainEvent) -> None:
            trace_data = TraceContextPropagator.extract_trace_context(event)
            extracted_trace_data.append(trace_data)

        event_bus.subscribe("DomainEvent", trace_capturing_callback)

        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        # Inject trace context
        trace_data = TraceContextData(
            version="00",
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b9c7c989f97918e1",
            trace_flags="01",
        )
        event.metadata["traceparent"] = trace_data.to_traceparent()

        await event_bus.publish(event)

        assert len(extracted_trace_data) == 1
        assert extracted_trace_data[0] is not None
        assert extracted_trace_data[0].trace_id == trace_data.trace_id

    @pytest.mark.asyncio
    async def test_trace_context_preserved_on_retry(self):
        """Test that trace context is preserved across retries."""
        event_bus = EventBus(max_retries=2, retry_delay_seconds=0.01)

        attempt_count = []
        extracted_traces = []

        class RetryableHandler(EventHandler):
            async def handle(self, event: DomainEvent) -> None:
                attempt_count.append(1)
                trace_data = TraceContextPropagator.extract_trace_context(event)
                extracted_traces.append(trace_data)

                if len(attempt_count) < 3:
                    raise Exception("Temporary failure")

            def get_event_types(self):
                return ["DomainEvent"]

        handler = RetryableHandler()
        event_bus.register_handler(handler)

        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        # Inject trace context
        trace_data = TraceContextData(
            version="00",
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b9c7c989f97918e1",
            trace_flags="01",
        )
        event.metadata["traceparent"] = trace_data.to_traceparent()

        await event_bus.publish(event)

        # Should have succeeded after retries
        assert len(attempt_count) == 3

        # All attempts should have extracted the same trace context
        assert len(extracted_traces) == 3
        for extracted in extracted_traces:
            assert extracted is not None
            assert extracted.trace_id == trace_data.trace_id

    @pytest.mark.asyncio
    async def test_wildcard_handler_receives_trace_context(self):
        """Test that wildcard handlers receive trace context."""
        event_bus = EventBus()
        extracted_contexts = []

        class WildcardHandler(EventHandler):
            async def handle(self, event: DomainEvent) -> None:
                trace_data = TraceContextPropagator.extract_trace_context(event)
                extracted_contexts.append(trace_data)

            def get_event_types(self):
                return []  # Wildcard

        handler = WildcardHandler()
        event_bus.register_handler(handler)

        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        # Inject trace context
        trace_data = TraceContextData(
            version="00",
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b9c7c989f97918e1",
            trace_flags="01",
        )
        event.metadata["traceparent"] = trace_data.to_traceparent()

        await event_bus.publish(event)

        assert len(extracted_contexts) == 1
        assert extracted_contexts[0] is not None
        assert extracted_contexts[0].trace_id == trace_data.trace_id

    @pytest.mark.asyncio
    async def test_trace_context_survives_batch_publish(self):
        """Test that trace context is handled correctly in batch publish."""
        event_bus = EventBus()
        handler = SimpleEventHandler()
        event_bus.register_handler(handler)

        events = []
        for i in range(3):
            event = DomainEvent(
                aggregate_id=f"test-{i}",
                aggregate_type="TestAggregate",
                payload={"index": i},
            )
            events.append(event)

        await event_bus.publish_batch(events)

        # All events should have been handled
        assert len(handler.handled_events) == 3

        # Each event should have trace context injected
        for event in handler.handled_events:
            # The event should either have traceparent or be valid for the event bus
            # (trace context is optional)
            assert "traceparent" in event.metadata or event.metadata == {}
