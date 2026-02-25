"""Production circuit breaker implementation.

Provides circuit breaker pattern with CLOSED/OPEN/HALF_OPEN states.
"""

import asyncio
import time
from collections.abc import Callable
from datetime import datetime
from typing import TypeVar

from .exceptions import CircuitBreakerOpenError
from .interfaces import CircuitBreakerStats, CircuitState, ICircuitBreaker

T = TypeVar("T")


class CircuitBreaker(ICircuitBreaker):
    """
    Circuit breaker with half-open state for recovery testing.

    State transitions:
    - CLOSED -> OPEN: After failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After timeout_seconds elapsed
    - HALF_OPEN -> CLOSED: After success_threshold consecutive successes
    - HALF_OPEN -> OPEN: On any failure
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: float = 60,
        success_threshold: int = 2,
        expected_exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Failures before opening circuit
            timeout_seconds: Time before attempting recovery (HALF_OPEN)
            success_threshold: Successes needed to close circuit from HALF_OPEN
            expected_exceptions: Exceptions that trigger circuit breaker
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold
        self.expected_exceptions = expected_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._last_success_time: float | None = None

        # Statistics
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0

        self._lock = asyncio.Lock()

    async def call(self, operation: Callable[..., T], operation_name: str, *args, **kwargs) -> T:
        """Execute operation with circuit breaker protection."""
        async with self._lock:
            self._total_calls += 1

            # Check if circuit should transition to HALF_OPEN
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    message = (
                        f"Circuit breaker open for {operation_name}. Will retry in {self._time_until_retry():.1f}s"
                    )
                    raise CircuitBreakerOpenError(message, retry_after_seconds=self._time_until_retry())

        # Execute operation (outside lock to avoid holding during I/O)
        try:
            result = await operation(*args, **kwargs)

            # Handle success
            async with self._lock:
                self._on_success()

            return result

        except self.expected_exceptions:
            # Handle failure
            async with self._lock:
                self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.timeout_seconds

    def _time_until_retry(self) -> float:
        """Calculate time until next retry attempt."""
        if self._last_failure_time is None:
            return 0
        elapsed = time.time() - self._last_failure_time
        return max(0, self.timeout_seconds - elapsed)

    def _on_success(self) -> None:
        """Handle successful operation."""
        self._last_success_time = time.time()
        self._total_successes += 1

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                # Recovered! Close the circuit
                self._state = CircuitState.CLOSED
                self._failure_count = 0
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0

    def _on_failure(self) -> None:
        """Handle failed operation."""
        self._last_failure_time = time.time()
        self._total_failures += 1
        self._failure_count += 1

        if self._state == CircuitState.HALF_OPEN:
            # Failed during recovery - reopen circuit
            self._state = CircuitState.OPEN
        elif self._state == CircuitState.CLOSED:
            # Check if we should open circuit
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    def get_stats(self) -> CircuitBreakerStats:
        """Get statistics."""
        return CircuitBreakerStats(
            state=self._state,
            failure_count=self._failure_count,
            success_count=self._success_count,
            last_failure_time=datetime.fromtimestamp(self._last_failure_time) if self._last_failure_time else None,
            last_success_time=datetime.fromtimestamp(self._last_success_time) if self._last_success_time else None,
            total_calls=self._total_calls,
            total_failures=self._total_failures,
            total_successes=self._total_successes,
        )

    def reset(self) -> None:
        """Reset to initial state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._last_success_time = None

    def force_open(self) -> None:
        """Manually open circuit."""
        self._state = CircuitState.OPEN
        self._last_failure_time = time.time()

    def force_close(self) -> None:
        """Manually close circuit."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
