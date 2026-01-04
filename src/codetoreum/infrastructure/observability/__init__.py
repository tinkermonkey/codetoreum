"""
Observability Infrastructure for Codetoreum

Provides OpenTelemetry integration with Signoz for distributed tracing and logging.

This package enables:
- Automatic distributed tracing for FastAPI requests
- Trace context injection into application logs (trace_id/span_id)
- Correlation between logs and traces in Signoz
- Graceful degradation when observability services are unavailable
- Configurable sampling strategies and performance tuning
- Granular enable/disable controls for all observability features

Quick Start:
    from codetoreum.infrastructure.observability import ObservabilityConfig, setup_opentelemetry

    # Load comprehensive config from environment
    config = ObservabilityConfig.from_env()

    # Initialize OpenTelemetry with Signoz
    setup_opentelemetry(config, app)
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
]
