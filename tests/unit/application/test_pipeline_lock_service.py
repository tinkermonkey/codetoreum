"""Unit tests for IPipelineLockService with position-based queue ordering.

Tests the application-layer pipeline lock service including:
- Lock acquisition when available
- Queue management when lock is held
- Lock release granting to next queued item
- Queue ordering by board position
- Queue position updates when cards are reordered
- Edge cases (duplicate holder, empty queue, etc.)
"""

import pytest
from datetime import datetime, timezone

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.application.pipeline_lock_service import (
    LockStatus,
    LockAcquisitionResult,
    LockReleaseResult,
)


class TestLockAcquisition:
    """Tests for lock acquisition logic."""

    @pytest.mark.asyncio
    async def test_acquire_lock_when_available(self):
        """Lock acquisition should succeed when no lock is held."""
        service = InMemoryLockService()

        result = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        assert result.status == LockStatus.ACQUIRED
        assert result.work_item_id == "item-1"
        assert result.queue_position is None
        assert result.queue_length == 0

    @pytest.mark.asyncio
    async def test_acquire_lock_twice_returns_already_held(self):
        """Acquiring same lock twice should return ALREADY_HELD."""
        service = InMemoryLockService()

        # First acquisition succeeds
        result1 = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )
        assert result1.status == LockStatus.ACQUIRED

        # Second acquisition with same work item returns ALREADY_HELD
        result2 = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )
        assert result2.status == LockStatus.ALREADY_HELD
        assert result2.work_item_id == "item-1"
        assert result2.queue_position is None

    @pytest.mark.asyncio
    async def test_acquire_lock_when_held_adds_to_queue(self):
        """Lock acquisition should queue work item when lock is held."""
        service = InMemoryLockService()

        # Acquire lock with first item
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        # Try to acquire with second item
        result = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1
        )

        assert result.status == LockStatus.QUEUED
        assert result.work_item_id == "item-2"
        assert result.queue_position == 0  # First in queue
        assert result.queue_length == 1

    @pytest.mark.asyncio
    async def test_acquire_lock_with_different_boards(self):
        """Different boards should have independent locks."""
        service = InMemoryLockService()

        # Acquire lock on board 1
        result1 = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )
        assert result1.status == LockStatus.ACQUIRED

        # Should be able to acquire on board 2
        result2 = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-2",
            work_item_id="item-2",
            board_position=0
        )
        assert result2.status == LockStatus.ACQUIRED

    @pytest.mark.asyncio
    async def test_acquire_lock_with_different_projects(self):
        """Different projects should have independent locks."""
        service = InMemoryLockService()

        # Acquire lock in project 1
        result1 = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )
        assert result1.status == LockStatus.ACQUIRED

        # Should be able to acquire in project 2
        result2 = await service.try_acquire_lock(
            project_id="proj-2",
            board_id="board-1",
            work_item_id="item-2",
            board_position=0
        )
        assert result2.status == LockStatus.ACQUIRED


class TestQueueOrdering:
    """Tests for position-based queue ordering."""

    @pytest.mark.asyncio
    async def test_queue_orders_by_board_position_ascending(self):
        """Queue should order items by board position (lowest first = topmost)."""
        service = InMemoryLockService()

        # Acquire lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        # Add items to queue in non-sequential order
        result_3 = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-3",
            board_position=3
        )
        assert result_3.queue_position == 0

        result_2 = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1
        )
        assert result_2.queue_position == 0  # item-2 should be first (position 1 < 3)

        result_4 = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-4",
            board_position=2
        )
        assert result_4.queue_position == 1  # item-4 is between item-2 and item-3

        # Verify final queue order
        state = await service.get_queue_state("proj-1", "board-1")
        assert len(state.queue) == 3
        assert state.queue[0].work_item_id == "item-2"  # position 1
        assert state.queue[1].work_item_id == "item-4"  # position 2
        assert state.queue[2].work_item_id == "item-3"  # position 3

    @pytest.mark.asyncio
    async def test_queue_orders_topmost_items_first(self):
        """Topmost items (position 0) should have highest queue priority."""
        service = InMemoryLockService()

        # Acquire lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-holder",
            board_position=10
        )

        # Add items with positions
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-at-top",
            board_position=0
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-at-middle",
            board_position=5
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-at-bottom",
            board_position=9
        )

        # Verify topmost item is first in queue
        state = await service.get_queue_state("proj-1", "board-1")
        assert state.queue[0].work_item_id == "item-at-top"
        assert state.queue[0].board_position == 0

    @pytest.mark.asyncio
    async def test_queue_maintains_order_with_many_items(self):
        """Queue should maintain correct ordering with many items."""
        service = InMemoryLockService()

        # Acquire lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="lock-holder",
            board_position=100
        )

        # Add 10 items in random positions
        positions = {
            "item-1": 5,
            "item-2": 15,
            "item-3": 3,
            "item-4": 20,
            "item-5": 1,
            "item-6": 10,
            "item-7": 8,
            "item-8": 12,
            "item-9": 2,
            "item-10": 18,
        }

        for work_item_id, position in positions.items():
            await service.try_acquire_lock(
                project_id="proj-1",
                board_id="board-1",
                work_item_id=work_item_id,
                board_position=position
            )

        # Verify queue is sorted by position
        state = await service.get_queue_state("proj-1", "board-1")
        assert len(state.queue) == 10

        for i in range(len(state.queue) - 1):
            assert state.queue[i].board_position <= state.queue[i + 1].board_position


class TestLockRelease:
    """Tests for lock release and queue advancement."""

    @pytest.mark.asyncio
    async def test_release_lock_succeeds_for_holder(self):
        """Lock release should succeed if held by work_item_id."""
        service = InMemoryLockService()

        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        result = await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1"
        )

        assert result.released_work_item_id == "item-1"
        assert result.next_work_item_id is None
        assert result.queue_length_after_release == 0

    @pytest.mark.asyncio
    async def test_release_lock_fails_if_not_holder(self):
        """Lock release should fail if not held by work_item_id."""
        service = InMemoryLockService()

        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        with pytest.raises(ValueError, match="does not hold lock"):
            await service.release_lock(
                project_id="proj-1",
                board_id="board-1",
                work_item_id="item-2"
            )

    @pytest.mark.asyncio
    async def test_release_lock_fails_if_not_held(self):
        """Lock release should fail if lock is not held."""
        service = InMemoryLockService()

        with pytest.raises(ValueError, match="does not hold lock"):
            await service.release_lock(
                project_id="proj-1",
                board_id="board-1",
                work_item_id="item-1"
            )

    @pytest.mark.asyncio
    async def test_release_lock_grants_to_first_queued(self):
        """Lock release should grant to first item in queue."""
        service = InMemoryLockService()

        # Acquire lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        # Queue second item
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1
        )

        # Release lock
        result = await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1"
        )

        assert result.next_work_item_id == "item-2"
        assert result.queue_length_after_release == 0

        # Verify item-2 now holds lock
        state = await service.get_queue_state("proj-1", "board-1")
        assert state.lock_holder == "item-2"

    @pytest.mark.asyncio
    async def test_release_lock_grants_to_topmost_in_queue(self):
        """Lock release should grant to topmost (lowest position) item in queue."""
        service = InMemoryLockService()

        # Acquire lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-holder",
            board_position=0
        )

        # Queue items with positions (added in non-order)
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-at-3",
            board_position=3
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-at-1",
            board_position=1
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-at-2",
            board_position=2
        )

        # Release lock
        result = await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-holder"
        )

        # Should grant to topmost (position 1)
        assert result.next_work_item_id == "item-at-1"

        # Verify item-at-1 now holds lock
        state = await service.get_queue_state("proj-1", "board-1")
        assert state.lock_holder == "item-at-1"
        assert len(state.queue) == 2
        assert state.queue[0].work_item_id == "item-at-2"
        assert state.queue[1].work_item_id == "item-at-3"

    @pytest.mark.asyncio
    async def test_release_empty_queue_leaves_lock_available(self):
        """Lock release with empty queue should make lock available."""
        service = InMemoryLockService()

        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1"
        )

        state = await service.get_queue_state("proj-1", "board-1")
        assert state.lock_holder is None
        assert state.lock_acquired_at is None
        assert len(state.queue) == 0


class TestQueuePositionUpdates:
    """Tests for updating queue when cards are reordered."""

    @pytest.mark.asyncio
    async def test_update_queue_positions_reorders_queue(self):
        """Update positions should re-sort queue by new positions."""
        service = InMemoryLockService()

        # Acquire lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="lock-holder",
            board_position=10
        )

        # Queue items with initial positions
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=1
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=2
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-3",
            board_position=3
        )

        # Verify initial order
        state = await service.get_queue_state("proj-1", "board-1")
        assert state.queue[0].work_item_id == "item-1"
        assert state.queue[1].work_item_id == "item-2"
        assert state.queue[2].work_item_id == "item-3"

        # Reorder via human card movement
        await service.update_queue_positions(
            project_id="proj-1",
            board_id="board-1",
            updated_positions={
                "item-1": 5,  # Moved down
                "item-2": 0,  # Moved to top
                "item-3": 2,  # Stayed roughly same
            }
        )

        # Verify queue is re-sorted
        state = await service.get_queue_state("proj-1", "board-1")
        assert state.queue[0].work_item_id == "item-2"  # Now topmost
        assert state.queue[0].board_position == 0
        assert state.queue[1].work_item_id == "item-3"  # Next
        assert state.queue[1].board_position == 2
        assert state.queue[2].work_item_id == "item-1"  # Last
        assert state.queue[2].board_position == 5

    @pytest.mark.asyncio
    async def test_update_queue_positions_partial_update(self):
        """Update positions should only affect items in updated_positions."""
        service = InMemoryLockService()

        # Acquire lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="lock-holder",
            board_position=10
        )

        # Queue items
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=1
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=2
        )

        # Only update item-1
        await service.update_queue_positions(
            project_id="proj-1",
            board_id="board-1",
            updated_positions={"item-1": 5}
        )

        state = await service.get_queue_state("proj-1", "board-1")
        assert state.queue[0].work_item_id == "item-2"  # item-2 position unchanged
        assert state.queue[0].board_position == 2
        assert state.queue[1].work_item_id == "item-1"  # item-1 updated
        assert state.queue[1].board_position == 5

    @pytest.mark.asyncio
    async def test_update_queue_positions_empty_queue(self):
        """Update positions on empty queue should be safe."""
        service = InMemoryLockService()

        # No-op on empty queue
        await service.update_queue_positions(
            project_id="proj-1",
            board_id="board-1",
            updated_positions={"item-1": 5}
        )

        state = await service.get_queue_state("proj-1", "board-1")
        assert len(state.queue) == 0

    @pytest.mark.asyncio
    async def test_update_queue_positions_nonexistent_board(self):
        """Update positions on nonexistent board should be safe."""
        service = InMemoryLockService()

        # No-op on nonexistent board
        await service.update_queue_positions(
            project_id="proj-1",
            board_id="board-1",
            updated_positions={"item-1": 5}
        )

        state = await service.get_queue_state("proj-1", "board-1")
        assert len(state.queue) == 0


class TestQueueStateQueries:
    """Tests for querying queue state."""

    @pytest.mark.asyncio
    async def test_get_queue_state_empty(self):
        """Get queue state should return empty state for new board."""
        service = InMemoryLockService()

        state = await service.get_queue_state("proj-1", "board-1")

        assert state.project_id == "proj-1"
        assert state.board_id == "board-1"
        assert state.lock_holder is None
        assert state.lock_acquired_at is None
        assert len(state.queue) == 0

    @pytest.mark.asyncio
    async def test_get_queue_state_with_lock_holder(self):
        """Get queue state should return lock holder info."""
        service = InMemoryLockService()

        before = datetime.now(timezone.utc)
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )
        after = datetime.now(timezone.utc)

        state = await service.get_queue_state("proj-1", "board-1")

        assert state.lock_holder == "item-1"
        assert state.lock_acquired_at is not None
        assert before <= state.lock_acquired_at <= after

    @pytest.mark.asyncio
    async def test_get_queue_state_with_queued_items(self):
        """Get queue state should return all queued items."""
        service = InMemoryLockService()

        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=2
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-3",
            board_position=1
        )

        state = await service.get_queue_state("proj-1", "board-1")

        assert state.lock_holder == "item-1"
        assert len(state.queue) == 2
        assert state.queue[0].work_item_id == "item-3"
        assert state.queue[1].work_item_id == "item-2"

    @pytest.mark.asyncio
    async def test_get_queue_state_returns_copy(self):
        """Get queue state should return a copy (not reference)."""
        service = InMemoryLockService()

        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1
        )

        state1 = await service.get_queue_state("proj-1", "board-1")
        initial_queue_length = len(state1.queue)

        # Modify the returned state
        state1.queue.clear()

        # Get state again - should not be affected by modification
        state2 = await service.get_queue_state("proj-1", "board-1")
        assert len(state2.queue) == initial_queue_length


class TestOrphanedLockHolder:
    """Tests for edge cases involving orphaned lock holders.

    An orphaned lock holder is a work item that holds a lock but has been
    removed from the board (deleted, moved to another board, etc.). The system
    should handle this gracefully.
    """

    @pytest.mark.asyncio
    async def test_orphaned_lock_holder_identified_in_queue_state(self):
        """Queue state should identify orphaned lock holders."""
        service = InMemoryLockService()

        # Item-1 acquires lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        # Item-2 queued
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1
        )

        # Check queue state - item-1 holds lock
        state = await service.get_queue_state("proj-1", "board-1")
        assert state.lock_holder == "item-1"
        assert len(state.queue) == 1

        # Scenario: item-1 has been removed from board (orphaned)
        # The queue state should still show item-1 as holder
        # (Recovery would happen via lock timeout or manual release)
        assert state.lock_holder == "item-1"
        assert state.queue[0].work_item_id == "item-2"

    @pytest.mark.asyncio
    async def test_release_lock_for_orphaned_holder_grants_to_next(self):
        """Releasing an orphaned lock holder's lock should grant to next in queue."""
        service = InMemoryLockService()

        # Item-1 acquires lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        # Item-2 and item-3 queued
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-3",
            board_position=2
        )

        # Scenario: item-1 removed from board (orphaned)
        # System releases item-1's lock manually (e.g., via board reconciliation)
        result = await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1"
        )

        # Lock should be granted to item-2
        assert result.released_work_item_id == "item-1"
        assert result.next_work_item_id == "item-2"
        assert result.queue_length_after_release == 1  # Only item-3 remains

        # Verify new lock holder
        state = await service.get_queue_state("proj-1", "board-1")
        assert state.lock_holder == "item-2"
        assert len(state.queue) == 1
        assert state.queue[0].work_item_id == "item-3"

    @pytest.mark.asyncio
    async def test_acquire_lock_after_orphaned_holder_removed(self):
        """After orphaned lock holder is removed, new items can acquire lock."""
        service = InMemoryLockService()

        # Item-1 acquires lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        # Scenario: item-1 removed from board (orphaned)
        # System releases lock
        await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1"
        )

        # New item should be able to acquire lock
        result = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1
        )

        assert result.status == LockStatus.ACQUIRED
        assert result.work_item_id == "item-2"

        # Verify lock holder
        state = await service.get_queue_state("proj-1", "board-1")
        assert state.lock_holder == "item-2"

    @pytest.mark.asyncio
    async def test_multiple_orphaned_items_in_queue(self):
        """Queue can contain multiple orphaned items waiting for lock."""
        service = InMemoryLockService()

        # Item-1 holds lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

        # Item-2, item-3, item-4 queued
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-3",
            board_position=2
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-4",
            board_position=3
        )

        # Scenario: item-2 and item-3 removed from board (orphaned)
        # Queue state should still show all items
        state = await service.get_queue_state("proj-1", "board-1")
        assert state.lock_holder == "item-1"
        assert len(state.queue) == 3
        assert state.queue[0].work_item_id == "item-2"
        assert state.queue[1].work_item_id == "item-3"
        assert state.queue[2].work_item_id == "item-4"

        # When lock is released, it grants to first queued item (item-2)
        # even though item-2 is orphaned
        result = await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1"
        )
        assert result.next_work_item_id == "item-2"

        # Orphaned item-2 now holds lock
        # This would be cleaned up by board reconciliation/timeout logic
        state = await service.get_queue_state("proj-1", "board-1")
        assert state.lock_holder == "item-2"
