"""Tests for circuit breaker implementations."""

import asyncio

import pytest

from codetoreum.infrastructure.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    MockCircuitBreaker,
)


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    @pytest.mark.asyncio
    async def test_allows_calls_when_closed(self):
        """Test that calls succeed when circuit is closed."""
        breaker = CircuitBreaker(failure_threshold=3)

        call_count = 0

        async def successful_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await breaker.call(successful_operation, "test_op")

        assert result == "success"
        assert call_count == 1
        assert breaker.get_state() == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        """Test that circuit opens after failure threshold."""
        breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

        async def failing_operation():
            raise Exception("Simulated failure")

        # First 3 failures should pass through
        for i in range(3):
            with pytest.raises(Exception, match="Simulated failure"):
                await breaker.call(failing_operation, "test_op")

        # Circuit should now be open
        assert breaker.get_state() == CircuitState.OPEN

        # 4th call should raise CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(failing_operation, "test_op")

    @pytest.mark.asyncio
    async def test_transitions_to_half_open(self):
        """Test transition from OPEN to HALF_OPEN after timeout."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            timeout_seconds=0.5,  # Short timeout for testing
            success_threshold=1,
        )

        async def failing_operation():
            raise Exception("Simulated failure")

        async def successful_operation():
            return "success"

        # Cause circuit to open
        for i in range(2):
            with pytest.raises(Exception):
                await breaker.call(failing_operation, "test_op")

        assert breaker.get_state() == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.6)

        # Next call should transition to HALF_OPEN
        result = await breaker.call(successful_operation, "test_op")

        assert result == "success"
        assert breaker.get_state() == CircuitState.CLOSED  # Should close after success

    @pytest.mark.asyncio
    async def test_closes_from_half_open_on_success(self):
        """Test that circuit closes from HALF_OPEN after success threshold."""
        breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=0.5, success_threshold=2)

        async def failing_operation():
            raise Exception("Simulated failure")

        async def successful_operation():
            return "success"

        # Open the circuit
        for i in range(2):
            with pytest.raises(Exception):
                await breaker.call(failing_operation, "test_op")

        # Wait for timeout
        await asyncio.sleep(0.6)

        # First success (HALF_OPEN)
        await breaker.call(successful_operation, "test_op")
        assert breaker.get_state() == CircuitState.HALF_OPEN

        # Second success should close circuit
        await breaker.call(successful_operation, "test_op")
        assert breaker.get_state() == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_reopens_from_half_open_on_failure(self):
        """Test that circuit reopens from HALF_OPEN on any failure."""
        breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=0.5)

        async def failing_operation():
            raise Exception("Simulated failure")

        # Open the circuit
        for i in range(2):
            with pytest.raises(Exception):
                await breaker.call(failing_operation, "test_op")

        # Wait for timeout
        await asyncio.sleep(0.6)

        # Failure in HALF_OPEN should reopen circuit
        with pytest.raises(Exception):
            await breaker.call(failing_operation, "test_op")

        assert breaker.get_state() == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_resets_failure_count_on_success(self):
        """Test that failure count resets on successful call."""
        breaker = CircuitBreaker(failure_threshold=3)

        async def failing_operation():
            raise Exception("Simulated failure")

        async def successful_operation():
            return "success"

        # Two failures
        for i in range(2):
            with pytest.raises(Exception):
                await breaker.call(failing_operation, "test_op")

        # Success should reset count
        await breaker.call(successful_operation, "test_op")

        # Two more failures shouldn't open circuit
        for i in range(2):
            with pytest.raises(Exception):
                await breaker.call(failing_operation, "test_op")

        assert breaker.get_state() == CircuitState.CLOSED

    def test_get_stats(self):
        """Test that statistics are tracked correctly."""
        breaker = CircuitBreaker(failure_threshold=5)

        stats = breaker.get_stats()

        assert stats.state == CircuitState.CLOSED
        assert stats.failure_count == 0
        assert stats.total_calls == 0

    def test_force_open(self):
        """Test manually opening circuit."""
        breaker = CircuitBreaker()

        assert breaker.get_state() == CircuitState.CLOSED

        breaker.force_open()

        assert breaker.get_state() == CircuitState.OPEN

    def test_force_close(self):
        """Test manually closing circuit."""
        breaker = CircuitBreaker()

        breaker.force_open()
        assert breaker.get_state() == CircuitState.OPEN

        breaker.force_close()
        assert breaker.get_state() == CircuitState.CLOSED

    def test_reset(self):
        """Test that reset returns to initial state."""
        breaker = CircuitBreaker()

        breaker.force_open()
        assert breaker.get_state() == CircuitState.OPEN

        breaker.reset()

        assert breaker.get_state() == CircuitState.CLOSED
        stats = breaker.get_stats()
        assert stats.failure_count == 0


class TestMockCircuitBreaker:
    """Tests for MockCircuitBreaker."""

    @pytest.mark.asyncio
    async def test_mock_records_calls(self):
        """Test that mock records all calls."""
        breaker = MockCircuitBreaker()

        async def test_operation():
            return "success"

        await breaker.call(test_operation, "op1")
        await breaker.call(test_operation, "op2")

        assert len(breaker.call_history) == 2
        assert breaker.call_history[0]["operation"] == "op1"
        assert breaker.call_history[1]["operation"] == "op2"

    @pytest.mark.asyncio
    async def test_mock_can_simulate_open_circuit(self):
        """Test that mock can simulate circuit being open."""
        breaker = MockCircuitBreaker(initial_state=CircuitState.OPEN)

        async def test_operation():
            return "success"

        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(test_operation, "test_op")

    @pytest.mark.asyncio
    async def test_mock_can_fail_after_calls(self):
        """Test that mock can fail after N calls."""
        breaker = MockCircuitBreaker(fail_after_calls=3)

        async def test_operation():
            return "success"

        # First 3 should succeed
        for i in range(3):
            await breaker.call(test_operation, "test_op")

        # 4th should fail
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(test_operation, "test_op")

    def test_assert_called(self):
        """Test the assert_called helper method."""
        breaker = MockCircuitBreaker()

        async def dummy():
            return None

        # Manually add to history for testing
        breaker.call_history.append(
            {"operation": "op1", "state": CircuitState.CLOSED, "timestamp": None, "call_number": 1}
        )
        breaker.call_history.append(
            {"operation": "op1", "state": CircuitState.CLOSED, "timestamp": None, "call_number": 2}
        )

        # Should pass
        breaker.assert_called("op1", min_count=2)

        # Should fail
        with pytest.raises(AssertionError):
            breaker.assert_called("op1", min_count=5)
