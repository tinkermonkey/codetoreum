"""
Structured Logging Infrastructure

Provides centralized logging configuration with JSON formatting for production,
sensitive data scrubbing, and correlation ID support.
"""

import json
import logging
import os
import re
from contextvars import ContextVar
from typing import Any, Dict, Optional

# Context variable for correlation ID
correlation_id_context: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that scrubs sensitive data from log records.

    Removes or masks:
    - API keys, tokens, secrets
    - Passwords
    - Email addresses (partially masked)
    - Credit card numbers
    - Social security numbers
    - JWT tokens
    - Database connection strings
    - Private keys
    - Webhook URLs
    """

    # Default patterns for sensitive data
    DEFAULT_PATTERNS = [
        # API keys, tokens, secrets (various formats)
        (re.compile(r'(?i)(api[_-]?key|token|secret|password|passwd|pwd)[\s:=]+["\']?([^\s"\']+)["\']?'), r'\1=***REDACTED***'),
        # JWT tokens (starts with eyJ)
        (re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'), r'***REDACTED_JWT***'),
        # Bearer tokens
        (re.compile(r'(?i)bearer\s+([^\s]+)'), r'Bearer ***REDACTED***'),
        # Basic auth
        (re.compile(r'(?i)basic\s+([^\s]+)'), r'Basic ***REDACTED***'),
        # Email addresses (show first 2 chars + domain)
        (re.compile(r'\b([a-zA-Z0-9]{1,2})[a-zA-Z0-9._%+-]*@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'), r'\1***@\2'),
        # Credit card numbers
        (re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'), r'****-****-****-****'),
        # Social security numbers
        (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), r'***-**-****'),
        # AWS keys
        (re.compile(r'(?i)(AKIA|A3T|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}'), r'***REDACTED_AWS_KEY***'),
        # GitHub tokens
        (re.compile(r'ghp_[a-zA-Z0-9]{36}'), r'***REDACTED_GITHUB_TOKEN***'),
        # Database connection strings
        (re.compile(r'(?i)(postgres|mysql|mongodb|redis)://[^:]+:([^@]+)@'), r'\1://user:***REDACTED***@'),
        # Private keys
        (re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[^-]+-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----'), r'***REDACTED_PRIVATE_KEY***'),
        # Slack webhooks
        (re.compile(r'https://hooks\.slack\.com/services/[A-Z0-9/]+'), r'***REDACTED_SLACK_WEBHOOK***'),
        # Discord webhooks
        (re.compile(r'https://discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+'), r'***REDACTED_DISCORD_WEBHOOK***'),
        # Generic tokens
        (re.compile(r'(?i)(key|token|secret)["\']\s*:\s*["\']([^"\']{8,})["\']'), r'\1": "***REDACTED***"'),
    ]

    def __init__(self, custom_patterns: Optional[list] = None):
        """
        Initialize filter with optional custom patterns.

        Args:
            custom_patterns: Additional patterns to use for scrubbing (list of tuples: pattern, replacement)
        """
        super().__init__()
        self.patterns = self.DEFAULT_PATTERNS.copy()
        if custom_patterns:
            self.patterns.extend(custom_patterns)

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter and scrub sensitive data from log record.

        Args:
            record: Log record to filter

        Returns:
            True (always allows record through, just modifies it)
        """
        # Scrub message
        if record.msg:
            record.msg = self._scrub(str(record.msg))

        # Scrub args
        if record.args:
            record.args = tuple(
                self._scrub(str(arg)) if isinstance(arg, (str, bytes)) else arg
                for arg in record.args
            )

        return True

    def _scrub(self, text: str) -> str:
        """
        Scrub sensitive data from text using pattern matching.

        Args:
            text: Text to scrub

        Returns:
            Scrubbed text
        """
        for pattern, replacement in self.patterns:
            text = pattern.sub(replacement, text)
        return text


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging in production.

    Outputs logs in JSON format with standard fields:
    - timestamp
    - level
    - logger
    - message
    - correlation_id (if available)
    - Additional context fields
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if available
        correlation_id = correlation_id_context.get()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        return json.dumps(log_data)


class CorrelationIdFilter(logging.Filter):
    """
    Logging filter that adds correlation ID to log records.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add correlation ID to log record.

        Args:
            record: Log record to modify

        Returns:
            True (always allows record through)
        """
        correlation_id = correlation_id_context.get()
        record.correlation_id = correlation_id or "N/A"
        return True


def configure_logging(
    level: Optional[int] = None,
    json_format: bool = False,
    scrub_sensitive: bool = True,
    custom_patterns: Optional[list] = None,
) -> None:
    """
    Configure application logging with security best practices.

    Args:
        level: Logging level (defaults to INFO in production, DEBUG in development)
        json_format: Use JSON formatting for structured logs (recommended for production)
        scrub_sensitive: Enable sensitive data scrubbing (should always be True)
        custom_patterns: Additional patterns for sensitive data scrubbing (list of tuples: pattern, replacement)
    """
    try:
        # Determine environment
        env = os.getenv("CODETOREUM_ENV", "development")
        is_production = env == "production"

        # Set default level based on environment
        if level is None:
            level = logging.INFO if is_production else logging.DEBUG

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # Remove existing handlers
        root_logger.handlers.clear()

        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)

        # Set formatter
        if json_format:
            formatter = JSONFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        console_handler.setFormatter(formatter)

        # Add filters
        if scrub_sensitive:
            console_handler.addFilter(SensitiveDataFilter(custom_patterns=custom_patterns))

        console_handler.addFilter(CorrelationIdFilter())

        # Add handler to root logger
        root_logger.addHandler(console_handler)

        # Configure third-party loggers to be less verbose
        logging.getLogger("uvicorn").setLevel(logging.WARNING)
        logging.getLogger("fastapi").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    except Exception as e:
        # Fallback to basic configuration if structured logging fails
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        logging.error(f"Failed to configure structured logging, using basic config: {e}")


def set_correlation_id(correlation_id: str) -> None:
    """
    Set correlation ID for the current context.

    Args:
        correlation_id: Correlation ID to set
    """
    correlation_id_context.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """
    Get correlation ID from current context.

    Returns:
        Correlation ID or None
    """
    return correlation_id_context.get()


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
