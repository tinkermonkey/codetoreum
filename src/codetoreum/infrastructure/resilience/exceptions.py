"""Resilience infrastructure exceptions.

Provides a hierarchy of exceptions for resilience-related errors.
"""

from typing import Optional


class ResilienceError(Exception):
    """Base exception for resilience infrastructure."""
    pass


class RateLimitExceededError(ResilienceError):
    """Raised when rate limit exceeded and max wait exceeded."""

    def __init__(self, message: str, retry_after_seconds: Optional[float] = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class CircuitBreakerOpenError(ResilienceError):
    """Raised when circuit breaker is open."""

    def __init__(self, message: str, retry_after_seconds: Optional[float] = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class MaxRetriesExceededError(ResilienceError):
    """Raised when all retry attempts exhausted."""

    def __init__(self, message: str, last_exception: Optional[Exception] = None):
        super().__init__(message)
        self.last_exception = last_exception


class TimeoutError(ResilienceError):
    """Raised when operation exceeds timeout."""
    pass
