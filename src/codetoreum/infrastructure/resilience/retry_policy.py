"""Production retry policy implementation.

Provides exponential backoff retry logic with jitter.
"""

import asyncio
import random
from collections.abc import Callable
from typing import TypeVar

from .exceptions import MaxRetriesExceededError
from .interfaces import IRetryPolicy, RetryStats

T = TypeVar("T")


class ExponentialBackoffRetry(IRetryPolicy):
    """
    Retry policy with exponential backoff and jitter.

    Implements industry-standard retry logic:
    - Exponential backoff: delay = base_delay * (exponential_base ^ attempt)
    - Jitter: Adds randomness to prevent thundering herd
    - Configurable max retries and max delay
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    ):
        """
        Initialize retry policy.

        Args:
            max_retries: Maximum retry attempts
            base_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential calculation
            jitter: Add random jitter to delays
            retryable_exceptions: Exceptions that should trigger retry
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions

        # Statistics
        self._total_attempts = 0
        self._total_retries = 0
        self._total_successes = 0
        self._total_failures = 0

    async def execute(
        self,
        operation: Callable[..., T],
        operation_name: str,
        *args,
        **kwargs
    ) -> T:
        """Execute operation with retry logic."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            self._total_attempts += 1

            try:
                result = await operation(*args, **kwargs)
                self._total_successes += 1
                return result

            except Exception as e:
                last_exception = e

                # Check if we should retry
                if not self.should_retry(e):
                    self._total_failures += 1
                    raise

                # Check if we've exhausted retries
                if attempt >= self.max_retries:
                    self._total_failures += 1
                    raise MaxRetriesExceededError(
                        f"Max retries ({self.max_retries}) exceeded for {operation_name}",
                        last_exception=e
                    ) from e

                # Calculate delay
                delay = self._calculate_delay(attempt)

                self._total_retries += 1

                # Log retry (would integrate with ILogger)
                # logger.warning(f"Retry {attempt + 1}/{self.max_retries} for {operation_name} after {delay:.2f}s")

                await asyncio.sleep(delay)

        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        raise MaxRetriesExceededError(f"Unexpected error in retry loop for {operation_name}")

    def should_retry(self, exception: BaseException) -> bool:
        """Determine if exception is retryable."""
        # Don't retry certain exceptions
        non_retryable = (
            KeyboardInterrupt,
            SystemExit,
        )

        if isinstance(exception, non_retryable):
            return False

        # Check if it's a retryable exception type
        return isinstance(exception, self.retryable_exceptions)

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt."""
        # Exponential backoff: delay = base * (exponential_base ^ attempt)
        delay = self.base_delay * (self.exponential_base ** attempt)

        # Cap at max delay
        delay = min(delay, self.max_delay)

        # Add jitter: random value between 0 and delay
        if self.jitter:
            delay = random.uniform(0, delay)

        return delay

    def get_stats(self) -> RetryStats:
        """Get retry statistics."""
        total_completed = self._total_successes + self._total_failures
        avg_attempts = (
            self._total_attempts / total_completed
            if total_completed > 0
            else 0
        )

        return RetryStats(
            total_attempts=self._total_attempts,
            total_retries=self._total_retries,
            total_successes=self._total_successes,
            total_failures=self._total_failures,
            average_attempts=avg_attempts
        )

    def reset(self) -> None:
        """Reset statistics."""
        self._total_attempts = 0
        self._total_retries = 0
        self._total_successes = 0
        self._total_failures = 0
