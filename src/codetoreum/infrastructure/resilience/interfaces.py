"""Resilience component interfaces.

Provides abstract base classes for rate limiting, circuit breaking,
retry policies, and timeout handling.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TypeVar

T = TypeVar("T")


# ============================================================================
# Rate Limiter
# ============================================================================


@dataclass
class RateLimitStats:
    """Rate limiter statistics."""

    requests_in_window: int
    tokens_in_window: int
    max_requests: int
    max_tokens: int | None
    window_seconds: int
    utilization: float  # 0.0 to 1.0
    next_available: datetime | None


class IRateLimiter(ABC):
    """
    Rate limiter abstraction.

    Prevents exceeding external API rate limits.
    Supports both request-based and token-based limiting.
    """

    @abstractmethod
    async def acquire(self, operation: str, cost: int = 1) -> None:
        """
        Wait until operation can proceed within rate limits.

        Args:
            operation: Operation name (for logging/metrics)
            cost: Cost in tokens/requests (default 1)

        Raises:
            RateLimitExceededError: If limit exceeded and wait would be too long
        """

    @abstractmethod
    def try_acquire(self, operation: str, cost: int = 1) -> bool:
        """
        Try to acquire without blocking.

        Returns:
            True if acquired, False if would exceed limit
        """

    @abstractmethod
    def get_stats(self) -> RateLimitStats:
        """Get current rate limit statistics."""

    @abstractmethod
    def reset(self) -> None:
        """Reset rate limiter state (for testing)."""


# ============================================================================
# Circuit Breaker
# ============================================================================


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""

    state: CircuitState
    failure_count: int
    success_count: int
    last_failure_time: datetime | None
    last_success_time: datetime | None
    total_calls: int
    total_failures: int
    total_successes: int


class ICircuitBreaker(ABC):
    """
    Circuit breaker abstraction.

    Prevents cascading failures by failing fast when
    downstream service is unhealthy.
    """

    @abstractmethod
    async def call(self, operation: Callable[..., T], operation_name: str, *args, **kwargs) -> T:
        """
        Execute operation with circuit breaker protection.

        Args:
            operation: Async function to execute
            operation_name: Operation name (for logging)
            *args, **kwargs: Passed to operation

        Returns:
            Result from operation

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Original exception: If operation fails
        """

    @abstractmethod
    def get_state(self) -> CircuitState:
        """Get current circuit state."""

    @abstractmethod
    def get_stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""

    @abstractmethod
    def reset(self) -> None:
        """Reset circuit breaker (for testing)."""

    @abstractmethod
    def force_open(self) -> None:
        """Manually open circuit (for maintenance)."""

    @abstractmethod
    def is_open(self) -> bool:
        """Return True if the circuit is currently open (rejecting calls)."""

    @abstractmethod
    def force_close(self) -> None:
        """Manually close circuit (for recovery)."""


# ============================================================================
# Retry Policy
# ============================================================================


@dataclass
class RetryStats:
    """Retry policy statistics."""

    total_attempts: int
    total_retries: int
    total_successes: int
    total_failures: int
    average_attempts: float


class IRetryPolicy(ABC):
    """
    Retry policy abstraction.

    Handles transient failures with configurable backoff strategies.
    """

    @abstractmethod
    async def execute(self, operation: Callable[..., T], operation_name: str, *args, **kwargs) -> T:
        """
        Execute operation with retry logic.

        Args:
            operation: Async function to execute
            operation_name: Operation name (for logging)
            *args, **kwargs: Passed to operation

        Returns:
            Result from operation

        Raises:
            MaxRetriesExceededError: If all retries exhausted
            Original exception: From last retry attempt
        """

    @abstractmethod
    def should_retry(self, exception: BaseException) -> bool:
        """
        Determine if exception is retryable.

        Args:
            exception: Exception that occurred

        Returns:
            True if should retry, False otherwise
        """

    @abstractmethod
    def get_stats(self) -> RetryStats:
        """Get retry statistics."""

    @abstractmethod
    def reset(self) -> None:
        """Reset retry statistics (for testing)."""


# ============================================================================
# Timeout
# ============================================================================


@dataclass
class TimeoutStats:
    """Timeout statistics."""

    total_operations: int
    total_timeouts: int
    average_duration_ms: float
    max_duration_ms: float


class ITimeout(ABC):
    """
    Timeout abstraction.

    Prevents operations from hanging indefinitely.
    """

    @abstractmethod
    async def execute(
        self,
        operation: Callable[..., T],
        timeout_seconds: float,
        operation_name: str,
        *args,
        **kwargs,
    ) -> T:
        """
        Execute operation with timeout.

        Args:
            operation: Async function to execute
            timeout_seconds: Timeout in seconds
            operation_name: Operation name (for logging)
            *args, **kwargs: Passed to operation

        Returns:
            Result from operation

        Raises:
            TimeoutError: If operation exceeds timeout
        """

    @abstractmethod
    def get_stats(self) -> TimeoutStats:
        """Get timeout statistics."""
