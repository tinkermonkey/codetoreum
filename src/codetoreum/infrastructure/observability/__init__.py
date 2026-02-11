"""
Observability Infrastructure for Codetoreum

Provides OpenTelemetry integration with Signoz for distributed tracing and logging.

This package enables:
- Automatic distributed tracing for FastAPI requests
- Trace context injection into application logs (trace_id/span_id)
- Correlation between logs and traces in Signoz
- W3C Trace Context propagation through the event bus
- Graceful degradation when observability services are unavailable
- Configurable sampling strategies and performance tuning
- Granular enable/disable controls for all observability features

Quick Start:
    from codetoreum.infrastructure.observability import ObservabilityConfig, setup_opentelemetry

    # Load comprehensive config from environment
    config = ObservabilityConfig.from_env()

    # Initialize OpenTelemetry with Signoz
    setup_opentelemetry(config, app)

Trace Context Propagation:
    from codetoreum.infrastructure.observability import TraceContextPropagator

    # Inject trace context into events when publishing
    TraceContextPropagator.inject_trace_context(event)

    # Extract and activate trace context when handling events
    trace_data = TraceContextPropagator.extract_trace_context(event)
"""

from .config import SignozConfig, ObservabilityConfig
from .otel_setup import setup_opentelemetry
from .logging_integration import TraceContextInjector
from .instrumentation import (
    instrument_function,
    instrument_async_function,
    instrument_class,
    add_span_attributes,
    add_span_event,
)
from .auto_instrument import (
    setup_library_instrumentation,
    instrument_sqlalchemy_engine,
)
from .trace_context_propagation import (
    TraceContextData,
    TraceContextPropagator,
    EventBusTraceContext,
    inject_current_trace_context_into_event,
    extract_and_activate_trace_context,
)

# Note: InstrumentedEventBus and InstrumentedEventHandler are available via:
# from codetoreum.infrastructure.observability.event_bus_instrumentation import ...
# They are not imported here to avoid circular dependencies with event_bus.py

__all__ = [
    # Configuration
    "SignozConfig",
    "ObservabilityConfig",
    # Setup
    "setup_opentelemetry",
    "setup_library_instrumentation",
    # Logging integration
    "TraceContextInjector",
    # Manual instrumentation decorators
    "instrument_function",
    "instrument_async_function",
    "instrument_class",
    # Span utilities
    "add_span_attributes",
    "add_span_event",
    # Engine instrumentation
    "instrument_sqlalchemy_engine",
    # Trace context propagation (W3C)
    "TraceContextData",
    "TraceContextPropagator",
    "EventBusTraceContext",
    "inject_current_trace_context_into_event",
    "extract_and_activate_trace_context",
]
