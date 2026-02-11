"""
ITracer Output Port

Provides an abstraction for distributed tracing across the system.
Enables tracking of requests as they flow through application services,
adapters, and infrastructure components.

This port abstracts OpenTelemetry for production and enables mock tracing
for simulation testing without external infrastructure.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class SpanKind(str, Enum):
    """OpenTelemetry-compatible span kinds."""

    INTERNAL = "INTERNAL"
    SERVER = "SERVER"
    CLIENT = "CLIENT"
    PRODUCER = "PRODUCER"
    CONSUMER = "CONSUMER"


class SpanStatus(str, Enum):
    """Span completion status."""

    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


@dataclass
class SpanEvent:
    """Event recorded on a span."""

    name: str
    timestamp: datetime
    attributes: Dict[str, Any]


@dataclass
class Span:
    """Distributed trace span."""

    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    kind: SpanKind
    status: SpanStatus
    start_time: datetime
    end_time: Optional[datetime]
    attributes: Dict[str, Any]
    events: list[SpanEvent]

    @property
    def duration_ms(self) -> Optional[float]:
        """Calculate span duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds() * 1000

    @property
    def traceparent(self) -> str:
        """Get W3C traceparent format for this span."""
        return f"00-{self.trace_id}-{self.span_id}-01"

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        self.attributes[key] = value

    def add_event(
        self, name: str, attributes: Optional[Dict[str, Any]] = None
    ) -> None:
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

    def record_exception(self, exception: Exception) -> None:
        """Record an exception in the span."""
        self.set_status(SpanStatus.ERROR)
        self.add_event(
            "exception",
            {
                "exception.type": type(exception).__name__,
                "exception.message": str(exception),
            },
        )


class ITracer(ABC):
    """
    Interface for distributed tracing.

    Enables tracking of requests and operations as they flow through the system.
    Provides span lifecycle management, attribute setting, and trace context
    propagation.

    Used by application services, adapters, and infrastructure components.
    """

    @abstractmethod
    async def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_context: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """
        Start a new span.

        Args:
            name: Span name (e.g., "agent.execute", "github.api.call")
            kind: Span kind indicating the role in trace
            parent_context: Parent span context for linking spans
            attributes: Initial span attributes

        Returns:
            Span: New span instance

        Example:
            span = await tracer.start_span(
                "agent.execute",
                kind=SpanKind.INTERNAL,
                attributes={"agent_id": "123"}
            )
        """
        pass

    @abstractmethod
    async def end_span(self, span: Span) -> None:
        """
        End a span.

        Marks span completion time and makes it available for export/analysis.

        Args:
            span: Span to end
        """
        pass

    @abstractmethod
    async def add_event(
        self,
        span: Span,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add an event to a span.

        Events mark noteworthy occurrences during span execution.

        Args:
            span: Span to add event to
            name: Event name
            attributes: Event attributes
        """
        pass

    @abstractmethod
    async def set_attribute(
        self,
        span: Span,
        key: str,
        value: Any,
    ) -> None:
        """
        Set a span attribute.

        Attributes provide context and metadata for the span.

        Args:
            span: Span to set attribute on
            key: Attribute key
            value: Attribute value
        """
        pass

    @abstractmethod
    async def record_exception(
        self,
        span: Span,
        exception: Exception,
    ) -> None:
        """
        Record an exception in a span.

        Sets span status to ERROR and captures exception details.

        Args:
            span: Span to record exception in
            exception: Exception that occurred
        """
        pass

    @abstractmethod
    async def extract_context(self, carrier: Dict[str, str]) -> Optional[str]:
        """
        Extract trace context from a carrier.

        Used to extract parent trace context from messages, events, or HTTP headers.

        Args:
            carrier: Dictionary containing trace context (e.g., HTTP headers)

        Returns:
            Parent context string or None if no context found
        """
        pass

    @abstractmethod
    async def inject_context(
        self,
        span: Span,
        carrier: Dict[str, str],
    ) -> None:
        """
        Inject trace context into a carrier.

        Used to propagate span context to messages, events, or HTTP headers.

        Args:
            span: Span to inject context from
            carrier: Dictionary to inject context into
        """
        pass
