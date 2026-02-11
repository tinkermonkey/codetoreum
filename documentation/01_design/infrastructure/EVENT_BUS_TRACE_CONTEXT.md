# Event Bus W3C Trace Context Propagation

**Status:** Implemented
**Date:** February 2026
**Version:** 1.0

## Overview

This document describes W3C Trace Context propagation through the event bus. This feature enables complete distributed tracing of events as they flow through the system, allowing visibility into the complete lifecycle of an event from publication to handling.

## Problem Statement

Without trace context propagation, events published to the bus lose their trace context. This means:
- Downstream handlers cannot continue the trace from the original request
- Multiple handlers processing the same event appear as separate, unrelated traces
- Event chains create gaps in distributed tracing visibility
- Debugging event-driven flows requires manual correlation

## Solution: W3C Trace Context Propagation

### W3C Traceparent Format

The W3C Trace Context standard defines a `traceparent` header format:

```
version-trace_id-span_id-trace_flags

Example:
00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01
```

**Components:**
- **version** (2 hex digits): Protocol version (always `00` for current spec)
- **trace_id** (32 hex digits): Unique identifier for the entire trace
- **span_id** (16 hex digits): Parent span ID
- **trace_flags** (2 hex digits): Trace flags
  - `01` = sampled/traced
  - `00` = not sampled

### Implementation Architecture

```
┌─ HTTP Request ─────────────────────────────────────────┐
│                                                          │
│  GET /api/work-items                                   │
│  traceparent: 00-xxx-yyy-01                            │
│                                                          │
└─────────────────────────────┬──────────────────────────┘
                              ▼
                   [FastAPI Auto-Instrumentation]
                              ▼
┌─ Create Span ──────────────────────────────────────────┐
│                                                          │
│  span.trace_id = 0xabc...                              │
│  span.span_id = 0x123...                               │
│                                                          │
└─────────────────────────────┬──────────────────────────┘
                              ▼
            [Application Service / Domain Logic]
                              ▼
┌─ Publish Event ────────────────────────────────────────┐
│                                                          │
│  WorkItemCreatedEvent(...)                             │
│  ↓                                                      │
│  [EventBus.publish()]                                  │
│    • Inject current trace context                      │
│    • event.metadata['traceparent'] = '00-abc-123-01'  │
│                                                          │
└─────────────────────────────┬──────────────────────────┘
                              ▼
┌─ Event Bus ────────────────────────────────────────────┐
│                                                          │
│  Distribute event to all handlers:                     │
│  • Handler 1, Handler 2, Handler 3                    │
│                                                          │
└─────────────────────────────┬──────────────────────────┘
                              ▼
┌─ Event Handler ────────────────────────────────────────┐
│                                                          │
│  class WorkItemHandler:                                │
│    async def handle(event):                            │
│      # Extract and activate trace context             │
│      trace_data = extract_trace_context(event)        │
│      ctx = activate_trace_context(trace_data)         │
│      # All spans created here are children of parent  │
│                                                          │
└─────────────────────────────┬──────────────────────────┘
                              ▼
                    [Child Spans Created]
```

## Implementation Details

### 1. TraceContextData Class

Represents W3C trace context data:

```python
from codetoreum.infrastructure.observability import TraceContextData

# Parse from traceparent header
trace_data = TraceContextData.from_traceparent(
    "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"
)

# Serialize to traceparent format
traceparent = trace_data.to_traceparent()
# Output: "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"

# Create from OpenTelemetry SpanContext
from opentelemetry.trace import get_current_span
span_context = get_current_span().get_span_context()
trace_data = TraceContextData.from_span_context(span_context)
```

### 2. TraceContextPropagator Class

Core propagation logic:

```python
from codetoreum.infrastructure.observability import TraceContextPropagator
from codetoreum.domain.events import DomainEvent

# Inject trace context into event
event = WorkItemCreatedEvent(...)
TraceContextPropagator.inject_trace_context(event)
# event.metadata['traceparent'] now contains the current trace context

# Extract trace context from event
trace_data = TraceContextPropagator.extract_trace_context(event)
if trace_data:
    print(f"Trace ID: {trace_data.trace_id}")
    print(f"Span ID: {trace_data.span_id}")

# Activate trace context in execution context
ctx = TraceContextPropagator.activate_trace_context(trace_data)
# Now any spans created will be children of this trace
```

### 3. EventBusTraceContext Helper

Simplified API for common patterns:

```python
from codetoreum.infrastructure.observability import EventBusTraceContext

# Extract and prepare trace context from event
trace_ctx = EventBusTraceContext.from_event(event)

if trace_ctx.has_trace_context():
    ctx = trace_ctx.activate()
    # Spans created here are children of event's trace
```

### 4. Convenience Functions

For simple use cases:

```python
from codetoreum.infrastructure.observability import (
    inject_current_trace_context_into_event,
    extract_and_activate_trace_context,
)

# Inject when publishing
inject_current_trace_context_into_event(event)

# Extract and activate when handling
ctx = extract_and_activate_trace_context(event)
```

## Event Bus Integration

### Automatic Injection on Publish

When an event is published, the event bus automatically injects trace context:

```python
# In EventBus.publish()
await event_bus.publish(event)
# ↓
# Automatically calls: inject_current_trace_context_into_event(event)
# ↓
# event.metadata['traceparent'] is set to current span context
```

### Automatic Extraction on Handle

When events are dispatched to handlers, trace context is extracted and activated:

```python
# In EventBus._dispatch_to_handler()
trace_context = extract_and_activate_trace_context(event)
# ↓
# Extracts traceparent from event.metadata
# ↓
# Creates new SpanContext and sets it as parent for any new spans
await handler.handle(event)
# ↓
# Handler's spans are children of the event's trace
```

## Data Flow

### Event Metadata Structure

Trace context is stored in the event's metadata field:

```python
event = WorkItemCreatedEvent(
    aggregate_id="item-123",
    aggregate_type="WorkItem",
)

# After publishing:
event.metadata = {
    "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"
}

# Persisted to Redis Streams (if configured)
# Can be recovered and replayed with full trace context
```

### Trace Chain Example

Request → Handler 1 → Event 1 → Handler 2 → Event 2 → Handler 3

All spans share the same `trace_id`, creating a complete trace:

```
Trace: 0af7651916cd43dd8448eb211c80319c
├── Span: Handle GET /api/work-items
│   ├── Span: ProcessWorkItem (application)
│   │   └── Span: PublishWorkItemCreated (domain)
│   │       └── [Event 1 published]
│   ├── Span: WorkItemBoardAdapter.update (Handler 1)
│   │   └── [Event 2 published]
│   └── Span: WorkItemAuditAdapter.log (Handler 2)
└── Span: WorkItemNotificationAdapter.notify (Handler 3)
    └── [Another Handler processes Event 2]
```

## Configuration

### Environment Variables

No additional configuration is required. Trace context propagation uses the existing OpenTelemetry setup:

```bash
# OpenTelemetry master switch
OTEL_ENABLED=true

# Tracing must be enabled
OTEL_TRACES_ENABLED=true

# Sampling strategy (recommended)
OTEL_TRACES_SAMPLER=traceidratio
OTEL_TRACES_SAMPLER_ARG=1.0  # 100% sampling for development
```

### Graceful Degradation

If OpenTelemetry is not installed or disabled:
- Trace context injection becomes a no-op
- Trace context extraction returns None
- Event bus continues to function normally
- No performance impact

## Error Handling

Trace context propagation includes comprehensive error handling:

```python
# All errors are caught and logged, never propagated to caller
# - Invalid traceparent format → logged, extraction returns None
# - Missing OpenTelemetry packages → handled gracefully
# - Invalid hex values → logged, activation returns None

# Example: Invalid traceparent
event.metadata["traceparent"] = "invalid-format"
trace_data = TraceContextPropagator.extract_trace_context(event)
# Returns None, logs warning, event bus continues

# Example: OpenTelemetry unavailable
TraceContextPropagator.inject_trace_context(event)
# No-op if OpenTelemetry not available
```

## Testing

### Unit Tests

Comprehensive unit tests in `tests/unit/infrastructure/observability/test_trace_context_propagation.py`:

```bash
pytest tests/unit/infrastructure/observability/test_trace_context_propagation.py -v
# 21 tests covering:
# - TraceContextData parsing/serialization
# - Trace context injection/extraction
# - SpanContext activation
# - Edge cases and error handling
```

### Integration Tests

Event bus integration tests in `tests/integration/infrastructure/test_event_bus_trace_context.py`:

```bash
pytest tests/integration/infrastructure/test_event_bus_trace_context.py -v
# 8 tests covering:
# - Automatic injection on publish
# - Automatic extraction on handle
# - Multiple handlers receive same trace context
# - Trace context preserved on retry
# - Wildcard handlers
# - Batch publishing
```

## Usage Examples

### Example 1: Standard Event Publishing

```python
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.domain.events import DomainEvent

# Create event bus
event_bus = EventBus()

# Register handler
event_bus.register_handler(my_handler)

# Publish event - trace context automatically injected
event = WorkItemCreatedEvent(...)
await event_bus.publish(event)
# event.metadata['traceparent'] is now set with current trace context
```

### Example 2: Manual Trace Context Control

```python
from codetoreum.infrastructure.observability import TraceContextPropagator
from opentelemetry import trace

# Get current span
current_span = trace.get_current_span()
span_context = current_span.get_span_context()

# Create event with specific trace context
event = WorkItemCreatedEvent(...)
TraceContextPropagator.inject_trace_context(event, span_context)

# Now event carries this specific trace context downstream
```

### Example 3: Handler with Trace Extraction

```python
from codetoreum.infrastructure.event_bus import EventHandler
from codetoreum.infrastructure.observability import TraceContextPropagator
from opentelemetry import trace

class MyEventHandler(EventHandler):
    async def handle(self, event):
        # Extract trace context from event
        trace_data = TraceContextPropagator.extract_trace_context(event)

        # Get current tracer
        tracer = trace.get_tracer(__name__)

        # Any spans created here will be children of the event's trace
        with tracer.start_as_current_span("my_handler.process") as span:
            span.set_attribute("event.type", event.event_type)
            # ... handler logic
```

### Example 4: Distributed Event Chain

```python
async def process_request(work_item_id: str):
    # 1. Original request creates span
    # trace_id = 0xabc...

    # 2. Publish WorkItemCreated event
    event1 = WorkItemCreatedEvent(...)
    await event_bus.publish(event1)
    # trace_id = 0xabc... (same trace)

    # 3. Handler 1 processes event
    # Creates spans with trace_id = 0xabc...

    # 4. Handler 1 publishes WorkItemAssigned event
    event2 = WorkItemAssignedEvent(...)
    await event_bus.publish(event2)
    # trace_id = 0xabc... (same trace continues)

    # 5. Handler 2 processes event with same trace
    # Complete visibility of entire event chain
```

## Performance Considerations

### Zero Overhead When Disabled

When OpenTelemetry is disabled (`OTEL_ENABLED=false`):
- Trace context injection: O(1) no-op
- Trace context extraction: O(1) no-op
- No measurable performance impact

### Minimal Overhead When Enabled

When enabled:
- **Injection**: String conversion (~1-2 microseconds)
- **Extraction**: String parsing (~1-2 microseconds)
- **Activation**: Context creation (~1-2 microseconds)
- Total per event: <10 microseconds

### Memory Impact

- Per-event overhead: ~200 bytes (traceparent string in metadata)
- No long-term memory accumulation (GC'd with event)

## Limitations and Future Work

### Current Limitations

1. **No tracestate support**: Only traceparent header, not full W3C tracestate
2. **Single parent per event**: Events have one parent span, not multiple
3. **No baggage propagation**: OpenTelemetry baggage not propagated through events

### Future Enhancements

1. **Tracestate support**: Implement full W3C tracestate for vendor-specific data
2. **Baggage propagation**: Propagate OpenTelemetry baggage through events
3. **Sampling decisions**: Propagate sampling decisions from parent to children
4. **Parent selection**: Support selecting which span to use as parent in multi-parent scenarios

## References

- **W3C Trace Context Spec**: https://www.w3.org/TR/trace-context/
- **OpenTelemetry Tracing**: https://opentelemetry.io/docs/concepts/signals/traces/
- **OpenTelemetry API**: https://opentelemetry.io/docs/reference/specification/trace/
- **Implementation**: `src/codetoreum/infrastructure/observability/trace_context_propagation.py`
- **Event Bus**: `src/codetoreum/infrastructure/event_bus.py`

## Related Documentation

- [OTEL Instrumentation Status](../claude_thoughts/otel_instrumentation_status.md)
- [Full OTEL Instrumentation Plan](../claude_thoughts/full_otel_instrumentation_plan.md)
- [Event Bus Architecture](../infrastructure/event_bus_architecture.md)
- [Domain Events Design](../domains/domain_events.md)
