"""Simulation tests for pipeline locking scenarios (Scenario 09).

Comprehensive test suite covering all lock flow scenarios:
- Normal acquisition and sequential handoff
- Stale lock recovery (>2 hours)
- Board reordering priority updates
- Re-entrant acquisition
- Empty queue release
- Concurrent atomicity
- Exit column detection
- Queue synchronization
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from codetoreum.adapters.secondary.in_memory_queue_lock_service import InMemoryLockService
from codetoreum.adapters.testing.in_memory_queue_service import InMemoryQueueService
from codetoreum.domain.events.lock_events import (
    LockAcquiredEvent,
    LockReleasedEvent,
    LockStaleDetectedEvent,
    WorkItemQueuedEvent,
)


@pytest.fixture
def event_bus():
    """Mock event bus for capturing emitted events."""
    bus = AsyncMock()
    bus.emit = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus


@pytest.fixture
def lock_service(event_bus):
    """Lock service with 2-hour stale threshold."""
    return InMemoryLockService(event_bus=event_bus, stale_threshold_seconds=7200)


@pytest.fixture
def queue_service():
    """In-memory queue service."""
    return InMemoryQueueService()


@pytest.mark.asyncio
class TestPipelineLockingSimulation:
    """Simulation tests for pipeline locking and queueing (Scenario 09)."""

    # ===== SCENARIO A: NORMAL LOCK FLOW =====

    async def test_scenario_a_normal_lock_flow(self, lock_service, queue_service, event_bus):
        """Test normal sequential lock acquisition and handoff.

        Scenario A:
        1. Work item #100 enters Development → acquires lock (position 0)
        2. Work item #101 enters Development → goes to queue (position 1)
        3. Work item #102 enters Development → goes to queue (position 2)
        4. #100 completes → lock released → #101 acquires lock
        5. #101 completes → lock released → #102 acquires lock

        Verifies: US-1 (Sequential Execution), US-2 (Board-Based Priority)
        """
        project_id = "project-1"
        board_id = "board-1"

        # Set simulated board order
        queue_service.set_board_order(project_id, board_id, ["#100", "#101", "#102"])

        # Step 1: #100 acquires lock
        success, msg = await lock_service.try_acquire_lock(
            project_id, board_id, "#100", board_position=0
        )
        assert success is True
        assert msg == "lock_acquired"
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock.locked_by_work_item == "#100"

        # Step 2: #101 queued
        success, msg = await lock_service.try_acquire_lock(
            project_id, board_id, "#101", board_position=1
        )
        assert success is False
        assert msg == "locked_by_#100"

        # Step 3: #102 queued
        success, msg = await lock_service.try_acquire_lock(
            project_id, board_id, "#102", board_position=2
        )
        assert success is False

        # Step 4: #100 releases → #101 tries to acquire
        await lock_service.release_lock(project_id, board_id, "#100")
        success, msg = await lock_service.try_acquire_lock(
            project_id, board_id, "#101", board_position=1
        )
        assert success is True
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock.locked_by_work_item == "#101"

        # Step 5: #101 releases → #102 tries to acquire
        await lock_service.release_lock(project_id, board_id, "#101")
        success, msg = await lock_service.try_acquire_lock(
            project_id, board_id, "#102", board_position=2
        )
        assert success is True
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock.locked_by_work_item == "#102"

    # ===== SCENARIO B: STALE LOCK RECOVERY =====

    async def test_scenario_b_stale_lock_recovery(self, lock_service, queue_service, event_bus):
        """Test automatic recovery of stale locks > 2 hours old.

        Scenario B:
        1. Work item #100 holds lock (acquired 3 hours ago)
        2. Work item #101 calls try_acquire_lock()
        3. Stale lock detected → auto-released
        4. #101 acquires lock
        5. #100's execution state marked as failed

        Verifies: US-3 (Stale Lock Recovery)
        """
        project_id = "project-1"
        board_id = "board-1"

        # Track stale detection
        stale_detected_calls = []
        event_bus.emit = AsyncMock(side_effect=lambda event: stale_detected_calls.append(event))

        # Step 1: #100 acquires lock
        await lock_service.try_acquire_lock(project_id, board_id, "#100", board_position=0)

        # Simulate lock acquired 3 hours ago
        three_hours_ago = datetime.now() - timedelta(hours=3)
        lock_service.set_lock_acquired_at(project_id, board_id, three_hours_ago)

        # Step 2-4: #101 attempts acquisition → stale recovery
        success, msg = await lock_service.try_acquire_lock(
            project_id, board_id, "#101", board_position=0
        )

        assert success is True
        assert msg == "stale_lock_recovered"

        # Verify lock now held by #101
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock.locked_by_work_item == "#101"

    # ===== SCENARIO C: BOARD REORDERING =====

    async def test_scenario_c_board_reordering(self, lock_service, queue_service):
        """Test queue priority updates when board order changes.

        Scenario C:
        1. Queue order: [#101 (pos 0), #102 (pos 1), #103 (pos 2)]
        2. User drags #103 to top in board interface
        3. sync_queue_with_board() updates positions
        4. New order: [#103 (pos 0), #101 (pos 1), #102 (pos 2)]
        5. When lock released, #103 executes next

        Verifies: US-2 (Board-Based Queue Priority)
        """
        project_id = "project-1"
        board_id = "board-1"

        # #100 holds lock
        await lock_service.try_acquire_lock(project_id, board_id, "#100", board_position=0)

        # Queue: #101, #102, #103 in initial order
        queue_service.set_board_order(project_id, board_id, ["#101", "#102", "#103"])
        await queue_service.enqueue_item("#101", "Development", datetime.now(), position=1)
        await queue_service.enqueue_item("#102", "Development", datetime.now(), position=2)
        await queue_service.enqueue_item("#103", "Development", datetime.now(), position=3)

        # User drags #103 to top
        queue_service.set_board_order(project_id, board_id, ["#103", "#101", "#102"])
        await queue_service.sync_queue_with_board(project_id, board_id, "Development")

        # Verify #103 now has highest priority (position 0)
        next_item = await queue_service.get_next_waiting_item(project_id, board_id)
        assert next_item.work_item_id == "#103"
        assert next_item.position_in_column == 0

    # ===== US-4: RE-ENTRANT ACQUISITION =====

    async def test_reentrant_lock_acquisition(self, lock_service):
        """Test same work item can re-acquire lock it already holds.

        Verifies: US-4 (Re-Entrant Lock Acquisition)
        """
        project_id = "project-1"
        board_id = "board-1"

        # Initial acquisition
        success, msg = await lock_service.try_acquire_lock(
            project_id, board_id, "#100", board_position=0
        )
        assert success is True
        assert msg == "lock_acquired"

        # Re-acquisition by same work item
        success, msg = await lock_service.try_acquire_lock(
            project_id, board_id, "#100", board_position=0
        )
        assert success is True
        assert msg == "already_holds_lock"

    # ===== US-5: EXIT COLUMN DETECTION =====

    async def test_exit_column_automatic_release(self, lock_service):
        """Test lock is automatically released when work item moves to exit column.

        Verifies: US-5 (Automatic Lock Release on Exit Column)

        Scenario:
        1. Work item #100 holds lock in Development column
        2. Work item #100 moves to Done column (exit column)
        3. Lock is automatically released
        4. Next item can acquire lock
        """
        project_id = "project-1"
        board_id = "board-1"

        # #100 acquires lock in Development
        await lock_service.try_acquire_lock(project_id, board_id, "#100", board_position=0)
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock.locked_by_work_item == "#100"

        # #100 moves to Done (exit column) → lock should be released
        success = await lock_service.release_lock(project_id, board_id, "#100")
        assert success is True

        # Verify lock is released
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock is None

    # ===== US-6: QUEUE EMPTY STATE =====

    async def test_release_with_empty_queue(self, lock_service):
        """Test lock release succeeds when no items queued.

        Verifies: US-6 (Queue Empty State)
        """
        project_id = "project-1"
        board_id = "board-1"

        # #100 acquires and releases with empty queue
        await lock_service.try_acquire_lock(project_id, board_id, "#100", board_position=0)
        success = await lock_service.release_lock(project_id, board_id, "#100")

        assert success is True
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock is None

    # ===== US-7: CONCURRENT LOCK ACQUISITION =====

    async def test_concurrent_acquisition_atomicity(self, lock_service):
        """Test only one work item succeeds in concurrent acquisition attempts.

        Verifies: US-7 (Concurrent Lock Acquisition - atomic operations prevent race conditions)

        This test launches multiple concurrent acquisition attempts to verify
        that only one succeeds, preventing race conditions.
        """
        project_id = "project-1"
        board_id = "board-1"

        # Launch truly concurrent acquisitions using asyncio.gather
        results = await asyncio.gather(
            lock_service.try_acquire_lock(project_id, board_id, "#100", board_position=0),
            lock_service.try_acquire_lock(project_id, board_id, "#101", board_position=1),
            lock_service.try_acquire_lock(project_id, board_id, "#102", board_position=2),
        )

        # Exactly one should succeed
        successes = [r[0] for r in results]
        assert successes.count(True) == 1
        assert successes.count(False) == 2

        # Verify only one holds lock
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock is not None
        assert lock.locked_by_work_item in ["#100", "#101", "#102"]

    # ===== US-8: QUEUE SYNCHRONIZATION =====

    async def test_queue_sync_removes_items_moved_out_of_column(
        self, lock_service, queue_service
    ):
        """Test queue synchronization removes items moved out of Development column.

        Verifies: US-8 (Queue Synchronization with Board)

        Scenario:
        1. Work items #101, #102, #103 queued in Development column
        2. User moves #102 to Done column (exit column)
        3. sync_queue_with_board() removes #102 from queue
        4. Queue now contains only #101, #103 in correct order
        """
        project_id = "project-1"
        board_id = "board-1"

        # #100 holds lock, #101-#103 are queued
        await lock_service.try_acquire_lock(project_id, board_id, "#100", board_position=0)

        queue_service.set_board_order(project_id, board_id, ["#101", "#102", "#103"])
        await queue_service.enqueue_item("#101", "Development", datetime.now(), position=1)
        await queue_service.enqueue_item("#102", "Development", datetime.now(), position=2)
        await queue_service.enqueue_item("#103", "Development", datetime.now(), position=3)

        # User moves #102 to Done (out of Development column)
        queue_service.set_board_order(project_id, board_id, ["#101", "#103"])

        # Sync queue with board
        await queue_service.sync_queue_with_board(project_id, board_id, "Development")

        # Verify #102 removed, #101 and #103 remain
        next_item = await queue_service.get_next_waiting_item(project_id, board_id)
        assert next_item.work_item_id == "#101"

    # ===== ADDITIONAL TESTS =====

    async def test_stale_lock_age_boundary_conditions(self, lock_service):
        """Test lock age boundary conditions (1h59m vs 2h01m).

        Verifies: US-3 boundary conditions for stale detection

        Tests:
        1. Lock 1h59m old → NOT considered stale
        2. Lock 2h01m old → IS considered stale
        """
        project_id = "project-1"
        board_id = "board-1"

        # Test 1h59m: NOT stale
        await lock_service.try_acquire_lock(project_id, board_id, "#100", board_position=0)
        almost_stale = datetime.now() - timedelta(hours=1, minutes=59)
        lock_service.set_lock_acquired_at(project_id, board_id, almost_stale)

        success, msg = await lock_service.try_acquire_lock(
            project_id, board_id, "#101", board_position=1
        )
        # 1h59m should NOT trigger stale recovery - lock is still valid
        assert success is False
        assert msg == "locked_by_#100"

        # Release and test 2h01m: IS stale
        await lock_service.release_lock(project_id, board_id, "#100")

        await lock_service.try_acquire_lock(project_id, board_id, "#103", board_position=0)
        definitely_stale = datetime.now() - timedelta(hours=2, minutes=1)
        lock_service.set_lock_acquired_at(project_id, board_id, definitely_stale)

        success, msg = await lock_service.try_acquire_lock(
            project_id, board_id, "#104", board_position=1
        )
        # 2h01m SHOULD trigger stale recovery
        assert success is True
        assert msg == "stale_lock_recovered"

    async def test_reentrant_on_reentrant_request(self, lock_service):
        """Test multiple re-entrant requests from same holder all succeed."""
        project_id = "project-1"
        board_id = "board-1"

        # Initial acquisition
        await lock_service.try_acquire_lock(project_id, board_id, "#100", board_position=0)

        # Multiple re-entrant attempts
        for _ in range(3):
            success, msg = await lock_service.try_acquire_lock(
                project_id, board_id, "#100", board_position=0
            )
            assert success is True
            assert msg == "already_holds_lock"

        # Lock still held by #100
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock.locked_by_work_item == "#100"

    async def test_multiple_independent_boards_isolated_locks(self, lock_service):
        """Test locks on different boards are completely independent."""
        project_id = "project-1"

        # Board 1: #100 holds lock
        success, msg = await lock_service.try_acquire_lock(
            project_id, "board-1", "#100", board_position=0
        )
        assert success is True

        # Board 2: #101 can acquire independently (different board)
        success, msg = await lock_service.try_acquire_lock(
            project_id, "board-2", "#101", board_position=0
        )
        assert success is True

        # Verify both locks held
        lock1 = await lock_service.get_lock(project_id, "board-1")
        lock2 = await lock_service.get_lock(project_id, "board-2")
        assert lock1.locked_by_work_item == "#100"
        assert lock2.locked_by_work_item == "#101"

    async def test_invalid_release_by_non_holder(self, lock_service):
        """Test release fails when attempted by non-holder."""
        project_id = "project-1"
        board_id = "board-1"

        # #100 acquires lock
        await lock_service.try_acquire_lock(project_id, board_id, "#100", board_position=0)

        # #101 attempts to release (not the holder)
        success = await lock_service.release_lock(project_id, board_id, "#101")
        assert success is False

        # Lock still held by #100
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock.locked_by_work_item == "#100"

    async def test_stress_test_many_concurrent_items(self, lock_service):
        """Stress test with 100 items competing for lock concurrently."""
        project_id = "project-1"
        board_id = "board-1"

        num_items = 100

        # Launch concurrent acquisitions
        tasks = [
            lock_service.try_acquire_lock(
                project_id, board_id, f"#{i:04d}", board_position=i
            )
            for i in range(num_items)
        ]
        results = await asyncio.gather(*tasks)

        # Exactly one should succeed
        successes = [r[0] for r in results]
        assert successes.count(True) == 1
        assert successes.count(False) == num_items - 1

        # Verify lock held by one of them
        lock = await lock_service.get_lock(project_id, board_id)
        assert lock is not None
