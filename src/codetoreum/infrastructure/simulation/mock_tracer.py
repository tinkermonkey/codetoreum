"""Mock tracer for simulation testing of trace propagation.

Provides in-memory span recording and trace context validation for testing
trace propagation without OpenTelemetry infrastructure.

This module implements:
- MockTracer: Tracer that records spans in memory
- SpanCapture: Immutable record of a span with parent-child relationships
- TraceContextValidator: Assertion helper for trace structure validation
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from codetoreum.infrastructure.observability.trace_context_propagation import (
    TraceContextData,
    W3C_TRACE_CONTEXT_VERSION,
)
from codetoreum.ports.output.i_tracer import (
    ITracer as ITracerPort,
    SpanKind,
    SpanStatus,
    SpanEvent,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpanCapture:
    """Immutable record of a span for testing."""

    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    kind: SpanKind
    status: SpanStatus
    start_time: datetime
    end_time: Optional[datetime]
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[SpanEvent] = field(default_factory=list)
    span_context_injected: bool = False

    @property
    def duration_ms(self) -> Optional[float]:
        """Calculate span duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000

    @property
    def traceparent(self) -> str:
        """Get W3C traceparent format for this span."""
        return f"{W3C_TRACE_CONTEXT_VERSION}-{self.trace_id}-{self.span_id}-01"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind.value,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": [
                {
                    "name": e.name,
                    "timestamp": e.timestamp.isoformat(),
                    "attributes": e.attributes,
                }
                for e in self.events
            ],
            "span_context_injected": self.span_context_injected,
        }


class MockSpan:
    """In-memory span for recording."""

    def __init__(
        self,
        name: str,
        span_id: str,
        trace_id: str,
        parent_span_id: Optional[str] = None,
        kind: SpanKind = SpanKind.INTERNAL,
    ):
        self.name = name
        self.span_id = span_id
        self.trace_id = trace_id
        self.parent_span_id = parent_span_id
        self.kind = kind
        self.status = SpanStatus.UNSET
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None
        self.attributes: Dict[str, Any] = {}
        self.events: List[SpanEvent] = []
        self.span_context_injected = False

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        self.attributes[key] = value

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add an event to the span."""
        self.events.append(
            SpanEvent(
                name=name,
                timestamp=datetime.now(timezone.utc),
                attributes=attributes or {},
            )
        )

    def set_status(self, status: SpanStatus) -> None:
        """Set the span status."""
        self.status = status

    def end(self) -> None:
        """End the span."""
        self.end_time = datetime.now(timezone.utc)

    def mark_context_injected(self) -> None:
        """Mark that trace context was injected into an event."""
        self.span_context_injected = True

    @property
    def duration_ms(self) -> Optional[float]:
        """Get span duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000

    @property
    def traceparent(self) -> str:
        """Get W3C Trace Context traceparent header."""
        # Per W3C spec, trace_flags (least significant bit) indicates sampling decision:
        # 01 = sampled (trace should be sampled/collected)
        # 00 = not sampled
        # Error status is tracked in span status, not in trace_flags
        return f"{W3C_TRACE_CONTEXT_VERSION}-{self.trace_id}-{self.span_id}-01"

    def record_exception(self, exception: Exception) -> None:
        """Record an exception on the span."""
        self.add_event(
            "exception",
            attributes={
                "exception.type": type(exception).__name__,
                "exception.message": str(exception),
            },
        )
        self.set_status(SpanStatus.ERROR)

    def to_capture(self) -> SpanCapture:
        """Convert to SpanCapture for immutable storage."""
        return SpanCapture(
            span_id=self.span_id,
            trace_id=self.trace_id,
            parent_span_id=self.parent_span_id,
            name=self.name,
            kind=self.kind,
            status=self.status,
            start_time=self.start_time,
            end_time=self.end_time,
            attributes=self.attributes.copy(),
            events=self.events.copy(),
            span_context_injected=self.span_context_injected,
        )


class MockTracer(ITracerPort):
    """Mock OpenTelemetry tracer for simulation testing.

    Records all spans in memory for verification of trace propagation.
    Does not require OpenTelemetry infrastructure.
    Implements the ITracer port for async trace propagation testing.

    Usage:
        tracer = MockTracer()
        span = await tracer.start_span("operation")
        await tracer.set_attribute(span, "key", "value")
        # Do work
        await tracer.end_span(span)
        # Verify
        spans = tracer.get_spans()
        assert len(spans) == 1
    """

    def __init__(self, service_name: str = "simulation"):
        self.service_name = service_name
        self.spans: List[SpanCapture] = []
        self.active_span: Optional[MockSpan] = None
        self.root_trace_id: Optional[str] = None
        self.span_counter = 0
        self.trace_counter = 0  # Counter for generating unique trace IDs

    async def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_context: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> MockSpan:
        """
        Start a new span (ITracer protocol).

        Args:
            name: Span name
            kind: Span kind (INTERNAL, CLIENT, etc.)
            parent_context: Parent span context (for linking)
            attributes: Initial span attributes

        Returns:
            MockSpan instance
        """
        span = self.start_span_sync(
            name=name,
            kind=kind,
            parent_context=parent_context,
        )
        # Set initial attributes if provided
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        return span

    def _start_span_internal(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_span_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> MockSpan:
        """
        Internal span creation (used by both async and sync methods).

        Args:
            name: Span name
            kind: Span kind (INTERNAL, CLIENT, etc.)
            parent_span_id: Parent span ID if child of existing span
            trace_id: Trace ID (creates new if not provided)
            attributes: Initial span attributes

        Returns:
            MockSpan instance
        """
        # Generate or use provided trace ID
        if trace_id is None:
            # If no parent_span_id and no active span, start a new trace
            if parent_span_id is None and (self.active_span is None):
                trace_id = self._generate_trace_id()
                self.root_trace_id = trace_id
            else:
                # Use existing root trace ID or create new one
                trace_id = self.root_trace_id or self._generate_trace_id()
                if self.root_trace_id is None:
                    self.root_trace_id = trace_id

        # Generate span ID
        span_id = self._generate_span_id()

        # Create span
        span = MockSpan(
            name=name,
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            kind=kind,
        )

        # Set initial attributes
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)

        self.active_span = span
        logger.debug(f"Started span: {name} (id={span_id}, trace={trace_id})")

        return span

    async def end_span(self, span: MockSpan) -> None:
        """
        End a span (ITracer protocol).

        Args:
            span: Span to end
        """
        self.end_span_sync(span)

    async def add_event(
        self,
        span: MockSpan,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add an event to a span (ITracer protocol).

        Args:
            span: Span to add event to
            name: Event name
            attributes: Event attributes
        """
        span.add_event(name, attributes)

    async def set_attribute(
        self,
        span: MockSpan,
        key: str,
        value: Any,
    ) -> None:
        """
        Set a span attribute (ITracer protocol).

        Args:
            span: Span to set attribute on
            key: Attribute key
            value: Attribute value
        """
        span.set_attribute(key, value)

    async def record_exception(
        self,
        span: MockSpan,
        exception: Exception,
    ) -> None:
        """
        Record an exception in a span (ITracer protocol).

        Args:
            span: Span to record exception in
            exception: Exception that occurred
        """
        span.set_status(SpanStatus.ERROR)
        span.add_event(
            "exception",
            {
                "exception.type": type(exception).__name__,
                "exception.message": str(exception),
            },
        )

    async def extract_context(self, carrier: Dict[str, str]) -> Optional[str]:
        """
        Extract trace context from a carrier (ITracer protocol).

        Args:
            carrier: Dictionary containing trace context

        Returns:
            Context string in W3C traceparent format or None
        """
        # Look for traceparent header
        if "traceparent" in carrier:
            return carrier["traceparent"]
        if "Traceparent" in carrier:
            return carrier["Traceparent"]
        return None

    async def inject_context(
        self,
        span: MockSpan,
        carrier: Dict[str, str],
    ) -> None:
        """
        Inject trace context into a carrier (ITracer protocol).

        Args:
            span: Span to inject context from
            carrier: Dictionary to inject context into
        """
        carrier["traceparent"] = f"{W3C_TRACE_CONTEXT_VERSION}-{span.trace_id}-{span.span_id}-01"
        span.mark_context_injected()

    def start_new_trace(self) -> None:
        """
        Start a new trace, resetting trace context for independent operations.

        Use this method to reset just the trace context without clearing
        all recorded spans. Useful for testing independent operations in
        the same test scenario.

        Example:
            # Test first operation
            span1 = await tracer.start_span("operation1")
            await tracer.end_span(span1)

            # Reset trace context for independent operation
            tracer.start_new_trace()

            # Test second operation (separate trace)
            span2 = await tracer.start_span("operation2")
            await tracer.end_span(span2)

            # Both operations recorded, different trace IDs
            spans = tracer.get_spans()
            assert spans[0].trace_id != spans[1].trace_id
        """
        self.root_trace_id = None
        self.active_span = None
        logger.debug("Started new trace (trace context reset)")

    def get_current_span(self) -> Optional[MockSpan]:
        """Get the currently active span."""
        return self.active_span

    def get_current_trace_context(self) -> Optional[TraceContextData]:
        """Get trace context for the current span."""
        if self.active_span is None:
            return None

        return TraceContextData(
            version=W3C_TRACE_CONTEXT_VERSION,
            trace_id=self.active_span.trace_id,
            span_id=self.active_span.span_id,
            trace_flags="01",
        )

    def get_spans(self) -> List[SpanCapture]:
        """Get all recorded spans."""
        return self.spans.copy()

    def get_spans_by_name(self, name: str) -> List[SpanCapture]:
        """Get spans matching a name."""
        return [s for s in self.spans if s.name == name]

    def get_spans_by_kind(self, kind: SpanKind) -> List[SpanCapture]:
        """Get spans matching a kind."""
        return [s for s in self.spans if s.kind == kind]

    def get_spans_by_trace_id(self, trace_id: str) -> List[SpanCapture]:
        """Get spans in a specific trace."""
        return [s for s in self.spans if s.trace_id == trace_id]

    def get_span_hierarchy(self) -> Dict[Optional[str], List[SpanCapture]]:
        """Get spans organized by parent span ID."""
        hierarchy: Dict[Optional[str], List[SpanCapture]] = {}
        for span in self.spans:
            parent_id = span.parent_span_id
            if parent_id not in hierarchy:
                hierarchy[parent_id] = []
            hierarchy[parent_id].append(span)
        return hierarchy

    def start_span_sync(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_context: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> MockSpan:
        """
        Start a new span (synchronous version).

        Args:
            name: Span name
            kind: Span kind (INTERNAL, CLIENT, etc.)
            parent_context: Parent span context for linking (W3C traceparent format)
            parent_span_id: Parent span ID if child of existing span
            trace_id: Trace ID (creates new if not provided)

        Returns:
            MockSpan instance
        """
        # If parent_context is provided, extract parent info from it
        if parent_context:
            # Format: "00-{trace_id}-{span_id}-01"
            parts = parent_context.split("-")
            if len(parts) >= 3:
                trace_id = parts[1]
                parent_span_id = parts[2]

        return self._start_span_internal(
            name=name,
            kind=kind,
            parent_span_id=parent_span_id,
            trace_id=trace_id,
        )

    def end_span_sync(self, span: MockSpan) -> None:
        """
        End a span (synchronous version for backwards compatibility).

        Args:
            span: Span to end
        """
        span.end()
        self.spans.append(span.to_capture())
        self.active_span = None
        logger.debug(f"Ended span: {span.name} (id={span.span_id})")

    def clear(self) -> None:
        """Clear all recorded spans."""
        self.spans.clear()
        self.active_span = None
        self.root_trace_id = None
        self.span_counter = 0

    def _generate_trace_id(self) -> str:
        """Generate a trace ID (32-character hex)."""
        return f"{uuid4().int:032x}"

    def _generate_span_id(self) -> str:
        """Generate a span ID (16-character hex)."""
        self.span_counter += 1
        return f"{self.span_counter:016x}"

    def print_spans(self) -> None:
        """Print all recorded spans for debugging."""
        print(f"\n=== Mock Tracer Spans ({self.service_name}) ===")
        for span in self.spans:
            indent = "  " if span.parent_span_id else ""
            print(
                f"{indent}[{span.kind.value}] {span.name} "
                f"(trace={span.trace_id[:8]}, span={span.span_id[:8]}, "
                f"duration={span.duration_ms:.2f}ms)"
            )
            if span.attributes:
                for key, value in span.attributes.items():
                    print(f"{indent}  @{key}={value}")
        print("=" * 60)


class TraceContextValidator:
    """Helper for validating trace context in tests."""

    def __init__(self, tracer: MockTracer):
        self.tracer = tracer

    def assert_span_exists(self, name: str) -> SpanCapture:
        """Assert a span with given name exists."""
        spans = self.tracer.get_spans_by_name(name)
        if not spans:
            raise AssertionError(f"No span found with name: {name}")
        return spans[0]

    def assert_span_kind(self, name: str, expected_kind: SpanKind) -> None:
        """Assert a span has a specific kind."""
        span = self.assert_span_exists(name)
        if span.kind != expected_kind:
            raise AssertionError(
                f"Span {name} has kind {span.kind.value}, expected {expected_kind.value}"
            )

    def assert_span_attribute(
        self, name: str, key: str, expected_value: Optional[Any] = None
    ) -> Any:
        """Assert a span has an attribute."""
        span = self.assert_span_exists(name)
        if key not in span.attributes:
            raise AssertionError(f"Span {name} missing attribute: {key}")

        value = span.attributes[key]
        if expected_value is not None and value != expected_value:
            raise AssertionError(
                f"Span {name} attribute {key}={value}, expected {expected_value}"
            )
        return value

    def assert_span_parent_child(self, parent_name: str, child_name: str) -> None:
        """Assert parent-child relationship between two spans."""
        parent = self.assert_span_exists(parent_name)
        child = self.assert_span_exists(child_name)

        if child.parent_span_id != parent.span_id:
            raise AssertionError(
                f"Span {child_name} parent is {child.parent_span_id}, "
                f"expected {parent.span_id} ({parent_name})"
            )

        if child.trace_id != parent.trace_id:
            raise AssertionError(
                f"Span {child_name} trace {child.trace_id} does not match "
                f"parent trace {parent.trace_id}"
            )

    def assert_span_context_injected(self, span_name: str) -> None:
        """Assert trace context was injected for a span."""
        span = self.assert_span_exists(span_name)
        if not span.span_context_injected:
            raise AssertionError(f"Span {span_name} did not inject trace context")

    def assert_trace_chain(self, span_names: List[str]) -> None:
        """Assert a chain of parent-child spans."""
        for i in range(len(span_names) - 1):
            self.assert_span_parent_child(span_names[i], span_names[i + 1])

    def assert_span_count(self, expected_count: int) -> None:
        """Assert total span count."""
        actual_count = len(self.tracer.get_spans())
        if actual_count != expected_count:
            raise AssertionError(
                f"Expected {expected_count} spans, got {actual_count}"
            )

    def assert_span_count_by_kind(self, kind: SpanKind, expected_count: int) -> None:
        """Assert span count by kind."""
        spans = self.tracer.get_spans_by_kind(kind)
        if len(spans) != expected_count:
            raise AssertionError(
                f"Expected {expected_count} {kind.value} spans, got {len(spans)}"
            )
