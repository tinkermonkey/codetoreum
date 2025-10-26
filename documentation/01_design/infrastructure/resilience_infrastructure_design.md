# Infrastructure Resilience Layer - Detailed Design

## Overview

This document defines the **infrastructure resilience layer** that provides cross-cutting concerns for all external system integrations in Codetoreum. These capabilities are centralized, reusable, and work with any adapter through the decorator pattern.

## Purpose

Provide production-grade resilience patterns that:
1. **Prevent cascading failures** (circuit breakers)
2. **Respect API rate limits** (rate limiters)
3. **Handle transient errors** (retry policies)
4. **Prevent hung operations** (timeouts)
5. **Enable observability** (metrics and monitoring)
6. **Support simulation testing** (mock implementations)

## Architecture Position

In hexagonal architecture, resilience concerns live in the **infrastructure layer** and wrap adapters via **decorators**:

```
┌─────────────────────────────────────────────────────────────┐
│              APPLICATION LAYER                              │
│  WorkflowOrchestrator | AgentScheduler | ReviewService      │
│  (Uses ports - unaware of resilience)                       │
└─────────────────────────┬───────────────────────────────────┘
                          │ depends on
┌─────────────────────────▼───────────────────────────────────┐
│              OUTPUT PORTS (Interfaces)                      │
│  ITicketSystem | ILLMProvider | IRepository | IContainer    │
└─────────────────────────┬───────────────────────────────────┘
                          │ implemented by
┌─────────────────────────▼───────────────────────────────────┐
│          INFRASTRUCTURE RESILIENCE LAYER                    │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Resilient Decorators (composable wrappers)         │    │
│  ├────────────────────────────────────────────────────┤    │
│  │ • ResilientTicketSystemDecorator                   │    │
│  │ • ResilientLLMProviderDecorator                    │    │
│  │ • ResilientRepositoryDecorator                     │    │
│  │ • ResilientContainerDecorator                      │    │
│  └─────────────────┬──────────────────────────────────┘    │
│                    │ uses                                   │
│  ┌─────────────────▼──────────────────────────────────┐    │
│  │ Resilience Components                              │    │
│  ├────────────────────────────────────────────────────┤    │
│  │ • IRateLimiter (interface)                         │    │
│  │   - TokenBucketRateLimiter (production)            │    │
│  │   - SlidingWindowRateLimiter (production)          │    │
│  │   - MockRateLimiter (simulation)                   │    │
│  │                                                     │    │
│  │ • ICircuitBreaker (interface)                      │    │
│  │   - CircuitBreaker (production)                    │    │
│  │   - MockCircuitBreaker (simulation)                │    │
│  │                                                     │    │
│  │ • IRetryPolicy (interface)                         │    │
│  │   - ExponentialBackoffRetry (production)           │    │
│  │   - MockRetryPolicy (simulation)                   │    │
│  │                                                     │    │
│  │ • ITimeout (interface)                             │    │
│  │   - AsyncTimeout (production)                      │    │
│  │   - MockTimeout (simulation)                       │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │ wraps
┌─────────────────────────▼───────────────────────────────────┐
│              SECONDARY ADAPTERS                             │
│  GitHubTicketAdapter | ClaudeCodeAdapter | DockerAdapter    │
│  (Pure adapter logic - no resilience code)                  │
└─────────────────────────────────────────────────────────────┘
```

**Key Principle**: Adapters remain **pure** (no resilience logic). Resilience is **injected** through decorators at composition time.

---

## Core Interfaces

### IRateLimiter

```python
from abc import ABC, abstractmethod
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class RateLimitStats:
    """Rate limiter statistics."""
    requests_in_window: int
    tokens_in_window: int
    max_requests: int
    max_tokens: Optional[int]
    window_seconds: int
    utilization: float  # 0.0 to 1.0
    next_available: Optional[datetime]

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
        pass

    @abstractmethod
    def try_acquire(self, operation: str, cost: int = 1) -> bool:
        """
        Try to acquire without blocking.

        Returns:
            True if acquired, False if would exceed limit
        """
        pass

    @abstractmethod
    def get_stats(self) -> RateLimitStats:
        """Get current rate limit statistics."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset rate limiter state (for testing)."""
        pass
```

### ICircuitBreaker

```python
from enum import Enum
from typing import Callable, TypeVar, Any

T = TypeVar('T')

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Failing, reject requests
    HALF_OPEN = "half_open"    # Testing recovery

@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    state: CircuitState
    failure_count: int
    success_count: int
    last_failure_time: Optional[datetime]
    last_success_time: Optional[datetime]
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
    async def call(
        self,
        operation: Callable[..., T],
        operation_name: str,
        *args,
        **kwargs
    ) -> T:
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
        pass

    @abstractmethod
    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        pass

    @abstractmethod
    def get_stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset circuit breaker (for testing)."""
        pass

    @abstractmethod
    def force_open(self) -> None:
        """Manually open circuit (for maintenance)."""
        pass

    @abstractmethod
    def force_close(self) -> None:
        """Manually close circuit (for recovery)."""
        pass
```

### IRetryPolicy

```python
from typing import Callable, Type, Tuple

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
    async def execute(
        self,
        operation: Callable[..., T],
        operation_name: str,
        *args,
        **kwargs
    ) -> T:
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
        pass

    @abstractmethod
    def should_retry(self, exception: Exception) -> bool:
        """
        Determine if exception is retryable.

        Args:
            exception: Exception that occurred

        Returns:
            True if should retry, False otherwise
        """
        pass

    @abstractmethod
    def get_stats(self) -> RetryStats:
        """Get retry statistics."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset retry statistics (for testing)."""
        pass
```

### ITimeout

```python
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
        **kwargs
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
        pass

    @abstractmethod
    def get_stats(self) -> TimeoutStats:
        """Get timeout statistics."""
        pass
```

---

## Production Implementations

### TokenBucketRateLimiter

```python
import time
import asyncio
from collections import deque
from typing import Optional

class TokenBucketRateLimiter(IRateLimiter):
    """
    Token bucket rate limiter with sliding window.

    Supports both request-based and token-based limiting
    (e.g., for LLM APIs with token quotas).

    Thread-safe for async operations.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: int = 60,
        max_tokens: Optional[int] = None,
        max_wait_seconds: Optional[float] = None
    ):
        """
        Initialize rate limiter.

        Args:
            max_requests: Max requests per window
            window_seconds: Time window in seconds
            max_tokens: Optional token limit per window (for APIs with token quotas)
            max_wait_seconds: Max time to wait before raising error (None = infinite)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_tokens = max_tokens
        self.max_wait_seconds = max_wait_seconds

        self._lock = asyncio.Lock()
        self._request_timestamps: deque = deque()
        self._token_usage: deque = deque()  # (timestamp, tokens)

    async def acquire(self, operation: str, cost: int = 1) -> None:
        """Wait until operation can proceed within rate limits."""
        start_time = time.time()

        async with self._lock:
            while True:
                now = time.time()

                # Check if we've waited too long
                if self.max_wait_seconds:
                    elapsed = now - start_time
                    if elapsed > self.max_wait_seconds:
                        raise RateLimitExceededError(
                            f"Rate limit wait exceeded {self.max_wait_seconds}s for {operation}"
                        )

                # Remove expired entries
                cutoff = now - self.window_seconds
                self._cleanup_old_entries(cutoff)

                # Check if we can proceed
                current_requests = len(self._request_timestamps)
                current_tokens = sum(t for _, t in self._token_usage)

                can_proceed = current_requests < self.max_requests
                if self.max_tokens:
                    can_proceed = can_proceed and (current_tokens + cost <= self.max_tokens)

                if can_proceed:
                    # Record this operation
                    self._request_timestamps.append(now)
                    self._token_usage.append((now, cost))
                    return

                # Calculate wait time
                wait_time = self._calculate_wait_time()

                # Release lock during wait
                await asyncio.sleep(wait_time)

    def try_acquire(self, operation: str, cost: int = 1) -> bool:
        """Try to acquire without blocking."""
        now = time.time()
        cutoff = now - self.window_seconds

        # Remove expired entries
        self._cleanup_old_entries(cutoff)

        # Check if we can proceed
        current_requests = len(self._request_timestamps)
        current_tokens = sum(t for _, t in self._token_usage)

        can_proceed = current_requests < self.max_requests
        if self.max_tokens:
            can_proceed = can_proceed and (current_tokens + cost <= self.max_tokens)

        if can_proceed:
            self._request_timestamps.append(now)
            self._token_usage.append((now, cost))
            return True

        return False

    def _cleanup_old_entries(self, cutoff: float) -> None:
        """Remove entries older than cutoff."""
        while self._request_timestamps and self._request_timestamps[0] < cutoff:
            self._request_timestamps.popleft()

        while self._token_usage and self._token_usage[0][0] < cutoff:
            self._token_usage.popleft()

    def _calculate_wait_time(self) -> float:
        """Calculate optimal wait time."""
        if not self._request_timestamps:
            return 0.1

        # Wait until oldest entry expires
        oldest = self._request_timestamps[0]
        now = time.time()
        expires_at = oldest + self.window_seconds

        wait = max(0.1, expires_at - now)
        return min(wait, 1.0)  # Cap at 1 second

    def get_stats(self) -> RateLimitStats:
        """Get current statistics."""
        now = time.time()
        cutoff = now - self.window_seconds

        recent_requests = [t for t in self._request_timestamps if t >= cutoff]
        recent_tokens = sum(t for ts, t in self._token_usage if ts >= cutoff)

        utilization = len(recent_requests) / self.max_requests if self.max_requests > 0 else 0

        next_available = None
        if len(recent_requests) >= self.max_requests:
            oldest = self._request_timestamps[0]
            next_available = datetime.fromtimestamp(oldest + self.window_seconds)

        return RateLimitStats(
            requests_in_window=len(recent_requests),
            tokens_in_window=recent_tokens,
            max_requests=self.max_requests,
            max_tokens=self.max_tokens,
            window_seconds=self.window_seconds,
            utilization=utilization,
            next_available=next_available
        )

    def reset(self) -> None:
        """Reset state."""
        self._request_timestamps.clear()
        self._token_usage.clear()
```

### CircuitBreaker

```python
import time
from typing import Optional

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
        timeout_seconds: int = 60,
        success_threshold: int = 2,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,)
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
        self._last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None

        # Statistics
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0

        self._lock = asyncio.Lock()

    async def call(
        self,
        operation: Callable,
        operation_name: str,
        *args,
        **kwargs
    ):
        """Execute operation with circuit breaker protection."""
        async with self._lock:
            self._total_calls += 1

            # Check if circuit should transition to HALF_OPEN
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker open for {operation_name}. "
                        f"Will retry in {self._time_until_retry():.1f}s"
                    )

        # Execute operation (outside lock to avoid holding during I/O)
        try:
            result = await operation(*args, **kwargs)

            # Handle success
            async with self._lock:
                self._on_success()

            return result

        except self.expected_exceptions as e:
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
            total_successes=self._total_successes
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
```

### ExponentialBackoffRetry

```python
import random
import asyncio
from typing import List, Type

class ExponentialBackoffRetry(IRetryPolicy):
    """
    Retry policy with exponential backoff and jitter.

    Implements industry-standard retry logic:
    - Exponential backoff: delay = base_delay * (2 ^ attempt)
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
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
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
        operation: Callable,
        operation_name: str,
        *args,
        **kwargs
    ):
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
                    raise

                # Check if we've exhausted retries
                if attempt >= self.max_retries:
                    self._total_failures += 1
                    raise MaxRetriesExceededError(
                        f"Max retries ({self.max_retries}) exceeded for {operation_name}"
                    ) from e

                # Calculate delay
                delay = self._calculate_delay(attempt)

                self._total_retries += 1

                # Log retry (would integrate with ILogger)
                # logger.warning(f"Retry {attempt + 1}/{self.max_retries} for {operation_name} after {delay:.2f}s")

                await asyncio.sleep(delay)

        # Should never reach here, but just in case
        raise last_exception

    def should_retry(self, exception: Exception) -> bool:
        """Determine if exception is retryable."""
        # Don't retry certain exceptions
        non_retryable = (
            KeyboardInterrupt,
            SystemExit,
            ValidationError,  # Business logic errors shouldn't be retried
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
        avg_attempts = (
            self._total_attempts / (self._total_successes + self._total_failures)
            if (self._total_successes + self._total_failures) > 0
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
```

### AsyncTimeout

```python
import asyncio
from typing import Optional

class AsyncTimeout(ITimeout):
    """
    Async timeout implementation using asyncio.wait_for.

    Prevents operations from hanging indefinitely.
    """

    def __init__(self):
        self._total_operations = 0
        self._total_timeouts = 0
        self._durations: List[float] = []

    async def execute(
        self,
        operation: Callable,
        timeout_seconds: float,
        operation_name: str,
        *args,
        **kwargs
    ):
        """Execute operation with timeout."""
        self._total_operations += 1
        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                operation(*args, **kwargs),
                timeout=timeout_seconds
            )

            duration = (time.time() - start_time) * 1000  # Convert to ms
            self._durations.append(duration)

            return result

        except asyncio.TimeoutError:
            self._total_timeouts += 1
            raise TimeoutError(
                f"Operation {operation_name} exceeded timeout of {timeout_seconds}s"
            )

    def get_stats(self) -> TimeoutStats:
        """Get timeout statistics."""
        avg_duration = sum(self._durations) / len(self._durations) if self._durations else 0
        max_duration = max(self._durations) if self._durations else 0

        return TimeoutStats(
            total_operations=self._total_operations,
            total_timeouts=self._total_timeouts,
            average_duration_ms=avg_duration,
            max_duration_ms=max_duration
        )
```

---

## Mock Implementations (for Simulation)

### MockRateLimiter

```python
from typing import List, Tuple

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
        self.acquire_calls.append((operation, cost, datetime.utcnow()))

        if self._delegate:
            await self._delegate.acquire(operation, cost)
        elif self.simulated_delay_ms > 0:
            await asyncio.sleep(self.simulated_delay_ms / 1000)

    def try_acquire(self, operation: str, cost: int = 1) -> bool:
        """Always succeeds in mock mode."""
        self.acquire_calls.append((operation, cost, datetime.utcnow()))

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
```

### MockCircuitBreaker

```python
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

        self.call_history: List[Dict] = []
        self._call_count = 0

    async def call(
        self,
        operation: Callable,
        operation_name: str,
        *args,
        **kwargs
    ):
        """Execute with configurable behavior."""
        self._call_count += 1

        self.call_history.append({
            "operation": operation_name,
            "state": self._state,
            "timestamp": datetime.utcnow(),
            "call_number": self._call_count
        })

        # Simulate opening circuit after N calls
        if self.fail_after_calls and self._call_count >= self.fail_after_calls:
            self._state = CircuitState.OPEN

        # Check state
        if self._state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(f"Circuit open: {operation_name}")

        # Execute operation
        return await operation(*args, **kwargs)

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
            last_success_time=datetime.utcnow(),
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
```

### MockRetryPolicy

```python
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

        self.execution_history: List[Dict] = []
        self._delegate: Optional[IRetryPolicy] = None

        if simulate_retries:
            self._delegate = ExponentialBackoffRetry(
                max_retries=max_retries,
                base_delay=0.01  # Very short delays for testing
            )

    async def execute(
        self,
        operation: Callable,
        operation_name: str,
        *args,
        **kwargs
    ):
        """Execute with optional retry simulation."""
        self.execution_history.append({
            "operation": operation_name,
            "timestamp": datetime.utcnow()
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
```

### MockTimeout

```python
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
        self.execution_history: List[Dict] = []

    async def execute(
        self,
        operation: Callable,
        timeout_seconds: float,
        operation_name: str,
        *args,
        **kwargs
    ):
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
                raise TimeoutError(f"Operation {operation_name} timed out")
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
```

---

## Resilient Decorators

### ResilientTicketSystemDecorator

```python
from src.ports.output.iticket_system import ITicketSystem, WorkItem, Comment, ProjectBoard

class ResilientTicketSystemDecorator(ITicketSystem):
    """
    Wraps ITicketSystem with resilience patterns.

    Applies rate limiting, circuit breaking, retries, and timeouts
    to all ticket system operations.
    """

    def __init__(
        self,
        wrapped: ITicketSystem,
        rate_limiter: Optional[IRateLimiter] = None,
        circuit_breaker: Optional[ICircuitBreaker] = None,
        retry_policy: Optional[IRetryPolicy] = None,
        timeout: Optional[ITimeout] = None,
        metrics: Optional[IMetrics] = None,
        default_timeout_seconds: float = 30.0
    ):
        """
        Initialize resilient decorator.

        Args:
            wrapped: Underlying ticket system adapter
            rate_limiter: Optional rate limiter
            circuit_breaker: Optional circuit breaker
            retry_policy: Optional retry policy
            timeout: Optional timeout handler
            metrics: Optional metrics collector
            default_timeout_seconds: Default operation timeout
        """
        self._wrapped = wrapped
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker
        self._retry_policy = retry_policy
        self._timeout = timeout
        self._metrics = metrics
        self._default_timeout = default_timeout_seconds

    async def get_work_item(self, item_id: str) -> WorkItem:
        """Get work item with full resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.get_work_item(item_id),
            operation_name="get_work_item",
            rate_limit_cost=1
        )

    async def create_work_item(
        self,
        title: str,
        description: str,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        parent_id: Optional[str] = None
    ) -> WorkItem:
        """Create work item with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.create_work_item(
                title, description, labels, assignees, parent_id
            ),
            operation_name="create_work_item",
            rate_limit_cost=2  # Writes cost more
        )

    async def update_work_item(
        self,
        item_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        labels: Optional[List[str]] = None
    ) -> WorkItem:
        """Update work item with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.update_work_item(
                item_id, title, description, status, labels
            ),
            operation_name="update_work_item",
            rate_limit_cost=2
        )

    async def create_comment(
        self,
        work_item_id: str,
        body: str,
        reply_to: Optional[str] = None
    ) -> Comment:
        """Create comment with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.create_comment(
                work_item_id, body, reply_to
            ),
            operation_name="create_comment",
            rate_limit_cost=1
        )

    async def list_work_items(
        self,
        status: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None
    ) -> List[WorkItem]:
        """List work items with resilience."""
        return await self._execute_resilient(
            operation=lambda: self._wrapped.list_work_items(status, labels, assignee),
            operation_name="list_work_items",
            rate_limit_cost=1
        )

    async def _execute_resilient(
        self,
        operation: Callable,
        operation_name: str,
        rate_limit_cost: int = 1,
        timeout_seconds: Optional[float] = None
    ):
        """
        Execute operation with all resilience patterns.

        Order of application:
        1. Rate limiting (prevent overload)
        2. Circuit breaker (fail fast if unhealthy)
        3. Timeout (prevent hanging)
        4. Retry (handle transient errors)
        5. Metrics (observe behavior)
        """
        start_time = time.time()

        try:
            # 1. Rate limiting
            if self._rate_limiter:
                await self._rate_limiter.acquire(operation_name, rate_limit_cost)

            # 2. Circuit breaker wraps the rest
            if self._circuit_breaker:
                result = await self._circuit_breaker.call(
                    self._execute_with_timeout_and_retry,
                    operation_name,
                    operation,
                    operation_name,
                    timeout_seconds or self._default_timeout
                )
            else:
                result = await self._execute_with_timeout_and_retry(
                    operation,
                    operation_name,
                    timeout_seconds or self._default_timeout
                )

            # Record success metrics
            if self._metrics:
                duration_ms = (time.time() - start_time) * 1000
                await self._metrics.record_operation(
                    operation=f"ticket_system.{operation_name}",
                    success=True,
                    duration_ms=duration_ms
                )

            return result

        except Exception as e:
            # Record failure metrics
            if self._metrics:
                duration_ms = (time.time() - start_time) * 1000
                await self._metrics.record_operation(
                    operation=f"ticket_system.{operation_name}",
                    success=False,
                    duration_ms=duration_ms,
                    error=str(e)
                )
            raise

    async def _execute_with_timeout_and_retry(
        self,
        operation: Callable,
        operation_name: str,
        timeout_seconds: float
    ):
        """Apply timeout and retry."""
        # 3. Timeout wraps operation
        async def timed_operation():
            if self._timeout:
                return await self._timeout.execute(
                    operation,
                    timeout_seconds,
                    operation_name
                )
            else:
                return await operation()

        # 4. Retry wraps timeout
        if self._retry_policy:
            return await self._retry_policy.execute(
                timed_operation,
                operation_name
            )
        else:
            return await timed_operation()

    # Implement remaining ITicketSystem methods similarly...
    # (create_label, add_labels, list_comments, move_work_item, etc.)
```

### ResilientLLMProviderDecorator

```python
from src.ports.output.illm_provider import ILLMProvider, LLMResponse, LLMExecutionContext

class ResilientLLMProviderDecorator(ILLMProvider):
    """
    Wraps ILLMProvider with resilience patterns.

    Special considerations for LLMs:
    - Token-based rate limiting (not just request count)
    - Longer timeouts (LLM calls can take minutes)
    - Less aggressive retries (LLM calls are expensive)
    """

    def __init__(
        self,
        wrapped: ILLMProvider,
        rate_limiter: Optional[IRateLimiter] = None,
        circuit_breaker: Optional[ICircuitBreaker] = None,
        retry_policy: Optional[IRetryPolicy] = None,
        timeout: Optional[ITimeout] = None,
        metrics: Optional[IMetrics] = None,
        default_timeout_seconds: float = 300.0  # 5 minutes for LLM
    ):
        self._wrapped = wrapped
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker
        self._retry_policy = retry_policy
        self._timeout = timeout
        self._metrics = metrics
        self._default_timeout = default_timeout_seconds

    async def execute(
        self,
        prompt: str,
        context: LLMExecutionContext,
        stream_callback: Optional[Callable] = None
    ) -> LLMResponse:
        """Execute with resilience."""
        # Estimate token cost for rate limiting
        estimated_tokens = self._estimate_tokens(prompt)

        return await self._execute_resilient(
            operation=lambda: self._wrapped.execute(prompt, context, stream_callback),
            operation_name="llm_execute",
            rate_limit_cost=estimated_tokens
        )

    async def execute_conversational(
        self,
        messages: List[LLMMessage],
        context: LLMExecutionContext,
        stream_callback: Optional[Callable] = None
    ) -> LLMResponse:
        """Execute conversational with resilience."""
        # Estimate tokens for all messages
        total_text = " ".join(msg.content for msg in messages)
        estimated_tokens = self._estimate_tokens(total_text)

        return await self._execute_resilient(
            operation=lambda: self._wrapped.execute_conversational(
                messages, context, stream_callback
            ),
            operation_name="llm_execute_conversational",
            rate_limit_cost=estimated_tokens
        )

    async def _execute_resilient(
        self,
        operation: Callable,
        operation_name: str,
        rate_limit_cost: int
    ):
        """Execute with resilience patterns."""
        start_time = time.time()

        try:
            # Rate limiting with token cost
            if self._rate_limiter:
                await self._rate_limiter.acquire(operation_name, rate_limit_cost)

            # Circuit breaker
            if self._circuit_breaker:
                result = await self._circuit_breaker.call(
                    self._execute_with_timeout_and_retry,
                    operation_name,
                    operation,
                    operation_name
                )
            else:
                result = await self._execute_with_timeout_and_retry(
                    operation,
                    operation_name
                )

            # Record actual token usage
            if self._metrics and result.tokens_used:
                await self._metrics.record_llm_usage(
                    model=result.model,
                    input_tokens=result.tokens_used.get('input', 0),
                    output_tokens=result.tokens_used.get('output', 0),
                    duration_ms=(time.time() - start_time) * 1000
                )

            return result

        except Exception as e:
            if self._metrics:
                await self._metrics.record_operation(
                    operation=f"llm.{operation_name}",
                    success=False,
                    duration_ms=(time.time() - start_time) * 1000,
                    error=str(e)
                )
            raise

    async def _execute_with_timeout_and_retry(
        self,
        operation: Callable,
        operation_name: str
    ):
        """Apply timeout and retry."""
        async def timed_operation():
            if self._timeout:
                return await self._timeout.execute(
                    operation,
                    self._default_timeout,
                    operation_name
                )
            else:
                return await operation()

        if self._retry_policy:
            return await self._retry_policy.execute(timed_operation, operation_name)
        else:
            return await timed_operation()

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token)."""
        return max(1, len(text) // 4)

    # Implement remaining ILLMProvider methods...
    async def stream_execute(self, prompt: str, context: LLMExecutionContext):
        # Streaming doesn't work well with retries, so less resilience
        return self._wrapped.stream_execute(prompt, context)

    def get_model_info(self):
        return self._wrapped.get_model_info()

    async def validate_auth(self):
        return await self._wrapped.validate_auth()
```

---

## Resilience Factory

```python
from typing import Dict, Any
from enum import Enum

class OperationMode(Enum):
    """System operation mode."""
    PRODUCTION = "production"
    SIMULATION = "simulation"
    INTEGRATION_TEST = "integration_test"

class ResilienceFactory:
    """
    Creates resilient adapters with appropriate components.

    Switches between production and mock implementations based on mode.
    """

    def __init__(
        self,
        mode: OperationMode = OperationMode.PRODUCTION,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize factory.

        Args:
            mode: Operation mode (production, simulation, integration_test)
            config: Configuration overrides
        """
        self.mode = mode
        self.config = config or {}

    def create_resilient_ticket_system(
        self,
        adapter: ITicketSystem,
        service_config: Optional[Dict[str, Any]] = None
    ) -> ITicketSystem:
        """
        Create resilient ticket system adapter.

        Args:
            adapter: Underlying ticket system adapter (GitHub, Jira, etc.)
            service_config: Service-specific configuration
        """
        cfg = {**self.config, **(service_config or {})}

        # Create components based on mode
        if self.mode == OperationMode.PRODUCTION:
            rate_limiter = TokenBucketRateLimiter(
                max_requests=cfg.get('max_requests_per_hour', 5000),
                window_seconds=3600,
                max_wait_seconds=cfg.get('max_wait_seconds', 60)
            )

            circuit_breaker = CircuitBreaker(
                failure_threshold=cfg.get('failure_threshold', 5),
                timeout_seconds=cfg.get('circuit_timeout_seconds', 60),
                success_threshold=cfg.get('success_threshold', 2)
            )

            retry_policy = ExponentialBackoffRetry(
                max_retries=cfg.get('max_retries', 3),
                base_delay=cfg.get('base_delay', 1.0),
                max_delay=cfg.get('max_delay', 60.0)
            )

            timeout = AsyncTimeout()

        elif self.mode == OperationMode.SIMULATION:
            # Mock components with no delays
            rate_limiter = MockRateLimiter(enforce_limits=False)
            circuit_breaker = MockCircuitBreaker()
            retry_policy = MockRetryPolicy(simulate_retries=False)
            timeout = MockTimeout(simulate_timeouts=False)

        else:  # INTEGRATION_TEST
            # Mock components but enforce limits for realistic testing
            rate_limiter = MockRateLimiter(enforce_limits=True)
            circuit_breaker = CircuitBreaker(
                failure_threshold=3,
                timeout_seconds=5
            )
            retry_policy = MockRetryPolicy(simulate_retries=True, max_retries=2)
            timeout = AsyncTimeout()

        return ResilientTicketSystemDecorator(
            wrapped=adapter,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            retry_policy=retry_policy,
            timeout=timeout,
            default_timeout_seconds=cfg.get('default_timeout', 30.0)
        )

    def create_resilient_llm_provider(
        self,
        adapter: ILLMProvider,
        service_config: Optional[Dict[str, Any]] = None
    ) -> ILLMProvider:
        """
        Create resilient LLM provider adapter.

        LLM-specific configuration:
        - Token-based rate limiting
        - Longer timeouts
        - Less aggressive retries (expensive operations)
        """
        cfg = {**self.config, **(service_config or {})}

        if self.mode == OperationMode.PRODUCTION:
            # Token-based rate limiting for LLMs
            rate_limiter = TokenBucketRateLimiter(
                max_requests=cfg.get('max_requests_per_minute', 50),
                window_seconds=60,
                max_tokens=cfg.get('max_tokens_per_minute', 40000)
            )

            circuit_breaker = CircuitBreaker(
                failure_threshold=cfg.get('failure_threshold', 3),
                timeout_seconds=cfg.get('circuit_timeout_seconds', 120)
            )

            # Only retry on network errors, not LLM errors
            retry_policy = ExponentialBackoffRetry(
                max_retries=cfg.get('max_retries', 2),
                base_delay=cfg.get('base_delay', 2.0),
                max_delay=cfg.get('max_delay', 30.0)
            )

            timeout = AsyncTimeout()

        elif self.mode == OperationMode.SIMULATION:
            rate_limiter = MockRateLimiter(enforce_limits=False)
            circuit_breaker = MockCircuitBreaker()
            retry_policy = MockRetryPolicy(simulate_retries=False)
            timeout = MockTimeout(simulate_timeouts=False)

        else:  # INTEGRATION_TEST
            rate_limiter = MockRateLimiter(enforce_limits=True)
            circuit_breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=10)
            retry_policy = MockRetryPolicy(simulate_retries=True, max_retries=1)
            timeout = AsyncTimeout()

        return ResilientLLMProviderDecorator(
            wrapped=adapter,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            retry_policy=retry_policy,
            timeout=timeout,
            default_timeout_seconds=cfg.get('default_timeout', 300.0)
        )

    def create_resilient_repository(
        self,
        adapter: IRepository,
        service_config: Optional[Dict[str, Any]] = None
    ) -> IRepository:
        """Create resilient repository adapter (similar pattern)."""
        # Implementation similar to ticket system...
        pass

    def create_resilient_container(
        self,
        adapter: IContainer,
        service_config: Optional[Dict[str, Any]] = None
    ) -> IContainer:
        """Create resilient container adapter (similar pattern)."""
        # Implementation similar to ticket system...
        pass
```

---

## Configuration

### Resilience Configuration Schema

```python
from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class RateLimitConfig:
    """Rate limiter configuration."""
    max_requests: int
    window_seconds: int = 60
    max_tokens: Optional[int] = None
    max_wait_seconds: Optional[float] = None

@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    timeout_seconds: int = 60
    success_threshold: int = 2

@dataclass
class RetryConfig:
    """Retry policy configuration."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True

@dataclass
class TimeoutConfig:
    """Timeout configuration."""
    default_timeout_seconds: float = 30.0

@dataclass
class ServiceResilienceConfig:
    """Complete resilience configuration for a service."""
    service_name: str
    rate_limit: Optional[RateLimitConfig] = None
    circuit_breaker: Optional[CircuitBreakerConfig] = None
    retry: Optional[RetryConfig] = None
    timeout: Optional[TimeoutConfig] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {"service_name": self.service_name}

        if self.rate_limit:
            result["rate_limit"] = {
                "max_requests": self.rate_limit.max_requests,
                "window_seconds": self.rate_limit.window_seconds,
                "max_tokens": self.rate_limit.max_tokens,
                "max_wait_seconds": self.rate_limit.max_wait_seconds
            }

        if self.circuit_breaker:
            result["circuit_breaker"] = {
                "failure_threshold": self.circuit_breaker.failure_threshold,
                "timeout_seconds": self.circuit_breaker.timeout_seconds,
                "success_threshold": self.circuit_breaker.success_threshold
            }

        if self.retry:
            result["retry"] = {
                "max_retries": self.retry.max_retries,
                "base_delay": self.retry.base_delay,
                "max_delay": self.retry.max_delay,
                "exponential_base": self.retry.exponential_base,
                "jitter": self.retry.jitter
            }

        if self.timeout:
            result["timeout"] = {
                "default_timeout_seconds": self.timeout.default_timeout_seconds
            }

        return result


# Example configurations

# GitHub API configuration
GITHUB_RESILIENCE_CONFIG = ServiceResilienceConfig(
    service_name="github",
    rate_limit=RateLimitConfig(
        max_requests=5000,
        window_seconds=3600,  # GitHub: 5000 req/hour
        max_wait_seconds=60
    ),
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=60,
        success_threshold=2
    ),
    retry=RetryConfig(
        max_retries=3,
        base_delay=1.0,
        max_delay=30.0
    ),
    timeout=TimeoutConfig(
        default_timeout_seconds=30.0
    )
)

# Claude API configuration
CLAUDE_RESILIENCE_CONFIG = ServiceResilienceConfig(
    service_name="claude",
    rate_limit=RateLimitConfig(
        max_requests=50,
        window_seconds=60,  # Claude: ~50 req/min
        max_tokens=40000,   # Claude: 40k tokens/min
        max_wait_seconds=120
    ),
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=3,  # Fail faster for expensive LLM calls
        timeout_seconds=120,
        success_threshold=2
    ),
    retry=RetryConfig(
        max_retries=2,  # Less aggressive for expensive operations
        base_delay=2.0,
        max_delay=30.0
    ),
    timeout=TimeoutConfig(
        default_timeout_seconds=300.0  # 5 minutes for LLM
    )
)
```

---

## Exception Hierarchy

```python
class ResilienceError(Exception):
    """Base exception for resilience infrastructure."""
    pass

class RateLimitExceededError(ResilienceError):
    """Raised when rate limit exceeded and max wait exceeded."""
    pass

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
```

---

## Usage Examples

### Production Composition

```python
# Application startup - production mode

from src.adapters.secondary.github_ticket_adapter import GitHubTicketAdapter
from src.adapters.secondary.claude_code_adapter import ClaudeCodeAdapter
from src.infrastructure.resilience.factory import ResilienceFactory, OperationMode

# Create factory in production mode
resilience_factory = ResilienceFactory(mode=OperationMode.PRODUCTION)

# Create raw adapters
github_adapter = GitHubTicketAdapter(
    owner="myorg",
    repo="myrepo",
    token=os.getenv("GITHUB_TOKEN")
)

claude_adapter = ClaudeCodeAdapter(
    oauth_token=os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
)

# Wrap with resilience
resilient_github = resilience_factory.create_resilient_ticket_system(
    adapter=github_adapter,
    service_config=GITHUB_RESILIENCE_CONFIG.to_dict()
)

resilient_claude = resilience_factory.create_resilient_llm_provider(
    adapter=claude_adapter,
    service_config=CLAUDE_RESILIENCE_CONFIG.to_dict()
)

# Inject into application services
workflow_orchestrator = WorkflowOrchestrator(
    ticket_system=resilient_github,  # Application uses resilient version
    llm_provider=resilient_claude,
    event_store=event_store
)
```

### Simulation Mode

```python
# Test setup - simulation mode

resilience_factory = ResilienceFactory(mode=OperationMode.SIMULATION)

# Mock adapters
mock_github = InMemoryTicketAdapter()
mock_claude = MockLLMProvider()

# Wrap with mock resilience (no delays, just tracking)
resilient_github = resilience_factory.create_resilient_ticket_system(mock_github)
resilient_claude = resilience_factory.create_resilient_llm_provider(mock_claude)

# Use in simulation
orchestrator = WorkflowOrchestrator(
    ticket_system=resilient_github,
    llm_provider=resilient_claude,
    event_store=in_memory_event_store
)

# Run simulation (fast, no external calls)
await orchestrator.handle_card_movement(event)

# Assert resilience was tracked
assert resilient_github._rate_limiter.acquire_calls  # Tracked but didn't delay
```

---

## Testing Strategy

### Unit Tests

Test resilience components in isolation:

```python
import pytest
import asyncio

# Test rate limiter
async def test_rate_limiter_enforces_limits():
    limiter = TokenBucketRateLimiter(
        max_requests=5,
        window_seconds=1
    )

    # First 5 should succeed immediately
    for i in range(5):
        await limiter.acquire("test_op")

    # 6th should block
    start = time.time()
    await limiter.acquire("test_op")
    elapsed = time.time() - start

    assert elapsed >= 0.9  # Should have waited ~1 second

# Test circuit breaker
async def test_circuit_breaker_opens_after_failures():
    breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

    async def failing_operation():
        raise Exception("Simulated failure")

    # First 3 failures should pass through
    for i in range(3):
        with pytest.raises(Exception, match="Simulated failure"):
            await breaker.call(failing_operation, "test_op")

    # 4th should raise CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(failing_operation, "test_op")

    assert breaker.get_state() == CircuitState.OPEN

# Test retry policy
async def test_retry_policy_retries_on_failure():
    policy = ExponentialBackoffRetry(max_retries=3, base_delay=0.01)

    call_count = 0

    async def operation_that_succeeds_on_third_try():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Transient error")
        return "success"

    result = await policy.execute(
        operation_that_succeeds_on_third_try,
        "test_op"
    )

    assert result == "success"
    assert call_count == 3
    assert policy.get_stats().total_retries == 2
```

### Integration Tests

Test decorators with real adapters:

```python
@pytest.mark.integration
async def test_resilient_github_adapter():
    """Test resilient GitHub adapter with real API."""

    # Use integration test mode (enforces limits but with mock components)
    factory = ResilienceFactory(mode=OperationMode.INTEGRATION_TEST)

    github_adapter = GitHubTicketAdapter(
        owner="test-org",
        repo="test-repo",
        token=os.getenv("GITHUB_TOKEN")
    )

    resilient_github = factory.create_resilient_ticket_system(github_adapter)

    # Test operations work through resilience layer
    item = await resilient_github.get_work_item("1")
    assert item.number == 1

    # Check resilience stats
    stats = resilient_github._rate_limiter.get_stats()
    assert stats.requests_in_window >= 1
```

### Simulation Tests

Test full workflows with mock resilience:

```python
async def test_full_workflow_simulation():
    """Test complete workflow in simulation mode."""

    # Setup simulation
    factory = ResilienceFactory(mode=OperationMode.SIMULATION)

    mock_github = InMemoryTicketAdapter()
    mock_claude = MockLLMProvider()

    resilient_github = factory.create_resilient_ticket_system(mock_github)
    resilient_claude = factory.create_resilient_llm_provider(mock_claude)

    # Prepare test data
    work_item = WorkItem(id="1", title="Test", ...)
    mock_github.add_test_work_item(work_item)

    # Run workflow
    orchestrator = WorkflowOrchestrator(
        ticket_system=resilient_github,
        llm_provider=resilient_claude,
        event_store=InMemoryEventStore()
    )

    await orchestrator.handle_card_movement(
        CardMovedEvent("1", "Requirements Analysis")
    )

    # Verify resilience was applied (but didn't slow things down)
    assert len(resilient_github._rate_limiter.acquire_calls) > 0
    assert len(resilient_claude._rate_limiter.acquire_calls) > 0
```

---

## Observability Integration

### Metrics Collection

```python
from src.ports.output.imetrics import IMetrics

class ResilienceMetricsCollector:
    """
    Collects metrics from resilience components.

    Integrates with IMetrics port for centralized observability.
    """

    def __init__(self, metrics: IMetrics):
        self.metrics = metrics

    async def collect_rate_limiter_metrics(
        self,
        service_name: str,
        rate_limiter: IRateLimiter
    ):
        """Collect rate limiter metrics."""
        stats = rate_limiter.get_stats()

        await self.metrics.record_gauge(
            f"resilience.rate_limit.requests_in_window",
            stats.requests_in_window,
            tags={"service": service_name}
        )

        await self.metrics.record_gauge(
            f"resilience.rate_limit.utilization",
            stats.utilization,
            tags={"service": service_name}
        )

    async def collect_circuit_breaker_metrics(
        self,
        service_name: str,
        circuit_breaker: ICircuitBreaker
    ):
        """Collect circuit breaker metrics."""
        stats = circuit_breaker.get_stats()

        await self.metrics.record_gauge(
            f"resilience.circuit_breaker.state",
            1 if stats.state == CircuitState.OPEN else 0,
            tags={"service": service_name}
        )

        await self.metrics.record_counter(
            f"resilience.circuit_breaker.total_failures",
            stats.total_failures,
            tags={"service": service_name}
        )
```

---

## Summary

The infrastructure resilience layer provides:

1. **Centralized resilience patterns** - Single implementation, reused everywhere
2. **Adapter-agnostic** - Works with any port implementation via decorators
3. **Composable** - Mix and match rate limiting, circuit breakers, retries, timeouts
4. **Production-ready** - Battle-tested patterns with proper state management
5. **Simulation-friendly** - Mock implementations for fast testing without delays
6. **Observable** - Built-in metrics collection and statistics
7. **Configurable** - Per-service configuration via factory
8. **Testable** - Each component tested independently and in composition

This design ensures all external system integrations have reliable, testable resilience without coupling resilience logic to adapter implementations.
