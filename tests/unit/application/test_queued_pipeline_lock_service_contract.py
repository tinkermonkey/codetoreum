"""Contract tests for IQueuedPipelineLockService implementation.

These tests verify that implementations conform to the IQueuedPipelineLockService
interface contract. New implementations should pass all these tests.
"""

from datetime import UTC, datetime

import pytest

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.application.pipeline_lock_service import (
    IQueuedPipelineLockService,
    LockAcquisitionResult,
    LockReleaseResult,
    LockStatus,
    PipelineQueueState,
    QueueEntry,
)


class TestQueuedPipelineLockServiceContract:
    """Contract tests for IQueuedPipelineLockService implementations."""

    @pytest.fixture
    def service(self) -> IQueuedPipelineLockService:
        """Provide a service implementation."""
        return InMemoryLockService()

    # Input validation tests

    @pytest.mark.asyncio
    async def test_try_acquire_lock_empty_project_id_raises(self, service):
        """try_acquire_lock must raise ValueError for empty project_id."""
        with pytest.raises(ValueError, match="project_id"):
            await service.try_acquire_lock(project_id="", board_id="board-1", work_item_id="item-1", board_position=0)

    @pytest.mark.asyncio
    async def test_try_acquire_lock_empty_board_id_raises(self, service):
        """try_acquire_lock must raise ValueError for empty board_id."""
        with pytest.raises(ValueError, match="board_id"):
            await service.try_acquire_lock(project_id="proj-1", board_id="", work_item_id="item-1", board_position=0)

    @pytest.mark.asyncio
    async def test_try_acquire_lock_empty_work_item_id_raises(self, service):
        """try_acquire_lock must raise ValueError for empty work_item_id."""
        with pytest.raises(ValueError, match="work_item_id"):
            await service.try_acquire_lock(project_id="proj-1", board_id="board-1", work_item_id="", board_position=0)

    @pytest.mark.asyncio
    async def test_try_acquire_lock_negative_position_raises(self, service):
        """try_acquire_lock must raise ValueError for negative board_position."""
        with pytest.raises(ValueError, match="board_position"):
            await service.try_acquire_lock(
                project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=-1
            )

    @pytest.mark.asyncio
    async def test_release_lock_empty_project_id_raises(self, service):
        """release_lock must raise ValueError for empty project_id."""
        with pytest.raises(ValueError, match="project_id"):
            await service.release_lock(project_id="", board_id="board-1", work_item_id="item-1")

    @pytest.mark.asyncio
    async def test_release_lock_empty_board_id_raises(self, service):
        """release_lock must raise ValueError for empty board_id."""
        with pytest.raises(ValueError, match="board_id"):
            await service.release_lock(project_id="proj-1", board_id="", work_item_id="item-1")

    @pytest.mark.asyncio
    async def test_release_lock_empty_work_item_id_raises(self, service):
        """release_lock must raise ValueError for empty work_item_id."""
        with pytest.raises(ValueError, match="work_item_id"):
            await service.release_lock(project_id="proj-1", board_id="board-1", work_item_id="")

    @pytest.mark.asyncio
    async def test_get_queue_state_empty_project_id_raises(self, service):
        """get_queue_state must raise ValueError for empty project_id."""
        with pytest.raises(ValueError, match="project_id"):
            await service.get_queue_state(project_id="", board_id="board-1")

    @pytest.mark.asyncio
    async def test_get_queue_state_empty_board_id_raises(self, service):
        """get_queue_state must raise ValueError for empty board_id."""
        with pytest.raises(ValueError, match="board_id"):
            await service.get_queue_state(project_id="proj-1", board_id="")

    @pytest.mark.asyncio
    async def test_update_queue_positions_empty_project_id_raises(self, service):
        """update_queue_positions must raise ValueError for empty project_id."""
        with pytest.raises(ValueError, match="project_id"):
            await service.update_queue_positions(project_id="", board_id="board-1", updated_positions={})

    @pytest.mark.asyncio
    async def test_update_queue_positions_empty_board_id_raises(self, service):
        """update_queue_positions must raise ValueError for empty board_id."""
        with pytest.raises(ValueError, match="board_id"):
            await service.update_queue_positions(project_id="proj-1", board_id="", updated_positions={})

    # Lock acquisition contract tests

    @pytest.mark.asyncio
    async def test_try_acquire_lock_returns_lock_acquisition_result(self, service):
        """try_acquire_lock must return LockAcquisitionResult."""
        result = await service.try_acquire_lock(
            project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=0
        )
        assert isinstance(result, LockAcquisitionResult)
        assert result.status in [LockStatus.ACQUIRED, LockStatus.QUEUED, LockStatus.ALREADY_HELD]

    @pytest.mark.asyncio
    async def test_try_acquire_lock_acquired_has_no_queue_position(self, service):
        """When ACQUIRED, queue_position must be None."""
        result = await service.try_acquire_lock(
            project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=0
        )
        assert result.status == LockStatus.ACQUIRED
        assert result.queue_position is None

    @pytest.mark.asyncio
    async def test_try_acquire_lock_queued_has_queue_position(self, service):
        """When QUEUED, queue_position must be set (>= 0)."""
        # First acquire
        await service.try_acquire_lock(project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=0)
        # Second attempt gets queued
        result = await service.try_acquire_lock(
            project_id="proj-1", board_id="board-1", work_item_id="item-2", board_position=1
        )
        assert result.status == LockStatus.QUEUED
        assert result.queue_position is not None
        assert result.queue_position >= 0

    @pytest.mark.asyncio
    async def test_try_acquire_lock_already_held_has_no_queue_position(self, service):
        """When ALREADY_HELD, queue_position must be None."""
        # Acquire lock
        await service.try_acquire_lock(project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=0)
        # Try same item again
        result = await service.try_acquire_lock(
            project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=0
        )
        assert result.status == LockStatus.ALREADY_HELD
        assert result.queue_position is None

    # Release lock contract tests

    @pytest.mark.asyncio
    async def test_release_lock_returns_lock_release_result(self, service):
        """release_lock must return LockReleaseResult."""
        await service.try_acquire_lock(project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=0)
        result = await service.release_lock(project_id="proj-1", board_id="board-1", work_item_id="item-1")
        assert isinstance(result, LockReleaseResult)

    @pytest.mark.asyncio
    async def test_release_lock_non_holder_raises(self, service):
        """release_lock must raise if work_item_id doesn't hold lock."""
        await service.try_acquire_lock(project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=0)
        with pytest.raises(ValueError):
            await service.release_lock(project_id="proj-1", board_id="board-1", work_item_id="item-2")

    @pytest.mark.asyncio
    async def test_release_lock_with_queue_updates_holder(self, service):
        """When queue is non-empty, next item becomes lock holder."""
        # Item 1 gets lock
        await service.try_acquire_lock(project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=0)
        # Item 2 gets queued
        await service.try_acquire_lock(project_id="proj-1", board_id="board-1", work_item_id="item-2", board_position=1)
        # Release item 1
        result = await service.release_lock(project_id="proj-1", board_id="board-1", work_item_id="item-1")
        # Item 2 should be next in queue
        assert result.next_work_item_id == "item-2"

    # Queue state contract tests

    @pytest.mark.asyncio
    async def test_get_queue_state_returns_pipeline_queue_state(self, service):
        """get_queue_state must return PipelineQueueState."""
        result = await service.get_queue_state(project_id="proj-1", board_id="board-1")
        assert isinstance(result, PipelineQueueState)
        assert result.project_id == "proj-1"
        assert result.board_id == "board-1"

    @pytest.mark.asyncio
    async def test_get_queue_state_returns_copy(self, service):
        """get_queue_state must return a copy (modifications don't affect state)."""
        await service.try_acquire_lock(project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=0)
        state1 = await service.get_queue_state(project_id="proj-1", board_id="board-1")
        # Modify returned state
        state1.queue.append(QueueEntry(work_item_id="fake", board_position=999, enqueued_at=datetime.now(UTC)))
        # Get state again
        state2 = await service.get_queue_state(project_id="proj-1", board_id="board-1")
        # Queue should not have fake entry
        assert not any(e.work_item_id == "fake" for e in state2.queue)

    # Duplicate queue entry contract tests

    @pytest.mark.asyncio
    async def test_try_acquire_lock_duplicate_queue_entry_returns_queued(self, service):
        """Calling try_acquire_lock twice on queued item returns QUEUED with current position."""
        # Item 1 gets lock
        await service.try_acquire_lock(project_id="proj-1", board_id="board-1", work_item_id="item-1", board_position=0)
        # Item 2 gets queued
        result1 = await service.try_acquire_lock(
            project_id="proj-1", board_id="board-1", work_item_id="item-2", board_position=1
        )
        assert result1.status == LockStatus.QUEUED
        assert result1.queue_position == 0

        # Try again with item 2
        result2 = await service.try_acquire_lock(
            project_id="proj-1", board_id="board-1", work_item_id="item-2", board_position=1
        )
        assert result2.status == LockStatus.QUEUED
        assert result2.queue_position == result1.queue_position
