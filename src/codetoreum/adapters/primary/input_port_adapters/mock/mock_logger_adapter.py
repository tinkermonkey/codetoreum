"""Mock Logger Interface Adapter for FastAPI.

This adapter provides a simple logger interface for the FastAPI application layer.
"""

import logging

from codetoreum.infrastructure.error_ids import ErrorRegistry

logger = logging.getLogger(__name__)


class MockLoggerAdapter:
    """
    Mock logger interface adapter.

    Provides a simple logging interface for FastAPI, delegating to Python's
    standard logging module.
    """

    def info(self, message: str) -> None:
        """Log info level message."""
        logger.info(message)

    def warning(self, message: str) -> None:
        """Log warning level message."""
        logger.warning(message)

    def error(self, message: str) -> None:
        """Log error level message."""
        logger.error(message, extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR})

    def debug(self, message: str) -> None:
        """Log debug level message."""
        logger.debug(message)
