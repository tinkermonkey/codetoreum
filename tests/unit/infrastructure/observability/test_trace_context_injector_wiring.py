"""
Unit tests for TraceContextInjector root logger wiring.

Tests that the TraceContextInjector filter is properly added to the root logger
during _setup_log_export() initialization for log-trace correlation.
"""

import logging
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


class TestTraceContextInjectorRootLoggerWiring:
    """Tests for TraceContextInjector root logger wiring during setup."""

    @pytest.mark.skipif(
        not _is_opentelemetry_available(),
        reason="OpenTelemetry not available"
    )
    def test_trace_context_injector_added_to_root_logger(self):
        """Test TraceContextInjector filter is added to root logger during setup."""
        from codetoreum.infrastructure.observability.otel_setup import _setup_log_export
        from codetoreum.infrastructure.observability.logging_integration import TraceContextInjector
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, DEPLOYMENT_ENVIRONMENT

        # Create resource
        resource = Resource(
            attributes={
                SERVICE_NAME: "test_service",
                DEPLOYMENT_ENVIRONMENT: "test",
            }
        )

        # Create config with logs enabled
        signoz_config = SignozConfig(
            enabled=True,
            host="http://localhost",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="",
            service_name="test_service",
            environment="test",
            insecure=True,
        )

        config = ObservabilityConfig(
            enabled=True,
            traces_enabled=False,
            metrics_enabled=False,
            logs_enabled=True,
            signoz=signoz_config,
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

        # Get root logger before setup to verify it's modified
        root_logger = logging.getLogger()

        # Count filters before setup
        filters_before = len(root_logger.filters)

        # Call setup (may fail due to OTel availability, but filter should be added)
        try:
            _setup_log_export(config, resource)
        except Exception:
            # Ignore setup errors - we're only testing filter addition
            pass

        # Verify TraceContextInjector was added to root logger
        root_logger = logging.getLogger()
        filters_after = len(root_logger.filters)

        # Should have added at least one filter
        assert filters_after > filters_before, "TraceContextInjector filter was not added to root logger"

        # Verify the filter is TraceContextInjector
        injectors = [f for f in root_logger.filters if isinstance(f, TraceContextInjector)]
        assert len(injectors) >= 1, "No TraceContextInjector instance found in root logger filters"

    @pytest.mark.skipif(
        not _is_opentelemetry_available(),
        reason="OpenTelemetry not available"
    )
    def test_setup_log_export_skipped_when_logs_disabled(self):
        """Test _setup_log_export returns early when logs_enabled is False."""
        from codetoreum.infrastructure.observability.otel_setup import _setup_log_export
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, DEPLOYMENT_ENVIRONMENT

        resource = Resource(
            attributes={
                SERVICE_NAME: "test_service",
                DEPLOYMENT_ENVIRONMENT: "test",
            }
        )

        signoz_config = SignozConfig(
            enabled=True,
            host="http://localhost",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="",
            service_name="test_service",
            environment="test",
            insecure=True,
        )

        config = ObservabilityConfig(
            enabled=True,
            traces_enabled=False,
            metrics_enabled=False,
            logs_enabled=False,  # Disabled
            signoz=signoz_config,
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

        root_logger = logging.getLogger()
        filters_before = len(root_logger.filters)

        # Call setup with logs disabled
        _setup_log_export(config, resource)

        # Filter count should not increase since logs are disabled
        filters_after = len(root_logger.filters)
        assert filters_after == filters_before, "Filter was added when logs_enabled=False"

    @pytest.mark.skipif(
        not _is_opentelemetry_available(),
        reason="OpenTelemetry not available"
    )
    def test_trace_context_injector_filter_works_in_root_logger(self):
        """Test TraceContextInjector filter works when added to root logger."""
        from codetoreum.infrastructure.observability.logging_integration import TraceContextInjector
        from opentelemetry import trace
        from opentelemetry.trace import Status, StatusCode

        # Create a span context
        root_logger = logging.getLogger()

        # Create and add injector filter
        injector = TraceContextInjector()
        root_logger.addFilter(injector)

        try:
            # Create a test log record
            record = logging.LogRecord(
                name="test.module",
                level=logging.INFO,
                pathname="test.py",
                lineno=10,
                msg="Test message",
                args=(),
                exc_info=None,
            )

            # Filter should add trace context attributes
            result = injector.filter(record)

            # Filter should return True (allow record)
            assert result is True

            # Record should have trace context attributes added
            # (even if span context is empty, the filter still processes)
            assert hasattr(record, "trace_id")
            assert hasattr(record, "span_id")

        finally:
            # Clean up
            root_logger.removeFilter(injector)

    @pytest.mark.skipif(
        not _is_opentelemetry_available(),
        reason="OpenTelemetry not available"
    )
    def test_setup_log_export_with_signoz_disabled(self):
        """Test _setup_log_export returns early when Signoz is disabled."""
        from codetoreum.infrastructure.observability.otel_setup import _setup_log_export
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, DEPLOYMENT_ENVIRONMENT

        resource = Resource(
            attributes={
                SERVICE_NAME: "test_service",
                DEPLOYMENT_ENVIRONMENT: "test",
            }
        )

        signoz_config = SignozConfig(
            enabled=False,  # Disabled
            host="http://localhost",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="",
            service_name="test_service",
            environment="test",
            insecure=True,
        )

        config = ObservabilityConfig(
            enabled=True,
            traces_enabled=False,
            metrics_enabled=False,
            logs_enabled=True,  # Enabled
            signoz=signoz_config,
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

        root_logger = logging.getLogger()
        filters_before = len(root_logger.filters)

        # Call setup with Signoz disabled
        _setup_log_export(config, resource)

        # Filter count should not increase since Signoz is disabled
        filters_after = len(root_logger.filters)
        assert filters_after == filters_before, "Filter was added when signoz.enabled=False"
