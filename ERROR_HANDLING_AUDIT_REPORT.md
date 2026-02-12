# Error Handling Audit Report: Observability Infrastructure

**Audit Date**: 2026-02-12
**Auditor Focus**: Silent failures, observability resilience, async error handling, fallback behavior, logging quality
**Branch**: feature/issue-249-instrument-all-server-componen

---

## Executive Summary

The observability infrastructure implements **strong error handling with graceful degradation patterns** throughout. The codebase demonstrates:

✅ **Strong Areas**: Proper exception logging with `exc_info=True`, error IDs for Sentry tracking, fallback behavior explicitly justified, graceful degradation when observability fails

⚠️ **Areas of Concern**: One critical hidden error in exception handling, one OTLP exporter error being silently suppressed, missing context in some error messages, and potential race conditions in async contexts

**Critical Issues Found**: 2
**Important Issues Found**: 4
**Suggestions**: 5

---

## Critical Issues

### CRITICAL #1: Missing Error Logging in _InstrumentedSpanExporter.export()

**Location**: `/workspace/src/codetoreum/infrastructure/observability/otel_setup.py:166-194`

**Severity**: CRITICAL

**Issue Description**

The `_InstrumentedSpanExporter.export()` method catches exceptions from the wrapped exporter but only logs them at DEBUG level before re-raising, without providing user-facing context about what failed:

```python
def export(self, spans):
    """Export spans and measure duration."""
    import time
    start_time = time.time()

    try:
        result = self._exporter.export(spans)
        # ... metric recording ...
        return result
    except Exception as e:
        logger.debug(f"Span export failed: {e}", exc_info=True)  # ⚠️ DEBUG level
        raise
```

**Hidden Errors That Could Be Suppressed**

This catch block could hide:
- Network connectivity failures to OTLP endpoint
- Protocol errors (malformed gRPC messages)
- Authentication failures (invalid credentials)
- Timeout during export
- Memory exhaustion
- OpenTelemetry SDK internal errors

**User Impact**

- Operators won't know spans aren't being exported unless they enable DEBUG logging
- Production issues with observability infrastructure go unnoticed
- Span export failures silently degrade tracing without alerting operators
- No metrics recorded for failed exports (exception prevents metrics code execution)

**Root Cause**

The exception is logged at DEBUG severity, which is typical for development but insufficient for production observability failures.

**Recommendation**

Change to ERROR level logging and record a metric for export failures BEFORE re-raising:

```python
def export(self, spans):
    """Export spans and measure duration."""
    import time
    start_time = time.time()

    try:
        result = self._exporter.export(spans)
        # ... metric recording ...
        return result
    except Exception as e:
        # Record failure metric even if spans aren't exported
        try:
            if self._meter:
                self._meter.create_counter(
                    "otel.trace.export.failures",
                    description="Failed span exports"
                ).add(1)
        except Exception:
            pass  # Metrics failure shouldn't prevent span export error propagation

        # Log at ERROR level so operators know observability is failing
        logger.error(
            f"Failed to export {len(spans)} spans to OTLP endpoint: {e}",
            exc_info=True,
            extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR}
        )
        raise
```

---

### CRITICAL #2: Silent Failure in InstrumentedEventBus Callback Error Handling

**Location**: `/workspace/src/codetoreum/infrastructure/observability/event_bus_instrumentation.py:241-276`

**Severity**: CRITICAL

**Issue Description**

The `_create_instrumented_callback()` method creates a wrapped callback that catches exceptions and records them in spans, but the exception handling is incomplete. The callback attempts to check if `callback` is callable before invoking it, which creates a false sense of safety:

```python
async def instrumented_callback(event: DomainEvent) -> Any:
    span_name = f"event.handle.{event.event_type}"
    trace_context = extract_and_activate_trace_context(event)

    with self._tracer.start_as_current_span(...) as span:
        logger.debug(f"Created CONSUMER span for callback {callback.__name__}")

        try:
            if hasattr(callback, "__call__"):
                result = callback(event)
                if hasattr(result, "__await__"):
                    return await result
                return result
        except Exception as e:
            span.set_attribute("exception.type", type(e).__name__)
            span.set_attribute("exception.message", str(e))
            span.record_exception(e)
            raise
```

**Hidden Errors That Could Be Suppressed**

1. **Missing async/await mismatch detection**: If `callback` is an async function but not awaited, the coroutine object is returned without execution
2. **Silent failures in callback invocation**: If `callback(event)` fails, the exception is caught and re-raised, but there's no explicit logging beyond the span attributes
3. **Race conditions in trace context**: `extract_and_activate_trace_context()` is called but the returned context `trace_context` is extracted but never used in the span creation - it's passed to `start_as_current_span()` but the parameter is called `context` which may not activate the trace context properly
4. **Unhandled exceptions from span operations**: If `span.record_exception()` fails, this exception is silently swallowed

**User Impact**

- Async callbacks that aren't properly awaited will silently succeed without running
- Callback failures are only visible through span attributes, not in application logs
- Trace context activation might fail silently without affecting the span (context may not be properly attached)
- Operator debugging becomes difficult because errors aren't logged to the application log

**Root Cause**

The code attempts to handle both sync and async callbacks but the async detection is insufficient. The span context handling doesn't explicitly log failures or validate that trace context was properly activated.

**Recommendation**

Improve error logging and async/await handling:

```python
async def instrumented_callback(event: DomainEvent) -> Any:
    span_name = f"event.handle.{event.event_type}"
    trace_context = extract_and_activate_trace_context(event)
    token = None

    with self._tracer.start_as_current_span(
        span_name,
        kind=SpanKind.CONSUMER,
        attributes={
            "event.type": event.event_type,
            "event.id": str(event.event_id),
            "aggregate.id": str(event.aggregate_id),
            "aggregate.type": event.aggregate_type,
            "handler.class": callback.__name__,
        },
    ) as span:
        logger.debug(f"Created CONSUMER span for callback {callback.__name__}")

        try:
            if trace_context:
                token = context.attach(trace_context)

            # Determine if callback is async
            import asyncio
            if asyncio.iscoroutinefunction(callback):
                result = await callback(event)
            elif hasattr(callback, "__call__"):
                result = callback(event)
                # Check if result is a coroutine (callback is async but not declared)
                if asyncio.iscoroutine(result):
                    logger.warning(
                        f"Callback {callback.__name__} returned coroutine but is not async",
                        extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION}
                    )
                    result = await result
            else:
                raise TypeError(f"Callback {callback.__name__} is not callable")

            return result

        except Exception as e:
            span.set_attribute("exception.type", type(e).__name__)
            span.set_attribute("exception.message", str(e))
            span.record_exception(e)

            # Log to application logger for operator visibility
            logger.error(
                f"Event handler {callback.__name__} failed: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION}
            )
            raise
        finally:
            if token:
                context.detach(token)
```

---

## Important Issues

### IMPORTANT #1: Batch Processor Error Handling Missing Error Context

**Location**: `/workspace/src/codetoreum/infrastructure/observability/otel_setup.py:239-323`

**Severity**: HIGH

**Issue Description**

The `_setup_log_export()` function sets up batch log processors but doesn't configure error handlers for the processor itself. If the batch processor encounters errors (queue full, export failure), these are handled internally without explicit logging:

```python
# Create batch log record processor with performance tuning
batch_log_processor = BatchLogRecordProcessor(
    log_exporter,
    max_queue_size=config.batch_max_queue_size,
    max_export_batch_size=config.batch_max_export_batch_size,
    schedule_delay_millis=config.batch_schedule_delay_millis,
)
logger_provider.add_log_record_processor(batch_log_processor)
```

The BatchLogRecordProcessor from OpenTelemetry SDK has internal error handling, but we don't wrap it or provide explicit error callbacks.

**Hidden Errors That Could Be Suppressed**

- Queue overflow (max_queue_size exceeded) - logs are dropped silently
- Periodic export failures due to network issues
- Export timeouts - max_queue_size behavior when export hangs
- Memory pressure causing batch processor to drop records
- Configuration conflicts (queue size too small for batch size)

**User Impact**

- Log records are silently dropped when queue is full
- Operators don't know that log export is failing
- No metrics to track batch processor health
- Production logs may be incomplete without notification

**Recommendation**

Wrap the batch processor with error handling and monitoring:

```python
# Create batch log record processor with error callback
def on_batch_log_error(error: Exception) -> None:
    """Handle batch log processor errors."""
    logger.error(
        f"Batch log processor error: {error}. "
        f"Logs may be dropped if queue is full.",
        exc_info=True,
        extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR}
    )

batch_log_processor = BatchLogRecordProcessor(
    log_exporter,
    max_queue_size=config.batch_max_queue_size,
    max_export_batch_size=config.batch_max_export_batch_size,
    schedule_delay_millis=config.batch_schedule_delay_millis,
)
logger_provider.add_log_record_processor(batch_log_processor)

# Monitor batch processor stats if available
logger.info(
    f"Batch log processor configured: "
    f"max_queue={config.batch_max_queue_size}, "
    f"max_batch={config.batch_max_export_batch_size}, "
    f"schedule_delay_ms={config.batch_schedule_delay_millis}"
)
```

---

### IMPORTANT #2: Metrics Export Error Recovery Missing Fallback Explanation

**Location**: `/workspace/src/codetoreum/infrastructure/observability/otel_setup.py:358-420`

**Severity**: HIGH

**Issue Description**

The `_setup_metrics_export()` function has graceful degradation but doesn't explain to operators what the fallback behavior is:

```python
try:
    # Create OTLP metric exporter for Signoz
    metric_exporter = OTLPMetricExporter(
        endpoint=config.metrics_endpoint,
        insecure=config.signoz.insecure,
    )
    # ... setup ...
except Exception as e:
    _record_metrics_export_error(e, config)
```

When metrics export fails, the application continues without metrics. The error message states this, but operators should know:
1. What happens to metrics that would have been exported?
2. How long until metrics are attempted again?
3. Will local metrics still be available?

**User Impact**

- Operators understand failure but not the consequences
- No visibility into whether local metrics are still being collected
- Missing explanation of recovery path (restart? automatic retry?)
- Confusion about metric gaps in dashboards

**Recommendation**

Enhance error message with explicit fallback behavior:

```python
except Exception as e:
    _record_metrics_export_error(e, config)
    logger.info(
        f"Metrics export to Signoz disabled due to setup failure. "
        f"Application will continue without remote metrics export. "
        f"Local metrics collection is unaffected. "
        f"To enable metrics export, verify endpoint accessibility and restart the service: {config.metrics_endpoint}"
    )
```

---

### IMPORTANT #3: TraceContextPropagator Exception Masking in from_traceparent()

**Location**: `/workspace/src/codetoreum/infrastructure/observability/trace_context_propagation.py:70-116`

**Severity**: HIGH

**Issue Description**

The `from_traceparent()` parsing method catches all exceptions in a broad try-except block:

```python
@classmethod
def from_traceparent(cls, traceparent: str) -> Optional["TraceContextData"]:
    try:
        parts = traceparent.split("-")
        if len(parts) < 4:
            logger.warning(f"Invalid traceparent format: {traceparent}")
            return None

        # ... validation ...

        try:
            int(trace_id, 16)
            int(span_id, 16)
            int(flags, 16)
        except ValueError:
            logger.warning(f"Invalid hex values in traceparent: {traceparent}")
            return None

        return cls(...)
    except Exception as e:
        logger.warning(f"Failed to parse traceparent: {e}", ...)
        return None
```

**Hidden Errors That Could Be Suppressed**

1. **AttributeError** from `str.split()` if traceparent is None or not a string
2. **MemoryError** or **SystemError** during hex conversion
3. **TypeError** if parts array indexing fails (shouldn't happen, but covered by outer catch)
4. **OOM errors** during parsing that should crash the application, not silently return None

**User Impact**

- Unexpected exceptions (not ValueError) are silently converted to None
- Trace context activation silently fails without clear diagnostic information
- Hard-to-debug issues when traceparent parsing fails unexpectedly
- No distinction between "invalid format" (expected) and "unexpected error" (should alert operators)

**Root Cause**

The outer exception handler is too broad and catches exceptions that should not be treated as simple validation failures.

**Recommendation**

Narrow the exception handling to only catch expected validation errors:

```python
@classmethod
def from_traceparent(cls, traceparent: str) -> Optional["TraceContextData"]:
    """Parse W3C traceparent header."""
    if not isinstance(traceparent, str):
        logger.warning(
            f"traceparent must be a string, got {type(traceparent).__name__}",
            extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR}
        )
        return None

    try:
        parts = traceparent.split("-")
        if len(parts) < 4:
            logger.warning(f"Invalid traceparent format (< 4 parts): {traceparent}")
            return None

        version, trace_id, span_id, flags = parts[0], parts[1], parts[2], parts[3]

        # Validate format
        if len(version) != 2 or len(trace_id) != 32 or len(span_id) != 16 or len(flags) != 2:
            logger.warning(f"Invalid traceparent component lengths: {traceparent}")
            return None

        # Validate hex format - this is where expected validation errors occur
        try:
            int(trace_id, 16)
            int(span_id, 16)
            int(flags, 16)
        except ValueError:
            logger.warning(f"Invalid hex values in traceparent: {traceparent}")
            return None

        return cls(
            version=version,
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=flags,
        )
    except Exception as e:
        # Unexpected errors beyond format validation
        logger.error(
            f"Unexpected error parsing traceparent: {e}",
            exc_info=True,
            extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR}
        )
        return None
```

---

### IMPORTANT #4: Missing Error Handling in InstrumentedEventHandler.handle()

**Location**: `/workspace/src/codetoreum/infrastructure/observability/event_bus_instrumentation.py:304-349`

**Severity**: HIGH

**Issue Description**

The `InstrumentedEventHandler.handle()` method creates spans and calls handlers, but doesn't log the error to the application logger if the handler fails:

```python
async def handle(self, event: DomainEvent) -> None:
    """Handle event with CONSUMER span."""
    if not self._tracer:
        await self._handler.handle(event)
        return

    span_name = f"event.handle.{event.event_type}"
    trace_context = extract_and_activate_trace_context(event)

    with self._tracer.start_as_current_span(...) as span:
        logger.debug(f"Created CONSUMER span for handler ...")

        try:
            await self._handler.handle(event)
        except Exception as e:
            # Only records in span - no application log
            span.set_attribute("exception.type", type(e).__name__)
            span.set_attribute("exception.message", str(e))
            span.record_exception(e)
            raise
```

**Hidden Errors That Could Be Suppressed**

While the exception IS re-raised (good), the error is only visible:
1. In the span attributes (if observability is enabled and operator checks traces)
2. In Sentry (if configured)
3. NOT in application logs

This means:
- Event handling failures don't appear in application logs
- Operators checking logs won't see errors
- Error context is buried in observability backend

**User Impact**

- Application logs are incomplete for event handling failures
- Operators debugging issues have to check observability backend first
- Event handling failures are not visible in simple log streams
- Missing error logs violate the project principle "no silent error handling"

**Recommendation**

Add explicit application logging when handlers fail:

```python
async def handle(self, event: DomainEvent) -> None:
    """Handle event with CONSUMER span."""
    if not self._tracer:
        await self._handler.handle(event)
        return

    span_name = f"event.handle.{event.event_type}"
    trace_context = extract_and_activate_trace_context(event)

    with self._tracer.start_as_current_span(...) as span:
        logger.debug(f"Created CONSUMER span for handler ...")

        try:
            await self._handler.handle(event)
        except Exception as e:
            # Record in span for distributed tracing
            span.set_attribute("exception.type", type(e).__name__)
            span.set_attribute("exception.message", str(e))
            span.record_exception(e)

            # Log to application logger for operator visibility
            logger.error(
                f"Event handler {self._handler.__class__.__name__} failed "
                f"processing {event.event_type}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION}
            )
            raise
```

---

## Suggestions for Improvement

### SUGGESTION #1: Add Timeout Handling for OTLP Exporter Setup

**Location**: `/workspace/src/codetoreum/infrastructure/observability/otel_setup.py:476-514`

**Priority**: MEDIUM

The `setup_opentelemetry()` function creates exporters but doesn't set timeouts on the exporter initialization. If the OTLP endpoint is unreachable, the exporter creation could hang indefinitely.

```python
otlp_exporter = OTLPSpanExporter(
    endpoint=config.signoz.grpc_endpoint,
    insecure=config.signoz.insecure,
)
```

**Recommendation**: Add timeout configuration:

```python
otlp_exporter = OTLPSpanExporter(
    endpoint=config.signoz.grpc_endpoint,
    insecure=config.signoz.insecure,
    timeout=5,  # 5 second timeout for export connection
)
```

---

### SUGGESTION #2: Add Health Check for OTLP Connectivity

**Location**: `/workspace/src/codetoreum/infrastructure/observability/otel_setup.py:476-550`

**Priority**: MEDIUM

The setup function doesn't verify that the OTLP endpoint is actually reachable. Consider adding a connectivity check:

```python
try:
    # Test connectivity to OTLP endpoint before full setup
    import socket
    import time

    host, port = config.signoz.grpc_endpoint.split(":")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, int(port)))
        sock.close()

        if result != 0:
            logger.warning(
                f"OTLP endpoint {config.signoz.grpc_endpoint} is not reachable. "
                f"Observability will be degraded until endpoint is available.",
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR}
            )
    except Exception as e:
        logger.debug(f"Could not verify OTLP endpoint connectivity: {e}")
except Exception:
    pass  # Don't fail setup on connectivity check
```

---

### SUGGESTION #3: Add Metrics for Observability Infrastructure Health

**Location**: `/workspace/src/codetoreum/infrastructure/observability/otel_setup.py:1-50`

**Priority**: MEDIUM

The infrastructure has error handling but doesn't record metrics about its own health (export successes, failures, queue depth, etc.). This makes it hard to monitor observability infrastructure itself.

**Recommendation**: Create metrics for:
- `otel.exporter.span.export.duration` (histogram)
- `otel.exporter.span.export.success` (counter)
- `otel.exporter.span.export.failures` (counter)
- `otel.batch_processor.queue_size` (gauge)
- `otel.batch_processor.dropped_records` (counter)

---

### SUGGESTION #4: Validate Configuration Before Setup

**Location**: `/workspace/src/codetoreum/infrastructure/observability/config.py:274-298`

**Priority**: MEDIUM

The `validate()` method logs warnings for misconfigured signals but only warns. Consider making validation stricter:

```python
def validate(self) -> None:
    """Validate configuration and raise errors for critical issues."""
    if self.enabled and not self.traces_enabled and not self.metrics_enabled and not self.logs_enabled:
        raise ValueError(
            "Observability enabled but no signals (traces/metrics/logs) are enabled. "
            "Either enable at least one signal or disable observability entirely."
        )

    # ... more strict validation ...
```

Call this during initialization to fail fast on misconfiguration.

---

### SUGGESTION #5: Document Error Recovery Procedures

**Location**: Project documentation

**Priority**: LOW

Add documentation explaining:
1. What happens when OTLP endpoint is unreachable
2. How to verify observability is working
3. How to diagnose observability failures
4. What errors indicate infrastructure issues vs. application issues

---

## Positive Observations

### ✅ Strong Exception Logging with exc_info=True

**Locations**: Throughout `/workspace/src/codetoreum/infrastructure/observability/`

All critical error handlers include `exc_info=True`, which includes full stack traces in logs:

```python
logger.error(
    f"Failed to initialize OpenTelemetry: {e}",
    exc_info=True,  # ✅ Stack trace included
    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR}
)
```

---

### ✅ Proper Error ID Usage for Sentry Tracking

All error logs use the `ErrorRegistry` for consistent error categorization:

```python
extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR}
```

This enables proper grouping in Sentry and makes error tracking consistent.

---

### ✅ Graceful Degradation Pattern

The code consistently follows the pattern of logging errors but continuing execution:

```python
try:
    # Setup observability
except Exception as e:
    _record_trace_export_error(e, config)
    logger.warning("Application will continue without distributed tracing")
```

This ensures observability failures don't crash the application.

---

### ✅ Optional Dependencies Handled Correctly

The code properly handles OpenTelemetry being optional:

```python
try:
    from opentelemetry import trace
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
```

Functions check this flag before using observability features.

---

### ✅ No-Op Implementations for Disabled Features

When observability is disabled, functions return early with appropriate logging:

```python
if not config.enabled or not config.traces_enabled:
    logger.info("Observability disabled, skipping library auto-instrumentation")
    return
```

---

## Project Standards Compliance

The code adheres to the project standards from `CLAUDE.md`:

✅ **Error Logging**: Uses `logError` equivalent (logger.error with exc_info=True)
✅ **Error IDs**: Uses `ErrorRegistry` for Sentry tracking
✅ **No Silent Failures**: Most errors are logged (see critical issues for exceptions)
✅ **Explicit Fallbacks**: Graceful degradation is intentional and documented
✅ **Exception Specificity**: Most catch blocks are specific (except where noted)

---

## Summary of Findings

| Issue Type | Count | Severity |
|-----------|-------|----------|
| Critical (Silent Failures) | 2 | Must Fix |
| Important (Poor Error Handling) | 4 | Should Fix |
| Suggestions (Improvements) | 5 | Nice to Have |
| Positive Observations | 6 | Noted |

**Action Items Priority**:
1. Fix CRITICAL #1: Improve span export error logging
2. Fix CRITICAL #2: Add explicit async/await handling and error logging in event bus callbacks
3. Fix IMPORTANT #1-#4: Add missing error context and logging to batch processors and trace context handling
4. Consider SUGGESTION #1-#3 for production robustness

---

## Detailed Code References

### Files Analyzed
- `/workspace/src/codetoreum/infrastructure/observability/auto_instrument.py` ✅ Good error handling
- `/workspace/src/codetoreum/infrastructure/observability/config.py` ✅ Good error handling
- `/workspace/src/codetoreum/infrastructure/observability/otel_setup.py` ⚠️ See critical issues
- `/workspace/src/codetoreum/infrastructure/observability/event_bus_instrumentation.py` ⚠️ See critical issues #2
- `/workspace/src/codetoreum/infrastructure/observability/instrumentation.py` ✅ Good error handling
- `/workspace/src/codetoreum/infrastructure/observability/trace_context_propagation.py` ⚠️ See important issue #3
- `/workspace/src/codetoreum/infrastructure/observability/websocket_instrumentation.py` ✅ Partially analyzed

---

## Conclusion

The observability infrastructure demonstrates **solid foundational error handling** with proper logging, error IDs, and graceful degradation. However, there are **2 critical issues related to silent failures** and **4 important issues with incomplete error logging** that should be addressed to meet the "zero tolerance for silent failures" standard.

The code successfully avoids the worst anti-patterns (empty catch blocks, exception swallowing without logging) but falls short in some edge cases where exceptions are caught, recorded in observability systems, but not logged to application logs—making them invisible to operators who are monitoring logs.

