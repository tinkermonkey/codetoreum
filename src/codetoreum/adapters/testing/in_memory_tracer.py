"""In-memory tracer adapter for simulation and unit testing.

Provides a clock-aware ITracer implementation that stores spans in memory.
All timestamps use the injected time_source so simulation clock fast-forwarding
is reflected in span timings.
"""

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from codetoreum.infrastructure.simulation.mock_tracer import MockSpan
from codetoreum.ports.output.i_tracer import (
    ITracer,
    SpanEvent,
    SpanKind,
    SpanProtocol,
    SpanStatus,
)


class InMemoryTracer(ITracer):
    """Clock-aware in-memory ITracer implementation for simulation testing.

    All span timestamps (start, end, events) use the injected time_source,
    so simulation clock fast-forwarding is reflected in span durations.

    Stores completed spans for test verification.

    Test Helper Methods:
        - get_completed_spans() - All spans that have been ended
        - get_spans_by_name(name) - Filter completed spans by name
        - clear() - Reset all state between tests

    Example:
        # Setup with simulation clock
        clock = SimulationClock(...)
        tracer = InMemoryTracer(time_source=lambda: clock.now())

        span = await tracer.start_span("agent.execute", attributes={"agent": "a-1"})
        await tracer.set_attribute(span, "task_id", "t-123")
        await tracer.add_event(span, "task.started")
        await tracer.end_span(span)

        completed = tracer.get_completed_spans()
        assert len(completed) == 1
        assert completed[0].name == "agent.execute"
    """

    def __init__(self, time_source: Callable[[], datetime] | None = None) -> None:
        """Initialize the in-memory tracer.

        Args:
            time_source: Optional callable returning current datetime for simulation clock control.
                        Defaults to datetime.now(UTC).
        """
        self._time_source = time_source or (lambda: datetime.now(UTC))
        self._active_spans: dict[str, MockSpan] = {}  # span_id -> span
        self._completed_spans: list[MockSpan] = []
        self._lock = threading.Lock()
        self._span_counter = 0

    # =========================================================================
    # ITracer Implementation
    # =========================================================================

    async def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_context: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> SpanProtocol:
        """Start a new span with simulation clock start time.

        Args:
            name: Span name
            kind: Span kind
            parent_context: W3C traceparent string (00-{trace_id}-{span_id}-01)
            attributes: Initial attributes

        Returns:
            MockSpan with start_time from time_source
        """
        trace_id = self._generate_trace_id()
        parent_span_id: str | None = None

        if parent_context:
            parts = parent_context.split("-")
            if len(parts) >= 3:
                trace_id = parts[1]
                parent_span_id = parts[2]

        span_id = self._generate_span_id()

        span = MockSpan(
            name=name,
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            kind=kind,
        )
        # Override MockSpan's hardcoded datetime.now(UTC) with simulation time
        span.start_time = self._time_source()

        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)

        with self._lock:
            self._active_spans[span_id] = span

        return span

    async def end_span(self, span: SpanProtocol) -> None:
        """End a span using simulation clock end time.

        Args:
            span: Span to end
        """
        span.end_time = self._time_source()

        with self._lock:
            self._active_spans.pop(span.span_id, None)
            # The tracer only mints MockSpan instances internally; narrow the
            # wider SpanProtocol parameter at the store boundary.
            assert isinstance(span, MockSpan)
            self._completed_spans.append(span)

    async def add_event(
        self,
        span: SpanProtocol,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Add an event to a span with simulation clock timestamp.

        Args:
            span: Span to add event to
            name: Event name
            attributes: Event attributes
        """
        span.events.append(
            SpanEvent(
                name=name,
                timestamp=self._time_source(),
                attributes=attributes or {},
            )
        )

    async def set_attribute(
        self,
        span: SpanProtocol,
        key: str,
        value: Any,
    ) -> None:
        """Set a span attribute.

        Args:
            span: Span to set attribute on
            key: Attribute key
            value: Attribute value
        """
        span.set_attribute(key, value)

    async def record_exception(
        self,
        span: SpanProtocol,
        exception: Exception,
    ) -> None:
        """Record an exception in a span with simulation clock timestamp.

        Sets status to ERROR and adds an exception event.

        Args:
            span: Span to record exception in
            exception: Exception that occurred
        """
        span.set_status(SpanStatus.ERROR)
        await self.add_event(
            span,
            "exception",
            {
                "exception.type": type(exception).__name__,
                "exception.message": str(exception),
            },
        )

    async def extract_context(self, carrier: dict[str, str]) -> str | None:
        """Extract W3C traceparent from carrier.

        Args:
            carrier: Dictionary containing trace context headers

        Returns:
            traceparent string or None
        """
        return carrier.get("traceparent") or carrier.get("Traceparent")

    async def inject_context(
        self,
        span: SpanProtocol,
        carrier: dict[str, str],
    ) -> None:
        """Inject W3C traceparent into carrier.

        Args:
            span: Span to inject context from
            carrier: Dictionary to inject context into
        """
        carrier["traceparent"] = span.traceparent

    # =========================================================================
    # Test Helper Methods
    # =========================================================================

    def get_completed_spans(self) -> list[MockSpan]:
        """Return all spans that have been ended.

        Returns:
            List of completed MockSpan instances in order of completion
        """
        with self._lock:
            return list(self._completed_spans)

    def get_spans_by_name(self, name: str) -> list[MockSpan]:
        """Return completed spans matching a name.

        Args:
            name: Span name to filter by

        Returns:
            List of matching completed spans
        """
        with self._lock:
            return [s for s in self._completed_spans if s.name == name]

    def clear(self) -> None:
        """Reset all state for use between tests."""
        with self._lock:
            self._active_spans.clear()
            self._completed_spans.clear()
            self._span_counter = 0

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _generate_trace_id(self) -> str:
        """Generate a valid 32-char hex trace ID."""
        return f"{uuid4().int:032x}"

    def _generate_span_id(self) -> str:
        """Generate a valid 16-char hex span ID."""
        with self._lock:
            self._span_counter += 1
            return f"{self._span_counter:016x}"
