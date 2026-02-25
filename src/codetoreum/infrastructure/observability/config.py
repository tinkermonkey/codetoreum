"""
OpenTelemetry Observability Configuration

Provides comprehensive configuration for OpenTelemetry integration with Signoz.
Supports granular control over tracing, metrics, and logging.
"""

import logging
import os
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignozConfig:
    """
    Signoz observability configuration.

    Immutable configuration object that prevents accidental modification
    after initialization, ensuring consistency across the application.
    """

    enabled: bool
    host: str
    grpc_port: int
    http_port: int
    ui_port: int
    api_key: str
    service_name: str
    environment: str
    insecure: bool

    @property
    def grpc_endpoint(self) -> str:
        """Get the gRPC endpoint for OTLP traces (without http:// prefix)."""
        # Strip http:// or https:// prefix for gRPC
        host = self.host.replace("http://", "").replace("https://", "")
        return f"{host}:{self.grpc_port}"

    @property
    def http_endpoint(self) -> str:
        """Get the HTTP endpoint for OTLP logs/metrics."""
        return f"{self.host}:{self.http_port}"

    @property
    def logs_endpoint(self) -> str:
        """Get the HTTP endpoint for OTLP logs."""
        return f"{self.http_endpoint}/v1/logs"

    @property
    def metrics_endpoint(self) -> str:
        """Get the HTTP endpoint for OTLP metrics."""
        return f"{self.http_endpoint}/v1/metrics"

    @classmethod
    def from_env(cls) -> 'SignozConfig':
        """
        Load configuration from environment variables.

        Environment Variables:
            SIGNOZ_ENABLED: Enable/disable Signoz integration (default: false)
            SIGNOZ_HOST: Signoz host URL (default: http://localhost)
            SIGNOZ_GRPC_PORT: gRPC port for traces (default: 4317)
            SIGNOZ_HTTP_PORT: HTTP port for logs/metrics (default: 4318)
            SIGNOZ_UI_PORT: UI port (default: 8900)
            SIGNOZ_API_KEY: API key for querying Signoz (not needed for OTLP)
            SIGNOZ_SERVICE_NAME: Service name in traces (default: codetoreum)
            CODETOREUM_ENV: Environment (development/production)
            SIGNOZ_INSECURE: Use insecure connection (default: true for dev)

        Returns:
            SignozConfig instance
        """
        return cls(
            enabled=os.getenv("SIGNOZ_ENABLED", "false").lower() == "true",
            host=os.getenv("SIGNOZ_HOST", "http://localhost"),
            grpc_port=int(os.getenv("SIGNOZ_GRPC_PORT", "4317")),
            http_port=int(os.getenv("SIGNOZ_HTTP_PORT", "4318")),
            ui_port=int(os.getenv("SIGNOZ_UI_PORT", "8900")),
            api_key=os.getenv("SIGNOZ_API_KEY", ""),
            service_name=os.getenv("SIGNOZ_SERVICE_NAME", "codetoreum"),
            environment=os.getenv("CODETOREUM_ENV", "development"),
            insecure=os.getenv("SIGNOZ_INSECURE", "true").lower() == "true",
        )


@dataclass(frozen=True)
class ObservabilityConfig:
    """
    Comprehensive observability configuration for the entire platform.

    Provides granular control over:
    - Tracing (traces enabled/disabled, sampling strategy)
    - Metrics (metrics enabled/disabled)
    - Logs (log export enabled/disabled)
    - Auto-instrumentation (libraries, domain, application, adapters)
    - Performance tuning (batch sizes, queue sizes, delays)

    Immutable configuration object that prevents accidental modification
    after initialization, ensuring consistency across the application.
    """

    # Master switches
    enabled: bool
    traces_enabled: bool
    metrics_enabled: bool
    logs_enabled: bool

    # Signoz configuration
    signoz: SignozConfig

    # Sampling configuration
    sampler_type: Literal['always_on', 'always_off', 'traceidratio', 'parentbased_always_on']
    sampler_arg: float

    # Auto-instrumentation toggles
    auto_instrument_libraries: bool
    instrument_domain: bool
    instrument_application: bool
    instrument_adapters: bool

    # Performance tuning
    batch_max_queue_size: int
    batch_max_export_batch_size: int
    batch_schedule_delay_millis: int

    # Debug
    log_level: str

    @property
    def is_enabled(self) -> bool:
        """Check if any observability feature is enabled."""
        return self.enabled and (
            self.traces_enabled or self.metrics_enabled or self.logs_enabled
        )

    @property
    def traces_endpoint(self) -> str:
        """
        Returns trace-specific endpoint or falls back to unified gRPC endpoint.

        Priority: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT > signoz.grpc_endpoint

        Returns:
            The gRPC endpoint for traces without http:// prefix
        """
        env_traces = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        if env_traces:
            return env_traces
        return self.signoz.grpc_endpoint

    @property
    def logs_endpoint(self) -> str:
        """
        Returns log-specific endpoint or falls back to unified HTTP endpoint.

        Priority: OTEL_EXPORTER_OTLP_LOGS_ENDPOINT > signoz.logs_endpoint

        Returns:
            The HTTP endpoint for logs with /v1/logs path
        """
        env_logs = os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
        if env_logs:
            return env_logs
        return self.signoz.logs_endpoint

    @property
    def metrics_endpoint(self) -> str:
        """
        Returns metrics-specific endpoint or falls back to unified HTTP endpoint.

        Priority: OTEL_EXPORTER_OTLP_METRICS_ENDPOINT > signoz.metrics_endpoint

        Returns:
            The HTTP endpoint for metrics with /v1/metrics path
        """
        env_metrics = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
        if env_metrics:
            return env_metrics
        return self.signoz.metrics_endpoint

    @classmethod
    def from_env(cls) -> 'ObservabilityConfig':
        """
        Load configuration from environment variables.

        Environment Variables:
            OTEL_ENABLED: Master switch for all observability (default: true)
            OTEL_TRACES_ENABLED: Enable/disable traces (default: true)
            OTEL_METRICS_ENABLED: Enable/disable metrics (default: false)
            OTEL_LOGS_ENABLED: Enable/disable log export (default: false)
            OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: Trace-specific gRPC endpoint (uses signoz.grpc_endpoint if not set)
            OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: Metrics-specific HTTP endpoint (uses signoz.metrics_endpoint if not set)
            OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: Log-specific HTTP endpoint (uses signoz.logs_endpoint if not set)
            OTEL_TRACES_SAMPLER: Sampling strategy (default: always_on)
            OTEL_TRACES_SAMPLER_ARG: Sampler argument (default: 1.0)
            OTEL_AUTO_INSTRUMENT_LIBRARIES: Auto-instrument libraries (default: true)
            OTEL_INSTRUMENT_DOMAIN: Instrument domain layer (default: true)
            OTEL_INSTRUMENT_APPLICATION: Instrument application layer (default: true)
            OTEL_INSTRUMENT_ADAPTERS: Instrument adapters (default: true)
            OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE: Max queue size (default: 2048)
            OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE: Max batch size (default: 512)
            OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS: Batch delay ms (default: 5000)
            OTEL_LOG_LEVEL: Log level for OTel (default: info)

        Returns:
            ObservabilityConfig instance
        """
        otel_enabled = os.getenv("OTEL_ENABLED", "true").lower() == "true"

        config = cls(
            enabled=otel_enabled,
            traces_enabled=(
                os.getenv("OTEL_TRACES_ENABLED", "true").lower() == "true"
                and otel_enabled
            ),
            metrics_enabled=(
                os.getenv("OTEL_METRICS_ENABLED", "false").lower() == "true"
                and otel_enabled
            ),
            logs_enabled=(
                os.getenv("OTEL_LOGS_ENABLED", "false").lower() == "true"
                and otel_enabled
            ),
            signoz=SignozConfig.from_env(),
            sampler_type=cls._validate_sampler_type(os.getenv("OTEL_TRACES_SAMPLER", "always_on")),
            sampler_arg=float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0")),
            auto_instrument_libraries=(
                os.getenv("OTEL_AUTO_INSTRUMENT_LIBRARIES", "true").lower() == "true"
            ),
            instrument_domain=(
                os.getenv("OTEL_INSTRUMENT_DOMAIN", "true").lower() == "true"
            ),
            instrument_application=(
                os.getenv("OTEL_INSTRUMENT_APPLICATION", "true").lower() == "true"
            ),
            instrument_adapters=(
                os.getenv("OTEL_INSTRUMENT_ADAPTERS", "true").lower() == "true"
            ),
            batch_max_queue_size=int(
                os.getenv("OTEL_BATCH_SPAN_PROCESSOR_MAX_QUEUE_SIZE", "2048")
            ),
            batch_max_export_batch_size=int(
                os.getenv("OTEL_BATCH_SPAN_PROCESSOR_MAX_EXPORT_BATCH_SIZE", "512")
            ),
            batch_schedule_delay_millis=int(
                os.getenv("OTEL_BATCH_SPAN_PROCESSOR_SCHEDULE_DELAY_MILLIS", "5000")
            ),
            log_level=os.getenv("OTEL_LOG_LEVEL", "info"),
        )

        # Validate configuration before returning
        config.validate()

        return config

    @staticmethod
    def _validate_sampler_type(sampler_value: str) -> str:
        """
        Validate and normalize sampler_type at runtime.

        Args:
            sampler_value: Raw sampler type value from environment

        Returns:
            Valid sampler type or 'always_on' if invalid
        """
        valid_samplers = {'always_on', 'always_off', 'traceidratio', 'parentbased_always_on'}
        if sampler_value not in valid_samplers:
            logger.warning(
                f"Invalid sampler_type '{sampler_value}'. "
                f"Valid options: {valid_samplers}. Defaulting to 'always_on'."
            )
            return 'always_on'
        return sampler_value

    def validate(self) -> None:
        """
        Validate configuration and raise errors for critical issues.

        Raises:
            ValueError: If observability is enabled but no signals are configured,
                       or if a signal is enabled without a valid endpoint.

        Warnings:
            Logs warning if a signal is enabled but its endpoint is not configured.
        """
        # Error: Observability enabled but no signals configured (invalid state)
        if self.enabled and not self.traces_enabled and not self.metrics_enabled and not self.logs_enabled:
            raise ValueError(
                "Observability enabled but no signals (traces/metrics/logs) are enabled. "
                "Either enable at least one signal or disable observability entirely "
                "(set OTEL_ENABLED=false)."
            )

        # Error: Signal enabled without endpoint (will definitely fail at export time)
        if self.traces_enabled and not self.traces_endpoint:
            raise ValueError(
                "Traces enabled but traces_endpoint is not configured. "
                "Check OTEL_EXPORTER_OTLP_TRACES_ENDPOINT or Signoz gRPC configuration."
            )

        if self.logs_enabled and not self.logs_endpoint:
            raise ValueError(
                "Logs enabled but logs_endpoint is not configured. "
                "Check OTEL_EXPORTER_OTLP_LOGS_ENDPOINT or Signoz HTTP configuration."
            )

        if self.metrics_enabled and not self.metrics_endpoint:
            raise ValueError(
                "Metrics enabled but metrics_endpoint is not configured. "
                "Check OTEL_EXPORTER_OTLP_METRICS_ENDPOINT or Signoz HTTP configuration."
            )
