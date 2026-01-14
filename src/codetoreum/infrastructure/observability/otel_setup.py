"""
OpenTelemetry Setup for Signoz Integration

Initializes OpenTelemetry tracing with Signoz OTLP exporter.
Supports configurable sampling strategies, performance tuning, and granular enable/disable.
"""

import logging
from typing import Optional

# Try to import OpenTelemetry - it's optional
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import (
        TraceIdRatioBased,
        StaticSampler,
        Decision,
        ParentBased,
        ALWAYS_ON,
        ALWAYS_OFF,
    )
    from opentelemetry.sdk.resources import (
        Resource,
        SERVICE_NAME,
        DEPLOYMENT_ENVIRONMENT,
        SERVICE_VERSION,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    # Provide dummy values for when opentelemetry is not installed
    ALWAYS_ON = None
    ALWAYS_OFF = None

from .config import ObservabilityConfig

logger = logging.getLogger(__name__)


def _get_sampler(config: ObservabilityConfig):
    """
    Create sampler based on configuration.

    Args:
        config: Observability configuration

    Returns:
        OpenTelemetry sampler instance
    """
    sampler_type = config.sampler_type.lower()

    if sampler_type == "always_on":
        return ALWAYS_ON
    elif sampler_type == "always_off":
        return ALWAYS_OFF
    elif sampler_type == "traceidratio":
        return TraceIdRatioBased(config.sampler_arg)
    elif sampler_type == "parentbased_always_on":
        return ParentBased(root=ALWAYS_ON)
    else:
        logger.warning(
            f"Unknown sampler type '{sampler_type}', defaulting to ALWAYS_ON"
        )
        return ALWAYS_ON


def setup_opentelemetry(config: ObservabilityConfig, app=None) -> None:
    """
    Initialize OpenTelemetry with Signoz OTLP exporter.

    This function:
    1. Checks if observability is enabled globally and for traces
    2. Creates a Resource with service identification
    3. Configures sampling strategy based on configuration
    4. Configures OTLP span exporter for Signoz
    5. Sets up TracerProvider with batch processing and performance tuning
    6. Optionally instruments FastAPI for automatic request tracing

    Args:
        config: Comprehensive observability configuration
        app: FastAPI app instance (optional, for auto-instrumentation)

    Configuration Options:
        - enabled: Master switch for all observability
        - traces_enabled: Enable/disable distributed tracing
        - sampler_type: Sampling strategy (always_on, always_off, traceidratio, parentbased_always_on)
        - sampler_arg: Sampling ratio (0.0-1.0) for traceidratio sampler
        - batch_max_queue_size: Max queue size for batch processor
        - batch_max_export_batch_size: Max batch size for export
        - batch_schedule_delay_millis: Delay between batch exports

    Note:
        - If observability is disabled, this is a no-op
        - If initialization fails, the application continues without tracing
        - Graceful degradation ensures observability issues don't crash the service
    """
    # Check if OpenTelemetry is available
    if not OPENTELEMETRY_AVAILABLE:
        msg = "OpenTelemetry packages not installed - observability disabled"
        print(f"[OTEL] {msg}")
        logger.info(msg)
        return

    # DEBUG: Print to stdout since logger might not be configured yet
    print(f"[OTEL] setup_opentelemetry called with config.enabled={config.enabled}, traces_enabled={config.traces_enabled}, signoz.enabled={config.signoz.enabled}")

    # Check master switches
    if not config.enabled:
        msg = "Observability is disabled (OTEL_ENABLED=false)"
        print(f"[OTEL] {msg}")
        logger.info(msg)
        return

    if not config.traces_enabled:
        msg = "Tracing is disabled (OTEL_TRACES_ENABLED=false)"
        print(f"[OTEL] {msg}")
        logger.info(msg)
        return

    if not config.signoz.enabled:
        msg = "Signoz integration is disabled (SIGNOZ_ENABLED=false)"
        print(f"[OTEL] {msg}")
        logger.info(msg)
        return

    try:
        # Create resource with service identification
        resource = Resource(
            attributes={
                SERVICE_NAME: config.signoz.service_name,
                DEPLOYMENT_ENVIRONMENT: config.signoz.environment,
                SERVICE_VERSION: "2.0.0",  # TODO: Get from version file
            }
        )

        # Create sampler based on configuration
        sampler = _get_sampler(config)

        # Create OTLP span exporter for Signoz
        otlp_exporter = OTLPSpanExporter(
            endpoint=config.signoz.grpc_endpoint,
            insecure=config.signoz.insecure,
        )

        # Create tracer provider with configured sampling
        tracer_provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # Create batch span processor with performance tuning
        batch_processor = BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=config.batch_max_queue_size,
            max_export_batch_size=config.batch_max_export_batch_size,
            schedule_delay_millis=config.batch_schedule_delay_millis,
        )
        tracer_provider.add_span_processor(batch_processor)

        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)

        # Instrument FastAPI if app provided
        # This automatically creates spans for all HTTP requests
        if app:
            FastAPIInstrumentor.instrument_app(app)
            print("[OTEL] ✓ FastAPI auto-instrumentation enabled", flush=True)
            logger.info("FastAPI auto-instrumentation enabled")

        # Instrument third-party libraries (SQLAlchemy, Redis, HTTP clients)
        from .auto_instrument import setup_library_instrumentation

        print("[OTEL] Setting up library auto-instrumentation...", flush=True)
        setup_library_instrumentation(config)

        print(f"[OTEL] ✓ OpenTelemetry initialized successfully", flush=True)
        print(f"[OTEL]   → Sending traces to Signoz at {config.signoz.grpc_endpoint}", flush=True)
        print(f"[OTEL]   → Service: {config.signoz.service_name}, Env: {config.signoz.environment}", flush=True)
        print(f"[OTEL]   → Sampler: {config.sampler_type} ({config.sampler_arg if config.sampler_type == 'traceidratio' else 'N/A'})", flush=True)

        logger.info(
            f"OpenTelemetry tracing initialized successfully. "
            f"Sending traces to Signoz at {config.signoz.grpc_endpoint} "
            f"(service: {config.signoz.service_name}, "
            f"env: {config.signoz.environment}, "
            f"sampler: {config.sampler_type})"
        )

    except Exception as e:
        # Don't crash the application if observability fails
        logger.error(f"Failed to initialize OpenTelemetry: {e}", exc_info=True)
        logger.warning("Application will continue without distributed tracing")
