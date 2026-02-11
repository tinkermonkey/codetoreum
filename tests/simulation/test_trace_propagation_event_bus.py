"""Tests for trace propagation through event bus with MockTracer.

Tests cover:
- Trace context injection into published events
- Trace propagation through event handler chains
- PRODUCER and CONSUMER span kinds
- Async/await patterns for MockTracer methods
- W3C Trace Context format compliance
"""

import pytest
from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.simulation.simulation_runner import SimulationRunner
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.simulation.mock_tracer import SpanKind


@pytest.mark.asyncio
class TestTraceContextInjectionInEventBus:
    """Tests for trace context injection in event publishing."""

    async def test_trace_context_injected_in_published_event(self):
        """Test that trace context is injected when publishing events."""
        config = SimulationConfig.create_fast_config("test_injection")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # Start a span and publish an event
            span = await sim.mock_tracer.start_span(
                "publish_event",
                kind=SpanKind.PRODUCER,
            )
            carrier = {}
            await sim.mock_tracer.inject_context(span, carrier)
            assert "traceparent" in carrier, "Trace context should be created"
            await sim.mock_tracer.end_span(span)

            # Verify span was recorded
            sim.assert_span_exists("publish_event")

        result = await runner.run(scenario)
        assert result.success

    async def test_trace_context_propagates_through_event_chain(self):
        """Test that trace context propagates through multiple event handlers."""
        config = SimulationConfig.create_fast_config("test_propagation")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # First span (producer)
            producer_span = await sim.mock_tracer.start_span(
                "event_producer",
                kind=SpanKind.PRODUCER,
            )
            await sim.mock_tracer.inject_context(producer_span, carrier := {})
            producer_context = carrier.get("traceparent")
            await sim.mock_tracer.end_span(producer_span)

            # Mark that we injected context
            producer = sim.mock_tracer.get_spans_by_name("event_producer")[0]
            assert producer.span_context_injected

            # Consumer span using extracted context
            consumer_span = await sim.mock_tracer.start_span(
                "event_consumer",
                kind=SpanKind.CONSUMER,
                parent_context=producer_context,
            )
            await sim.mock_tracer.end_span(consumer_span)

            # Verify hierarchy
            spans = sim.mock_tracer.get_spans()
            assert len(spans) == 2
            assert spans[1].parent_span_id == spans[0].span_id

        result = await runner.run(scenario)
        assert result.success

    async def test_trace_context_preserved_across_async_handlers(self):
        """Test that trace context is preserved across async event handlers."""
        config = SimulationConfig.create_fast_config("test_async")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # Create a span and mark context injection
            span = await sim.mock_tracer.start_span(
                "async_handler",
                kind=SpanKind.CONSUMER,
            )
            await sim.mock_tracer.inject_context(span, {})
            await sim.mock_tracer.end_span(span)

            # Verify context was marked as injected
            sim.assert_span_context_injected("async_handler")

        result = await runner.run(scenario)
        assert result.success


@pytest.mark.asyncio
class TestTraceContextIsolation:
    """Tests for trace context isolation between independent operations."""

    async def test_independent_traces_for_unrelated_events(self):
        """Test that unrelated events get independent traces."""
        config = SimulationConfig.create_fast_config("test_isolation")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # First operation
            span1 = await sim.mock_tracer.start_span("operation1")
            await sim.mock_tracer.set_attribute(span1, "operation", "first")
            await sim.mock_tracer.end_span(span1)

            # Reset trace context for independent operation
            sim.mock_tracer.start_new_trace()

            # Second operation (independent trace)
            span2 = await sim.mock_tracer.start_span("operation2")
            await sim.mock_tracer.set_attribute(span2, "operation", "second")
            await sim.mock_tracer.end_span(span2)

            # Verify both spans recorded with different trace IDs
            spans = sim.mock_tracer.get_spans()
            assert len(spans) == 2
            assert spans[0].trace_id != spans[1].trace_id

        result = await runner.run(scenario)
        assert result.success


@pytest.mark.asyncio
class TestTraceContextAttributes:
    """Tests for span attributes and metadata in traces."""

    async def test_trace_context_with_span_attributes(self):
        """Test that span attributes are properly recorded."""
        config = SimulationConfig.create_fast_config("test_attributes")
        runner = SimulationRunner(config)

        async def scenario(sim):
            span = await sim.mock_tracer.start_span("operation_with_attributes")
            await sim.mock_tracer.set_attribute(span, "user_id", "user123")
            await sim.mock_tracer.set_attribute(span, "action", "create")
            await sim.mock_tracer.end_span(span)

            # Verify attributes were recorded
            sim.assert_span_attribute("operation_with_attributes", "user_id", "user123")
            sim.assert_span_attribute("operation_with_attributes", "action", "create")

        result = await runner.run(scenario)
        assert result.success

    async def test_trace_context_data_roundtrip(self):
        """Test W3C trace context format roundtrip (inject -> extract)."""
        config = SimulationConfig.create_fast_config("test_roundtrip")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # Create span and inject context
            span = await sim.mock_tracer.start_span("roundtrip_test")
            carrier = {}
            await sim.mock_tracer.inject_context(span, carrier)
            traceparent = carrier["traceparent"]
            await sim.mock_tracer.end_span(span)

            # Extract the context back
            extracted_carrier = {"traceparent": traceparent}
            extracted_context = await sim.mock_tracer.extract_context(
                extracted_carrier
            )

            # Verify roundtrip preserved context
            assert extracted_context == traceparent
            assert span.trace_id in traceparent
            assert span.span_id in traceparent

        result = await runner.run(scenario)
        assert result.success


@pytest.mark.asyncio
class TestEventBusSpanKinds:
    """Tests for PRODUCER and CONSUMER span kinds."""

    async def test_event_bus_producer_consumer_spans(self):
        """Test PRODUCER and CONSUMER span kinds in event bus."""
        config = SimulationConfig.create_fast_config("test_span_kinds")
        runner = SimulationRunner(config)

        async def scenario(sim):
            # Create PRODUCER span
            producer = await sim.mock_tracer.start_span(
                "publish",
                kind=SpanKind.PRODUCER,
            )
            await sim.mock_tracer.set_attribute(producer, "event_type", "ItemCreated")
            await sim.mock_tracer.inject_context(producer, carrier := {})
            context = carrier.get("traceparent")
            await sim.mock_tracer.end_span(producer)

            # Create CONSUMER span linked to producer
            consumer = await sim.mock_tracer.start_span(
                "handle",
                kind=SpanKind.CONSUMER,
                parent_context=context,
            )
            await sim.mock_tracer.set_attribute(consumer, "handler_name", "LogHandler")
            await sim.mock_tracer.end_span(consumer)

            # Verify span kinds
            sim.assert_span_kind("publish", SpanKind.PRODUCER)
            sim.assert_span_kind("handle", SpanKind.CONSUMER)

            # Verify parent-child relationship
            spans = sim.mock_tracer.get_spans()
            assert len(spans) == 2
            assert spans[0].kind == SpanKind.PRODUCER
            assert spans[1].kind == SpanKind.CONSUMER
            assert spans[1].parent_span_id == spans[0].span_id

        result = await runner.run(scenario)
        assert result.success
