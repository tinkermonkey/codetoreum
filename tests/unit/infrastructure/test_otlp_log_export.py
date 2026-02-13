"""
Unit tests for OTLP log export functionality.

Tests the configuration and initialization of log export with trace correlation.
"""

import os
import pytest
from unittest import mock

from codetoreum.infrastructure.observability.config import (
    ObservabilityConfig,
    SignozConfig,
)


def _is_opentelemetry_available() -> bool:
    """Check if OpenTelemetry is available."""
    try:
        import opentelemetry  # noqa: F401
        return True
    except ImportError:
        return False


class TestLogExportConfiguration:
    """Tests for log export configuration."""

    def test_logs_enabled_flag_from_env(self):
        """Test OTEL_LOGS_ENABLED flag is properly parsed."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_LOGS_ENABLED": "true",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = ObservabilityConfig.from_env()
            assert config.logs_enabled is True

    def test_logs_disabled_by_default(self):
        """Test logs are disabled by default."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = ObservabilityConfig.from_env()
            assert config.logs_enabled is False

    def test_logs_disabled_when_otel_disabled(self):
        """Test logs_enabled is False when OTEL_ENABLED is false."""
        env = {
            "OTEL_ENABLED": "false",
            "OTEL_LOGS_ENABLED": "true",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = ObservabilityConfig.from_env()
            assert config.logs_enabled is False

    def test_custom_logs_endpoint_from_env(self):
        """Test OTEL_EXPORTER_OTLP_LOGS_ENDPOINT overrides default."""
        custom_endpoint = "http://custom.logs.host:4318/v1/logs"
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_LOGS_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": custom_endpoint,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = ObservabilityConfig.from_env()
            assert config.logs_endpoint == custom_endpoint

    def test_logs_endpoint_from_signoz_config(self):
        """Test logs_endpoint falls back to Signoz HTTP endpoint."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_LOGS_ENABLED": "true",
            "SIGNOZ_ENABLED": "true",
            "SIGNOZ_HOST": "http://signoz.local",
            "SIGNOZ_HTTP_PORT": "4318",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = ObservabilityConfig.from_env()
            assert config.logs_endpoint == "http://signoz.local:4318/v1/logs"


class TestLogExportSetupFunction:
    """Tests for _setup_log_export function."""

    def test_setup_log_export_not_imported_before_use(self):
        """Test that _setup_log_export is properly defined and can be imported."""
        # Simply importing should not raise an error
        from codetoreum.infrastructure.observability.otel_setup import _setup_log_export
        assert _setup_log_export is not None

    def test_setup_log_export_handles_missing_endpoint(self):
        """Test _setup_log_export handles missing endpoint gracefully."""
        from codetoreum.infrastructure.observability.otel_setup import _setup_log_export

        # Use actual Resource if available
        try:
            from opentelemetry.sdk.resources import Resource, SERVICE_NAME, DEPLOYMENT_ENVIRONMENT
            resource = Resource(
                attributes={
                    SERVICE_NAME: "test_service",
                    DEPLOYMENT_ENVIRONMENT: "development",
                }
            )
        except ImportError:
            # Fallback if OpenTelemetry not installed
            class MockResource:
                def __init__(self, attributes):
                    self.attributes = attributes
            resource = MockResource(attributes={"service.name": "test_service"})

        config = ObservabilityConfig(
            enabled=True,
            traces_enabled=True,
            metrics_enabled=False,
            logs_enabled=True,
            signoz=SignozConfig(
                enabled=False,  # Disabled, so no logs_endpoint
                host="http://localhost",
                grpc_port=4317,
                http_port=4318,
                ui_port=8900,
                api_key="",
                service_name="test_service",
                environment="development",
                insecure=True,
            ),
            sampler_type="always_on",
            sampler_arg=1.0,
            auto_instrument_libraries=True,
            instrument_domain=True,
            instrument_application=True,
            instrument_adapters=True,
            batch_max_queue_size=2048,
            batch_max_export_batch_size=512,
            batch_schedule_delay_millis=5000,
            log_level="info",
        )

        # Should handle gracefully without raising
        _setup_log_export(config, resource)  # type: ignore


class TestTraceCorrelationInLogs:
    """Tests for trace context correlation with logs."""

    def test_trace_context_injector_available(self):
        """Test TraceContextInjector can be imported and used."""
        from codetoreum.infrastructure.observability.logging_integration import (
            TraceContextInjector,
        )

        filter_obj = TraceContextInjector()
        assert filter_obj is not None

    def test_trace_context_injector_sets_defaults(self):
        """Test TraceContextInjector sets N/A when no span active."""
        from codetoreum.infrastructure.observability.logging_integration import (
            TraceContextInjector,
        )
        import logging

        filter_obj = TraceContextInjector()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Filter should add trace_id and span_id
        result = filter_obj.filter(record)
        assert result is True
        assert hasattr(record, "trace_id")
        assert hasattr(record, "span_id")
        # When no span is active, should be N/A
        assert record.trace_id in ("N/A", ) or len(record.trace_id) == 32

    def test_logging_integration_filter_in_handler(self):
        """Test TraceContextInjector can be added to logging handler."""
        from codetoreum.infrastructure.observability.logging_integration import (
            TraceContextInjector,
        )
        import logging

        handler = logging.StreamHandler()
        filter_obj = TraceContextInjector()

        # Should not raise
        handler.addFilter(filter_obj)
        assert filter_obj in handler.filters

