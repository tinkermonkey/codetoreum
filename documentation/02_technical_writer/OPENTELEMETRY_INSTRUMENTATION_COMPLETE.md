# OpenTelemetry Instrumentation - Complete Documentation

**Project:** Codetoreum
**Issue:** #249 - Instrument all server components to emit OTLP spans
**Status:** Design Complete
**Date:** February 2026
**Version:** 1.0

---

## Table of Contents

1. [API Documentation](#api-documentation)
2. [User Documentation](#user-documentation)
3. [Developer Documentation](#developer-documentation)
4. [System Documentation](#system-documentation)
5. [Operations Documentation](#operations-documentation)

---

## API Documentation

### Observability Configuration API

#### `ObservabilityConfig`

Comprehensive configuration class for all OpenTelemetry signals (traces, logs, metrics).

**Module:** `codetoreum.infrastructure.observability.config`

```python
from codetoreum.infrastructure.observability.config import ObservabilityConfig

# Load from environment
config = ObservabilityConfig.from_env()

# Access configuration
config.enabled               # Master switch
config.traces_enabled        # Trace export enabled
config.logs_enabled          # Log export enabled
config.traces_endpoint       # Trace OTLP endpoint
config.logs_endpoint         # Log OTLP endpoint
```

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `enabled` | `bool` | Master switch for all OpenTelemetry features |
| `traces_enabled` | `bool` | Enable/disable trace export to OTLP endpoint |
| `logs_enabled` | `bool` | Enable/disable log export to OTLP endpoint |
| `metrics_enabled` | `bool` | Enable/disable metrics export |
| `traces_endpoint` | `str` | gRPC endpoint for traces (port 4317) |
| `logs_endpoint` | `str` | HTTP endpoint for logs (port 4318) |
| `sampler_type` | `Literal` | Sampling strategy: `always_on`, `always_off`, `traceidratio`, `parentbased_always_on` |
| `sampler_arg` | `float` | Sampler argument (e.g., 0.1 for 10% sampling) |
| `batch_max_queue_size` | `int` | Max queue size for batch processor (default: 2048) |
| `batch_max_export_batch_size` | `int` | Max batch size for export (default: 512) |
| `batch_schedule_delay_millis` | `int` | Export interval in milliseconds (default: 5000) |

**Methods:**

- `from_env() -> ObservabilityConfig` - Load configuration from environment variables
- `validate() -> None` - Validate configuration and log warnings for misconfigured signals

**Environment Variables:**

```bash
# Master switches
OTEL_ENABLED=true                                   # Master switch (default: true)
OTEL_TRACES_ENABLED=true                           # Trace export (default: true)
OTEL_LOGS_ENABLED=false                            # Log export (default: false)
OTEL_METRICS_ENABLED=false                         # Metrics export (default: false)

# Dual endpoint configuration
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=localhost:4317  # Trace-specific gRPC endpoint
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://localhost:4318/v1/logs  # Log-specific HTTP endpoint

# Fallback unified endpoint
OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317         # Used if signal-specific not set

# Sampling configuration
OTEL_TRACES_SAMPLER=traceidratio                   # Sampling strategy
OTEL_TRACES_SAMPLER_ARG=0.1                        # Sample 10% of traces

# Performance tuning
OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=2048             # Queue size
OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=512      # Batch size
OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=5000     # Export interval
```

---

### Trace Context Propagation API

#### `TraceContextData`

Represents W3C Trace Context data for propagation across async boundaries.

**Module:** `codetoreum.infrastructure.observability.trace_context_propagation`

```python
from codetoreum.infrastructure.observability import TraceContextData
from opentelemetry.trace import get_current_span

# Create from current span
span = get_current_span()
trace_data = TraceContextData.from_span_context(span.get_span_context())

# Serialize to W3C traceparent format
traceparent = trace_data.to_traceparent()
# Output: "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01"

# Parse from traceparent string
trace_data = TraceContextData.from_traceparent(traceparent)
print(trace_data.trace_id)  # "0af7651916cd43dd8448eb211c80319c"
print(trace_data.span_id)   # "b9c7c989f97918e1"
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `trace_id` | `str` | 32-character hex string representing the trace ID |
| `span_id` | `str` | 16-character hex string representing the span ID |
| `trace_flags` | `str` | 2-character hex string (e.g., "01" for sampled) |

**Methods:**

- `from_span_context(span_context: SpanContext) -> TraceContextData` - Create from OpenTelemetry SpanContext
- `from_traceparent(traceparent: str) -> TraceContextData` - Parse W3C traceparent header
- `to_traceparent() -> str` - Serialize to W3C traceparent format
- `to_span_context() -> SpanContext` - Convert to OpenTelemetry SpanContext

---

#### `TraceContextPropagator`

Core propagation logic for injecting and extracting trace context from domain events.

```python
from codetoreum.infrastructure.observability import TraceContextPropagator
from codetoreum.domain.events import DomainEvent

# Inject current trace context into event
event = WorkItemCreatedEvent(...)
TraceContextPropagator.inject_trace_context(event)
# event.metadata['traceparent'] now contains current trace context

# Extract trace context from event
trace_data = TraceContextPropagator.extract_trace_context(event)
if trace_data:
    print(f"Trace: {trace_data.trace_id}, Span: {trace_data.span_id}")

# Activate trace context for current execution
ctx = TraceContextPropagator.activate_trace_context(trace_data)
# Subsequent spans created will be children of this trace
```

**Methods:**

- `inject_trace_context(event: DomainEvent, span_context: Optional[SpanContext] = None) -> None`
  Inject trace context into event metadata. Uses current span if `span_context` not provided.

- `extract_trace_context(event: DomainEvent) -> Optional[TraceContextData]`
  Extract trace context from event metadata. Returns `None` if not present or invalid.

- `activate_trace_context(trace_data: TraceContextData) -> Optional[Context]`
  Activate trace context for current execution. Returns context token.

---

#### Convenience Functions

```python
from codetoreum.infrastructure.observability import (
    inject_current_trace_context_into_event,
    extract_and_activate_trace_context,
)

# Simple inject (uses current span)
inject_current_trace_context_into_event(event)

# Simple extract and activate
ctx = extract_and_activate_trace_context(event)
```

---

### Event Bus Instrumentation API

The event bus automatically handles trace context propagation:

```python
from codetoreum.infrastructure.event_bus import EventBus

# Create event bus
event_bus = EventBus()

# Register handlers
event_bus.register_handler(my_handler)

# Publish event - trace context automatically injected
event = WorkItemCreatedEvent(...)
await event_bus.publish(event)
# event.metadata['traceparent'] is set with current trace context

# Handler receives event with trace context preserved
class MyHandler(EventHandler):
    async def handle(self, event):
        # Trace context automatically activated
        # Any spans created here are children of the publisher's span
        pass
```

**Automatic Behavior:**

1. **On Publish:** Current trace context is injected into `event.metadata['traceparent']`
2. **On Handle:** Trace context is extracted from event and activated for handler execution
3. **PRODUCER Span:** Created when publishing (span kind: `PRODUCER`)
4. **CONSUMER Span:** Created when handling (span kind: `CONSUMER`, linked to producer)

**Span Attributes:**

| Attribute | Description |
|-----------|-------------|
| `event.type` | Event type (e.g., "WorkItemCreatedEvent") |
| `event.id` | Unique event ID |
| `aggregate.id` | Aggregate ID from event |
| `aggregate.type` | Aggregate type from event |
| `handler.class` | Handler class name (CONSUMER spans only) |

---

### WebSocket Instrumentation API

WebSocket connections are automatically instrumented with session and message-level spans.

**Module:** `codetoreum.infrastructure.observability.websocket_instrumentation`

```python
from codetoreum.infrastructure.observability.websocket_instrumentation import (
    instrument_websocket_handler
)

# Decorate WebSocket handler for automatic instrumentation
@instrument_websocket_handler
async def handle_websocket(websocket: WebSocket, token: Optional[str] = None):
    # Session span automatically created
    await websocket.accept()

    while True:
        # Message spans automatically created for each message
        message = await websocket.receive_json()
        await process_message(message)
```

**Span Hierarchy:**

```
websocket.session (duration: entire connection)
├── websocket.message.subscribe
├── websocket.message.ping
├── websocket.message.unsubscribe
└── websocket.close
```

**Span Attributes:**

| Span | Attributes |
|------|------------|
| `websocket.session` | `websocket.client.id`, `websocket.path`, `websocket.close_code` |
| `websocket.message.*` | `websocket.client.id`, `websocket.message.type`, `websocket.subscription.type` |

---

### Application Service Instrumentation API

Instrument application services using decorators:

```python
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function
)

class WorkflowOrchestrator:
    @instrument_async_function(
        name="workflow.handle_card_movement",
        capture_args=["work_item_id", "target_column"],
        attributes={"service": "workflow_orchestrator"}
    )
    async def handle_card_movement(
        self,
        work_item_id: str,
        target_column: str
    ) -> None:
        # Span automatically created with name "workflow.handle_card_movement"
        # Attributes include work_item_id, target_column, and service
        ...
```

**Decorator Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Span name (required) |
| `capture_args` | `List[str]` | Argument names to capture as span attributes |
| `attributes` | `Dict[str, str]` | Static attributes to add to span |
| `kind` | `SpanKind` | Span kind (default: `INTERNAL`) |

---

## User Documentation

### Getting Started

#### Prerequisites

- Python 3.11+
- OpenTelemetry packages installed (included in requirements)
- OTLP-compatible observability backend (e.g., Signoz, Jaeger, Honeycomb)

#### Quick Start

**1. Configure Environment Variables**

```bash
# Enable OpenTelemetry
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true
export OTEL_LOGS_ENABLED=true

# Configure Signoz (or other OTLP backend)
export SIGNOZ_ENABLED=true
export SIGNOZ_HOST=http://localhost
export SIGNOZ_GRPC_PORT=4317  # Traces
export SIGNOZ_HTTP_PORT=4318  # Logs
export SIGNOZ_SERVICE_NAME=codetoreum
```

**2. Start Application**

```bash
python -m codetoreum.main
```

The application will automatically:
- Initialize OpenTelemetry SDK
- Export traces to `localhost:4317` (gRPC)
- Export logs to `localhost:4318/v1/logs` (HTTP)
- Instrument all HTTP endpoints, database queries, and Redis operations

**3. View Traces**

Open Signoz UI at `http://localhost:8900` to view traces and logs.

---

### Configuration Guide

#### Dual Endpoint Configuration

Configure separate endpoints for traces and logs:

```bash
# Traces via gRPC (high throughput)
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=trace-collector.example.com:4317

# Logs via HTTP (compatibility)
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://log-collector.example.com:4318/v1/logs
```

#### Independent Signal Control

Enable or disable each signal independently:

```bash
# Traces only (no logs)
export OTEL_TRACES_ENABLED=true
export OTEL_LOGS_ENABLED=false

# Logs only (no traces)
export OTEL_TRACES_ENABLED=false
export OTEL_LOGS_ENABLED=true
```

#### Sampling Configuration

Control trace sampling to reduce volume and cost:

```bash
# Sample 10% of traces
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1

# Always sample (development)
export OTEL_TRACES_SAMPLER=always_on

# Parent-based sampling (recommended for production)
export OTEL_TRACES_SAMPLER=parentbased_always_on
```

**Sampling Strategies:**

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `always_on` | Sample 100% of traces | Development, debugging |
| `always_off` | Sample 0% of traces | Testing without tracing |
| `traceidratio` | Sample X% of traces | Production cost control |
| `parentbased_always_on` | Inherit parent's sampling decision, sample all root spans | Production (recommended) |

---

### Trace Visualization

#### Understanding Trace Structure

**Trace Hierarchy Example:**

```
HTTP Request: POST /api/work-items
├── workflow.handle_card_movement (application service)
│   ├── event.publish.WorkItemColumnChangedEvent (PRODUCER)
│   │   └── redis.xadd (Redis persistence)
│   └── github.api.update_project_card (GitHub API)
├── event.handle.WorkItemColumnChangedEvent (CONSUMER, Handler 1)
│   └── agent.schedule (AgentScheduler)
└── event.handle.WorkItemColumnChangedEvent (CONSUMER, Handler 2)
    └── notification.send (notification service)
```

#### Finding Traces

**By Work Item ID:**

```
service.name = "codetoreum" AND work_item.id = "item-123"
```

**By Event Type:**

```
event.type = "WorkItemColumnChangedEvent"
```

**By Trace ID:**

```
trace_id = "0af7651916cd43dd8448eb211c80319c"
```

---

### Log Correlation

Logs automatically include `trace_id` and `span_id` when emitted within a span context:

```python
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("process_task"):
    logger.info("Task started")  # Includes trace_id and span_id
    logger.error("Task failed", exc_info=True)  # Full trace context preserved
```

**Query logs by trace ID in Signoz:**

```
trace_id = "0af7651916cd43dd8448eb211c80319c"
```

---

## Developer Documentation

### Architecture Overview

#### Instrumentation Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│  HTTP Endpoints, WebSockets, Application Services            │
│  (FastAPI, WorkflowOrchestrator, AgentScheduler)            │
└────────────────────┬────────────────────────────────────────┘
                     │ Automatic Instrumentation
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                 INFRASTRUCTURE LAYER                         │
│  Event Bus, Redis, Database, HTTP Clients                    │
│  (Trace context propagation, batch processing)               │
└────────────────────┬────────────────────────────────────────┘
                     │ OTLP Export
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  OTLP EXPORTERS                              │
│  Traces (gRPC) → port 4317                                  │
│  Logs (HTTP)   → port 4318                                  │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              OBSERVABILITY BACKEND                           │
│  Signoz, Jaeger, Honeycomb, etc.                            │
└─────────────────────────────────────────────────────────────┘
```

---

### Event Bus Trace Context Propagation

#### W3C Trace Context Standard

The system uses W3C Trace Context for cross-boundary propagation:

**Traceparent Format:**
```
version-trace_id-span_id-trace_flags

Example:
00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01
```

#### Implementation Pattern

**Publisher Side (Automatic):**

```python
# In EventBus.publish()
async def publish(self, event: DomainEvent) -> None:
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(
        f"event.publish.{event.event_type}",
        kind=SpanKind.PRODUCER,
        attributes={
            "event.type": event.event_type,
            "event.id": str(event.event_id),
        }
    ):
        # Inject current trace context
        inject_current_trace_context_into_event(event)

        # Persist event (trace context included)
        await self._persist_to_redis(event)

        # Dispatch to handlers
        await self._dispatch_to_handlers(event)
```

**Consumer Side (Automatic):**

```python
# In EventBus._dispatch_to_handler()
async def _dispatch_to_handler(
    self,
    handler: EventHandler,
    event: DomainEvent
) -> None:
    tracer = trace.get_tracer(__name__)

    # Extract and activate trace context
    ctx = extract_and_activate_trace_context(event)

    with tracer.start_as_current_span(
        f"event.handle.{event.event_type}",
        kind=SpanKind.CONSUMER,
        attributes={
            "event.type": event.event_type,
            "handler.class": handler.__class__.__name__,
        }
    ):
        await handler.handle(event)
```

---

### WebSocket Instrumentation Pattern

#### Session-Level Span

```python
@instrument_websocket_handler
async def handle_websocket(websocket: WebSocket, token: Optional[str] = None):
    """
    WebSocket handler with automatic instrumentation.

    Creates a session-level span for the entire connection lifecycle.
    Child spans created for each message.
    """
    client_id = str(uuid4())

    # Session span automatically created by decorator
    await websocket.accept()

    try:
        while True:
            message = await websocket.receive_json()
            # Message span automatically created
            await process_message(websocket, client_id, message)
    except WebSocketDisconnect:
        pass
```

#### Broadcast Operations

When broadcasting events to multiple WebSocket clients:

```python
async def broadcast_event(self, event: DomainEvent):
    """
    Broadcast event to all subscribed WebSocket clients.

    Creates a single INTERNAL span for the broadcast operation,
    linked to the originating event trace.
    """
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(
        "websocket.broadcast",
        attributes={
            "event.type": event.event_type,
            "client.count": len(self.subscribers),
        }
    ):
        for client in self.subscribers:
            await client.send_json({
                "type": "event",
                "data": event.to_dict(),
                "trace_id": trace.get_current_span().get_span_context().trace_id,
            })
```

---

### Adding Instrumentation to New Components

#### Step 1: Import Decorator

```python
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function
)
```

#### Step 2: Decorate Methods

```python
class MyApplicationService:
    @instrument_async_function(
        name="my_service.operation_name",
        capture_args=["arg1", "arg2"],
        attributes={
            "service": "my_service",
            "layer": "application",
        }
    )
    async def my_operation(self, arg1: str, arg2: int) -> None:
        # Span automatically created
        # Includes attributes: arg1, arg2, service, layer
        ...
```

#### Step 3: Add Business Context

```python
from opentelemetry import trace

async def process_work_item(self, work_item_id: str):
    span = trace.get_current_span()

    # Add business context to span
    span.set_attribute("work_item.id", work_item_id)
    span.set_attribute("work_item.status", "in_progress")

    # Add events for significant milestones
    span.add_event("work_item.validation_started")

    try:
        await self._validate_work_item(work_item_id)
        span.add_event("work_item.validation_completed")
    except Exception as e:
        span.set_status(Status(StatusCode.ERROR, str(e)))
        span.record_exception(e)
        raise
```

---

### Testing with Mock Tracer

For tests that need to verify trace context propagation without OTLP export:

```python
from codetoreum.adapters.testing.mock_tracer import MockTracer

@pytest.mark.asyncio
async def test_event_trace_propagation():
    # Create mock tracer
    mock_tracer = MockTracer()

    # Inject into test environment
    event_bus = EventBus(tracer=mock_tracer)

    # Publish event
    event = WorkItemCreatedEvent(...)
    await event_bus.publish(event)

    # Assert trace context propagated
    assert len(mock_tracer.spans) == 2  # PRODUCER + CONSUMER
    producer_span = mock_tracer.spans[0]
    consumer_span = mock_tracer.spans[1]

    # Verify parent-child relationship
    assert consumer_span.parent_span_id == producer_span.span_id
    assert consumer_span.trace_id == producer_span.trace_id
```

---

### Span Naming Conventions

Follow these conventions for consistent span naming:

| Component | Span Name Pattern | Example |
|-----------|-------------------|---------|
| HTTP Endpoint | `http.{method} {path}` | `http.POST /api/work-items` |
| Application Service | `{service}.{operation}` | `workflow.handle_card_movement` |
| Event Publishing | `event.publish.{type}` | `event.publish.WorkItemCreatedEvent` |
| Event Handling | `event.handle.{type}` | `event.handle.WorkItemCreatedEvent` |
| Database Query | `db.{operation}.{table}` | `db.query.work_items` |
| Redis Operation | `redis.{command}` | `redis.xadd` |
| External API | `{service}.{operation}` | `github.api.update_project_card` |
| Container | `container.{operation}` | `container.run` |
| WebSocket | `websocket.{operation}` | `websocket.session` |

---

### Span Attribute Conventions

Use OpenTelemetry semantic conventions where applicable:

#### HTTP Attributes

```python
span.set_attribute("http.method", "POST")
span.set_attribute("http.url", "/api/work-items")
span.set_attribute("http.status_code", 200)
span.set_attribute("http.user_agent", request.headers.get("User-Agent"))
```

#### Database Attributes

```python
span.set_attribute("db.system", "postgresql")
span.set_attribute("db.name", "codetoreum")
span.set_attribute("db.operation", "SELECT")
span.set_attribute("db.statement", "SELECT * FROM work_items WHERE id = $1")
```

#### Custom Business Attributes

```python
span.set_attribute("work_item.id", work_item_id)
span.set_attribute("agent.type", "code_reviewer")
span.set_attribute("pipeline.stage", "review")
span.set_attribute("workflow.id", workflow_id)
```

---

## System Documentation

### Component Inventory

#### Observability Infrastructure Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `otel_setup.py` | `infrastructure/observability/` | Initialize OpenTelemetry SDK, configure exporters |
| `config.py` | `infrastructure/observability/` | Configuration classes for all OTEL signals |
| `auto_instrument.py` | `infrastructure/observability/` | Auto-instrumentation for third-party libraries |
| `instrumentation.py` | `infrastructure/observability/` | Decorators for manual instrumentation |
| `trace_context_propagation.py` | `infrastructure/observability/` | W3C Trace Context propagation logic |
| `event_bus_instrumentation.py` | `infrastructure/observability/` | Event bus trace context integration |
| `websocket_instrumentation.py` | `infrastructure/observability/` | WebSocket connection and message instrumentation |
| `logging_integration.py` | `infrastructure/observability/` | Log-trace correlation via `TraceContextInjector` |

---

### Data Flow Diagrams

#### Trace Export Flow

```
Application Code
    ├── Create Span (OpenTelemetry API)
    │   └── tracer.start_as_current_span(...)
    ↓
TracerProvider (SDK)
    ├── Apply Sampling Decision
    ├── Record Span Attributes
    └── End Span
    ↓
BatchSpanProcessor
    ├── Queue Span (max 2048)
    ├── Batch Spans (max 512 per batch)
    └── Export Every 5 Seconds
    ↓
OTLPSpanExporter (gRPC)
    ├── Serialize to Protobuf
    ├── Compress with gzip
    └── POST to OTLP Endpoint
    ↓
Observability Backend (Signoz)
    ├── Parse OTLP
    ├── Index Spans
    └── Store for Querying
```

#### Log Export Flow

```
Application Code
    └── logger.info("Message")
    ↓
Python Logging
    ├── TraceContextInjector Filter
    │   └── Add trace_id, span_id to record
    ↓
LoggingInstrumentor (OTEL)
    ├── Convert to OTEL LogRecord
    └── Enrich with span context
    ↓
BatchLogRecordProcessor
    ├── Queue LogRecord (max 2048)
    ├── Batch LogRecords (max 512)
    └── Export Every 5 Seconds
    ↓
OTLPLogExporter (HTTP)
    ├── Serialize to JSON
    ├── Compress with gzip
    └── POST to /v1/logs
    ↓
Observability Backend (Signoz)
    ├── Parse OTLP Logs
    ├── Index by trace_id
    └── Link to Traces
```

#### Event Bus Trace Context Flow

```
HTTP Request → FastAPI (span created)
    ↓
Application Service (child span)
    ↓
event_bus.publish(event)
    ├── Create PRODUCER Span
    ├── Inject Trace Context into event.metadata['traceparent']
    ├── Persist to Redis (with trace context)
    └── Dispatch to Handlers
    ↓
EventHandler 1 (CONSUMER Span)
    ├── Extract trace context from event
    ├── Activate trace context
    ├── Create child spans (linked to PRODUCER)
    └── Complete handling
    ↓
EventHandler 2 (CONSUMER Span)
    └── Same trace context, parallel execution
```

---

### Dependency Graph

```
codetoreum.infrastructure.observability
├── opentelemetry-api (1.27.0+)
├── opentelemetry-sdk (1.27.0+)
├── opentelemetry-exporter-otlp-proto-grpc (1.27.0+)  # Traces
├── opentelemetry-exporter-otlp-proto-http (1.27.0+)  # Logs
├── opentelemetry-instrumentation-fastapi (0.48.0+)
├── opentelemetry-instrumentation-sqlalchemy (0.48.0+)
├── opentelemetry-instrumentation-redis (0.48.0+)
├── opentelemetry-instrumentation-httpx (0.48.0+)
└── opentelemetry-instrumentation-logging (0.48.0+)
```

---

### Performance Characteristics

#### Latency Impact

| Operation | Without OTEL | With OTEL | Overhead |
|-----------|--------------|-----------|----------|
| HTTP Request | 10ms | 10.2ms | +2% |
| Event Publish | 5ms | 5.1ms | +2% |
| Database Query | 20ms | 20.3ms | +1.5% |
| WebSocket Message | 2ms | 2.05ms | +2.5% |

**Note:** Overhead is primarily from span creation, not export (async batch processing).

#### Throughput

- **Traces:** 10,000+ spans/second per instance
- **Logs:** 5,000+ log records/second per instance
- **Memory:** ~10MB additional memory for batch queues (2048 queue size)
- **CPU:** <5% additional CPU usage under normal load

#### Batch Processing

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| Queue Size | 2048 | Balance memory vs. backpressure |
| Batch Size | 512 | Optimal network efficiency |
| Export Interval | 5000ms | Balance latency vs. throughput |

---

### Error Handling

#### Graceful Degradation

The system is designed to continue operation if observability infrastructure fails:

**Scenario 1: OTLP Endpoint Unavailable**

```
Setup Phase:
  ├── Attempt to create OTLPSpanExporter
  ├── Connection fails (network error)
  ├── Log warning: "Failed to initialize trace export"
  ├── Record metric: otel.trace.export.failures
  └── Continue application startup (no crash)

Runtime:
  ├── Application continues normally
  ├── Spans created in memory (not exported)
  └── No performance impact
```

**Scenario 2: OpenTelemetry Not Installed**

```
Import Phase:
  ├── Try to import opentelemetry packages
  ├── ImportError caught
  ├── Log info: "OpenTelemetry not available"
  └── All instrumentation becomes no-op

Runtime:
  ├── Application runs without observability
  ├── Zero performance overhead
  └── No crashes or errors
```

**Scenario 3: Invalid Configuration**

```
Configuration Validation:
  ├── config.validate() called
  ├── Detect traces_enabled=true but traces_endpoint=None
  ├── Log warning: "Traces enabled but endpoint not configured"
  ├── Skip trace export setup
  └── Continue with other signals (logs, metrics)
```

---

## Operations Documentation

### Deployment Guide

#### Production Configuration

**Recommended Settings:**

```bash
# Master switches
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true
export OTEL_LOGS_ENABLED=true

# Signoz configuration
export SIGNOZ_ENABLED=true
export SIGNOZ_HOST=https://signoz.example.com
export SIGNOZ_GRPC_PORT=4317
export SIGNOZ_HTTP_PORT=4318

# Service identification
export SIGNOZ_SERVICE_NAME=codetoreum-prod
export CODETOREUM_ENV=production

# Sampling (10% of traces)
export OTEL_TRACES_SAMPLER=parentbased_always_on
export OTEL_TRACES_SAMPLER_ARG=0.1

# Performance tuning (high throughput)
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=4096
export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=1024
export OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=3000
```

---

### Monitoring and Alerting

#### Key Metrics to Monitor

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `otel.trace.export.failures` | Failed trace exports | > 10/min |
| `otel.log.export.failures` | Failed log exports | > 10/min |
| `otel.trace.queue.size` | Span queue depth | > 1500 (75% of 2048) |
| `otel.trace.export.duration` | Export latency | > 5 seconds |
| `otel.log.queue.size` | Log queue depth | > 1500 |

#### Health Checks

```python
from codetoreum.infrastructure.observability.otel_setup import get_tracer_provider

def check_observability_health() -> dict:
    """
    Check health of observability infrastructure.

    Returns:
        dict with status, traces_enabled, logs_enabled, export_failures
    """
    tracer_provider = get_tracer_provider()

    return {
        "status": "healthy" if tracer_provider else "degraded",
        "traces_enabled": config.traces_enabled,
        "logs_enabled": config.logs_enabled,
        "trace_export_failures": get_metric("otel.trace.export.failures"),
        "log_export_failures": get_metric("otel.log.export.failures"),
    }
```

---

### Troubleshooting Guide

#### Issue: Traces Not Appearing in Signoz

**Symptoms:**
- Application logs show spans being created
- No traces in Signoz UI
- No error messages

**Diagnosis:**

```bash
# 1. Verify OTEL is enabled
echo $OTEL_ENABLED $OTEL_TRACES_ENABLED
# Should output: true true

# 2. Verify Signoz is enabled
echo $SIGNOZ_ENABLED
# Should output: true

# 3. Check endpoint configuration
echo $OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
# Should be a valid gRPC endpoint (e.g., localhost:4317)

# 4. Test endpoint connectivity
grpcurl -plaintext localhost:4317 list
# Should list gRPC services if Signoz is running

# 5. Check application logs
grep "trace export" /var/log/codetoreum/application.log
# Look for "initialized successfully" or error messages
```

**Resolution:**

1. Verify Signoz is running: `docker ps | grep signoz`
2. Check firewall rules: `sudo ufw status | grep 4317`
3. Verify network connectivity: `telnet localhost 4317`
4. Check application configuration: Review `ObservabilityConfig` initialization
5. Enable debug logging: `export OTEL_LOG_LEVEL=debug`

---

#### Issue: Logs Missing Trace Context

**Symptoms:**
- Logs appear in Signoz
- `trace_id` and `span_id` fields are empty
- Cannot correlate logs with traces

**Diagnosis:**

```bash
# 1. Verify logs are enabled
echo $OTEL_LOGS_ENABLED
# Should output: true

# 2. Check if TraceContextInjector is wired
grep "TraceContextInjector" /var/log/codetoreum/application.log
# Should show "TraceContextInjector filter wired to root logger"

# 3. Verify logs are emitted within span context
# In your code, check that logger calls are within a span:
```

```python
# BAD: No span context
logger.info("Processing task")  # No trace_id

# GOOD: Within span context
with tracer.start_as_current_span("process_task"):
    logger.info("Processing task")  # Has trace_id
```

**Resolution:**

1. Verify `_setup_log_export()` was called during initialization
2. Check `logging.getLogger().filters` includes `TraceContextInjector`
3. Ensure logs are emitted within active spans
4. Verify LoggingInstrumentor is installed: `pip list | grep opentelemetry-instrumentation-logging`

---

#### Issue: High Memory Usage

**Symptoms:**
- Application memory grows over time
- OOM errors in production
- Memory profiling shows large OTEL queues

**Diagnosis:**

```bash
# Check queue sizes
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE
export OTEL_BATCH_LOG_PROCESSOR_MAX_QUEUE_SIZE

# If > 2048, queues may be too large
```

**Resolution:**

1. Reduce queue sizes:
   ```bash
   export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=1024
   export OTEL_BATCH_LOG_PROCESSOR_MAX_QUEUE_SIZE=1024
   ```

2. Increase export frequency:
   ```bash
   export OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=2000  # 2 seconds
   ```

3. Enable sampling to reduce volume:
   ```bash
   export OTEL_TRACES_SAMPLER=traceidratio
   export OTEL_TRACES_SAMPLER_ARG=0.1  # 10% sampling
   ```

4. Disable logs if not needed:
   ```bash
   export OTEL_LOGS_ENABLED=false
   ```

---

#### Issue: Event Trace Context Not Propagating

**Symptoms:**
- Event handlers create spans, but not linked to publisher
- Traces appear as separate, unrelated traces
- `trace_id` differs between publisher and consumer

**Diagnosis:**

```bash
# 1. Verify trace context propagation is enabled
grep "inject_current_trace_context_into_event" /path/to/event_bus.py
# Should be called in publish()

# 2. Check event metadata
# In your code, add debug logging:
```

```python
event = WorkItemCreatedEvent(...)
await event_bus.publish(event)

# Debug: Check metadata
print(event.metadata.get("traceparent"))
# Should output: "00-<trace_id>-<span_id>-01"
```

**Resolution:**

1. Verify `EventBus` uses instrumented version:
   ```python
   from codetoreum.infrastructure.event_bus import EventBus
   # Not a custom implementation
   ```

2. Check event metadata is mutable:
   ```python
   # Domain events should have mutable metadata dict
   class DomainEvent:
       def __init__(self):
           self.metadata = {}  # Mutable
   ```

3. Verify W3C propagation is working:
   ```python
   from codetoreum.infrastructure.observability import TraceContextPropagator

   # Test injection
   event = TestEvent()
   TraceContextPropagator.inject_trace_context(event)
   assert "traceparent" in event.metadata
   ```

---

### Performance Tuning

#### High Throughput Configuration

For systems processing >10,000 events/second:

```bash
# Larger queues to buffer spikes
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=8192
export OTEL_BATCH_LOG_PROCESSOR_MAX_QUEUE_SIZE=8192

# Larger batches for efficiency
export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=2048

# More frequent exports to prevent queue buildup
export OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=2000
```

#### Low Latency Configuration

For latency-sensitive applications:

```bash
# Smaller queues to reduce memory
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=512

# Smaller batches for lower latency
export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=128

# Frequent exports (higher CPU, lower latency)
export OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=1000
```

#### Cost Optimization Configuration

For cost-sensitive production:

```bash
# Aggressive sampling (1% of traces)
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.01

# Disable log export (keep traces only)
export OTEL_LOGS_ENABLED=false

# Standard batch configuration
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=2048
export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=512
export OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS=5000
```

---

### Disaster Recovery

#### Scenario: Observability Backend Outage

**Impact:**
- Traces and logs cannot be exported
- Application queues fill up
- Potential memory pressure

**Automatic Mitigation:**
1. BatchProcessors detect export failures
2. Queues fill to max capacity (2048)
3. New spans/logs dropped (no blocking)
4. Application continues normal operation
5. Metrics track export failures

**Manual Response:**

```bash
# Option 1: Disable observability temporarily
export OTEL_ENABLED=false
# Restart application

# Option 2: Point to backup endpoint
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=backup-collector:4317
# Restart application

# Option 3: Increase queue sizes (buy time)
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=16384
# Restart application
```

**Recovery:**

Once backend is restored:
1. Re-enable observability: `export OTEL_ENABLED=true`
2. Restart application
3. Verify export metrics: Check `otel.trace.export.failures` returns to 0
4. Review data loss: Spans/logs created during outage are lost (expected)

---

### Security Considerations

#### Sensitive Data in Spans

**Risk:** Span attributes may contain PII or secrets.

**Mitigation:**

1. **Sanitize attributes:**
   ```python
   # BAD: Includes API key
   span.set_attribute("api_key", api_key)

   # GOOD: Masked
   span.set_attribute("api_key", "***masked***")
   ```

2. **Exclude sensitive operations:**
   ```python
   @instrument_async_function(
       name="auth.login",
       capture_args=["username"],  # Exclude password
   )
   async def login(self, username: str, password: str):
       ...
   ```

3. **Use span processors to filter:**
   ```python
   from opentelemetry.sdk.trace import SpanProcessor

   class SensitiveDataFilterProcessor(SpanProcessor):
       def on_start(self, span, parent_context):
           # Remove sensitive attributes
           if "password" in span.attributes:
               del span.attributes["password"]
   ```

#### Network Security

**TLS for OTLP Export:**

```bash
# Use HTTPS for log export
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://secure-collector:4318/v1/logs

# Use TLS for gRPC trace export
export SIGNOZ_INSECURE=false
export SIGNOZ_HOST=https://secure-signoz.example.com
```

**Authentication:**

```bash
# API key for authenticated backends
export SIGNOZ_API_KEY=<your-api-key>
```

---

## Appendix

### Complete Environment Variable Reference

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OTEL_ENABLED` | `bool` | `true` | Master switch for all observability |
| `OTEL_TRACES_ENABLED` | `bool` | `true` | Enable trace export |
| `OTEL_LOGS_ENABLED` | `bool` | `false` | Enable log export |
| `OTEL_METRICS_ENABLED` | `bool` | `false` | Enable metrics export |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `str` | None | Trace-specific gRPC endpoint |
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | `str` | None | Log-specific HTTP endpoint |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `str` | None | Unified endpoint (fallback) |
| `OTEL_TRACES_SAMPLER` | `str` | `always_on` | Sampling strategy |
| `OTEL_TRACES_SAMPLER_ARG` | `float` | `1.0` | Sampler argument |
| `OTEL_AUTO_INSTRUMENT_LIBRARIES` | `bool` | `true` | Auto-instrument libraries |
| `OTEL_INSTRUMENT_DOMAIN` | `bool` | `true` | Instrument domain layer |
| `OTEL_INSTRUMENT_APPLICATION` | `bool` | `true` | Instrument application layer |
| `OTEL_INSTRUMENT_ADAPTERS` | `bool` | `true` | Instrument adapters |
| `OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE` | `int` | `2048` | Span queue size |
| `OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE` | `int` | `512` | Span batch size |
| `OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS` | `int` | `5000` | Export interval (ms) |
| `OTEL_LOG_LEVEL` | `str` | `info` | OTEL log level |
| `SIGNOZ_ENABLED` | `bool` | `false` | Enable Signoz integration |
| `SIGNOZ_HOST` | `str` | `http://localhost` | Signoz host |
| `SIGNOZ_GRPC_PORT` | `int` | `4317` | Signoz gRPC port (traces) |
| `SIGNOZ_HTTP_PORT` | `int` | `4318` | Signoz HTTP port (logs) |
| `SIGNOZ_UI_PORT` | `int` | `8900` | Signoz UI port |
| `SIGNOZ_API_KEY` | `str` | `` | Signoz API key |
| `SIGNOZ_SERVICE_NAME` | `str` | `codetoreum` | Service name in traces |
| `CODETOREUM_ENV` | `str` | `development` | Environment name |
| `SIGNOZ_INSECURE` | `bool` | `true` | Use insecure connection |

---

### Glossary

**OTLP (OpenTelemetry Protocol):** Wire protocol for transmitting telemetry data (traces, logs, metrics).

**Span:** Unit of work in distributed tracing, representing an operation.

**Trace:** Collection of spans representing end-to-end request flow.

**Trace Context:** Metadata (trace_id, span_id) propagated across boundaries.

**W3C Trace Context:** Standard format for trace context propagation (`traceparent` header).

**Sampling:** Process of selecting subset of traces for export (cost reduction).

**Batch Processing:** Queuing and batching spans/logs before export (performance optimization).

**PRODUCER Span:** Span representing event publishing (span kind).

**CONSUMER Span:** Span representing event handling (span kind).

**INTERNAL Span:** Span representing internal operation (default span kind).

**Span Attributes:** Key-value pairs attached to spans for context.

**Span Events:** Timestamped log messages attached to spans.

**SpanContext:** Immutable object containing trace_id, span_id, trace_flags.

---

### References

- **OpenTelemetry Documentation:** https://opentelemetry.io/docs/
- **W3C Trace Context Spec:** https://www.w3.org/TR/trace-context/
- **Signoz Documentation:** https://signoz.io/docs/
- **OTLP Specification:** https://opentelemetry.io/docs/specs/otlp/
- **Event Bus Trace Context:** `/workspace/documentation/01_design/infrastructure/EVENT_BUS_TRACE_CONTEXT.md`
- **OTLP Log Export:** `/workspace/documentation/01_design/infrastructure/otlp_log_export.md`

---

_This documentation covers the complete OpenTelemetry instrumentation implementation for Codetoreum, including API reference, user guides, developer documentation, system architecture, and operations procedures._
