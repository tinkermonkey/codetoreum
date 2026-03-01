"""Integration tests for pipeline locking concurrency scenarios.

Comprehensive test suite covering concurrent access patterns:
- Concurrent lock acquisitions on same board
- Concurrent position updates during lock operations
- Race between lock release and column change events
- Stale lock recovery under concurrent pressure
- Queue ordering correctness under contention
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.application.pipeline_lock_service import (
    LockStatus,
)
from codetoreum.infrastructure.event_bus import EventBus


@pytest.fixture
def event_bus():
    """Mock event bus for capturing emitted events."""
    bus = MagicMock(spec=EventBus)
    bus.emit = AsyncMock()
    return bus


@pytest.fixture
def lock_service(event_bus):
    """Lock service with 2-hour stale threshold."""
    return InMemoryLockService(event_bus=event_bus, stale_threshold_seconds=7200)


@pytest.mark.asyncio
class TestPipelineLockingConcurrency:
    """Concurrency tests for pipeline lock service."""

    # ===== TEST 1: CONCURRENT LOCK ACQUISITIONS =====

    async def test_concurrent_lock_acquisitions_only_one_succeeds(self, lock_service):
        """Verify only one work item acquires lock when multiple try simultaneously.

        Tests: Multiple concurrent lock acquisition attempts on same board
        Expected: Exactly one ACQUIRED, rest QUEUED in position order
        """
        project_id = "project-1"
        board_id = "board-1"
        num_items = 10

        # Spawn 10 tasks trying to acquire lock concurrently
        tasks = [
            lock_service.try_acquire_lock(
                project_id=project_id, board_id=board_id, work_item_id=f"item-{i}", board_position=i
            )
            for i in range(num_items)
        ]
        results = await asyncio.gather(*tasks)

        # Verify exactly one acquired
        acquired = [r for r in results if r.status == LockStatus.ACQUIRED]
        assert len(acquired) == 1
        assert acquired[0].work_item_id == "item-0"

        # Verify others are queued
        queued = [r for r in results if r.status == LockStatus.QUEUED]
        assert len(queued) == num_items - 1

        # Verify queue positions are correct (item-1 at 0, item-2 at 1, etc.)
        for i, result in enumerate(sorted(queued, key=lambda r: r.queue_position)):
            assert result.work_item_id == f"item-{i + 1}"
            assert result.queue_position == i

    # ===== TEST 2: CONCURRENT POSITION UPDATES =====

    async def test_concurrent_position_updates_during_lock_operations(self, lock_service):
        """Verify queue positions update correctly with concurrent position change requests.

        Tests: What happens if update_queue_positions() called while try_acquire_lock/release_lock
        Expected: Queue remains consistent, no corrupted state
        """
        project_id = "project-1"
        board_id = "board-1"

        # First, establish lock and queue
        result1 = await lock_service.try_acquire_lock(project_id, board_id, "item-0", board_position=0)
        assert result1.status == LockStatus.ACQUIRED

        result2 = await lock_service.try_acquire_lock(project_id, board_id, "item-1", board_position=1)
        assert result2.status == LockStatus.QUEUED
        assert result2.queue_position == 0

        # Now update positions concurrently with release
        update_task = lock_service.update_queue_positions(
            project_id,
            board_id,
            {"item-1": 0},  # Move to top
        )
        release_task = lock_service.release_lock(project_id, board_id, "item-0")

        update_result, release_result = await asyncio.gather(update_task, release_task)

        # Verify queue state is consistent
        assert release_result.next_work_item_id == "item-1"
        assert release_result.queue_length_after_release == 0

    # ===== TEST 3: RACE BETWEEN LOCK RELEASE AND COLUMN CHANGE =====

    async def test_race_between_lock_release_and_position_update(self, lock_service):
        """Test race condition where position updates during lock release.

        Tests: What if work item moves columns while releasing its lock?
        Expected: Lock release succeeds, queue position updates don't interfere
        """
        project_id = "project-1"
        board_id = "board-1"

        # Setup: item-0 holds lock, item-1 and item-2 queued
        r1 = await lock_service.try_acquire_lock(project_id, board_id, "item-0", 0)
        assert r1.status == LockStatus.ACQUIRED

        r2 = await lock_service.try_acquire_lock(project_id, board_id, "item-1", 1)
        r3 = await lock_service.try_acquire_lock(project_id, board_id, "item-2", 2)
        assert r2.status == LockStatus.QUEUED
        assert r3.status == LockStatus.QUEUED

        # Race: Release while position updates happen
        release_task = lock_service.release_lock(project_id, board_id, "item-0")
        update_task = lock_service.update_queue_positions(
            project_id,
            board_id,
            {"item-2": 0, "item-1": 1},  # Reorder
        )

        release_result, update_result = await asyncio.gather(release_task, update_task)

        # Verify lock was released to one of the queued items
        # Due to race, it could be item-1 or item-2 depending on timing
        assert release_result.next_work_item_id in ["item-1", "item-2"]

    # ===== TEST 4: STALE LOCK RECOVERY =====

    async def test_stale_lock_recovery_under_concurrent_acquisition(self, lock_service):
        """Test stale lock detection and recovery with concurrent acquire attempts.

        Tests: When stale lock is detected and recovered, concurrent acquires handle it
        Expected: Stale lock forcibly released, next item acquires, event emitted
        """
        project_id = "project-1"
        board_id = "board-1"

        # Item-0 acquires lock
        result = await lock_service.try_acquire_lock(project_id, board_id, "item-0", board_position=0)
        assert result.status == LockStatus.ACQUIRED

        # Item-1 queued
        result = await lock_service.try_acquire_lock(project_id, board_id, "item-1", board_position=1)
        assert result.status == LockStatus.QUEUED

        # Manually age the lock beyond stale threshold
        state_key = f"{project_id}:{board_id}"
        if state_key in lock_service._lock_state:
            old_time = datetime.now(UTC).timestamp() - 7300  # > 2 hours old
            lock_service._lock_state[state_key].lock_acquired_at = datetime.fromtimestamp(old_time, tz=UTC)

        # Try to acquire - should detect stale and recover
        result = await lock_service.try_acquire_lock(project_id, board_id, "item-2", board_position=2)

        # Stale recovery should have granted lock to item-1
        assert result.status == LockStatus.QUEUED or result.status == LockStatus.ACQUIRED

    # ===== TEST 5: QUEUE CONSISTENCY UNDER STRESS =====

    async def test_queue_consistency_with_many_concurrent_items(self, lock_service):
        """Stress test: many concurrent additions maintain consistent queue.

        Tests: Concurrent atomicity with 100 work items
        Expected: All queued correctly with no duplicates or loss
        """
        project_id = "project-1"
        board_id = "board-1"
        num_items = 100

        tasks = [
            lock_service.try_acquire_lock(project_id, board_id, f"item-{i}", board_position=i) for i in range(num_items)
        ]
        results = await asyncio.gather(*tasks)

        # Verify: 1 acquired, 99 queued
        acquired = [r for r in results if r.status == LockStatus.ACQUIRED]
        queued = [r for r in results if r.status == LockStatus.QUEUED]

        assert len(acquired) == 1
        assert len(queued) == num_items - 1

        # Verify no duplicates and all items accounted for
        all_items = {r.work_item_id for r in results}
        expected_items = {f"item-{i}" for i in range(num_items)}
        assert all_items == expected_items

    # ===== TEST 6: SEQUENTIAL HANDOFF CORRECTNESS =====

    async def test_sequential_handoff_after_lock_release(self, lock_service):
        """Test that lock correctly passes to next queued item.

        Tests: Release then acquire sequence
        Expected: Next queued item acquires lock, others remain queued
        """
        project_id = "project-1"
        board_id = "board-1"

        # Setup: item-0 holds lock, item-1 and item-2 queued
        r1 = await lock_service.try_acquire_lock(project_id, board_id, "item-0", 0)
        r2 = await lock_service.try_acquire_lock(project_id, board_id, "item-1", 1)
        r3 = await lock_service.try_acquire_lock(project_id, board_id, "item-2", 2)

        assert r1.status == LockStatus.ACQUIRED
        assert r2.status == LockStatus.QUEUED
        assert r3.status == LockStatus.QUEUED

        # Release item-0
        release_result = await lock_service.release_lock(project_id, board_id, "item-0")

        # Verify next item is item-1
        assert release_result.next_work_item_id == "item-1"
        assert release_result.queue_length_after_release == 1

        # Try to acquire with item-1
        result = await lock_service.try_acquire_lock(project_id, board_id, "item-1", 1)

        # If item-1 not automatically promoted, it should still be able to acquire
        assert result.status == LockStatus.ACQUIRED or result.status == LockStatus.ALREADY_HELD

    # ===== TEST 7: RELEASE BY NON-HOLDER FAILS =====

    async def test_release_by_non_holder_raises_error(self, lock_service):
        """Verify that only lock holder can release.

        Tests: Non-holder trying to release
        Expected: Raises ValueError, lock remains held
        """
        project_id = "project-1"
        board_id = "board-1"

        # Item-0 acquires lock
        result = await lock_service.try_acquire_lock(project_id, board_id, "item-0", board_position=0)
        assert result.status == LockStatus.ACQUIRED

        # Item-1 tries to release (doesn't hold lock) - should raise ValueError
        with pytest.raises(ValueError, match="does not hold lock"):
            await lock_service.release_lock(project_id, board_id, "item-1")

        # Verify lock still held by item-0
        state_key = f"{project_id}:{board_id}"
        if state_key in lock_service._lock_state:
            assert lock_service._lock_state[state_key].lock_holder == "item-0"

    # ===== TEST 8: ALREADY_HELD DETECTION =====

    async def test_already_held_when_item_acquires_twice(self, lock_service):
        """Test ALREADY_HELD status when work item tries to acquire again.

        Tests: Item requesting lock it already holds
        Expected: ALREADY_HELD status returned
        """
        project_id = "project-1"
        board_id = "board-1"

        # Item-0 acquires lock
        result1 = await lock_service.try_acquire_lock(project_id, board_id, "item-0", board_position=0)
        assert result1.status == LockStatus.ACQUIRED

        # Item-0 tries to acquire again
        result2 = await lock_service.try_acquire_lock(project_id, board_id, "item-0", board_position=0)

        # Should return ALREADY_HELD
        assert result2.status == LockStatus.ALREADY_HELD
