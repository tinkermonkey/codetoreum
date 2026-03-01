"""Production timeout implementation.

Provides async timeout handling using asyncio.wait_for.
"""

import asyncio
import time
from collections.abc import Callable
from typing import TypeVar

from .exceptions import TimeoutError as ResilienceTimeoutError
from .interfaces import ITimeout, TimeoutStats

T = TypeVar("T")


class AsyncTimeout(ITimeout):
    """
    Async timeout implementation using asyncio.wait_for.

    Prevents operations from hanging indefinitely.
    """

    def __init__(self):
        self._total_operations = 0
        self._total_timeouts = 0
        self._durations: list[float] = []

    async def execute(
        self,
        operation: Callable[..., T],
        timeout_seconds: float,
        operation_name: str,
        *args,
        **kwargs,
    ) -> T:
        """Execute operation with timeout."""
        self._total_operations += 1
        start_time = time.time()

        try:
            result = await asyncio.wait_for(operation(*args, **kwargs), timeout=timeout_seconds)

            duration = (time.time() - start_time) * 1000  # Convert to ms
            self._durations.append(duration)

            return result

        except TimeoutError:
            self._total_timeouts += 1
            message = f"Operation {operation_name} exceeded timeout of {timeout_seconds}s"
            raise ResilienceTimeoutError(message)

    def get_stats(self) -> TimeoutStats:
        """Get timeout statistics."""
        avg_duration = sum(self._durations) / len(self._durations) if self._durations else 0
        max_duration = max(self._durations) if self._durations else 0

        return TimeoutStats(
            total_operations=self._total_operations,
            total_timeouts=self._total_timeouts,
            average_duration_ms=avg_duration,
            max_duration_ms=max_duration,
        )
