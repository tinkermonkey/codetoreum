# ITracer Output Port Design

## Overview

The `ITracer` port provides an abstraction for distributed tracing. This port enables tracking of requests as they flow through the system, providing insights into performance bottlenecks and system behavior.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class SpanKind(Enum):
    """Span types."""
    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"

class ITracer(ABC):
    """Interface for distributed tracing."""

    @abstractmethod
    async def start_span(self,
                        name: str,
                        kind: SpanKind = SpanKind.INTERNAL,
                        parent_context: Optional[str] = None,
                        attributes: Optional[Dict[str, Any]] = None) -> Span:
        """
        Start a new span.

        Args:
            name: Span name
            kind: Span kind
            parent_context: Parent span context
            attributes: Span attributes

        Returns:
            Span: New span
        """
        pass

    @abstractmethod
    async def end_span(self, span: 'Span') -> None:
        """End a span."""
        pass

    @abstractmethod
    async def add_event(self,
                       span: 'Span',
                       name: str,
                       attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add event to span."""
        pass

    @abstractmethod
    async def set_attribute(self,
                           span: 'Span',
                           key: str,
                           value: Any) -> None:
        """Set span attribute."""
        pass

    @abstractmethod
    async def record_exception(self,
                              span: 'Span',
                              exception: Exception) -> None:
        """Record exception in span."""
        pass

    @abstractmethod
    async def extract_context(self, carrier: Dict[str, str]) -> Optional[str]:
        """Extract trace context from carrier."""
        pass

    @abstractmethod
    async def inject_context(self,
                            span: 'Span',
                            carrier: Dict[str, str]) -> None:
        """Inject trace context into carrier."""
        pass
```

## Data Models

```python
@dataclass
class Span:
    """Trace span."""
    span_id: str
    trace_id: str
    name: str
    kind: SpanKind
    start_time: datetime
    end_time: Optional[datetime]
    attributes: Dict[str, Any]
    events: List[SpanEvent]
    status: SpanStatus

@dataclass
class SpanEvent:
    """Span event."""
    name: str
    timestamp: datetime
    attributes: Dict[str, Any]

@dataclass
class SpanStatus:
    """Span status."""
    code: str  # OK, ERROR, UNSET
    message: Optional[str]
```

## Adapter Implementations

### OpenTelemetry Tracer

```python
class OpenTelemetryTracer(ITracer):
    """OpenTelemetry implementation."""

    def __init__(self, service_name: str):
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        self.tracer = trace.get_tracer(service_name)

    async def start_span(self,
                        name: str,
                        kind: SpanKind = SpanKind.INTERNAL,
                        parent_context: Optional[str] = None,
                        attributes: Optional[Dict[str, Any]] = None) -> Span:
        """Start OpenTelemetry span."""
        otel_span = self.tracer.start_span(name)

        if attributes:
            for key, value in attributes.items():
                otel_span.set_attribute(key, value)

        return self._convert_span(otel_span)
```

### Mock Tracer (Testing)

```python
class MockTracer(ITracer):
    """Mock tracer for testing."""

    def __init__(self):
        self.spans: List[Span] = []
        self.active_spans: Dict[str, Span] = {}

    async def start_span(self,
                        name: str,
                        kind: SpanKind = SpanKind.INTERNAL,
                        parent_context: Optional[str] = None,
                        attributes: Optional[Dict[str, Any]] = None) -> Span:
        """Create mock span."""
        span = Span(
            span_id=str(uuid4()),
            trace_id=str(uuid4()),
            name=name,
            kind=kind,
            start_time=datetime.utcnow(),
            end_time=None,
            attributes=attributes or {},
            events=[],
            status=SpanStatus(code="UNSET", message=None)
        )

        self.active_spans[span.span_id] = span
        return span

    async def end_span(self, span: Span) -> None:
        """End mock span."""
        span.end_time = datetime.utcnow()
        self.spans.append(span)
        del self.active_spans[span.span_id]
```

## Common Span Names

### Agent Execution
- `agent.execute`
- `agent.prepare_workspace`
- `agent.finalize_execution`

### Workflow Operations
- `workflow.orchestrate`
- `pipeline.execute_stage`
- `review.cycle`

### External Calls
- `github.api.call`
- `llm.execute`
- `container.run`

## Integration Points

### Used By
- All Application Services (optional)
- Request middleware
- Performance monitoring

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Sampling**: Configure sampling to manage overhead
2. **Attributes**: Add relevant attributes for filtering
3. **Context Propagation**: Propagate context across async boundaries
4. **Performance**: Minimize tracing overhead
5. **Correlation**: Link traces with logs and metrics
