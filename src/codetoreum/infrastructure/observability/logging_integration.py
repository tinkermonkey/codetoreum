"""
Logging Integration with OpenTelemetry Tracing

Provides log filters to inject trace context into log records for correlation.
"""

import logging

# Try to import OpenTelemetry - it's optional
try:
    from opentelemetry import trace

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    trace = None  # type: ignore


class TraceContextInjector(logging.Filter):
    """
    Logging filter that injects OpenTelemetry trace context into log records.

    This filter adds trace_id and span_id attributes to log records, enabling
    correlation between logs and distributed traces in observability platforms
    like Signoz.

    The filter is safe to use even when OpenTelemetry is not initialized - it
    will simply set trace_id and span_id to "N/A" when no active span exists.

    Attributes Added to LogRecord:
        trace_id (str): 32-character hex string of the trace ID (or "N/A")
        span_id (str): 16-character hex string of the span ID (or "N/A")

    Usage:
        handler = logging.StreamHandler()
        handler.addFilter(TraceContextInjector())
        logger.addHandler(handler)
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add trace context to log record.

        Args:
            record: Log record to modify

        Returns:
            True (always allows record through)
        """
        # If OpenTelemetry is not available, set N/A
        if not OPENTELEMETRY_AVAILABLE:
            record.trace_id = "N/A"
            record.span_id = "N/A"
            return True

        span = trace.get_current_span()
        span_context = span.get_span_context()

        if span_context.is_valid:
            # Format as 32-digit hex for trace_id, 16-digit hex for span_id
            # This matches the format used by Signoz and other OTLP consumers
            record.trace_id = format(span_context.trace_id, "032x")
            record.span_id = format(span_context.span_id, "016x")
        else:
            # No active span - set to N/A for clarity
            record.trace_id = "N/A"
            record.span_id = "N/A"

        return True
