"""W3C Trace Context Propagation for Event Bus

Implements trace context propagation following the W3C Trace Context standard:
https://www.w3.org/TR/trace-context/

This module provides utilities to:
- Extract trace context from event metadata (W3C traceparent format)
- Inject trace context into events for downstream propagation
- Set active span context when processing events
- Support both distributed and in-process tracing

W3C Trace Context Format:
    traceparent: version-trace_id-parent_id-trace_flags
    Example: 00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01

Key Concepts:
- Trace ID: 32-character hex identifier for the entire trace
- Parent ID (Span ID): 16-character hex identifier for the parent span
- Trace Flags: Single byte with flags (01 = sampled/traced, 00 = not sampled)
- Version: Always 00 for current W3C Trace Context version
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

try:
    from opentelemetry import trace, context
    from opentelemetry.trace import (
        SpanContext,
        TraceFlags,
        get_current_span,
        set_span_in_context,
    )
    from opentelemetry.context import Context

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    SpanContext = None
    TraceFlags = None
    Context = None

from codetoreum.domain.events import DomainEvent

logger = logging.getLogger(__name__)

# W3C Trace Context version constant (RFC: https://www.w3.org/TR/trace-context/)
# Update this when W3C releases new trace context versions
W3C_TRACE_CONTEXT_VERSION = "00"


@dataclass
class TraceContextData:
    """W3C Trace Context data extracted from events or HTTP headers."""

    trace_id: str  # 32-character hex string
    span_id: str  # 16-character hex string
    trace_flags: str  # 2-character hex string (e.g., "01")
    version: str = W3C_TRACE_CONTEXT_VERSION  # W3C Trace Context version

    def to_traceparent(self) -> str:
        """
        Serialize to W3C traceparent format.

        Returns:
            traceparent header value (version-trace_id-span_id-flags)
        """
        return f"{self.version}-{self.trace_id}-{self.span_id}-{self.trace_flags}"

    @classmethod
    def from_traceparent(cls, traceparent: str) -> Optional["TraceContextData"]:
        """
        Parse W3C traceparent header.

        Args:
            traceparent: W3C Trace Context traceparent header value

        Returns:
            TraceContextData if valid, None otherwise

        Example:
            data = TraceContextData.from_traceparent("00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01")
        """
        try:
            parts = traceparent.split("-")
            if len(parts) < 4:
                logger.warning(f"Invalid traceparent format: {traceparent}")
                return None

            version, trace_id, span_id, flags = parts[0], parts[1], parts[2], parts[3]

            # Validate format
            if len(version) != 2 or len(trace_id) != 32 or len(span_id) != 16 or len(flags) != 2:
                logger.warning(f"Invalid traceparent component lengths: {traceparent}")
                return None

            # Validate hex format
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
            logger.warning(f"Failed to parse traceparent: {e}")
            return None

    @classmethod
    def from_span_context(cls, span_context: "SpanContext") -> "TraceContextData":
        """
        Create TraceContextData from OpenTelemetry SpanContext.

        Args:
            span_context: OpenTelemetry SpanContext

        Returns:
            TraceContextData instance
        """
        trace_flags = "01" if span_context.trace_flags.sampled else "00"
        return cls(
            version=W3C_TRACE_CONTEXT_VERSION,
            trace_id=format(span_context.trace_id, "032x"),
            span_id=format(span_context.span_id, "016x"),
            trace_flags=trace_flags,
        )


class TraceContextPropagator:
    """
    Propagates W3C trace context through events.

    Provides methods to:
    - Extract trace context from current span
    - Inject trace context into event metadata
    - Activate trace context when handling events
    """

    # Metadata key for storing trace context in events
    TRACE_CONTEXT_KEY = "traceparent"
    STATE_KEY = "tracestate"

    @staticmethod
    def inject_trace_context(event: DomainEvent, span_context: Optional["SpanContext"] = None) -> None:
        """
        Inject current trace context into event metadata.

        If span_context is provided, uses it. Otherwise extracts from current span.
        Stores as W3C traceparent format in event.metadata[TRACE_CONTEXT_KEY].

        Args:
            event: Domain event to inject trace context into
            span_context: Optional SpanContext to use (defaults to current span)

        Example:
            event = WorkItemCreated(...)
            TraceContextPropagator.inject_trace_context(event)
            # event.metadata['traceparent'] now contains W3C traceparent
        """
        if not OPENTELEMETRY_AVAILABLE:
            return

        try:
            # Get span context
            if span_context is None:
                current_span = get_current_span()
                span_context = current_span.get_span_context()

            if not span_context.is_valid:
                # No active trace - create a root span context with new trace ID
                logger.debug("No active span context, not injecting trace context")
                return

            # Convert to W3C format
            trace_data = TraceContextData.from_span_context(span_context)
            traceparent = trace_data.to_traceparent()

            # Inject into event metadata
            if event.metadata is None:
                event.metadata = {}

            event.metadata[TraceContextPropagator.TRACE_CONTEXT_KEY] = traceparent

            logger.debug(
                f"Injected trace context into event {event.event_type}: {traceparent}"
            )

        except Exception as e:
            logger.warning(f"Failed to inject trace context: {e}")

    @staticmethod
    def extract_trace_context(event: DomainEvent) -> Optional[TraceContextData]:
        """
        Extract trace context from event metadata.

        Looks for W3C traceparent in event.metadata[TRACE_CONTEXT_KEY].

        Args:
            event: Domain event to extract trace context from

        Returns:
            TraceContextData if found and valid, None otherwise

        Example:
            trace_data = TraceContextPropagator.extract_trace_context(event)
            if trace_data:
                TraceContextPropagator.activate_trace_context(trace_data)
        """
        if not event.metadata:
            return None

        traceparent = event.metadata.get(TraceContextPropagator.TRACE_CONTEXT_KEY)
        if not traceparent:
            return None

        trace_data = TraceContextData.from_traceparent(traceparent)
        if trace_data:
            logger.debug(
                f"Extracted trace context from event {event.event_type}: {traceparent}"
            )
        return trace_data

    @staticmethod
    def activate_trace_context(trace_data: TraceContextData) -> Optional["Context"]:
        """
        Activate trace context in the current execution context.

        Creates a new SpanContext with the provided trace data and returns it.
        Callers should attach the context using trace.attach_context() if they
        want to make it the active context for downstream spans.

        Args:
            trace_data: W3C Trace Context data

        Returns:
            New Context with trace context set, ready to be attached
            Returns None if OpenTelemetry unavailable or on error

        Example:
            trace_data = TraceContextData.from_traceparent(traceparent)
            ctx = TraceContextPropagator.activate_trace_context(trace_data)
            if ctx:
                token = trace.attach_context(ctx)
                try:
                    # Any spans created here will be children of this trace
                    pass
                finally:
                    trace.detach_context(token)
        """
        if not OPENTELEMETRY_AVAILABLE or SpanContext is None:
            return None

        try:
            from opentelemetry import context as otel_context

            # Parse trace IDs from hex strings
            trace_id_int = int(trace_data.trace_id, 16)
            span_id_int = int(trace_data.span_id, 16)
            sampled = trace_data.trace_flags == "01"

            # Create remote span context (indicates it came from distributed tracing)
            span_context = SpanContext(
                trace_id=trace_id_int,
                span_id=span_id_int,
                is_remote=True,  # Mark as remote (came from upstream service/event)
                trace_flags=TraceFlags(0x01 if sampled else 0x00),
            )

            # Create context with this span context
            ctx = set_span_in_context(span_context)

            logger.debug(
                f"Activated trace context: trace_id={trace_data.trace_id}, "
                f"span_id={trace_data.span_id}"
            )

            return ctx

        except Exception as e:
            logger.warning(f"Failed to activate trace context: {e}")
            return None


class EventBusTraceContext:
    """
    Helper for managing trace context in event bus operations.

    Simplifies the pattern of:
    1. Extracting trace context from event
    2. Activating it in the current context
    3. Creating spans for event handling

    Usage:
        trace_ctx = EventBusTraceContext.from_event(event)
        with trace_ctx.as_context():
            # Any spans created here will be children of the event's trace
            handler.handle(event)
    """

    def __init__(self, trace_data: Optional[TraceContextData] = None):
        """
        Initialize event bus trace context.

        Args:
            trace_data: Optional W3C Trace Context data
        """
        self.trace_data = trace_data
        self.context: Optional["Context"] = None

    @classmethod
    def from_event(cls, event: DomainEvent) -> "EventBusTraceContext":
        """
        Create trace context from event.

        Args:
            event: Domain event

        Returns:
            EventBusTraceContext instance
        """
        trace_data = TraceContextPropagator.extract_trace_context(event)
        return cls(trace_data)

    def activate(self) -> Optional["Context"]:
        """
        Activate trace context if available.

        Returns:
            New context if trace data exists, None otherwise
        """
        if not self.trace_data:
            return None

        self.context = TraceContextPropagator.activate_trace_context(self.trace_data)
        return self.context

    def has_trace_context(self) -> bool:
        """Check if trace context is available."""
        return self.trace_data is not None

    def get_traceparent(self) -> Optional[str]:
        """Get W3C traceparent header value."""
        if self.trace_data:
            return self.trace_data.to_traceparent()
        return None


# Convenience functions for event bus integration

def inject_current_trace_context_into_event(event: DomainEvent) -> None:
    """
    Inject current trace context into event (convenience function).

    Typically called when publishing events to ensure downstream handlers
    can continue the trace.

    Args:
        event: Domain event to inject trace context into
    """
    TraceContextPropagator.inject_trace_context(event)


def extract_and_activate_trace_context(event: DomainEvent) -> Optional["Context"]:
    """
    Extract trace context from event and activate it (convenience function).

    Typically called at the beginning of event handling to continue the trace.

    Args:
        event: Domain event to extract trace context from

    Returns:
        New context if trace context found, None otherwise
    """
    trace_data = TraceContextPropagator.extract_trace_context(event)
    if trace_data:
        return TraceContextPropagator.activate_trace_context(trace_data)
    return None
