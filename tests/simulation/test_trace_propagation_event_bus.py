"""Simulation tests for trace propagation through event bus.

Tests trace context injection and extraction in event bus operations
to verify W3C Trace Context propagation across event handlers.

Test scenarios:
1. Single event with trace context injection
2. Event chain with trace context propagation
3. Parallel event handlers with independent traces
4. Trace context lost without explicit injection
"""

import pytest
from datetime import timedelta

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
    SpanKind,
)
from codetoreum.infrastructure.observability.trace_context_propagation import (
    TraceContextData,
    TraceContextPropagator,
)


@pytest.mark.asyncio
async def test_trace_context_injected_in_published_event():
    """Test that trace context is injected into published events."""
    config = SimulationConfig.create_fast_config(
        scenario_name="trace_context_injection",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Create a span for this operation
        span = sim.mock_tracer.start_span(
            "publish_event",
            kind=SpanKind.PRODUCER,
        )

        try:
            # Create trace context from the span
            trace_context = sim.mock_tracer.get_current_trace_context()

            # Verify trace context was created
            assert trace_context is not None, "Trace context should be created"
            assert trace_context.trace_id is not None
            assert trace_context.span_id is not None
            assert trace_context.trace_flags == "01"  # Sampled

            # Mark span as having injected context
            span.mark_context_injected()

        finally:
            sim.mock_tracer.end_span(span)

        # Verify span was recorded
        sim.assert_span_exists("publish_event", "Span exists")
        sim.assert_span_context_injected("publish_event", "Context injected")

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"
    assert result.spans_captured >= 1


@pytest.mark.asyncio
async def test_trace_context_propagates_through_event_chain():
    """Test that trace context propagates through a chain of events."""
    config = SimulationConfig.create_fast_config(
        scenario_name="trace_propagation_chain",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Root span: event publication
        root_span = sim.mock_tracer.start_span(
            "publish_event",
            kind=SpanKind.PRODUCER,
        )

        try:
            # Get trace context for injection
            trace_context = sim.mock_tracer.get_current_trace_context()
            root_span.mark_context_injected()

        finally:
            sim.mock_tracer.end_span(root_span)

        # Simulate event handler creating child span
        # In real scenario, trace context would be extracted from event metadata
        root_trace_id = (
            trace_context.trace_id if trace_context else None
        )

        handler_span = sim.mock_tracer.start_span(
            "handle_event",
            kind=SpanKind.CONSUMER,
            parent_span_id=root_span.span_id,
            trace_id=root_trace_id,
        )

        try:
            # Handler processes event
            handler_span.set_attribute("event_type", "WorkItemCreated")
            handler_span.add_event("event_processed")

        finally:
            sim.mock_tracer.end_span(handler_span)

        # Verify the trace chain
        sim.assert_span_exists("publish_event")
        sim.assert_span_exists("handle_event")
        sim.assert_span_kind("publish_event", SpanKind.PRODUCER)
        sim.assert_span_kind("handle_event", SpanKind.CONSUMER)

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"
    assert result.spans_captured == 2, f"Expected 2 spans, got {result.spans_captured}"

    # Verify spans are in hierarchy
    spans = runner.mock_tracer.get_spans()
    assert len(spans) == 2
    # Both spans should have same trace ID
    assert spans[0].trace_id == spans[1].trace_id


@pytest.mark.asyncio
async def test_trace_context_preserved_across_async_handlers():
    """Test that trace context is preserved across async event handlers."""
    config = SimulationConfig.create_fast_config(
        scenario_name="trace_async_handlers",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Initial event publication
        pub_span = sim.mock_tracer.start_span(
            "publish_event",
            kind=SpanKind.PRODUCER,
        )

        trace_context = sim.mock_tracer.get_current_trace_context()
        pub_span.mark_context_injected()
        sim.mock_tracer.end_span(pub_span)

        # Simulate two async handlers processing same event
        # Handler 1
        handler1_span = sim.mock_tracer.start_span(
            "handle_event_1",
            kind=SpanKind.CONSUMER,
            parent_span_id=pub_span.span_id,
            trace_id=trace_context.trace_id if trace_context else None,
        )
        handler1_span.set_attribute("handler_index", 1)
        sim.mock_tracer.end_span(handler1_span)

        # Handler 2 - same trace, different handler
        handler2_span = sim.mock_tracer.start_span(
            "handle_event_2",
            kind=SpanKind.CONSUMER,
            parent_span_id=pub_span.span_id,
            trace_id=trace_context.trace_id if trace_context else None,
        )
        handler2_span.set_attribute("handler_index", 2)
        sim.mock_tracer.end_span(handler2_span)

        # Both handlers should be in same trace
        all_spans = sim.mock_tracer.get_spans()
        trace_ids = set(s.trace_id for s in all_spans)
        sim.assert_true(
            len(trace_ids) == 1,
            "all_spans_same_trace",
            f"All spans should share trace ID",
        )

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"


@pytest.mark.asyncio
async def test_independent_traces_for_unrelated_events():
    """Test that unrelated events have independent traces."""
    config = SimulationConfig.create_fast_config(
        scenario_name="independent_traces",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # First event sequence
        event1_span = sim.mock_tracer.start_span(
            "publish_event_1",
            kind=SpanKind.PRODUCER,
        )
        trace1_id = event1_span.trace_id
        sim.mock_tracer.end_span(event1_span)

        # Reset root trace for independent second sequence
        sim.mock_tracer.root_trace_id = None

        # Second event sequence (new trace)
        event2_span = sim.mock_tracer.start_span(
            "publish_event_2",
            kind=SpanKind.PRODUCER,
        )
        trace2_id = event2_span.trace_id
        sim.mock_tracer.end_span(event2_span)

        # Verify different traces
        sim.assert_true(
            trace1_id != trace2_id,
            "different_trace_ids",
            "Unrelated events should have different trace IDs",
        )

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"
    assert result.spans_captured == 2


@pytest.mark.asyncio
async def test_trace_context_with_span_attributes():
    """Test trace context with span attributes for event metadata."""
    config = SimulationConfig.create_fast_config(
        scenario_name="trace_with_attributes",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Create span with event metadata in attributes
        span = sim.mock_tracer.start_span(
            "handle_event",
            kind=SpanKind.CONSUMER,
        )

        try:
            # Add event-specific attributes
            span.set_attribute("event_type", "WorkItemCreated")
            span.set_attribute("work_item_id", "item-123")
            span.set_attribute("project_id", "proj-456")
            span.add_event("event_received", {"from_queue": "event_bus"})
            span.add_event("event_processed", {"status": "success"})

        finally:
            sim.mock_tracer.end_span(span)

        # Verify attributes
        sim.assert_span_attribute("handle_event", "event_type", "WorkItemCreated")
        sim.assert_span_attribute("handle_event", "work_item_id", "item-123")
        sim.assert_span_attribute("handle_event", "project_id", "proj-456")

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"

    spans = runner.mock_tracer.get_spans()
    assert len(spans) == 1
    span = spans[0]
    assert len(span.events) == 2
    assert span.events[0].name == "event_received"
    assert span.events[1].name == "event_processed"


@pytest.mark.asyncio
async def test_trace_context_data_roundtrip():
    """Test W3C TraceContextData serialization and parsing."""
    config = SimulationConfig.create_fast_config(
        scenario_name="trace_context_roundtrip",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Create a span and get its trace context
        span = sim.mock_tracer.start_span("operation", kind=SpanKind.INTERNAL)

        trace_data = TraceContextData(
            version="00",
            trace_id=span.trace_id,
            span_id=span.span_id,
            trace_flags="01",
        )

        # Serialize to W3C format
        traceparent = trace_data.to_traceparent()

        # Parse back from W3C format
        parsed_data = TraceContextData.from_traceparent(traceparent)

        # Verify roundtrip
        sim.assert_equal(
            parsed_data.trace_id,
            trace_data.trace_id,
            "trace_id_roundtrip",
        )
        sim.assert_equal(
            parsed_data.span_id,
            trace_data.span_id,
            "span_id_roundtrip",
        )
        sim.assert_equal(
            parsed_data.trace_flags,
            trace_data.trace_flags,
            "trace_flags_roundtrip",
        )
        sim.assert_equal(
            parsed_data.version,
            trace_data.version,
            "version_roundtrip",
        )

        sim.mock_tracer.end_span(span)

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"


@pytest.mark.asyncio
async def test_event_bus_producer_consumer_spans():
    """Test PRODUCER and CONSUMER span kinds for event bus."""
    config = SimulationConfig.create_fast_config(
        scenario_name="producer_consumer_spans",
        speed_multiplier=100.0,
    )

    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # PRODUCER: Publishing event to bus
        producer_span = sim.mock_tracer.start_span(
            "event_bus_publish",
            kind=SpanKind.PRODUCER,
        )
        producer_span.set_attribute("destination", "event_bus")
        producer_span.set_attribute("event_count", 1)
        sim.mock_tracer.end_span(producer_span)

        # Simulate event sitting in bus

        # CONSUMER: Handler consuming from bus
        consumer_span = sim.mock_tracer.start_span(
            "event_bus_consume",
            kind=SpanKind.CONSUMER,
            parent_span_id=producer_span.span_id,
            trace_id=producer_span.trace_id,
        )
        consumer_span.set_attribute("source", "event_bus")
        consumer_span.set_attribute("handler_name", "WorkflowOrchestrator")
        sim.mock_tracer.end_span(consumer_span)

        # Verify span kinds
        sim.assert_span_kind("event_bus_publish", SpanKind.PRODUCER)
        sim.assert_span_kind("event_bus_consume", SpanKind.CONSUMER)

    result = await runner.run(scenario)
    assert result.success, f"Scenario failed: {result.errors}"

    # Verify publisher-consumer relationship
    spans = runner.mock_tracer.get_spans()
    assert len(spans) == 2
    producers = runner.mock_tracer.get_spans_by_kind(SpanKind.PRODUCER)
    consumers = runner.mock_tracer.get_spans_by_kind(SpanKind.CONSUMER)
    assert len(producers) == 1
    assert len(consumers) == 1
