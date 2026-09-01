"""Unit tests for BestEffortExecutionTrackerDecorator."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.resilience.decorators import (
    BestEffortExecutionTrackerDecorator,
)
from codetoreum.ports.output.work_execution_state_tracker import ExecutionState


class TestBestEffortExecutionTrackerDecorator:
    """Tests for BestEffortExecutionTrackerDecorator."""

    @pytest.mark.asyncio
    async def test_mark_execution_started_passes_through_on_success(self):
        """Test that mark_execution_started delegates to wrapped tracker on success."""
        wrapped = AsyncMock()
        deco = BestEffortExecutionTrackerDecorator(wrapped)

        await deco.mark_execution_started("proj1", "item-123", "claude")

        wrapped.mark_execution_started.assert_awaited_once_with(
            "proj1", "item-123", "claude"
        )

    @pytest.mark.asyncio
    async def test_mark_execution_started_swallows_exceptions(self, caplog):
        """Test that mark_execution_started gracefully handles failures.

        When the underlying tracker fails, the decorator logs the error
        and returns normally, allowing execution to proceed.
        """
        wrapped = AsyncMock()
        wrapped.mark_execution_started.side_effect = RuntimeError("Storage failure")
        deco = BestEffortExecutionTrackerDecorator(wrapped)

        # Should not raise
        with caplog.at_level(logging.ERROR):
            await deco.mark_execution_started("proj1", "item-123", "claude")

        # Verify error was logged
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert "Failed to update execution state tracker" in record.message
        assert "proj1" in record.message
        assert "item-123" in record.message
        assert "claude" in record.message
        assert record.exc_info is not None  # exc_info=True

    @pytest.mark.asyncio
    async def test_mark_execution_started_logs_with_error_registry(self, caplog):
        """Test that mark_execution_started uses ErrorRegistry for error IDs."""
        wrapped = AsyncMock()
        wrapped.mark_execution_started.side_effect = ValueError("Invalid state")
        deco = BestEffortExecutionTrackerDecorator(wrapped)

        with caplog.at_level(logging.ERROR):
            await deco.mark_execution_started("proj1", "item-123", "claude")

        record = caplog.records[0]
        # The error_id should be in the extra dict
        assert hasattr(record, "error_id")
        assert (
            record.error_id
            == ErrorRegistry.ERR_EXECUTION_TRACKER_UPDATE_FAILURE
        )

    @pytest.mark.asyncio
    async def test_load_state_passes_through_on_success(self):
        """Test that load_state delegates to wrapped tracker."""
        wrapped = AsyncMock()
        state = ExecutionState(outcome="in_progress", agent="claude")
        wrapped.load_state.return_value = state
        deco = BestEffortExecutionTrackerDecorator(wrapped)

        result = await deco.load_state("proj1", "item-123")

        assert result is state
        wrapped.load_state.assert_awaited_once_with("proj1", "item-123")

    @pytest.mark.asyncio
    async def test_load_state_passes_through_on_none(self):
        """Test that load_state returns None when wrapped tracker returns None."""
        wrapped = AsyncMock()
        wrapped.load_state.return_value = None
        deco = BestEffortExecutionTrackerDecorator(wrapped)

        result = await deco.load_state("proj1", "item-123")

        assert result is None
        wrapped.load_state.assert_awaited_once_with("proj1", "item-123")

    @pytest.mark.asyncio
    async def test_load_state_passes_through_exceptions(self):
        """Test that load_state does not swallow exceptions from wrapped tracker.

        Unlike mark_execution_started, load_state is not in the critical path
        (it's only called during recovery), so exceptions should propagate.
        """
        wrapped = AsyncMock()
        wrapped.load_state.side_effect = RuntimeError("Storage failure")
        deco = BestEffortExecutionTrackerDecorator(wrapped)

        with pytest.raises(RuntimeError, match="Storage failure"):
            await deco.load_state("proj1", "item-123")

    @pytest.mark.asyncio
    async def test_mark_execution_failed_passes_through_on_success(self):
        """Test that mark_execution_failed delegates to wrapped tracker."""
        wrapped = AsyncMock()
        deco = BestEffortExecutionTrackerDecorator(wrapped)

        await deco.mark_execution_failed(
            "proj1", "item-123", "claude", "Container lost connection"
        )

        wrapped.mark_execution_failed.assert_awaited_once_with(
            "proj1", "item-123", "claude", "Container lost connection"
        )

    @pytest.mark.asyncio
    async def test_mark_execution_failed_passes_through_exceptions(self):
        """Test that mark_execution_failed does not swallow exceptions.

        Unlike mark_execution_started, mark_execution_failed is not in the
        critical path (it's called during recovery), so exceptions should propagate.
        """
        wrapped = AsyncMock()
        wrapped.mark_execution_failed.side_effect = RuntimeError("Storage failure")
        deco = BestEffortExecutionTrackerDecorator(wrapped)

        with pytest.raises(RuntimeError, match="Storage failure"):
            await deco.mark_execution_failed(
                "proj1", "item-123", "claude", "Container lost connection"
            )

    @pytest.mark.asyncio
    async def test_decorator_contracts_isolation(self):
        """Test that the three contracts are independent.

        Verify that a failure in one method doesn't affect another method's
        behavior (e.g., mark_execution_started swallowing exceptions doesn't
        affect load_state's pass-through semantics).
        """
        wrapped = AsyncMock()
        wrapped.mark_execution_started.side_effect = RuntimeError("Tracker down")
        wrapped.load_state.side_effect = RuntimeError("Also down")
        deco = BestEffortExecutionTrackerDecorator(wrapped)

        # mark_execution_started should swallow
        await deco.mark_execution_started("proj1", "item-123", "claude")

        # load_state should still propagate
        with pytest.raises(RuntimeError, match="Also down"):
            await deco.load_state("proj1", "item-123")

    @pytest.mark.asyncio
    async def test_multiple_invocations_independent(self):
        """Test that multiple invocations are independent.

        Verify that a failure in one invocation doesn't affect subsequent
        invocations.
        """
        wrapped = AsyncMock()

        # First call fails
        wrapped.mark_execution_started.side_effect = [
            RuntimeError("First failure"),
            None,  # Second call succeeds
        ]
        deco = BestEffortExecutionTrackerDecorator(wrapped)

        # First invocation should swallow exception
        await deco.mark_execution_started("proj1", "item-1", "claude")

        # Second invocation should succeed
        await deco.mark_execution_started("proj1", "item-2", "claude")

        # Both calls should have been made
        assert wrapped.mark_execution_started.await_count == 2
