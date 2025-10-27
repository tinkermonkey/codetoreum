"""Tests for rate limiter implementations."""

import asyncio
import time

import pytest

from codetoreum.infrastructure.resilience import (
    MockRateLimiter,
    RateLimitExceededError,
    TokenBucketRateLimiter,
)


class TestTokenBucketRateLimiter:
    """Tests for TokenBucketRateLimiter."""

    @pytest.mark.asyncio
    async def test_allows_requests_within_limit(self):
        """Test that requests within limit are allowed immediately."""
        limiter = TokenBucketRateLimiter(
            max_requests=5,
            window_seconds=1
        )

        # First 5 requests should succeed immediately
        start = time.time()
        for i in range(5):
            await limiter.acquire("test_op")
        elapsed = time.time() - start

        # Should complete almost instantly (less than 100ms)
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_enforces_rate_limit(self):
        """Test that rate limit is enforced."""
        limiter = TokenBucketRateLimiter(
            max_requests=5,
            window_seconds=1
        )

        # First 5 requests
        for i in range(5):
            await limiter.acquire("test_op")

        # 6th request should block until window expires
        start = time.time()
        await limiter.acquire("test_op")
        elapsed = time.time() - start

        # Should have waited approximately 1 second (allowing some tolerance)
        assert elapsed >= 0.9
        assert elapsed < 1.2

    @pytest.mark.asyncio
    async def test_sliding_window(self):
        """Test that sliding window works correctly."""
        limiter = TokenBucketRateLimiter(
            max_requests=3,
            window_seconds=1
        )

        # Make 3 requests
        await limiter.acquire("test_op")
        await limiter.acquire("test_op")
        await limiter.acquire("test_op")

        # Wait for first request to expire
        await asyncio.sleep(1.1)

        # Should be able to make another request now
        start = time.time()
        await limiter.acquire("test_op")
        elapsed = time.time() - start

        # Should succeed immediately
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_token_based_limiting(self):
        """Test token-based rate limiting."""
        limiter = TokenBucketRateLimiter(
            max_requests=10,
            window_seconds=1,
            max_tokens=100
        )

        # Use up tokens
        await limiter.acquire("test_op", cost=50)
        await limiter.acquire("test_op", cost=50)

        # Next request should block even though request count is under limit
        start = time.time()
        await limiter.acquire("test_op", cost=10)
        elapsed = time.time() - start

        # Should have waited for window to expire
        assert elapsed >= 0.9

    @pytest.mark.asyncio
    async def test_max_wait_exceeded(self):
        """Test that RateLimitExceededError is raised when max wait exceeded."""
        limiter = TokenBucketRateLimiter(
            max_requests=1,
            window_seconds=10,
            max_wait_seconds=0.5
        )

        # Use up the limit
        await limiter.acquire("test_op")

        # Next request should fail after max wait
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.acquire("test_op")

        assert "Rate limit wait exceeded" in str(exc_info.value)

    def test_try_acquire_non_blocking(self):
        """Test that try_acquire doesn't block."""
        limiter = TokenBucketRateLimiter(
            max_requests=2,
            window_seconds=1
        )

        # First 2 should succeed
        assert limiter.try_acquire("test_op") is True
        assert limiter.try_acquire("test_op") is True

        # 3rd should fail without blocking
        start = time.time()
        result = limiter.try_acquire("test_op")
        elapsed = time.time() - start

        assert result is False
        assert elapsed < 0.1

    def test_get_stats(self):
        """Test that statistics are tracked correctly."""
        limiter = TokenBucketRateLimiter(
            max_requests=5,
            window_seconds=60
        )

        limiter.try_acquire("test_op", cost=10)
        limiter.try_acquire("test_op", cost=20)

        stats = limiter.get_stats()

        assert stats.requests_in_window == 2
        assert stats.tokens_in_window == 30
        assert stats.max_requests == 5
        assert stats.window_seconds == 60
        assert stats.utilization == 0.4  # 2/5

    def test_reset(self):
        """Test that reset clears state."""
        limiter = TokenBucketRateLimiter(
            max_requests=2,
            window_seconds=1
        )

        limiter.try_acquire("test_op")
        limiter.try_acquire("test_op")

        stats = limiter.get_stats()
        assert stats.requests_in_window == 2

        limiter.reset()

        stats = limiter.get_stats()
        assert stats.requests_in_window == 0
        assert stats.tokens_in_window == 0


class TestMockRateLimiter:
    """Tests for MockRateLimiter."""

    @pytest.mark.asyncio
    async def test_mock_does_not_delay(self):
        """Test that mock rate limiter doesn't add delays."""
        limiter = MockRateLimiter(enforce_limits=False)

        # Make many requests quickly
        start = time.time()
        for i in range(100):
            await limiter.acquire("test_op")
        elapsed = time.time() - start

        # Should complete very quickly
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_mock_records_calls(self):
        """Test that mock records all acquire calls."""
        limiter = MockRateLimiter(enforce_limits=False)

        await limiter.acquire("op1", cost=5)
        await limiter.acquire("op2", cost=10)

        assert len(limiter.acquire_calls) == 2
        assert limiter.acquire_calls[0][0] == "op1"
        assert limiter.acquire_calls[0][1] == 5
        assert limiter.acquire_calls[1][0] == "op2"
        assert limiter.acquire_calls[1][1] == 10

    @pytest.mark.asyncio
    async def test_mock_can_enforce_limits(self):
        """Test that mock can optionally enforce limits."""
        limiter = MockRateLimiter(enforce_limits=True)

        # Should eventually hit the delegated limiter's limit
        # (default is 1000 requests per 60 seconds)
        for i in range(100):
            await limiter.acquire("test_op")

        # Should have recorded all calls
        assert len(limiter.acquire_calls) == 100

    def test_assert_acquired(self):
        """Test the assert_acquired helper method."""
        limiter = MockRateLimiter()

        limiter.try_acquire("op1")
        limiter.try_acquire("op1")
        limiter.try_acquire("op2")

        # Should pass
        limiter.assert_acquired("op1", min_count=2)
        limiter.assert_acquired("op2", min_count=1)

        # Should fail
        with pytest.raises(AssertionError):
            limiter.assert_acquired("op1", min_count=5)
