"""
Unit tests for secure logging infrastructure.
"""

import json
import logging
import os
from unittest.mock import patch

import pytest

from codetoreum.infrastructure.logging import (
    CorrelationIdFilter,
    JSONFormatter,
    SensitiveDataFilter,
    configure_logging,
    get_correlation_id,
    get_logger,
    set_correlation_id,
)


class TestSensitiveDataFilter:
    """Tests for sensitive data scrubbing."""

    def test_scrubs_api_keys(self):
        """Test that API keys are scrubbed from log messages."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="API_KEY=sk_test_12345678901234567890",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "sk_test_12345678901234567890" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_scrubs_passwords(self):
        """Test that passwords are scrubbed from log messages."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="password=SuperSecret123!",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "SuperSecret123!" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_scrubs_bearer_tokens(self):
        """Test that bearer tokens are scrubbed."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in record.msg
        assert "Bearer ***REDACTED***" in record.msg

    def test_masks_email_addresses(self):
        """Test that email addresses are partially masked."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User email: john.doe@example.com",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "john.doe@example.com" not in record.msg
        assert "@example.com" in record.msg
        assert "jo***@example.com" in record.msg

    def test_scrubs_credit_card_numbers(self):
        """Test that credit card numbers are scrubbed."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Card: 4532-1234-5678-9010",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "4532-1234-5678-9010" not in record.msg
        assert "****-****-****-****" in record.msg

    def test_scrubs_github_tokens(self):
        """Test that GitHub tokens are scrubbed."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="GitHub token: ghp_1234567890abcdefghijklmnopqrstuv",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "ghp_1234567890abcdefghijklmnopqrstuv" not in record.msg
        # GitHub token pattern should match and redact
        assert "***REDACTED" in record.msg

    def test_scrubs_aws_keys(self):
        """Test that AWS access keys are scrubbed."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "AKIAIOSFODNN7EXAMPLE" not in record.msg
        assert "***REDACTED_AWS_KEY***" in record.msg

    def test_scrubs_json_secrets(self):
        """Test that secrets in JSON format are scrubbed."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='{"api_key": "sk_test_1234567890abcdef", "user": "john"}',
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "sk_test_1234567890abcdef" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_preserves_non_sensitive_data(self):
        """Test that non-sensitive data is not modified."""
        filter_obj = SensitiveDataFilter()
        original_msg = "Processing request for user ID 12345"
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=original_msg,
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert record.msg == original_msg

    def test_scrubs_jwt_tokens(self):
        """Test that JWT tokens are scrubbed from log messages."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_scrubs_database_connection_strings(self):
        """Test that database connection strings are scrubbed."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Connecting to postgres://admin:secret_password@localhost:5432/mydb",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "secret_password" not in record.msg
        assert "postgres://user:***REDACTED***@" in record.msg

    def test_scrubs_private_keys(self):
        """Test that private keys are scrubbed."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Private key: -----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "BEGIN RSA PRIVATE KEY" not in record.msg or "***REDACTED_PRIVATE_KEY***" in record.msg

    def test_scrubs_slack_webhooks(self):
        """Test that Slack webhooks are scrubbed."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Webhook URL: https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "T00000000/B00000000" not in record.msg
        assert "***REDACTED_SLACK_WEBHOOK***" in record.msg

    def test_scrubs_discord_webhooks(self):
        """Test that Discord webhooks are scrubbed."""
        filter_obj = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Discord: https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz123456",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "123456789012345678" not in record.msg or "***REDACTED_DISCORD_WEBHOOK***" in record.msg

    def test_custom_patterns(self):
        """Test that custom patterns can be added."""
        import re

        custom_patterns = [
            (re.compile(r'customer_id=(\d+)'), r'customer_id=***'),
        ]
        filter_obj = SensitiveDataFilter(custom_patterns=custom_patterns)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Processing order for customer_id=12345",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert "customer_id=12345" not in record.msg
        assert "customer_id=***" in record.msg


class TestJSONFormatter:
    """Tests for JSON log formatting."""

    def test_formats_log_as_json(self):
        """Test that logs are formatted as valid JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)

        # Should be valid JSON
        log_data = json.loads(result)
        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test.logger"
        assert log_data["message"] == "Test message"
        assert "timestamp" in log_data

    def test_includes_correlation_id(self):
        """Test that correlation ID is included when available."""
        formatter = JSONFormatter()
        correlation_id = "test-correlation-id-123"
        set_correlation_id(correlation_id)

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        assert log_data["correlation_id"] == correlation_id

    def test_includes_exception_info(self):
        """Test that exception info is included."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = formatter.format(record)
        log_data = json.loads(result)

        assert "exception" in log_data
        assert "ValueError: Test error" in log_data["exception"]


class TestCorrelationIdFilter:
    """Tests for correlation ID filter."""

    def test_adds_correlation_id_to_record(self):
        """Test that correlation ID is added to log record."""
        filter_obj = CorrelationIdFilter()
        correlation_id = "test-id-456"
        set_correlation_id(correlation_id)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert hasattr(record, "correlation_id")
        assert record.correlation_id == correlation_id

    def test_handles_missing_correlation_id(self):
        """Test that missing correlation ID is handled gracefully."""
        filter_obj = CorrelationIdFilter()
        set_correlation_id(None)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)

        assert result is True
        assert hasattr(record, "correlation_id")
        assert record.correlation_id == "N/A"


class TestLoggingConfiguration:
    """Tests for logging configuration."""

    @patch.dict(os.environ, {"CODETOREUM_ENV": "development"}, clear=False)
    def test_configure_logging_development(self):
        """Test logging configuration for development environment."""
        configure_logging()

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    @patch.dict(os.environ, {"CODETOREUM_ENV": "production"}, clear=False)
    def test_configure_logging_production(self):
        """Test logging configuration for production environment."""
        configure_logging()

        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO

    def test_configure_logging_custom_level(self):
        """Test logging configuration with custom level."""
        configure_logging(level=logging.WARNING)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

    def test_configure_logging_json_format(self):
        """Test logging configuration with JSON format."""
        configure_logging(json_format=True)

        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
        handler = root_logger.handlers[0]
        assert isinstance(handler.formatter, JSONFormatter)

    def test_configure_logging_scrubbing_enabled(self):
        """Test that sensitive data scrubbing is enabled by default."""
        configure_logging(scrub_sensitive=True)

        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]

        # Check that SensitiveDataFilter is in the filter chain
        has_sensitive_filter = any(
            isinstance(f, SensitiveDataFilter) for f in handler.filters
        )
        assert has_sensitive_filter


class TestCorrelationIdContextManagement:
    """Tests for correlation ID context management."""

    def test_set_and_get_correlation_id(self):
        """Test setting and getting correlation ID."""
        correlation_id = "test-correlation-789"
        set_correlation_id(correlation_id)

        result = get_correlation_id()
        assert result == correlation_id

    def test_get_correlation_id_when_not_set(self):
        """Test getting correlation ID when not set."""
        set_correlation_id(None)

        result = get_correlation_id()
        assert result is None


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a logger instance."""
        logger = get_logger("test.module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_get_logger_same_name_returns_same_instance(self):
        """Test that get_logger returns same instance for same name."""
        logger1 = get_logger("test.module")
        logger2 = get_logger("test.module")

        assert logger1 is logger2
