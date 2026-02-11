# Mock Tracer and Trace Propagation Testing Guide

## Overview

The Mock Tracer provides in-memory span recording for testing trace propagation without requiring OpenTelemetry infrastructure. It enables deterministic verification of trace context flow through events, adapters, and services.

**Key Components:**
- `MockTracer`: Records spans in memory
- `SpanCapture`: Immutable span records with parent-child relationships
- `TraceContextValidator`: Assertion helpers for trace structure verification
- `SimulationRunner` integration: Automatic trace context tracking in scenarios

## Quick Start

### Basic Span Recording

```python
from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
    SpanKind,
)

async def test_trace_propagation():
    config = SimulationConfig.create_fast_config(
        scenario_name="my_trace_test",
        speed_multiplier=100.0,
    )
    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Start a span
        span = sim.mock_tracer.start_span(
            "my_operation",
            kind=SpanKind.INTERNAL,
        )

        try:
            # Add attributes
            span.set_attribute("key", "value")
            # Add events
            span.add_event("event_name", {"attr": "value"})
            # Do work...
        finally:
            sim.mock_tracer.end_span(span)

        # Verify
        sim.assert_span_exists("my_operation")
        sim.assert_span_attribute("my_operation", "key", "value")

    result = await runner.run(scenario)
    assert result.success
    assert result.spans_captured == 1
```

### Parent-Child Spans

```python
async def scenario(sim: SimulationRunner):
    # Parent span
    parent = sim.mock_tracer.start_span(
        "parent_operation",
        kind=SpanKind.INTERNAL,
    )

    try:
        # Child span with parent reference
        child = sim.mock_tracer.start_span(
            "child_operation",
            kind=SpanKind.CLIENT,
            parent_span_id=parent.span_id,
            trace_id=parent.trace_id,
        )

        try:
            # Child work
            pass
        finally:
            sim.mock_tracer.end_span(child)

    finally:
        sim.mock_tracer.end_span(parent)

    # Verify parent-child relationship
    spans = sim.mock_tracer.get_spans()
    assert len(spans) == 2
    assert spans[1].parent_span_id == spans[0].span_id
```

## Span Kinds

The `SpanKind` enum follows OpenTelemetry conventions:

- **INTERNAL**: Synchronous operations within a process
  - Orchestrator methods, service calls, internal logic
  - Example: `WorkflowOrchestrator.handle_card_movement`

- **CLIENT**: Outbound calls to external systems
  - Adapter calls, external service requests
  - Example: `ContainerAdapter.run`, `llm.chat_completion`

- **SERVER**: Inbound requests (usually handled by framework)
  - REST endpoints, WebSocket handlers
  - Typically auto-instrumented by FastAPI

- **PRODUCER**: Publishing events/messages
  - Event bus publish operations
  - Example: `event_bus_publish`

- **CONSUMER**: Processing events/messages
  - Event handler operations
  - Example: `event_bus_consume`

## W3C Trace Context Propagation

The mock tracer uses W3C Trace Context format for compatibility:

```python
from codetoreum.infrastructure.observability.trace_context_propagation import (
    TraceContextData,
)

# Create trace context
trace_data = TraceContextData(
    version="00",
    trace_id=span.trace_id,  # 32-character hex
    span_id=span.span_id,    # 16-character hex
    trace_flags="01",        # "01" = sampled, "00" = not sampled
)

# Serialize to W3C format
traceparent = trace_data.to_traceparent()
# Result: "00-{trace_id}-{span_id}-01"

# Parse from W3C format
parsed = TraceContextData.from_traceparent(traceparent)
assert parsed.trace_id == trace_data.trace_id
```

## Testing Patterns

### 1. Event Bus Trace Propagation

Test that trace context flows from publisher to consumer:

```python
async def scenario(sim: SimulationRunner):
    # Publisher: Create PRODUCER span
    pub_span = sim.mock_tracer.start_span(
        "event_bus_publish",
        kind=SpanKind.PRODUCER,
    )

    trace_context = sim.mock_tracer.get_current_trace_context()
    pub_span.mark_context_injected()  # Simulate injecting into event metadata
    sim.mock_tracer.end_span(pub_span)

    # Consumer: Create CONSUMER span with same trace
    consumer_span = sim.mock_tracer.start_span(
        "event_bus_consume",
        kind=SpanKind.CONSUMER,
        parent_span_id=pub_span.span_id,
        trace_id=trace_context.trace_id,
    )
    sim.mock_tracer.end_span(consumer_span)

    # Verify chain
    sim.assert_span_kind("event_bus_publish", SpanKind.PRODUCER)
    sim.assert_span_kind("event_bus_consume", SpanKind.CONSUMER)
```

### 2. Adapter Call Chains

Test trace propagation through service → adapter → external system:

```python
async def scenario(sim: SimulationRunner):
    # Service layer
    service_span = sim.mock_tracer.start_span(
        "MyService.do_something",
        kind=SpanKind.INTERNAL,
    )

    # Adapter layer (child of service)
    adapter_span = sim.mock_tracer.start_span(
        "MyAdapter.external_call",
        kind=SpanKind.CLIENT,
        parent_span_id=service_span.span_id,
        trace_id=service_span.trace_id,
    )
    adapter_span.set_attribute("external_system", "GitHub")
    adapter_span.set_attribute("endpoint", "/repos/owner/repo/pulls")

    sim.mock_tracer.end_span(adapter_span)
    sim.mock_tracer.end_span(service_span)

    # Verify
    sim.assert_span_attribute("MyAdapter.external_call", "external_system", "GitHub")
```

### 3. Complex Workflows

Test trace propagation through multi-service workflows:

```python
async def scenario(sim: SimulationRunner):
    # Root operation
    root = sim.mock_tracer.start_span(
        "workflow_execute",
        kind=SpanKind.INTERNAL,
    )

    # Service 1
    svc1 = sim.mock_tracer.start_span(
        "Service1.process",
        kind=SpanKind.INTERNAL,
        parent_span_id=root.span_id,
        trace_id=root.trace_id,
    )
    sim.mock_tracer.end_span(svc1)

    # Service 2
    svc2 = sim.mock_tracer.start_span(
        "Service2.process",
        kind=SpanKind.INTERNAL,
        parent_span_id=root.span_id,
        trace_id=root.trace_id,
    )

    # Adapter from Service 2
    adapter = sim.mock_tracer.start_span(
        "Adapter.call",
        kind=SpanKind.CLIENT,
        parent_span_id=svc2.span_id,
        trace_id=root.trace_id,
    )
    sim.mock_tracer.end_span(adapter)
    sim.mock_tracer.end_span(svc2)

    sim.mock_tracer.end_span(root)

    # All in same trace
    all_trace_ids = set(s.trace_id for s in sim.mock_tracer.get_spans())
    assert len(all_trace_ids) == 1
```

## SimulationRunner Assertion Methods

### Span Existence and Properties

```python
# Check span exists
sim.assert_span_exists("operation_name")

# Check span kind
sim.assert_span_kind("operation_name", SpanKind.INTERNAL)

# Check span attribute
sim.assert_span_attribute("operation_name", "key", "value")
sim.assert_span_attribute("operation_name", "key")  # Just check existence

# Check context was injected (for PRODUCER spans)
sim.assert_span_context_injected("event_bus_publish")

# Check total span count
sim.assert_span_count(expected_count)
```

### Debugging

```python
# Print all spans for debugging
sim.print_spans()

# Access spans directly
spans = sim.mock_tracer.get_spans()
spans_by_name = sim.mock_tracer.get_spans_by_name("operation")
spans_by_kind = sim.mock_tracer.get_spans_by_kind(SpanKind.CLIENT)
spans_by_trace = sim.mock_tracer.get_spans_by_trace_id("trace-id-here")

# Get span hierarchy
hierarchy = sim.mock_tracer.get_span_hierarchy()
root_spans = hierarchy.get(None, [])  # Spans with no parent
```

## Span Lifecycle

### Creating Spans

```python
span = sim.mock_tracer.start_span(
    name="operation",
    kind=SpanKind.INTERNAL,
    parent_span_id=parent_id,  # Optional
    trace_id=trace_id,  # Optional - new trace if not provided
)
```

### Modifying Spans

```python
# Set attributes
span.set_attribute("key", "value")
span.set_attribute("count", 42)

# Add events
span.add_event("event_name")
span.add_event("event_with_attrs", {"attr1": "value1", "attr2": 123})

# Set status
from codetoreum.infrastructure.simulation import SpanStatus
span.set_status(SpanStatus.OK)
span.set_status(SpanStatus.ERROR)

# Mark context injected (for event publishers)
span.mark_context_injected()
```

### Ending Spans

```python
span.end()
# After end(), span is immutable and stored in tracer
```

### Using Context Manager Pattern

While the mock tracer doesn't provide a context manager, you can create one:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def trace_span(sim, name, kind, parent_id=None):
    parent_trace_id = None
    if parent_id:
        parent = [s for s in sim.mock_tracer.get_spans() if s.span_id == parent_id][0]
        parent_trace_id = parent.trace_id

    span = sim.mock_tracer.start_span(
        name,
        kind=kind,
        parent_span_id=parent_id,
        trace_id=parent_trace_id,
    )
    try:
        yield span
    finally:
        sim.mock_tracer.end_span(span)

# Usage
async with trace_span(sim, "operation", SpanKind.INTERNAL) as span:
    span.set_attribute("key", "value")
    # Do work
```

## SpanCapture Data Structure

Spans are recorded as `SpanCapture` objects (immutable):

```python
@dataclass
class SpanCapture:
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    kind: SpanKind
    status: SpanStatus
    start_time: datetime
    end_time: Optional[datetime]
    attributes: Dict[str, any]
    events: List[SpanEvent]
    span_context_injected: bool

    # Calculated properties
    @property
    def duration_ms(self) -> Optional[float]:
        """Duration in milliseconds"""

    @property
    def traceparent(self) -> str:
        """W3C traceparent format"""

    def to_dict(self) -> Dict:
        """JSON-serializable representation"""
```

### Accessing Span Data

```python
spans = sim.mock_tracer.get_spans()

for span in spans:
    print(f"Name: {span.name}")
    print(f"Kind: {span.kind.value}")
    print(f"Status: {span.status.value}")
    print(f"Duration: {span.duration_ms:.2f}ms")
    print(f"Attributes: {span.attributes}")
    print(f"Events: {len(span.events)}")

    # Access W3C traceparent
    traceparent = span.traceparent
    # "00-{32-char-hex}-{16-char-hex}-01"

    # Convert to JSON
    span_dict = span.to_dict()
```

## Test Scenarios Reference

### Event Bus Tests
Location: `tests/simulation/test_trace_propagation_event_bus.py`

- Single event with trace context injection
- Event chain with trace context propagation
- Parallel event handlers with independent traces
- Trace context lost without explicit injection
- Producer-consumer span kinds

### Adapter Tests
Location: `tests/simulation/test_trace_propagation_adapters.py`

- Container adapter operations with span context
- LLM adapter calls with trace attributes
- Adapter error handling with spans
- Parallel adapter calls within same trace
- GitHub adapter span context
- Adapter span timing/duration

### Service Tests
Location: `tests/simulation/test_trace_propagation_services.py`

- Trace propagation through workflow orchestration
- Trace propagation through execution service
- Multi-service execution trace
- Service-adapter handoff trace
- Repair cycle trace propagation
- Exception handling in service trace

## Common Patterns

### Pattern 1: Instrument Service Calls

```python
async def scenario(sim: SimulationRunner):
    service_span = sim.mock_tracer.start_span(
        "MyService.method",
        kind=SpanKind.INTERNAL,
    )

    service_span.set_attribute("method_param", param_value)
    service_span.add_event("method_started")

    # Call adapters
    adapter_span = sim.mock_tracer.start_span(
        "MyAdapter.external_call",
        kind=SpanKind.CLIENT,
        parent_span_id=service_span.span_id,
        trace_id=service_span.trace_id,
    )
    # ... adapter call ...
    sim.mock_tracer.end_span(adapter_span)

    service_span.add_event("method_completed")
    sim.mock_tracer.end_span(service_span)
```

### Pattern 2: Verify Trace Chains

```python
async def scenario(sim: SimulationRunner):
    # Create spans in parent-child order
    p = sim.mock_tracer.start_span("parent", kind=SpanKind.INTERNAL)
    c = sim.mock_tracer.start_span("child", SpanKind.INTERNAL, p.span_id, p.trace_id)
    gc = sim.mock_tracer.start_span("grandchild", SpanKind.INTERNAL, c.span_id, p.trace_id)

    sim.mock_tracer.end_span(gc)
    sim.mock_tracer.end_span(c)
    sim.mock_tracer.end_span(p)

    # Verify chain
    spans = sim.mock_tracer.get_spans()
    assert spans[0].span_id == p.span_id  # Root
    assert spans[1].parent_span_id == p.span_id  # Child of parent
    assert spans[2].parent_span_id == c.span_id  # Child of child
```

### Pattern 3: Handle Errors with Spans

```python
from codetoreum.infrastructure.simulation import SpanStatus

async def scenario(sim: SimulationRunner):
    span = sim.mock_tracer.start_span("operation", kind=SpanKind.INTERNAL)

    try:
        # Do work that might fail
        raise Exception("Something went wrong")
    except Exception as e:
        span.set_status(SpanStatus.ERROR)
        span.add_event("error", {
            "exception_type": type(e).__name__,
            "message": str(e),
        })
    finally:
        sim.mock_tracer.end_span(span)

    # Verify error was recorded
    error_spans = [s for s in sim.mock_tracer.get_spans() if s.status == SpanStatus.ERROR]
    assert len(error_spans) == 1
```

## Integration with Real OpenTelemetry

When testing with real OpenTelemetry:

1. The mock tracer operates independently
2. Real traces from OpenTelemetry will not be captured by mock tracer
3. Test assertions should use mock tracer's recorded spans
4. In production, OpenTelemetry's real tracer will be used

### Recommended Approach

```python
# Simulation testing (mock tracer)
@pytest.mark.asyncio
async def test_with_mock_tracer():
    runner = SimulationRunner(config)
    result = await runner.run(scenario)
    assert result.spans_captured > 0

# Integration testing (real OpenTelemetry)
@pytest.mark.asyncio
@pytest.mark.integration
async def test_with_real_otel():
    # Use real application with OpenTelemetry enabled
    # Verify traces in Signoz or collector
    pass
```

## Troubleshooting

### Spans not captured

```python
# Make sure to call end_span
span = sim.mock_tracer.start_span("op", SpanKind.INTERNAL)
# ... do work ...
sim.mock_tracer.end_span(span)  # Required to record

# Check result
assert sim.mock_tracer.get_spans()  # Should not be empty
```

### Trace ID mismatch

```python
# Ensure consistent trace ID across parent-child
parent = sim.mock_tracer.start_span("parent", SpanKind.INTERNAL)
# Child must use parent's trace_id
child = sim.mock_tracer.start_span(
    "child",
    SpanKind.INTERNAL,
    parent_span_id=parent.span_id,
    trace_id=parent.trace_id,  # Critical!
)
```

### Parent span ID not set

```python
# If child's parent_span_id doesn't match parent's span_id
parent = sim.mock_tracer.start_span("parent", SpanKind.INTERNAL)
child = sim.mock_tracer.start_span(
    "child",
    SpanKind.INTERNAL,
    parent_span_id=parent.span_id,  # Must match exactly
)
```

## Best Practices

1. **Always end spans**: Use try-finally to ensure `end_span()` is called
2. **Use appropriate span kinds**: INTERNAL for services, CLIENT for adapters
3. **Set meaningful attributes**: Include IDs, names, and relevant context
4. **Trace full operations**: From entry point to completion
5. **Test trace chains**: Verify parent-child relationships
6. **Document trace structure**: Comment expected span hierarchy in tests
7. **Use meaningful names**: Span names should indicate operation (e.g., `ContainerAdapter.run`)
8. **Mark context injected**: For PRODUCER spans, call `mark_context_injected()`

## See Also

- `MockTracer` API: `/workspace/src/codetoreum/infrastructure/simulation/mock_tracer.py`
- `TraceContextPropagation`: `/workspace/src/codetoreum/infrastructure/observability/trace_context_propagation.py`
- Test examples: `tests/simulation/test_trace_propagation_*.py`
- W3C Trace Context: https://www.w3.org/TR/trace-context/
