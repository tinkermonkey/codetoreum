"""Tests for timeout implementations."""

import asyncio

import pytest

from codetoreum.infrastructure.resilience import AsyncTimeout, MockTimeout, TimeoutError


class TestAsyncTimeout:
    """Tests for AsyncTimeout."""

    @pytest.mark.asyncio
    async def test_allows_fast_operations(self):
        """Test that operations completing within timeout succeed."""
        timeout_handler = AsyncTimeout()

        async def fast_operation():
            await asyncio.sleep(0.1)
            return "success"

        result = await timeout_handler.execute(fast_operation, timeout_seconds=1.0, operation_name="test_op")

        assert result == "success"

        stats = timeout_handler.get_stats()
        assert stats.total_operations == 1
        assert stats.total_timeouts == 0

    @pytest.mark.asyncio
    async def test_raises_on_timeout(self):
        """Test that TimeoutError is raised when operation exceeds timeout."""
        timeout_handler = AsyncTimeout()

        async def slow_operation():
            await asyncio.sleep(2.0)
            return "success"

        with pytest.raises(TimeoutError) as exc_info:
            await timeout_handler.execute(slow_operation, timeout_seconds=0.5, operation_name="test_op")

        assert "exceeded timeout of 0.5s" in str(exc_info.value)

        stats = timeout_handler.get_stats()
        assert stats.total_operations == 1
        assert stats.total_timeouts == 1

    @pytest.mark.asyncio
    async def test_tracks_duration(self):
        """Test that operation duration is tracked."""
        timeout_handler = AsyncTimeout()

        async def timed_operation():
            await asyncio.sleep(0.1)
            return "success"

        await timeout_handler.execute(timed_operation, timeout_seconds=1.0, operation_name="test_op")

        stats = timeout_handler.get_stats()
        # Duration should be approximately 100ms
        assert 90 < stats.average_duration_ms < 150
        assert 90 < stats.max_duration_ms < 150

    @pytest.mark.asyncio
    async def test_tracks_multiple_operations(self):
        """Test statistics across multiple operations."""
        timeout_handler = AsyncTimeout()

        async def operation(delay: float) -> str:
            await asyncio.sleep(delay)
            return "success"

        await timeout_handler.execute(operation, 1.0, "op1", delay=0.1)
        await timeout_handler.execute(operation, 1.0, "op2", delay=0.2)

        stats = timeout_handler.get_stats()
        assert stats.total_operations == 2
        assert stats.total_timeouts == 0
        # Max should be around 200ms
        assert 180 < stats.max_duration_ms < 250


class TestMockTimeout:
    """Tests for MockTimeout."""

    @pytest.mark.asyncio
    async def test_mock_does_not_enforce_timeout_by_default(self):
        """Test that mock allows operations to complete regardless of timeout."""
        timeout_handler = MockTimeout(simulate_timeouts=False)

        async def slow_operation():
            await asyncio.sleep(0.2)
            return "success"

        # Should succeed even though timeout is very short
        result = await timeout_handler.execute(slow_operation, timeout_seconds=0.01, operation_name="test_op")

        assert result == "success"

    @pytest.mark.asyncio
    async def test_mock_records_executions(self):
        """Test that mock records all executions."""
        timeout_handler = MockTimeout(simulate_timeouts=False)

        async def test_operation():
            return "success"

        await timeout_handler.execute(test_operation, 1.0, "op1")
        await timeout_handler.execute(test_operation, 2.0, "op2")

        assert len(timeout_handler.execution_history) == 2
        assert timeout_handler.execution_history[0]["operation"] == "op1"
        assert timeout_handler.execution_history[0]["timeout_seconds"] == 1.0
        assert timeout_handler.execution_history[1]["operation"] == "op2"
        assert timeout_handler.execution_history[1]["timeout_seconds"] == 2.0

    @pytest.mark.asyncio
    async def test_mock_can_simulate_timeouts(self):
        """Test that mock can optionally enforce timeouts."""
        timeout_handler = MockTimeout(simulate_timeouts=True)

        async def slow_operation():
            await asyncio.sleep(1.0)
            return "success"

        with pytest.raises(TimeoutError):
            await timeout_handler.execute(slow_operation, timeout_seconds=0.1, operation_name="test_op")

        assert len(timeout_handler.execution_history) == 1
        assert timeout_handler.execution_history[0]["timed_out"] is True

    @pytest.mark.asyncio
    async def test_mock_tracks_duration(self):
        """Test that mock tracks operation duration."""
        timeout_handler = MockTimeout(simulate_timeouts=False)

        async def timed_operation():
            await asyncio.sleep(0.1)
            return "success"

        await timeout_handler.execute(timed_operation, 1.0, "test_op")

        stats = timeout_handler.get_stats()
        assert stats.total_operations == 1
        # Duration should be approximately 100ms
        assert 90 < stats.average_duration_ms < 150
