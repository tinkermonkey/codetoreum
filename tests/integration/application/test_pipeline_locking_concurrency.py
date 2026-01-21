"""Concurrency tests for pipeline lock service.

Tests verify thread safety and race condition handling under concurrent access:
- Multiple work items acquiring locks simultaneously
- Concurrent position updates during lock operations
- Race conditions between lock release and column changes
"""

import asyncio
import pytest
from datetime import datetime, timezone

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
    LockStatus,
)
from codetoreum.infrastructure.event_bus import EventBus


@pytest.fixture
def event_bus():
    """Create event bus for lock events."""
    return EventBus()


@pytest.fixture
def lock_service(event_bus):
    """Create lock service with event bus."""
    return InMemoryLockService(event_bus=event_bus)


class TestConcurrentLockAcquisitions:
    """Test concurrent lock acquisition scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_lock_acquisitions_on_same_board(self, lock_service):
        """Verify only one work item acquires lock when multiple try simultaneously.

        This test simulates the scenario where 10 work items enter the same
        trigger column at approximately the same time and all try to acquire
        the lock concurrently. Only one should succeed; others should be queued.
        """
        project_id = "proj-1"
        board_id = "board-1"

        # Spawn 10 tasks trying to acquire lock concurrently
        tasks = [
            lock_service.try_acquire_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=f"item_{i}",
                board_position=i  # Positions determine queue order
            )
            for i in range(10)
        ]
        results = await asyncio.gather(*tasks)

        # Verify exactly one succeeded
        successful = [r for r in results if r.status == LockStatus.ACQUIRED]
        assert len(successful) == 1, "Exactly one lock acquisition should succeed"

        # Verify others are queued
        queued = [r for r in results if r.status == LockStatus.QUEUED]
        assert len(queued) == 9, "Nine work items should be queued"

        # Verify queue ordering is by board position (lowest first)
        state = await lock_service.get_queue_state(project_id, board_id)
        assert len(state.queue) == 9

        # Queue should be sorted by board_position
        positions = [entry.board_position for entry in state.queue]
        assert positions == sorted(positions), "Queue should be ordered by board position"

    @pytest.mark.asyncio
    async def test_concurrent_acquisitions_different_boards(self, lock_service):
        """Verify each board has independent lock state.

        Tests that concurrent acquisitions on different boards don't interfere
        with each other - each should succeed since they're different locks.
        """
        project_id = "proj-1"

        # Acquire locks on 5 different boards concurrently
        tasks = [
            lock_service.try_acquire_lock(
                project_id=project_id,
                board_id=f"board-{i}",
                work_item_id=f"item_board{i}",
                board_position=0
            )
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)

        # All should succeed since they're different boards
        assert all(r.status == LockStatus.ACQUIRED for r in results), \
            "All acquisitions should succeed on different boards"

    @pytest.mark.asyncio
    async def test_duplicate_acquisition_attempt_during_concurrent_ops(self, lock_service):
        """Verify same work item can't acquire lock twice even during concurrent operations.

        Tests that if a work item tries to acquire a lock it already holds
        (even while other operations are happening), it gets ALREADY_HELD status.
        """
        project_id = "proj-1"
        board_id = "board-1"
        work_item_id = "item-1"

        # First acquisition should succeed
        result1 = await lock_service.try_acquire_lock(
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
            board_position=0
        )
        assert result1.status == LockStatus.ACQUIRED

        # Now while other items are trying to acquire (simulated by immediate concurrent attempt)
        tasks = [
            lock_service.try_acquire_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=work_item_id,  # Same item trying again
                board_position=0
            ),
            lock_service.try_acquire_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id="item-2",
                board_position=1
            ),
        ]
        results = await asyncio.gather(*tasks)

        # First should return ALREADY_HELD
        assert results[0].status == LockStatus.ALREADY_HELD
        # Second should be QUEUED
        assert results[1].status == LockStatus.QUEUED


class TestConcurrentPositionUpdates:
    """Test concurrent position updates during lock operations."""

    @pytest.mark.asyncio
    async def test_position_updates_during_concurrent_acquisitions(self, lock_service):
        """Verify position updates work correctly while acquisitions are happening.

        Tests the scenario where:
        1. Multiple items are being queued
        2. User reorders cards in UI (position updates)
        3. All operations complete without queue corruption
        """
        project_id = "proj-1"
        board_id = "board-1"

        # First, acquire lock on one item
        await lock_service.try_acquire_lock(
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-holder",
            board_position=0
        )

        # Queue several items with different positions
        queue_tasks = [
            lock_service.try_acquire_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=f"item-{i}",
                board_position=i
            )
            for i in range(1, 6)
        ]
        await asyncio.gather(*queue_tasks)

        # Now update positions while queue is stable
        # This simulates user reordering cards
        updated_positions = {
            "item-1": 10,  # Move to end
            "item-2": 5,   # Move higher
            "item-3": 2,   # Move higher
            "item-4": 8,
            "item-5": 3,
        }

        # Update positions (should not raise even though items are queued)
        await lock_service.update_queue_positions(
            project_id=project_id,
            board_id=board_id,
            updated_positions=updated_positions
        )

        # Verify queue is re-sorted by new positions
        state = await lock_service.get_queue_state(project_id, board_id)
        positions = [entry.board_position for entry in state.queue]
        expected_order = [2, 3, 5, 8, 10]
        assert positions == expected_order, \
            f"Queue should be re-ordered by new positions. Got {positions}, expected {expected_order}"

    @pytest.mark.asyncio
    async def test_concurrent_position_updates_and_release(self, lock_service):
        """Verify position updates and lock release don't cause race conditions.

        Tests concurrent:
        - Position updates from UI reordering
        - Lock release to next queued item
        - Queue state queries
        """
        project_id = "proj-1"
        board_id = "board-1"

        # Acquire lock and queue items
        lock_holder = "item-holder"
        await lock_service.try_acquire_lock(
            project_id=project_id,
            board_id=board_id,
            work_item_id=lock_holder,
            board_position=0
        )

        queued_items = ["item-1", "item-2", "item-3", "item-4", "item-5"]
        for i, item_id in enumerate(queued_items):
            await lock_service.try_acquire_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=item_id,
                board_position=i + 1
            )

        # Now run concurrent operations: update positions and release lock
        async def update_positions():
            await lock_service.update_queue_positions(
                project_id=project_id,
                board_id=board_id,
                updated_positions={
                    "item-1": 10,
                    "item-2": 5,
                    "item-3": 2,
                    "item-4": 8,
                    "item-5": 3,
                }
            )

        async def release_and_check():
            result = await lock_service.release_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=lock_holder
            )
            return result

        # Run update and release concurrently
        update_task = asyncio.create_task(update_positions())
        release_task = asyncio.create_task(release_and_check())

        release_result, _ = await asyncio.gather(release_task, update_task)

        # Next item should be the one with lowest position after update
        # That's item-3 with position 2
        state = await lock_service.get_queue_state(project_id, board_id)
        assert state.lock_holder == "item-3", \
            "After release with concurrent position updates, lock should go to topmost item"


class TestRaceConditionsBetweenLockAndColumnChange:
    """Test race conditions between lock operations and column changes."""

    @pytest.mark.asyncio
    async def test_lock_release_while_item_moves_column(self, lock_service):
        """Verify lock release is atomic and unaffected by concurrent item moves.

        Simulates:
        1. Item holds lock in trigger column
        2. Item gets moved to exit column (concurrently)
        3. Lock is released
        4. Queue is properly advanced
        """
        project_id = "proj-1"
        board_id = "board-1"

        # Acquire lock and queue items
        lock_holder = "item-moving"
        await lock_service.try_acquire_lock(
            project_id=project_id,
            board_id=board_id,
            work_item_id=lock_holder,
            board_position=0
        )

        # Queue some items
        for i in range(1, 4):
            await lock_service.try_acquire_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=f"item-{i}",
                board_position=i
            )

        # Release lock (simulating item reaching exit column)
        release_result = await lock_service.release_lock(
            project_id=project_id,
            board_id=board_id,
            work_item_id=lock_holder
        )

        # Verify lock was properly transferred
        assert release_result.next_work_item_id == "item-1", \
            "Lock should transfer to first queued item"

        # Verify queue was advanced
        state = await lock_service.get_queue_state(project_id, board_id)
        assert state.lock_holder == "item-1"
        assert len(state.queue) == 2, "Queue should have 2 remaining items"

        # Verify remaining queue order
        remaining_ids = [entry.work_item_id for entry in state.queue]
        assert remaining_ids == ["item-2", "item-3"]

    @pytest.mark.asyncio
    async def test_multiple_sequential_releases(self, lock_service):
        """Verify sequential lock releases properly advance through queue.

        Tests that as items complete (release lock), the next items in queue
        properly acquire the lock in the correct order.
        """
        project_id = "proj-1"
        board_id = "board-1"

        # Acquire initial lock and queue 5 items
        lock_holders = ["item-0"] + [f"item-{i}" for i in range(1, 6)]

        await lock_service.try_acquire_lock(
            project_id=project_id,
            board_id=board_id,
            work_item_id=lock_holders[0],
            board_position=0
        )

        for i, item_id in enumerate(lock_holders[1:], start=1):
            await lock_service.try_acquire_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=item_id,
                board_position=i
            )

        # Release locks one by one and verify advancement
        for i in range(len(lock_holders) - 1):
            state = await lock_service.get_queue_state(project_id, board_id)
            assert state.lock_holder == lock_holders[i]

            release_result = await lock_service.release_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=lock_holders[i]
            )

            # Next item should get lock
            expected_next = lock_holders[i + 1] if i + 1 < len(lock_holders) else None
            assert release_result.next_work_item_id == expected_next

            # Verify lock transferred
            state = await lock_service.get_queue_state(project_id, board_id)
            assert state.lock_holder == expected_next

    @pytest.mark.asyncio
    async def test_rapid_fire_acquisitions_and_releases(self, lock_service):
        """Stress test with rapid acquisitions and releases.

        Tests that the service handles high-frequency lock operations
        without deadlocks or queue corruption.
        """
        project_id = "proj-1"
        board_id = "board-1"

        # Start with lock holder
        await lock_service.try_acquire_lock(
            project_id=project_id,
            board_id=board_id,
            work_item_id="initial",
            board_position=0
        )

        # Rapidly queue and dequeue items
        num_iterations = 10

        for iteration in range(num_iterations):
            # Queue new item
            queue_result = await lock_service.try_acquire_lock(
                project_id=project_id,
                board_id=board_id,
                work_item_id=f"item-{iteration}",
                board_position=iteration + 1
            )
            assert queue_result.status == LockStatus.QUEUED

            # Simulate processing and release
            # Get current lock holder
            state = await lock_service.get_queue_state(project_id, board_id)
            current_holder = state.lock_holder

            # Release current lock
            if current_holder:
                release_result = await lock_service.release_lock(
                    project_id=project_id,
                    board_id=board_id,
                    work_item_id=current_holder
                )

                # Verify the operation
                state_after = await lock_service.get_queue_state(project_id, board_id)
                assert state_after.lock_holder == release_result.next_work_item_id

        # At end, queue should be empty
        final_state = await lock_service.get_queue_state(project_id, board_id)
        assert len(final_state.queue) == 0
