# OpenTelemetry Quick Reference Guide

**Project:** Codetoreum
**Audience:** Developers
**Last Updated:** February 2026

---

## Quick Setup

### 1. Enable OpenTelemetry (5 seconds)

```bash
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true
export OTEL_LOGS_ENABLED=true
export SIGNOZ_ENABLED=true
```

### 2. Start Signoz (Docker)

```bash
docker run -d --name signoz \
  -p 4317:4317 -p 4318:4318 -p 8900:8900 \
  signoz/signoz:latest
```

### 3. Run Application

```bash
python -m codetoreum.main
```

### 4. View Traces

Open http://localhost:8900

---

## Common Patterns

### Pattern 1: Add Span to Function

```python
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function
)

@instrument_async_function(
    name="my_service.my_operation",
    capture_args=["work_item_id"],
)
async def process_work_item(self, work_item_id: str):
    # Span automatically created
    ...
```

### Pattern 2: Manual Span Creation

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def my_function():
    with tracer.start_as_current_span("my_function") as span:
        span.set_attribute("key", "value")
        # Your code here
```

### Pattern 3: Add Business Context to Span

```python
from opentelemetry import trace

span = trace.get_current_span()
span.set_attribute("work_item.id", work_item_id)
span.set_attribute("agent.type", "code_reviewer")
```

### Pattern 4: Log with Trace Context

```python
import logging

logger = logging.getLogger(__name__)

# Just use standard logging - trace context added automatically
logger.info("Processing work item")  # Includes trace_id, span_id
```

### Pattern 5: Handle Errors in Spans

```python
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

span = trace.get_current_span()

try:
    await risky_operation()
except Exception as e:
    span.set_status(Status(StatusCode.ERROR, str(e)))
    span.record_exception(e)
    logger.error("Operation failed", exc_info=True)
    raise
```

### Pattern 6: Publish Event (Automatic Trace Context)

```python
from codetoreum.infrastructure.event_bus import EventBus

# Trace context automatically injected
event = WorkItemCreatedEvent(...)
await event_bus.publish(event)
# event.metadata['traceparent'] is set
```

### Pattern 7: Handle Event (Automatic Trace Context)

```python
from codetoreum.infrastructure.event_bus import EventHandler

class MyHandler(EventHandler):
    async def handle(self, event):
        # Trace context automatically activated
        # Spans created here are children of publisher's span
        await process_event(event)
```

---

## Configuration Cheat Sheet

### Development (Everything Enabled)

```bash
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true
export OTEL_LOGS_ENABLED=true
export SIGNOZ_ENABLED=true
export SIGNOZ_HOST=http://localhost
export OTEL_TRACES_SAMPLER=always_on  # 100% sampling
```

### Production (Cost Optimized)

```bash
export OTEL_ENABLED=true
export OTEL_TRACES_ENABLED=true
export OTEL_LOGS_ENABLED=false  # Logs optional
export SIGNOZ_ENABLED=true
export SIGNOZ_HOST=https://signoz.example.com
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1  # 10% sampling
export SIGNOZ_INSECURE=false  # Use TLS
```

### Testing (Disabled)

```bash
export OTEL_ENABLED=false
# All observability disabled, zero overhead
```

---

## Span Naming Quick Reference

| Component | Pattern | Example |
|-----------|---------|---------|
| HTTP | `http.{method} {path}` | `http.POST /api/work-items` |
| Application | `{service}.{operation}` | `workflow.process_stage` |
| Event Publish | `event.publish.{type}` | `event.publish.WorkItemCreated` |
| Event Handle | `event.handle.{type}` | `event.handle.WorkItemCreated` |
| Database | `db.{operation}.{table}` | `db.query.work_items` |
| External API | `{service}.{operation}` | `github.update_card` |

---

## Finding Traces in Signoz

### By Work Item ID

```
service.name = "codetoreum" AND work_item.id = "item-123"
```

### By Event Type

```
event.type = "WorkItemCreatedEvent"
```

### By User Action

```
http.url LIKE "/api/work-items%"
```

### By Error Status

```
status.code = "ERROR"
```

---

## Common Attributes

### Business Context

```python
span.set_attribute("work_item.id", work_item_id)
span.set_attribute("agent.id", agent_id)
span.set_attribute("agent.type", "code_reviewer")
span.set_attribute("pipeline.stage", "review")
span.set_attribute("workflow.id", workflow_id)
```

### HTTP Context

```python
span.set_attribute("http.method", "POST")
span.set_attribute("http.url", "/api/work-items")
span.set_attribute("http.status_code", 200)
```

### Database Context

```python
span.set_attribute("db.system", "postgresql")
span.set_attribute("db.operation", "SELECT")
span.set_attribute("db.statement", query)
```

---

## Troubleshooting One-Liners

### Check if OpenTelemetry is enabled

```bash
echo $OTEL_ENABLED $OTEL_TRACES_ENABLED
# Should output: true true
```

### Test Signoz connectivity

```bash
curl -v http://localhost:4318/v1/logs
# Should return HTTP 405 (Method Not Allowed) - endpoint is working
```

### View trace export errors in logs

```bash
grep "trace export" /var/log/codetoreum/application.log | tail -20
```

### Check current span in code

```python
from opentelemetry import trace
span = trace.get_current_span()
print(f"Trace: {span.get_span_context().trace_id:032x}")
```

---

## Performance Tips

### 1. Use Sampling in Production

```bash
# Sample 10% of traces
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1
```

### 2. Disable Logs if Not Needed

```bash
export OTEL_LOGS_ENABLED=false  # Keep traces only
```

### 3. Tune Batch Sizes for Your Load

```bash
# High throughput (>10k events/sec)
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=8192
export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=2048

# Low latency (<1k events/sec)
export OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE=512
export OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE=128
```

---

## Testing

### Unit Test with Mock Tracer

```python
from codetoreum.adapters.testing.mock_tracer import MockTracer

@pytest.mark.asyncio
async def test_operation():
    mock_tracer = MockTracer()
    service = MyService(tracer=mock_tracer)

    await service.operation()

    # Assert spans created
    assert len(mock_tracer.spans) == 2
    assert mock_tracer.spans[0].name == "operation"
```

### Integration Test (Real OTLP)

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_trace_export():
    # Assumes Signoz running on localhost:4317
    config = ObservabilityConfig.from_env()
    assert config.traces_enabled

    await trigger_operation()

    # Query Signoz API to verify trace was exported
    traces = await query_signoz(operation_name="my_operation")
    assert len(traces) > 0
```

---

## Don't Forget

✅ **Always log errors with `exc_info=True`** for full stack traces

```python
logger.error("Operation failed", exc_info=True)
```

✅ **Set span status on errors**

```python
span.set_status(Status(StatusCode.ERROR, str(e)))
```

✅ **Record exceptions in spans**

```python
span.record_exception(e)
```

✅ **Use semantic attribute names** (see OpenTelemetry conventions)

✅ **Test trace propagation** through event bus and WebSockets

❌ **Never include secrets in span attributes**

```python
# BAD
span.set_attribute("api_key", api_key)

# GOOD
span.set_attribute("api_key", "***masked***")
```

---

## Getting Help

- **Full Documentation:** `/workspace/documentation/02_technical_writer/OPENTELEMETRY_INSTRUMENTATION_COMPLETE.md`
- **Event Bus Trace Context:** `/workspace/documentation/01_design/infrastructure/EVENT_BUS_TRACE_CONTEXT.md`
- **OTLP Log Export:** `/workspace/documentation/01_design/infrastructure/otlp_log_export.md`
- **OpenTelemetry Docs:** https://opentelemetry.io/docs/
- **Signoz Docs:** https://signoz.io/docs/

---

_Quick reference for OpenTelemetry instrumentation in Codetoreum. For complete documentation, see OPENTELEMETRY_INSTRUMENTATION_COMPLETE.md._
