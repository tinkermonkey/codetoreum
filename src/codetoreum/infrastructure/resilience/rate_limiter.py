"""Production rate limiter implementation.

Provides token bucket rate limiting with sliding window support.
"""

import asyncio
import time
from collections import deque
from datetime import datetime

from .exceptions import RateLimitExceededError
from .interfaces import IRateLimiter, RateLimitStats


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
        max_tokens: int | None = None,
        max_wait_seconds: float | None = None
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

        while True:
            async with self._lock:
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

            # Wait outside the lock to allow other operations to proceed
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
        if len(recent_requests) >= self.max_requests and self._request_timestamps:
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
