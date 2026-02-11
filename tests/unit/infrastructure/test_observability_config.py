"""
Unit tests for OpenTelemetry observability configuration.

Tests the configuration loading from environment variables, fallback behavior,
and validation for signal-specific endpoints.
"""

import os
import pytest
from unittest import mock

from codetoreum.infrastructure.observability.config import (
    ObservabilityConfig,
    SignozConfig,
)


class TestSignozConfig:
    """Tests for SignozConfig."""

    def test_grpc_endpoint_with_http_prefix(self):
        """Test gRPC endpoint strips http:// prefix."""
        config = SignozConfig(
            enabled=True,
            host="http://localhost",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="test_key",
            service_name="test_service",
            environment="development",
            insecure=True,
        )
        assert config.grpc_endpoint == "localhost:4317"

    def test_grpc_endpoint_with_https_prefix(self):
        """Test gRPC endpoint strips https:// prefix."""
        config = SignozConfig(
            enabled=True,
            host="https://signoz.example.com",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="test_key",
            service_name="test_service",
            environment="development",
            insecure=False,
        )
        assert config.grpc_endpoint == "signoz.example.com:4317"

    def test_http_endpoint(self):
        """Test HTTP endpoint construction."""
        config = SignozConfig(
            enabled=True,
            host="http://localhost",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="test_key",
            service_name="test_service",
            environment="development",
            insecure=True,
        )
        assert config.http_endpoint == "http://localhost:4318"

    def test_logs_endpoint(self):
        """Test logs endpoint construction with /v1/logs path."""
        config = SignozConfig(
            enabled=True,
            host="http://localhost",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="test_key",
            service_name="test_service",
            environment="development",
            insecure=True,
        )
        assert config.logs_endpoint == "http://localhost:4318/v1/logs"

    def test_from_env_defaults(self):
        """Test SignozConfig.from_env uses defaults."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = SignozConfig.from_env()
            assert config.enabled is False
            assert config.host == "http://localhost"
            assert config.grpc_port == 4317
            assert config.http_port == 4318
            assert config.ui_port == 8900
            assert config.service_name == "codetoreum"
            assert config.insecure is True


class TestObservabilityConfigEndpoints:
    """Tests for ObservabilityConfig endpoint properties."""

    def test_traces_endpoint_uses_env_variable(self):
        """Test traces_endpoint returns OTEL_EXPORTER_OTLP_TRACES_ENDPOINT if set."""
        signoz_config = SignozConfig(
            enabled=True,
            host="http://localhost",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="",
            service_name="codetoreum",
            environment="development",
            insecure=True,
        )

        with mock.patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "custom.host:4317"},
        ):
            config = ObservabilityConfig(
                enabled=True,
                traces_enabled=True,
                metrics_enabled=False,
                logs_enabled=False,
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
            assert config.traces_endpoint == "custom.host:4317"

    def test_traces_endpoint_falls_back_to_signoz_grpc(self):
        """Test traces_endpoint falls back to signoz.grpc_endpoint when env var not set."""
        signoz_config = SignozConfig(
            enabled=True,
            host="http://signoz.local",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="",
            service_name="codetoreum",
            environment="development",
            insecure=True,
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            config = ObservabilityConfig(
                enabled=True,
                traces_enabled=True,
                metrics_enabled=False,
                logs_enabled=False,
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
            assert config.traces_endpoint == "signoz.local:4317"

    def test_logs_endpoint_uses_env_variable(self):
        """Test logs_endpoint returns OTEL_EXPORTER_OTLP_LOGS_ENDPOINT if set."""
        signoz_config = SignozConfig(
            enabled=True,
            host="http://localhost",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="",
            service_name="codetoreum",
            environment="development",
            insecure=True,
        )

        with mock.patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://custom.host:4318/v1/logs"},
        ):
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
            assert config.logs_endpoint == "http://custom.host:4318/v1/logs"

    def test_logs_endpoint_falls_back_to_signoz_logs(self):
        """Test logs_endpoint falls back to signoz.logs_endpoint when env var not set."""
        signoz_config = SignozConfig(
            enabled=True,
            host="http://signoz.local",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="",
            service_name="codetoreum",
            environment="development",
            insecure=True,
        )

        with mock.patch.dict(os.environ, {}, clear=True):
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
            assert config.logs_endpoint == "http://signoz.local:4318/v1/logs"

    def test_both_endpoints_can_be_independent(self):
        """Test that traces and logs endpoints can be independently configured."""
        signoz_config = SignozConfig(
            enabled=True,
            host="http://localhost",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="",
            service_name="codetoreum",
            environment="development",
            insecure=True,
        )

        env = {
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "traces.host:4317",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://logs.host:4318/v1/logs",
        }

        with mock.patch.dict(os.environ, env):
            config = ObservabilityConfig(
                enabled=True,
                traces_enabled=True,
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
            assert config.traces_endpoint == "traces.host:4317"
            assert config.logs_endpoint == "http://logs.host:4318/v1/logs"


class TestObservabilityConfigValidation:
    """Tests for ObservabilityConfig validation."""

    def test_validate_no_warning_when_traces_enabled_with_endpoint(self):
        """Test no warning when traces are enabled and endpoint is configured."""
        signoz_config = SignozConfig(
            enabled=True,
            host="http://localhost",
            grpc_port=4317,
            http_port=4318,
            ui_port=8900,
            api_key="",
            service_name="codetoreum",
            environment="development",
            insecure=True,
        )

        config = ObservabilityConfig(
            enabled=True,
            traces_enabled=True,
            metrics_enabled=False,
            logs_enabled=False,
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

        with mock.patch(
            "codetoreum.infrastructure.observability.config.logger"
        ) as mock_logger:
            config.validate()
            mock_logger.warning.assert_not_called()

    def test_validate_logs_warning_when_traces_enabled_without_endpoint(self):
        """Test warning is logged when traces enabled but endpoint not configured."""
        # Create a mock SignozConfig with empty grpc_endpoint
        signoz_config = mock.MagicMock(spec=SignozConfig)
        signoz_config.grpc_endpoint = ""
        signoz_config.logs_endpoint = "http://localhost:4318/v1/logs"

        config = ObservabilityConfig(
            enabled=True,
            traces_enabled=True,
            metrics_enabled=False,
            logs_enabled=False,
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

        with mock.patch(
            "codetoreum.infrastructure.observability.config.logger"
        ) as mock_logger:
            config.validate()
            mock_logger.warning.assert_called_once()
            assert "Traces enabled" in mock_logger.warning.call_args[0][0]

    def test_validate_logs_warning_when_logs_enabled_without_endpoint(self):
        """Test warning is logged when logs enabled but endpoint not configured."""
        signoz_config = mock.MagicMock(spec=SignozConfig)
        signoz_config.grpc_endpoint = "localhost:4317"
        signoz_config.logs_endpoint = ""

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

        with mock.patch(
            "codetoreum.infrastructure.observability.config.logger"
        ) as mock_logger:
            config.validate()
            mock_logger.warning.assert_called_once()
            assert "Logs enabled" in mock_logger.warning.call_args[0][0]

    def test_validate_logs_warnings_for_both_signals(self):
        """Test warnings for both traces and logs when endpoints not configured."""
        signoz_config = mock.MagicMock(spec=SignozConfig)
        signoz_config.grpc_endpoint = ""
        signoz_config.logs_endpoint = ""

        config = ObservabilityConfig(
            enabled=True,
            traces_enabled=True,
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

        with mock.patch(
            "codetoreum.infrastructure.observability.config.logger"
        ) as mock_logger:
            config.validate()
            assert mock_logger.warning.call_count == 2


class TestObservabilityConfigFromEnv:
    """Tests for ObservabilityConfig.from_env()."""

    def test_from_env_parses_signal_endpoints(self):
        """Test from_env correctly parses signal-specific endpoint environment variables."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_TRACES_ENABLED": "true",
            "OTEL_LOGS_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "traces.example.com:4317",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://logs.example.com:4318/v1/logs",
            "SIGNOZ_ENABLED": "true",
            "SIGNOZ_HOST": "http://localhost",
        }

        with mock.patch.dict(os.environ, env):
            config = ObservabilityConfig.from_env()
            assert config.traces_endpoint == "traces.example.com:4317"
            assert config.logs_endpoint == "http://logs.example.com:4318/v1/logs"

    def test_from_env_falls_back_when_no_signal_endpoints(self):
        """Test from_env falls back to SignozConfig when signal endpoints not set."""
        env = {
            "OTEL_ENABLED": "true",
            "OTEL_TRACES_ENABLED": "true",
            "OTEL_LOGS_ENABLED": "true",
            "SIGNOZ_ENABLED": "true",
            "SIGNOZ_HOST": "http://signoz.example.com",
            "SIGNOZ_GRPC_PORT": "4317",
            "SIGNOZ_HTTP_PORT": "4318",
        }

        with mock.patch.dict(os.environ, env, clear=True):
            config = ObservabilityConfig.from_env()
            assert config.traces_endpoint == "signoz.example.com:4317"
            assert config.logs_endpoint == "http://signoz.example.com:4318/v1/logs"

    def test_from_env_defaults(self):
        """Test from_env uses defaults when environment variables not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = ObservabilityConfig.from_env()
            assert config.enabled is True
            assert config.traces_enabled is True
            assert config.logs_enabled is False
            assert config.traces_endpoint == "localhost:4317"
            assert config.logs_endpoint == "http://localhost:4318/v1/logs"
