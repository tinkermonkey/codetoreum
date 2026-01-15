"""
Scenario 10: Comprehensive Pipeline Locking Scenarios

Tests the complete pipeline locking system including:
- Lock acquisition and release
- Queue management with position-based ordering
- Concurrent lock contention (multiple items competing for single lock)
- Stale lock detection and recovery
- Queue reordering when work items are moved on the board
- Lock timeout scenarios
- Deadlock prevention through queue-based waiting

Key Features Tested:
- Lock acquisition when available vs queuing when held
- FIFO queue ordering by board position (lowest position = highest priority)
- Lock release triggering next item in queue
- Stale lock detection (locks older than threshold)
- Stale lock recovery (automatic re-acquisition)
- Dynamic queue reordering when board changes
- Multiple independent boards with separate locks
- Edge cases (duplicate holders, orphaned locks, empty queues)

Expected Outcomes:
- Lock always held by one item (or none)
- Queue always sorted by board position
- No deadlocks (queue guarantees progression)
- Stale locks recovered automatically
- Each released lock triggers next acquisition
"""

from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.application.pipeline_lock_service import LockStatus
from codetoreum.domain.events.lock_events import (
    LockStaleDetectedEvent,
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
    WorkItemQueuedEvent,
)


@pytest.mark.asyncio
async def test_scenario_10_basic_lock_acquisition_and_release():
    """Test basic lock acquisition when available and release."""
    service = InMemoryLockService()

    # Acquire lock with first item
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

    # Release lock
    release_result = await service.release_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1"
    )

    assert release_result.released_work_item_id == "item-1"
    assert release_result.queue_length_after_release == 0
    assert release_result.next_work_item_id is None


@pytest.mark.asyncio
async def test_scenario_10_lock_queuing_when_held():
    """Test queuing behavior when lock is already held."""
    service = InMemoryLockService()

    # Acquire lock with first item
    result1 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        board_position=0
    )
    assert result1.status == LockStatus.ACQUIRED

    # Try to acquire with second item - should queue
    result2 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-2",
        board_position=1
    )
    assert result2.status == LockStatus.QUEUED
    assert result2.queue_position == 0
    assert result2.queue_length == 1

    # Third item tries to acquire - should queue after second
    result3 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-3",
        board_position=2
    )
    assert result3.status == LockStatus.QUEUED
    assert result3.queue_position == 1
    assert result3.queue_length == 2


@pytest.mark.asyncio
async def test_scenario_10_queue_position_ordering():
    """Test that queue is ordered by board position (topmost first)."""
    service = InMemoryLockService()

    # Acquire lock
    await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        board_position=0
    )

    # Queue items with non-sequential positions
    # Item with position 5 arrives first
    result_5 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-5",
        board_position=5
    )
    assert result_5.queue_position == 0
    assert result_5.queue_length == 1

    # Item with position 2 arrives second
    result_2 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-2",
        board_position=2
    )
    assert result_2.queue_position == 0  # Should be first because position 2 < 5
    assert result_2.queue_length == 2

    # Item with position 8 arrives third
    result_8 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-8",
        board_position=8
    )
    assert result_8.queue_position == 2  # After item-2 (pos 2) and item-5 (pos 5)
    assert result_8.queue_length == 3

    # Verify queue order
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert len(queue_state.queue) == 3
    assert queue_state.queue[0].work_item_id == "item-2"  # pos 2
    assert queue_state.queue[1].work_item_id == "item-5"  # pos 5
    assert queue_state.queue[2].work_item_id == "item-8"  # pos 8


@pytest.mark.asyncio
async def test_scenario_10_lock_release_advances_queue():
    """Test that releasing lock grants it to next queued item."""
    service = InMemoryLockService()

    # Setup: item-1 holds lock, item-2 and item-3 are queued
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

    await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-3",
        board_position=2
    )

    # Release lock held by item-1
    release_result = await service.release_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1"
    )

    assert release_result.released_work_item_id == "item-1"
    assert release_result.next_work_item_id == "item-2"
    assert release_result.queue_length_after_release == 1

    # Verify lock was transferred to item-2
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert queue_state.lock_holder == "item-2"
    assert len(queue_state.queue) == 1
    assert queue_state.queue[0].work_item_id == "item-3"


@pytest.mark.asyncio
async def test_scenario_10_concurrent_lock_contention():
    """Test multiple items competing for single lock."""
    service = InMemoryLockService()

    # Simulate 10 items competing for the same lock
    items = [f"item-{i}" for i in range(1, 11)]
    positions = list(range(0, 10))

    # First item acquires lock
    result = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id=items[0],
        board_position=positions[0]
    )
    assert result.status == LockStatus.ACQUIRED

    # Remaining items queue in random order
    queue_positions = []
    for i in range(1, len(items)):
        result = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id=items[i],
            board_position=positions[i]
        )
        assert result.status == LockStatus.QUEUED
        queue_positions.append((items[i], positions[i], result.queue_position))

    # Verify queue is sorted by position
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert len(queue_state.queue) == 9

    # Queue should be sorted by position (ascending)
    for idx, entry in enumerate(queue_state.queue):
        if idx > 0:
            assert entry.board_position >= queue_state.queue[idx - 1].board_position

    # Release items one by one and verify order
    current_holder = items[0]
    for expected_idx in range(1, len(items)):
        release_result = await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id=current_holder
        )
        assert release_result.next_work_item_id == items[expected_idx]
        current_holder = items[expected_idx]


@pytest.mark.asyncio
async def test_scenario_10_stale_lock_detection_and_recovery():
    """Test automatic detection and recovery of stale locks."""
    # Create service with very short stale threshold (1 second)
    service = InMemoryLockService(stale_threshold_seconds=1)

    # Acquire lock
    await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        board_position=0
    )

    # Queue another item
    result = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-2",
        board_position=1
    )
    assert result.status == LockStatus.QUEUED

    # Get current state
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert queue_state.lock_holder == "item-1"
    initial_acquisition_time = queue_state.lock_acquired_at

    # Simulate time passage by manually setting the acquired_at time to far past
    service.set_lock_acquired_at(
        project_id="proj-1",
        board_id="board-1",
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=5)
    )

    # Try to acquire lock again - stale lock should be detected and recovered
    result = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-2",
        board_position=1
    )

    # Should indicate we acquired the lock (stale recovery grants it to waiting item)
    assert result.status == LockStatus.ACQUIRED
    assert result.work_item_id == "item-2"

    # Verify lock holder changed
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert queue_state.lock_holder == "item-2"
    assert queue_state.lock_acquired_at > initial_acquisition_time


@pytest.mark.asyncio
async def test_scenario_10_queue_position_updates():
    """Test that queue respects position updates when items are reordered."""
    service = InMemoryLockService()

    # Setup initial state
    await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        board_position=0
    )

    # Queue items
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

    # Verify current queue order
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert queue_state.queue[0].work_item_id == "item-3"  # pos 1 < pos 2
    assert queue_state.queue[1].work_item_id == "item-2"  # pos 2

    # Update positions (simulate human reordering)
    # Give item-2 a higher priority (lower position)
    await service.update_queue_positions(
        project_id="proj-1",
        board_id="board-1",
        updated_positions={"item-2": 0, "item-3": 2}
    )

    # Verify queue was reordered
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert queue_state.queue[0].work_item_id == "item-2"  # pos 0.5
    assert queue_state.queue[1].work_item_id == "item-3"  # pos 2


@pytest.mark.asyncio
async def test_scenario_10_multiple_independent_boards():
    """Test that locks on different boards are independent."""
    service = InMemoryLockService()

    # Board 1: item-1 holds lock, item-2 queued
    result1 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        board_position=0
    )
    assert result1.status == LockStatus.ACQUIRED

    result2 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-2",
        board_position=1
    )
    assert result2.status == LockStatus.QUEUED

    # Board 2: item-3 should be able to acquire immediately
    result3 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-2",
        work_item_id="item-3",
        board_position=0
    )
    assert result3.status == LockStatus.ACQUIRED

    # Board 2: item-4 should queue on board-2 (not affected by board-1)
    result4 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-2",
        work_item_id="item-4",
        board_position=1
    )
    assert result4.status == LockStatus.QUEUED

    # Verify boards have independent states
    queue_state1 = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    queue_state2 = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-2"
    )

    assert queue_state1.lock_holder == "item-1"
    assert queue_state2.lock_holder == "item-3"
    assert len(queue_state1.queue) == 1
    assert len(queue_state2.queue) == 1


@pytest.mark.asyncio
async def test_scenario_10_duplicate_holder_request():
    """Test that same item requesting lock twice returns ALREADY_HELD."""
    service = InMemoryLockService()

    # Acquire lock
    result1 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        board_position=0
    )
    assert result1.status == LockStatus.ACQUIRED

    # Same item tries again
    result2 = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        board_position=0
    )
    assert result2.status == LockStatus.ALREADY_HELD
    assert result2.queue_position is None  # Not in queue


@pytest.mark.asyncio
async def test_scenario_10_orphaned_lock_holder():
    """Test behavior when releasing by non-lock holder raises error."""
    service = InMemoryLockService()

    # Acquire lock
    await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        board_position=0
    )

    # Queue other items
    await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-2",
        board_position=1
    )

    # Try to release non-existent lock holder - should raise error
    with pytest.raises(ValueError):
        await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-99"  # Not the lock holder
        )


@pytest.mark.asyncio
async def test_scenario_10_empty_queue_after_release():
    """Test lock release when no items are queued."""
    service = InMemoryLockService()

    # Single item acquires and releases
    await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        board_position=0
    )

    release_result = await service.release_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1"
    )

    assert release_result.released_work_item_id == "item-1"
    assert release_result.next_work_item_id is None
    assert release_result.queue_length_after_release == 0

    # Verify lock is free
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert queue_state.lock_holder is None
    assert len(queue_state.queue) == 0


@pytest.mark.asyncio
async def test_scenario_10_with_event_bus():
    """Test lock events are emitted to event bus."""
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock()
    service = InMemoryLockService(event_bus=event_bus)

    # Acquire lock
    await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1",
        board_position=0
    )

    # Verify acquisition event was emitted
    assert event_bus.publish.called
    acquisition_event = event_bus.publish.call_args_list[0][0][0]
    assert isinstance(acquisition_event, PipelineLockAcquiredEvent)
    assert acquisition_event.work_item_id == "item-1"

    # Queue another item
    event_bus.publish.reset_mock()
    await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-2",
        board_position=1
    )

    # Verify queue event was emitted
    assert event_bus.publish.called
    queued_event = event_bus.publish.call_args_list[0][0][0]
    assert isinstance(queued_event, WorkItemQueuedEvent)
    assert queued_event.work_item_id == "item-2"

    # Release lock
    event_bus.publish.reset_mock()
    await service.release_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-1"
    )

    # Verify release event was emitted
    assert event_bus.publish.called
    release_event = event_bus.publish.call_args_list[0][0][0]
    assert isinstance(release_event, PipelineLockReleasedEvent)
    assert release_event.work_item_id == "item-1"


@pytest.mark.asyncio
async def test_scenario_10_deadlock_prevention():
    """Test that queue-based lock system prevents deadlocks."""
    service = InMemoryLockService()

    # Create a chain of items that would deadlock in a different design
    # Item A holds lock, waiting for item B to complete
    # Item B is queued, waiting for Item A to release lock
    # With queue-based system, B will get lock when A releases (no deadlock)

    await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-A",
        board_position=0
    )

    result_B = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-B",
        board_position=1
    )
    assert result_B.status == LockStatus.QUEUED

    # Item C also queued
    result_C = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-C",
        board_position=2
    )
    assert result_C.status == LockStatus.QUEUED

    # A releases - B automatically gets it (guaranteed by queue)
    release_AB = await service.release_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-A"
    )
    assert release_AB.next_work_item_id == "item-B"

    # B releases - C automatically gets it
    release_BC = await service.release_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id="item-B"
    )
    assert release_BC.next_work_item_id == "item-C"

    # Verify no deadlock occurred
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert queue_state.lock_holder == "item-C"
    assert len(queue_state.queue) == 0


@pytest.mark.asyncio
async def test_scenario_10_stress_test_many_items():
    """Stress test with many items competing for single lock."""
    service = InMemoryLockService()

    num_items = 100
    items = [f"item-{i:03d}" for i in range(num_items)]

    # First item acquires
    result = await service.try_acquire_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id=items[0],
        board_position=0
    )
    assert result.status == LockStatus.ACQUIRED

    # All others queue
    for i in range(1, num_items):
        result = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id=items[i],
            board_position=i
        )
        assert result.status == LockStatus.QUEUED
        assert result.queue_length == i

    # Verify queue size
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert len(queue_state.queue) == num_items - 1

    # Release all items and verify they progress through queue
    current_holder = items[0]
    for expected_next_idx in range(1, num_items):
        release_result = await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id=current_holder
        )
        expected_next = items[expected_next_idx]
        assert release_result.next_work_item_id == expected_next
        current_holder = expected_next

    # Final release
    release_result = await service.release_lock(
        project_id="proj-1",
        board_id="board-1",
        work_item_id=items[-1]
    )
    assert release_result.next_work_item_id is None

    # Queue should be empty
    queue_state = await service.get_queue_state(
        project_id="proj-1",
        board_id="board-1"
    )
    assert queue_state.lock_holder is None
    assert len(queue_state.queue) == 0


@pytest.mark.asyncio
async def test_scenario_10_input_validation():
    """Test that service validates input parameters."""
    service = InMemoryLockService()

    # Empty project_id
    with pytest.raises(ValueError):
        await service.try_acquire_lock(
            project_id="",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0
        )

    # Empty board_id
    with pytest.raises(ValueError):
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="",
            work_item_id="item-1",
            board_position=0
        )

    # Empty work_item_id
    with pytest.raises(ValueError):
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="",
            board_position=0
        )

    # Negative position
    with pytest.raises(ValueError):
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=-1
        )


if __name__ == "__main__":
    import asyncio

    async def run_all():
        """Run all scenario 10 tests."""
        print("\n" + "=" * 80)
        print("SCENARIO 10: Comprehensive Pipeline Locking")
        print("=" * 80)

        # Run tests
        await test_scenario_10_basic_lock_acquisition_and_release()
        print("✓ Basic lock acquisition and release test passed")

        await test_scenario_10_lock_queuing_when_held()
        print("✓ Lock queuing when held test passed")

        await test_scenario_10_queue_position_ordering()
        print("✓ Queue position ordering test passed")

        await test_scenario_10_lock_release_advances_queue()
        print("✓ Lock release advances queue test passed")

        await test_scenario_10_concurrent_lock_contention()
        print("✓ Concurrent lock contention test passed")

        await test_scenario_10_stale_lock_detection_and_recovery()
        print("✓ Stale lock detection and recovery test passed")

        await test_scenario_10_queue_position_updates()
        print("✓ Queue position updates test passed")

        await test_scenario_10_multiple_independent_boards()
        print("✓ Multiple independent boards test passed")

        await test_scenario_10_duplicate_holder_request()
        print("✓ Duplicate holder request test passed")

        await test_scenario_10_orphaned_lock_holder()
        print("✓ Orphaned lock holder test passed")

        await test_scenario_10_empty_queue_after_release()
        print("✓ Empty queue after release test passed")

        await test_scenario_10_with_event_bus()
        print("✓ Event bus integration test passed")

        await test_scenario_10_deadlock_prevention()
        print("✓ Deadlock prevention test passed")

        await test_scenario_10_stress_test_many_items()
        print("✓ Stress test with many items passed")

        await test_scenario_10_input_validation()
        print("✓ Input validation test passed")

        print("\n" + "=" * 80)
        print("All Scenario 10 tests completed successfully!")
        print("=" * 80 + "\n")

    asyncio.run(run_all())
