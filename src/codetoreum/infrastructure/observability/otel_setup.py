"""
OpenTelemetry Setup for Signoz Integration

Initializes OpenTelemetry tracing with Signoz OTLP exporter.
Supports configurable sampling strategies, performance tuning, and granular enable/disable.
"""

import logging as stdlib_logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.sdk.resources import Resource

# Try to import OpenTelemetry - it's optional
try:
    from opentelemetry import trace, logs
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
    from opentelemetry.exporter.otlp.proto.http.log_exporter import OTLPLogExporter
    from opentelemetry.sdk.logs import LoggerProvider
    from opentelemetry.sdk.logs.export import BatchLogRecordProcessor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    # Provide dummy values for when opentelemetry is not installed
    ALWAYS_ON = None
    ALWAYS_OFF = None

from .config import ObservabilityConfig
from codetoreum.infrastructure.error_ids import ErrorRegistry

logger = stdlib_logging.getLogger(__name__)


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


def _record_trace_export_error(error: Exception, config: ObservabilityConfig) -> None:
    """
    Record metric for trace export error and log warning.

    Emits otel.trace.export.failures counter metric to track export errors.
    Logs warning message with error details to aid troubleshooting.

    Args:
        error: The exception that occurred during trace export setup
        config: The observability configuration
    """
    # Record failure metric
    try:
        from opentelemetry import metrics
        meter = metrics.get_meter("codetoreum.observability")
        counter = meter.create_counter(
            "otel.trace.export.failures",
            description="Number of OTLP trace export failures"
        )
        counter.add(1)
    except Exception as metric_error:
        logger.warning(
            f"Failed to record trace export error metric: {metric_error}",
            exc_info=True
        )

    logger.warning(
        f"OTLP trace export setup failed: {error}. "
        f"Continuing without trace export to {config.signoz.grpc_endpoint}",
        exc_info=True,
        extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR}
    )


class _InstrumentedSpanExporter:
    """
    Wrapper around OTLPSpanExporter that measures export duration and records metrics.

    This exporter wraps an actual OTLP exporter and measures the time taken
    to export spans, recording the duration as a histogram metric.
    """

    def __init__(self, exporter):
        """
        Initialize with a wrapped exporter.

        Args:
            exporter: The OTLPSpanExporter to wrap
        """
        self._exporter = exporter
        self._meter = None
        self._duration_histogram = None
        self._export_counter = None

        try:
            from opentelemetry import metrics
            self._meter = metrics.get_meter("codetoreum.observability")

            # Create histogram for export duration in milliseconds
            self._duration_histogram = self._meter.create_histogram(
                "otel.trace.export.duration",
                description="Duration of OTLP trace export in milliseconds",
                unit="ms"
            )

            # Create counter for successful exports
            self._export_counter = self._meter.create_counter(
                "otel.trace.export.success",
                description="Number of successful OTLP trace exports"
            )
        except Exception as e:
            logger.debug(f"Failed to create metrics for span export: {e}")

    def export(self, spans):
        """
        Export spans and measure duration.

        Args:
            spans: List of spans to export

        Returns:
            Export result
        """
        import time
        start_time = time.time()

        try:
            result = self._exporter.export(spans)

            # Record duration metric
            if self._duration_histogram:
                duration_ms = (time.time() - start_time) * 1000
                self._duration_histogram.record(duration_ms)

            # Record success count
            if self._export_counter:
                self._export_counter.add(1)

            return result
        except Exception as e:
            logger.debug(f"Span export failed: {e}")
            raise

    def shutdown(self):
        """Shutdown the wrapped exporter."""
        return self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000):
        """Force flush the wrapped exporter."""
        return self._exporter.force_flush(timeout_millis)


def _record_log_export_error(error: Exception, config: ObservabilityConfig) -> None:
    """
    Record metric for log export error and log warning.

    Emits otel.log.export.failures counter metric to track export errors.
    Logs warning message with error details to aid troubleshooting.

    Args:
        error: The exception that occurred during log export setup
        config: The observability configuration
    """
    # Record failure metric
    try:
        from opentelemetry import metrics
        meter = metrics.get_meter("codetoreum.observability")
        counter = meter.create_counter(
            "otel.log.export.failures",
            description="Number of OTLP log export failures"
        )
        counter.add(1)
    except Exception as metric_error:
        logger.warning(
            f"Failed to record log export error metric: {metric_error}",
            exc_info=True
        )

    logger.warning(
        f"OTLP log export setup failed: {error}. "
        f"Continuing without log export to {config.logs_endpoint}",
        exc_info=True,
        extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR}
    )


def _setup_log_export(config: ObservabilityConfig, resource: "Resource") -> None:
    """
    Initialize OpenTelemetry log export to Signoz.

    This function:
    1. Creates an OTLPLogExporter configured for the logs HTTP endpoint
    2. Sets up a LoggerProvider with batch processing
    3. Instruments Python's logging module to export logs to OTLP
    4. Ensures logs are correlated with traces via trace context injection
    5. Wires TraceContextInjector filter to root logger for trace correlation

    Args:
        config: Observability configuration
        resource: OpenTelemetry resource with service identification

    Note:
        - Log export is only configured if logs_enabled is True, signoz.enabled is True, and an endpoint is configured
        - Graceful degradation: failures in log setup don't crash the application
        - Trace context is automatically injected into logs when this is enabled
    """
    if not config.logs_enabled:
        logger.debug("Log export disabled (OTEL_LOGS_ENABLED=false)")
        return

    if not config.signoz.enabled:
        logger.debug("Log export disabled (SIGNOZ_ENABLED=false)")
        return

    if not config.logs_endpoint:
        logger.warning(
            "Logs enabled but no logs endpoint configured. "
            "Check OTEL_EXPORTER_OTLP_LOGS_ENDPOINT or Signoz HTTP configuration."
        )
        return

    try:
        # Create OTLP log exporter for Signoz
        # Logs use HTTP/protobuf instead of gRPC
        log_exporter = OTLPLogExporter(
            endpoint=config.logs_endpoint,
            insecure=config.signoz.insecure,
        )

        # Create logger provider with resource
        logger_provider = LoggerProvider(resource=resource)

        # Create batch log record processor with performance tuning
        batch_log_processor = BatchLogRecordProcessor(
            log_exporter,
            max_queue_size=config.batch_max_queue_size,
            max_export_batch_size=config.batch_max_export_batch_size,
            schedule_delay_millis=config.batch_schedule_delay_millis,
        )
        logger_provider.add_log_record_processor(batch_log_processor)

        # Set global logger provider
        logs.set_logger_provider(logger_provider)

        # Instrument Python's logging module to export logs to OTLP
        # This hooks into the Python logging module and exports records to the OTLP backend
        # Trace context (trace_id, span_id) is automatically correlated
        LoggingInstrumentor().instrument(
            set_logging_format=False,  # Keep existing logging format
        )

        # Wire TraceContextInjector filter to root logger for trace correlation
        from codetoreum.infrastructure.observability.logging_integration import TraceContextInjector
        trace_filter = TraceContextInjector()
        stdlib_logging.getLogger().addFilter(trace_filter)

        logger.info(
            f"OTLP log export configured. "
            f"Sending logs to {config.logs_endpoint}"
        )
        logger.debug("TraceContextInjector wired to root logger for trace correlation")

    except Exception as e:
        _record_log_export_error(e, config)


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
        logger.info(msg)
        return

    # Check master switches
    if not config.enabled:
        msg = "Observability is disabled (OTEL_ENABLED=false)"
        logger.info(msg)
        return

    if not config.traces_enabled:
        msg = "Tracing is disabled (OTEL_TRACES_ENABLED=false)"
        logger.info(msg)
        return

    if not config.signoz.enabled:
        msg = "Signoz integration is disabled (SIGNOZ_ENABLED=false)"
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

        # Wrap exporter with instrumentation to measure export duration
        instrumented_exporter = _InstrumentedSpanExporter(otlp_exporter)

        # Create tracer provider with configured sampling
        tracer_provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # Create batch span processor with performance tuning
        batch_processor = BatchSpanProcessor(
            instrumented_exporter,
            max_queue_size=config.batch_max_queue_size,
            max_export_batch_size=config.batch_max_export_batch_size,
            schedule_delay_millis=config.batch_schedule_delay_millis,
        )
        tracer_provider.add_span_processor(batch_processor)

        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)

        # Configure OTLP log export with trace correlation
        _setup_log_export(config, resource)

        # Instrument FastAPI if app provided
        # This automatically creates spans for all HTTP requests
        if app:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI auto-instrumentation enabled")

        # Instrument third-party libraries (SQLAlchemy, Redis, HTTP clients)
        from .auto_instrument import setup_library_instrumentation

        setup_library_instrumentation(config)

        logger.info(
            f"OpenTelemetry initialized successfully. "
            f"Sending traces to Signoz at {config.signoz.grpc_endpoint} "
            f"(service: {config.signoz.service_name}, "
            f"env: {config.signoz.environment}, "
            f"sampler: {config.sampler_type})"
        )
        if config.logs_enabled:
            logger.info(f"OTLP log export enabled, sending logs to {config.logs_endpoint}")

    except Exception as e:
        # Record trace export failure metric
        _record_trace_export_error(e, config)
        # Don't crash the application if observability fails
        logger.error(f"Failed to initialize OpenTelemetry: {e}", exc_info=True, extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR})
        logger.warning("Application will continue without distributed tracing and log export")
