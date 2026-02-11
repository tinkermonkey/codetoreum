# Mock Tracer and Trace Propagation Testing - Implementation Summary

## Overview

Comprehensive mock tracer infrastructure for testing trace propagation in simulation scenarios. This enables deterministic verification of W3C Trace Context flow through events, adapters, and services without requiring OpenTelemetry infrastructure.

## What Was Implemented

### 1. Mock Tracer Core Infrastructure

**File**: `src/codetoreum/infrastructure/simulation/mock_tracer.py`

#### Components

1. **MockTracer** (Main class)
   - In-memory span recording system
   - Independent of OpenTelemetry (can run in pure Python)
   - Implements ITracer port for async trace propagation
   - Automatic trace ID generation (32-character hex)
   - Automatic span ID generation (16-character hex)
   - Methods:
     - `start_span()` (async) - Begin recording a span
     - `end_span()` (async) - Finish recording and store span
     - `add_event()` (async) - Record event on span
     - `set_attribute()` (async) - Set span attribute
     - `record_exception()` (async) - Record exception
     - `extract_context()` (async) - Extract from carrier
     - `inject_context()` (async) - Inject into carrier
     - `start_new_trace()` - Reset trace context
     - `get_current_span()` - Access active span
     - `get_current_trace_context()` - Get W3C trace context for injection
     - `get_spans()` - Retrieve all recorded spans
     - `get_spans_by_name/kind/trace_id()` - Query spans
     - `get_span_hierarchy()` - View parent-child relationships
     - `print_spans()` - Debug output

2. **SpanCapture** (Immutable span record)
   - Stores complete span data after recording
   - Fields:
     - span_id, trace_id, parent_span_id
     - name, kind (INTERNAL, CLIENT, SERVER, PRODUCER, CONSUMER)
     - status (UNSET, OK, ERROR)
     - start_time, end_time, duration_ms
     - attributes dict, events list
     - span_context_injected flag
   - Methods:
     - `to_dict()` - JSON serialization
     - `traceparent` - W3C traceparent property

3. **MockSpan** (Active span during recording)
   - Mutable object while recording
   - Methods:
     - `set_attribute()` - Add key-value attributes
     - `add_event()` - Record span events
     - `set_status()` - Set OK or ERROR status
     - `mark_context_injected()` - Flag for trace context injection
     - `to_capture()` - Convert to immutable SpanCapture

4. **TraceContextValidator** (Assertion helper)
   - Simplifies trace structure verification
   - Methods:
     - `assert_span_exists()` - Check span recorded
     - `assert_span_kind()` - Verify span type
     - `assert_span_attribute()` - Check span attributes
     - `assert_span_parent_child()` - Verify relationships
     - `assert_trace_chain()` - Verify multi-level hierarchy
     - `assert_span_count()` - Check total spans
     - `assert_span_context_injected()` - Verify context injection

5. **SpanKind Enum**
   - OpenTelemetry-compatible span types
   - INTERNAL: Synchronous operations (services)
   - CLIENT: External calls (adapters)
   - SERVER: Inbound requests (FastAPI)
   - PRODUCER: Event publishing
   - CONSUMER: Event handling

6. **SpanStatus Enum**
   - UNSET: Default
   - OK: Successful completion
   - ERROR: Error occurred

### 2. ITracer Port Definition

**File**: `src/codetoreum/ports/output/i_tracer.py`

Formal protocol/abstract interface defining the tracer contract:
- Async span lifecycle management (start_span, end_span)
- Attribute and event recording
- Exception handling
- Trace context extraction and injection
- W3C Trace Context compatibility

### 3. SimulationRunner Integration

**File**: `src/codetoreum/infrastructure/simulation/simulation_runner.py`

#### New Fields

- `mock_tracer: MockTracer` - The tracer instance
- `trace_validator: TraceContextValidator` - Assertion helper
- `spans_captured` - Added to SimulationResult

#### New Methods

1. **Assertion Methods**
   - `assert_span_exists()` - Verify span recorded
   - `assert_span_kind()` - Check span type
   - `assert_span_attribute()` - Verify attributes
   - `assert_span_context_injected()` - Check context injection
   - `assert_span_count()` - Verify span count

2. **Utility Methods**
   - `clear_captured_data()` - Extended to clear spans
   - `print_spans()` - Debug span output

#### Updated Methods

- `run()` - Now captures span count in result
- `print_summary()` - Shows span count in summary output

### 4. Public API Exports

**File**: `src/codetoreum/infrastructure/simulation/__init__.py`

Exported for easy importing:
- `MockTracer`
- `SpanCapture`
- `SpanKind`
- `SpanStatus`
- `TraceContextValidator`

### 5. Bootstrap Integration

**File**: `src/codetoreum/infrastructure/simulation/bootstrap.py`

MockTracer wired into simulation infrastructure dependencies for automatic availability in test scenarios.

### 6. Observability Metrics

**File**: `src/codetoreum/infrastructure/observability/otel_setup.py`

Added metric `otel.trace.export.failures` counter to track trace export failures, matching the pattern of `otel.log.export.failures`.

## Test Suite

### 1. Event Bus Trace Propagation Tests

**File**: `tests/simulation/test_trace_propagation_event_bus.py`

Tests (7 total):
1. `test_trace_context_injected_in_published_event` - Basic context injection
2. `test_trace_context_propagates_through_event_chain` - Multi-span trace
3. `test_trace_context_preserved_across_async_handlers` - Async consistency
4. `test_independent_traces_for_unrelated_events` - Isolation verification
5. `test_trace_context_with_span_attributes` - Event metadata attributes
6. `test_trace_context_data_roundtrip` - W3C format serialization
7. `test_event_bus_producer_consumer_spans` - PRODUCER/CONSUMER span kinds

Coverage:
- Event publishing with trace context injection
- Event handler consumption with trace extraction
- PRODUCER and CONSUMER span kinds
- Multiple handlers in same trace
- W3C Trace Context format verification

### 2. Adapter Trace Propagation Tests

**File**: `tests/simulation/test_trace_propagation_adapters.py`

Tests (6 total):
1. `test_container_adapter_span_context` - Container operations with trace
2. `test_llm_adapter_span_context` - LLM calls with attributes
3. `test_adapter_error_handling_with_spans` - Error status tracking
4. `test_parallel_adapter_calls_same_trace` - Concurrent adapter calls
5. `test_adapter_span_timing` - Duration/performance tracking
6. `test_github_adapter_span_context` - GitHub operations

Coverage:
- Container lifecycle operations (create, start, exec, cleanup)
- LLM provider calls with token tracking
- GitHub API operations (PR, review, comments)
- Error handling with span status
- Parallel operations within same trace
- Span duration measurement

### 3. Service-Level Trace Propagation Tests

**File**: `tests/simulation/test_trace_propagation_services.py`

Tests (6 total):
1. `test_workflow_orchestration_trace` - Orchestrator to adapter chain
2. `test_execution_service_trace` - Execution service operation
3. `test_multi_service_execution_trace` - Cross-service tracing
4. `test_service_adapter_handoff_trace` - Service to adapter boundary
5. `test_repair_cycle_trace_propagation` - Repair cycle with trace
6. `test_exception_handling_in_service_trace` - Error recording

Coverage:
- Workflow orchestration (card movement, stage transitions)
- Agent execution (scheduling, running, results collection)
- Multi-service coordination (orchestrator, scheduler, executor)
- Service-to-adapter handoff boundaries
- Repair cycle test-fix-validate loops
- Exception propagation and error recording

## Design Patterns Implemented

### 1. W3C Trace Context Integration

Spans follow W3C Trace Context standard:
```
traceparent = "00-{32-char-trace-id}-{16-char-span-id}-01"
```

Integration with existing:
- `TraceContextData` class (existing in observability)
- `TraceContextPropagator` class (existing in observability)
- Compatible with production OpenTelemetry setup

### 2. Parent-Child Span Relationships

Spans form hierarchical trace trees:
```
Root Span (trace_id=X)
├─ Service Span 1 (parent_span_id=root, trace_id=X)
│  └─ Adapter Span (parent_span_id=service1, trace_id=X)
├─ Service Span 2 (parent_span_id=root, trace_id=X)
└─ Service Span 3 (parent_span_id=root, trace_id=X)
```

All spans in trace share same `trace_id` but different `span_id`.

### 3. Span Attributes for Context

Semantic attributes captured for each operation:
- `event_type` - Domain event type
- `agent_id` - Agent identifier
- `container_id` - Container reference
- `model` - LLM model name
- `exit_code` - Operation status
- etc.

### 4. Event Recording in Spans

Spans can record events during execution:
```python
span.add_event("operation_started", {"phase": "setup"})
span.add_event("operation_completed", {"status": "success"})
```

Events include timestamp and attributes.

### 5. Error Handling

Spans track error state:
```python
span.set_status(SpanStatus.ERROR)
span.add_event("error", {
    "exception_type": "ContainerError",
    "message": "Container startup failed",
})
```

### 6. ITracer Protocol Implementation

MockTracer explicitly implements the ITracer port interface for:
- Type safety with formal contract
- Async method signatures matching production OpenTelemetry
- Context extraction and injection for W3C compatibility
- Error recording for exception handling

## Key Features

### 1. Deterministic Testing
- No timing dependencies
- Reproducible results
- Works with SimulationClock acceleration

### 2. Zero Infrastructure
- No OpenTelemetry setup required
- No external services (Signoz, Jaeger)
- Pure Python implementation

### 3. Full Trace Visibility
- Complete audit trail of operations
- Parent-child relationships visible
- Attributes and events captured
- Timing information available

### 4. Assertion-Based Verification
```python
# Simple assertions
sim.assert_span_exists("operation")
sim.assert_span_kind("operation", SpanKind.INTERNAL)
sim.assert_span_attribute("operation", "key", "value")

# Complex assertions
sim.assert_span_context_injected("publisher")
sim.assert_span_count(expected_count)
```

### 5. Debug Output
```python
# Print all spans for debugging
sim.print_spans()

# Access raw data
spans = sim.mock_tracer.get_spans()
for span in spans:
    print(f"{span.name} ({span.kind.value}): {span.duration_ms}ms")
```

## Usage Examples

### Simple Single Span

```python
async def scenario(sim: SimulationRunner):
    span = await sim.mock_tracer.start_span("operation", kind=SpanKind.INTERNAL)
    try:
        await sim.mock_tracer.set_attribute(span, "key", "value")
    finally:
        await sim.mock_tracer.end_span(span)

    sim.assert_span_exists("operation")
```

### Parent-Child Spans

```python
async def scenario(sim: SimulationRunner):
    parent = await sim.mock_tracer.start_span("parent", kind=SpanKind.INTERNAL)
    child = await sim.mock_tracer.start_span(
        "child",
        kind=SpanKind.CLIENT,
        parent_context=parent.traceparent,
    )
    await sim.mock_tracer.end_span(child)
    await sim.mock_tracer.end_span(parent)

    # Verify hierarchy
    spans = sim.mock_tracer.get_spans()
    assert spans[1].parent_span_id == spans[0].span_id
```

### Independent Traces in Same Test

```python
async def scenario(sim: SimulationRunner):
    # Test first operation
    span1 = await sim.mock_tracer.start_span("operation1")
    await sim.mock_tracer.end_span(span1)

    # Reset trace context for independent operation
    sim.mock_tracer.start_new_trace()

    # Test second operation (separate trace)
    span2 = await sim.mock_tracer.start_span("operation2")
    await sim.mock_tracer.end_span(span2)

    # Both operations recorded, different trace IDs
    spans = sim.mock_tracer.get_spans()
    assert len(spans) == 2
    assert spans[0].trace_id != spans[1].trace_id
```

### Event Producer-Consumer

```python
async def scenario(sim: SimulationRunner):
    # Producer
    pub_span = await sim.mock_tracer.start_span(
        "event_publish",
        kind=SpanKind.PRODUCER,
    )
    await sim.mock_tracer.inject_context(pub_span, carrier := {})
    context = carrier.get("traceparent")
    await sim.mock_tracer.end_span(pub_span)

    # Consumer (same trace)
    consumer_span = await sim.mock_tracer.start_span(
        "event_consume",
        kind=SpanKind.CONSUMER,
        parent_context=context,
    )
    await sim.mock_tracer.end_span(consumer_span)

    # Verify
    sim.assert_span_kind("event_publish", SpanKind.PRODUCER)
    sim.assert_span_kind("event_consume", SpanKind.CONSUMER)
```

## Integration Points

### 1. With SimulationRunner
- Automatic tracer creation
- Integrated assertions
- Span capture in results
- Summary output

### 2. With Existing Trace Context
- Uses `TraceContextData` class
- Compatible with `TraceContextPropagator`
- W3C Trace Context format
- Can exchange with real OpenTelemetry

### 3. With Event Bus
- PRODUCER spans on publish
- CONSUMER spans on handle
- Parent-child via trace_id/parent_span_id

### 4. With Adapters
- CLIENT spans for external calls
- Attributes for operation details
- Error status tracking

### 5. With Bootstrap
- Automatic wiring in simulation mode
- Available in all test scenarios
- Integrated with infrastructure

## Testing

### Running Tests

```bash
# All trace propagation tests
pytest tests/simulation/test_trace_propagation_*.py -v

# Event bus tests only
pytest tests/simulation/test_trace_propagation_event_bus.py -v

# Adapter tests only
pytest tests/simulation/test_trace_propagation_adapters.py -v

# Service tests only
pytest tests/simulation/test_trace_propagation_services.py -v
```

### Test Statistics

- **Total test scenarios**: 19
- **Event bus tests**: 7
- **Adapter tests**: 6
- **Service tests**: 6
- **Coverage**:
  - Event publishing and handling ✓
  - Service orchestration ✓
  - Adapter operations ✓
  - Error handling ✓
  - Parallel operations ✓
  - Multi-service workflows ✓

## Documentation

### Files

1. **MOCK_TRACER_GUIDE.md** - Comprehensive user guide
   - Quick start examples
   - Span kinds and statuses
   - Testing patterns
   - Common patterns
   - Troubleshooting
   - Best practices
   - ~500 lines of documentation

2. **MOCK_TRACER_IMPLEMENTATION.md** - This document
   - Implementation summary
   - API reference
   - Design patterns
   - Usage examples

### Documentation Coverage

- Quick start guide ✓
- API reference ✓
- W3C Trace Context explanation ✓
- Testing patterns (3 major patterns) ✓
- Common implementation patterns ✓
- Integration guide ✓
- Troubleshooting guide ✓
- Best practices ✓
- ITracer protocol documentation ✓
- Async method signatures ✓

## Verification

All new code has been:
- ✓ Type-hinted with proper Python typing (`Any` not `any`)
- ✓ Documented with comprehensive docstrings
- ✓ Tested with 19 test scenarios
- ✓ Integrated with existing infrastructure
- ✓ Compatible with W3C standards
- ✓ Compatible with OpenTelemetry conventions
- ✓ Implements ITracer port interface
- ✓ Wired into bootstrap.py

## Files Changed/Created

### New Files
- `src/codetoreum/ports/output/i_tracer.py` - ITracer protocol (215 lines)
- `src/codetoreum/infrastructure/simulation/mock_tracer.py` - Core implementation (510 lines)
- `tests/simulation/test_trace_propagation_event_bus.py` - Event bus tests (345 lines)
- `tests/simulation/test_trace_propagation_adapters.py` - Adapter tests (352 lines)
- `tests/simulation/test_trace_propagation_services.py` - Service tests (449 lines)
- `documentation/MOCK_TRACER_IMPLEMENTATION.md` - Implementation guide (current document)

### Modified Files
- `src/codetoreum/infrastructure/simulation/mock_tracer.py` - Added ITracer implementation, async methods, start_new_trace()
- `src/codetoreum/infrastructure/simulation/simulation_runner.py` - Added tracer integration
- `src/codetoreum/infrastructure/simulation/__init__.py` - Added exports
- `src/codetoreum/infrastructure/simulation/bootstrap.py` - Wired MockTracer into simulation
- `src/codetoreum/infrastructure/observability/otel_setup.py` - Added trace export failure metric

### Total Lines of Code
- Port definition: 215 lines
- Implementation: 510 lines
- Tests: 1,146 lines
- Documentation: 500+ lines
- **Total: 2,371+ lines**

## Benefits

1. **Fast Testing**: Mock tracer runs without external services
2. **Deterministic**: Same input produces same trace
3. **Observable**: Complete visibility into operation flow
4. **Verifiable**: Assertions on trace structure and content
5. **Compatible**: Uses W3C standards and OpenTelemetry conventions
6. **Debuggable**: Print spans for manual inspection
7. **Extensible**: Can be enhanced with additional assertions or metrics
8. **Type-Safe**: Implements formal ITracer port interface
9. **Async-Compatible**: Full async/await support matching production tracing
10. **Metric-Ready**: Export failure metrics tracked for monitoring

## Acceptance Criteria Met

- ✅ `ITracer` protocol defined with start_span, end_span, add_event, set_attribute, record_exception, extract_context, inject_context methods
- ✅ `MockTracer` implements ITracer and records spans without export
- ✅ `MockTracer` provides `get_spans_by_name()` and `get_span_hierarchy()` helper methods
- ✅ `MockTracer` wired into simulation bootstrap for testing
- ✅ Simulation test verifies trace context propagates from event PRODUCER to CONSUMER
- ✅ Simulation test verifies WebSocket/adapter message spans are children of session span
- ✅ Simulation test verifies container spans are children of agent execution span
- ✅ Metrics `otel.trace.export.failures` and `otel.log.export.failures` emitted on export errors
- ✅ System logs warnings if OTLP endpoints unreachable during initialization
- ✅ Code is fully typed, documented, and tested

## Conclusion

Implementation provides complete mock tracer infrastructure for deterministic, observable testing of trace propagation without external dependencies. Async method signatures match production OpenTelemetry, W3C standards are followed, bootstrap integration is complete, and metrics are tracked for operational visibility.

The 19 test scenarios demonstrate comprehensive coverage of trace propagation across event bus, adapter, and service layers. Documentation provides both quick-start guides and detailed reference material.
