"""Mock resilience components for simulation and testing.

Provides mock implementations that track calls but don't add delays,
enabling fast simulation tests.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from .exceptions import CircuitBreakerOpenError
from .exceptions import TimeoutError as ResilienceTimeoutError
from .interfaces import (
    CircuitBreakerStats,
    CircuitState,
    ICircuitBreaker,
    IRateLimiter,
    IRetryPolicy,
    ITimeout,
    RateLimitStats,
    RetryStats,
    TimeoutStats,
)
from .rate_limiter import TokenBucketRateLimiter
from .retry_policy import ExponentialBackoffRetry

T = TypeVar('T')


# ============================================================================
# Mock Rate Limiter
# ============================================================================

class MockRateLimiter(IRateLimiter):
    """
    Mock rate limiter for simulation and testing.

    - No actual delays (fast testing)
    - Records all acquire calls for assertions
    - Optionally enforces limits for integration testing
    """

    def __init__(self, enforce_limits: bool = False, simulated_delay_ms: float = 0):
        """
        Initialize mock rate limiter.

        Args:
            enforce_limits: If True, actually enforces rate limits (for integration tests)
            simulated_delay_ms: Simulated delay for realism (milliseconds)
        """
        self.enforce_limits = enforce_limits
        self.simulated_delay_ms = simulated_delay_ms

        self.acquire_calls: List[Tuple[str, int, datetime]] = []
        self._delegate: Optional[IRateLimiter] = None

        if enforce_limits:
            # Delegate to real implementation
            self._delegate = TokenBucketRateLimiter(
                max_requests=1000,
                window_seconds=60
            )

    async def acquire(self, operation: str, cost: int = 1) -> None:
        """Record acquire call and optionally enforce limits."""
        self.acquire_calls.append((operation, cost, datetime.now(timezone.utc)))

        if self._delegate:
            await self._delegate.acquire(operation, cost)
        elif self.simulated_delay_ms > 0:
            await asyncio.sleep(self.simulated_delay_ms / 1000)

    def try_acquire(self, operation: str, cost: int = 1) -> bool:
        """Always succeeds in mock mode."""
        self.acquire_calls.append((operation, cost, datetime.now(timezone.utc)))

        if self._delegate:
            return self._delegate.try_acquire(operation, cost)
        return True

    def get_stats(self) -> RateLimitStats:
        """Return mock stats."""
        if self._delegate:
            return self._delegate.get_stats()

        return RateLimitStats(
            requests_in_window=len(self.acquire_calls),
            tokens_in_window=sum(cost for _, cost, _ in self.acquire_calls),
            max_requests=9999,
            max_tokens=None,
            window_seconds=60,
            utilization=0.0,
            next_available=None
        )

    def reset(self) -> None:
        """Clear call history."""
        self.acquire_calls.clear()
        if self._delegate:
            self._delegate.reset()

    # Test helpers
    def assert_acquired(self, operation: str, min_count: int = 1) -> None:
        """Assert operation was acquired at least min_count times."""
        count = sum(1 for op, _, _ in self.acquire_calls if op == operation)
        assert count >= min_count, f"Expected {operation} to be acquired at least {min_count} times, got {count}"


# ============================================================================
# Mock Circuit Breaker
# ============================================================================

class MockCircuitBreaker(ICircuitBreaker):
    """
    Mock circuit breaker for simulation and testing.

    - Configurable state for testing different scenarios
    - Records all calls for assertions
    - Can simulate failures
    """

    def __init__(
        self,
        initial_state: CircuitState = CircuitState.CLOSED,
        fail_after_calls: Optional[int] = None
    ):
        """
        Initialize mock circuit breaker.

        Args:
            initial_state: Starting state
            fail_after_calls: If set, open circuit after this many calls
        """
        self._state = initial_state
        self.fail_after_calls = fail_after_calls

        self.call_history: List[Dict[str, Any]] = []
        self._call_count = 0

    async def call(
        self,
        operation: Callable[..., T],
        operation_name: str,
        *args,
        **kwargs
    ) -> T:
        """Execute with configurable behavior."""
        self._call_count += 1

        self.call_history.append({
            "operation": operation_name,
            "state": self._state,
            "timestamp": datetime.now(timezone.utc),
            "call_number": self._call_count
        })

        # Check state first
        if self._state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(f"Circuit open: {operation_name}")

        # Execute operation
        result = await operation(*args, **kwargs)

        # Simulate opening circuit after N successful calls
        if self.fail_after_calls and self._call_count >= self.fail_after_calls:
            self._state = CircuitState.OPEN

        return result

    def get_state(self) -> CircuitState:
        """Get current state."""
        return self._state

    def get_stats(self) -> CircuitBreakerStats:
        """Return mock stats."""
        return CircuitBreakerStats(
            state=self._state,
            failure_count=0,
            success_count=self._call_count,
            last_failure_time=None,
            last_success_time=datetime.now(timezone.utc),
            total_calls=self._call_count,
            total_failures=0,
            total_successes=self._call_count
        )

    def reset(self) -> None:
        """Reset state."""
        self._state = CircuitState.CLOSED
        self.call_history.clear()
        self._call_count = 0

    def force_open(self) -> None:
        """Force circuit open."""
        self._state = CircuitState.OPEN

    def force_close(self) -> None:
        """Force circuit closed."""
        self._state = CircuitState.CLOSED

    # Test helpers
    def set_state(self, state: CircuitState) -> None:
        """Set circuit state for testing."""
        self._state = state

    def assert_called(self, operation: str, min_count: int = 1) -> None:
        """Assert operation was called."""
        count = sum(1 for call in self.call_history if call["operation"] == operation)
        assert count >= min_count, f"Expected {operation} to be called at least {min_count} times, got {count}"


# ============================================================================
# Mock Retry Policy
# ============================================================================

class MockRetryPolicy(IRetryPolicy):
    """
    Mock retry policy for simulation and testing.

    - No actual retries (fast testing)
    - Records retry attempts
    - Configurable to simulate retry behavior
    """

    def __init__(
        self,
        simulate_retries: bool = False,
        max_retries: int = 3
    ):
        """
        Initialize mock retry policy.

        Args:
            simulate_retries: If True, actually performs retries
            max_retries: Max retries if simulating
        """
        self.simulate_retries = simulate_retries
        self.max_retries = max_retries

        self.execution_history: List[Dict[str, Any]] = []
        self._delegate: Optional[IRetryPolicy] = None

        if simulate_retries:
            self._delegate = ExponentialBackoffRetry(
                max_retries=max_retries,
                base_delay=0.01  # Very short delays for testing
            )

    async def execute(
        self,
        operation: Callable[..., T],
        operation_name: str,
        *args,
        **kwargs
    ) -> T:
        """Execute with optional retry simulation."""
        self.execution_history.append({
            "operation": operation_name,
            "timestamp": datetime.now(timezone.utc)
        })

        if self._delegate:
            return await self._delegate.execute(operation, operation_name, *args, **kwargs)
        else:
            # No retries, just execute once
            return await operation(*args, **kwargs)

    def should_retry(self, exception: Exception) -> bool:
        """Always returns True in mock mode."""
        return True

    def get_stats(self) -> RetryStats:
        """Return mock stats."""
        if self._delegate:
            return self._delegate.get_stats()

        return RetryStats(
            total_attempts=len(self.execution_history),
            total_retries=0,
            total_successes=len(self.execution_history),
            total_failures=0,
            average_attempts=1.0
        )

    def reset(self) -> None:
        """Reset history."""
        self.execution_history.clear()
        if self._delegate:
            self._delegate.reset()


# ============================================================================
# Mock Timeout
# ============================================================================

class MockTimeout(ITimeout):
    """
    Mock timeout for simulation and testing.

    - No actual timeouts (operations run to completion)
    - Records all timed operations
    - Configurable to simulate timeout errors
    """

    def __init__(self, simulate_timeouts: bool = False):
        """
        Initialize mock timeout.

        Args:
            simulate_timeouts: If True, actually enforces timeouts
        """
        self.simulate_timeouts = simulate_timeouts
        self.execution_history: List[Dict[str, Any]] = []

    async def execute(
        self,
        operation: Callable[..., T],
        timeout_seconds: float,
        operation_name: str,
        *args,
        **kwargs
    ) -> T:
        """Execute with optional timeout enforcement."""
        start_time = time.time()

        if self.simulate_timeouts:
            # Actually enforce timeout
            try:
                result = await asyncio.wait_for(
                    operation(*args, **kwargs),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                duration = time.time() - start_time
                self.execution_history.append({
                    "operation": operation_name,
                    "timeout_seconds": timeout_seconds,
                    "duration_seconds": duration,
                    "timed_out": True
                })
                raise ResilienceTimeoutError(f"Operation {operation_name} timed out")
        else:
            # No timeout, just execute
            result = await operation(*args, **kwargs)

        duration = time.time() - start_time
        self.execution_history.append({
            "operation": operation_name,
            "timeout_seconds": timeout_seconds,
            "duration_seconds": duration,
            "timed_out": False
        })

        return result

    def get_stats(self) -> TimeoutStats:
        """Return mock stats."""
        timeouts = sum(1 for ex in self.execution_history if ex["timed_out"])
        durations = [ex["duration_seconds"] * 1000 for ex in self.execution_history]

        return TimeoutStats(
            total_operations=len(self.execution_history),
            total_timeouts=timeouts,
            average_duration_ms=sum(durations) / len(durations) if durations else 0,
            max_duration_ms=max(durations) if durations else 0
        )
