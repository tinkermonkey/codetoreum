"""Tests for retry policy implementations."""

import pytest

from codetoreum.infrastructure.resilience import (
    ExponentialBackoffRetry,
    MaxRetriesExceededError,
    MockRetryPolicy,
)


class TestExponentialBackoffRetry:
    """Tests for ExponentialBackoffRetry."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        """Test that operation succeeding on first attempt doesn't retry."""
        policy = ExponentialBackoffRetry(max_retries=3)

        call_count = 0

        async def successful_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await policy.execute(successful_operation, "test_op")

        assert result == "success"
        assert call_count == 1

        stats = policy.get_stats()
        assert stats.total_attempts == 1
        assert stats.total_retries == 0
        assert stats.total_successes == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        """Test that operation is retried on failure."""
        policy = ExponentialBackoffRetry(
            max_retries=3,
            base_delay=0.01,  # Short delay for testing
        )

        call_count = 0

        async def operation_that_succeeds_on_third_try():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Transient error")
            return "success"

        result = await policy.execute(operation_that_succeeds_on_third_try, "test_op")

        assert result == "success"
        assert call_count == 3

        stats = policy.get_stats()
        assert stats.total_attempts == 3
        assert stats.total_retries == 2
        assert stats.total_successes == 1

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        """Test that MaxRetriesExceededError is raised after exhausting retries."""
        policy = ExponentialBackoffRetry(max_retries=3, base_delay=0.01)

        call_count = 0

        async def always_failing_operation():
            nonlocal call_count
            call_count += 1
            raise Exception("Persistent error")

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            await policy.execute(always_failing_operation, "test_op")

        assert "Max retries (3) exceeded" in str(exc_info.value)
        assert call_count == 4  # Initial attempt + 3 retries

        stats = policy.get_stats()
        assert stats.total_failures == 1
        assert stats.total_retries == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test that delays increase exponentially."""
        policy = ExponentialBackoffRetry(
            max_retries=3,
            base_delay=0.1,
            exponential_base=2.0,
            jitter=False,  # Disable jitter for predictable testing
        )

        delays: list[float] = []
        last_time = None

        async def failing_operation():
            nonlocal last_time
            import time

            current_time = time.time()
            if last_time is not None:
                delays.append(current_time - last_time)
            last_time = current_time
            raise Exception("Simulated failure")

        with pytest.raises(MaxRetriesExceededError):
            await policy.execute(failing_operation, "test_op")

        # Delays should be approximately: 0.1, 0.2, 0.4
        # (with some tolerance for timing variations)
        assert len(delays) == 3
        assert 0.08 < delays[0] < 0.12  # ~0.1s
        assert 0.18 < delays[1] < 0.22  # ~0.2s
        assert 0.38 < delays[2] < 0.42  # ~0.4s

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Test that delays are capped at max_delay."""
        policy = ExponentialBackoffRetry(
            max_retries=5, base_delay=1.0, max_delay=2.0, exponential_base=2.0, jitter=False
        )

        # Calculate what delay would be for attempt 4 without cap
        # delay = 1.0 * (2.0 ^ 4) = 16.0
        # With cap, should be 2.0

        delay = policy._calculate_delay(4)
        assert delay == 2.0

    def test_should_retry(self):
        """Test that should_retry correctly identifies retryable exceptions."""
        policy = ExponentialBackoffRetry()

        # Should retry regular exceptions
        assert policy.should_retry(Exception("test")) is True

        # Should not retry KeyboardInterrupt
        assert policy.should_retry(KeyboardInterrupt()) is False

        # Should not retry SystemExit
        assert policy.should_retry(SystemExit()) is False

    @pytest.mark.asyncio
    async def test_does_not_retry_non_retryable_exceptions(self):
        """Test that non-retryable exceptions are not retried."""
        policy = ExponentialBackoffRetry(max_retries=3)

        call_count = 0

        async def operation_with_keyboard_interrupt():
            nonlocal call_count
            call_count += 1
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            await policy.execute(operation_with_keyboard_interrupt, "test_op")

        # Should only be called once (no retries)
        assert call_count == 1

    def test_get_stats(self):
        """Test that statistics are tracked correctly."""
        policy = ExponentialBackoffRetry()

        stats = policy.get_stats()

        assert stats.total_attempts == 0
        assert stats.total_retries == 0
        assert stats.total_successes == 0
        assert stats.total_failures == 0
        assert stats.average_attempts == 0

    def test_reset(self):
        """Test that reset clears statistics."""
        policy = ExponentialBackoffRetry()

        # Manually set some stats
        policy._total_attempts = 10
        policy._total_retries = 3

        stats = policy.get_stats()
        assert stats.total_attempts == 10

        policy.reset()

        stats = policy.get_stats()
        assert stats.total_attempts == 0
        assert stats.total_retries == 0


class TestMockRetryPolicy:
    """Tests for MockRetryPolicy."""

    @pytest.mark.asyncio
    async def test_mock_does_not_retry_by_default(self):
        """Test that mock doesn't retry by default."""
        policy = MockRetryPolicy(simulate_retries=False)

        call_count = 0

        async def failing_operation():
            nonlocal call_count
            call_count += 1
            raise Exception("Simulated failure")

        # Should fail on first attempt
        with pytest.raises(Exception):
            await policy.execute(failing_operation, "test_op")

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_mock_records_executions(self):
        """Test that mock records all executions."""
        policy = MockRetryPolicy(simulate_retries=False)

        async def test_operation():
            return "success"

        await policy.execute(test_operation, "op1")
        await policy.execute(test_operation, "op2")

        assert len(policy.execution_history) == 2
        assert policy.execution_history[0]["operation"] == "op1"
        assert policy.execution_history[1]["operation"] == "op2"

    @pytest.mark.asyncio
    async def test_mock_can_simulate_retries(self):
        """Test that mock can optionally simulate retries."""
        policy = MockRetryPolicy(simulate_retries=True, max_retries=2)

        call_count = 0

        async def operation_that_succeeds_on_second_try():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Transient error")
            return "success"

        result = await policy.execute(operation_that_succeeds_on_second_try, "test_op")

        assert result == "success"
        assert call_count == 2
