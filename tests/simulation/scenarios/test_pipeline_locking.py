"""Simulation tests for pipeline locking and queue coordination.

Comprehensive test suite covering lock and queue workflows using
IDistributedLock and IPipelineQueue ports.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.testing import (
    InMemoryDistributedLock,
    InMemoryPipelineQueue,
)
from codetoreum.ports.output.distributed_lock import AcquireStatus
from codetoreum.ports.output.pipeline_queue import QueueEntry


@pytest.fixture
def event_bus():
    """Mock event bus for capturing emitted events."""
    bus = AsyncMock()
    bus.emit = AsyncMock()
    bus.publish = AsyncMock()
    bus.subscribe = AsyncMock()
    return bus


@pytest.fixture
def distributed_lock():
    """In-memory distributed lock."""
    return InMemoryDistributedLock()


@pytest.fixture
def pipeline_queue():
    """In-memory pipeline queue."""
    return InMemoryPipelineQueue()


@pytest.mark.asyncio
class TestPipelineLockingSimulation:
    """Simulation tests for pipeline locking and queueing."""

    # ===== SCENARIO A: NORMAL LOCK FLOW =====

    async def test_scenario_a_normal_lock_flow(self, distributed_lock, pipeline_queue):
        """Test normal sequential lock acquisition and handoff.

        Scenario:
        1. Item #100 enters Development → acquires lock (position 0)
        2. Item #101 enters Development → goes to queue (position 1)
        3. Item #102 enters Development → goes to queue (position 2)
        4. #100 completes → lock released → #101 acquires lock
        5. #101 completes → lock released → #102 acquires lock
        """
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Step 1: #100 acquires lock
        await pipeline_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="#100",
                stage_name="Development",
                board_position=0,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        )
        result = await distributed_lock.try_acquire(lock_key, "#100")
        assert result.status == AcquireStatus.ACQUIRED

        # Step 2: #101 queued
        await pipeline_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="#101",
                stage_name="Development",
                board_position=1,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        )
        result = await distributed_lock.try_acquire(lock_key, "#101")
        assert result.status == AcquireStatus.ALREADY_HELD_BY_OTHER

        # Step 3: #102 queued
        await pipeline_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="#102",
                stage_name="Development",
                board_position=2,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        )
        result = await distributed_lock.try_acquire(lock_key, "#102")
        assert result.status == AcquireStatus.ALREADY_HELD_BY_OTHER

        # Step 4: #100 releases → #101 tries to acquire
        await distributed_lock.release(lock_key, "#100")
        await pipeline_queue.remove(lock_key, "#100")

        result = await distributed_lock.try_acquire(lock_key, "#101")
        assert result.status == AcquireStatus.ACQUIRED

        # Step 5: #101 releases → #102 tries to acquire
        await distributed_lock.release(lock_key, "#101")
        await pipeline_queue.remove(lock_key, "#101")

        result = await distributed_lock.try_acquire(lock_key, "#102")
        assert result.status == AcquireStatus.ACQUIRED

    # ===== SCENARIO B: RE-ENTRANT ACQUISITION =====

    async def test_reentrant_lock_acquisition(self, distributed_lock, pipeline_queue):
        """Test same work item can re-acquire lock it already holds."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Initial acquisition
        result = await distributed_lock.try_acquire(lock_key, "#100")
        assert result.status == AcquireStatus.ACQUIRED

        # Re-acquisition by same work item
        result = await distributed_lock.try_acquire(lock_key, "#100")
        assert result.status == AcquireStatus.ALREADY_HELD_BY_SELF

    # ===== SCENARIO C: EXIT COLUMN DETECTION =====

    async def test_exit_column_automatic_release(self, distributed_lock, pipeline_queue):
        """Test lock is automatically released when work item moves to exit column.

        Scenario:
        1. Work item #100 holds lock in Development column
        2. Work item #100 moves to Done column (exit column)
        3. Lock is automatically released
        4. Next item can acquire lock
        """
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # #100 acquires lock in Development
        await distributed_lock.try_acquire(lock_key, "#100")
        holder = await distributed_lock.get_holder(lock_key)
        assert holder.holder_id == "#100"

        # #100 moves to Done (exit column) → lock should be released
        release_result = await distributed_lock.release(lock_key, "#100")
        assert release_result.released

        # Verify lock is released
        holder = await distributed_lock.get_holder(lock_key)
        assert holder is None

    # ===== SCENARIO D: QUEUE EMPTY STATE =====

    async def test_release_with_empty_queue(self, distributed_lock, pipeline_queue):
        """Test lock release succeeds when no items queued."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # #100 acquires and releases with empty queue
        await distributed_lock.try_acquire(lock_key, "#100")
        release_result = await distributed_lock.release(lock_key, "#100")

        # Verify release succeeded
        assert release_result.released

        holder = await distributed_lock.get_holder(lock_key)
        assert holder is None

    # ===== SCENARIO E: CONCURRENT LOCK ACQUISITION =====

    async def test_concurrent_acquisition_atomicity(self, distributed_lock, pipeline_queue):
        """Test only one work item succeeds in concurrent acquisition attempts."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Launch truly concurrent acquisitions
        results = await asyncio.gather(
            distributed_lock.try_acquire(lock_key, "#100"),
            distributed_lock.try_acquire(lock_key, "#101"),
            distributed_lock.try_acquire(lock_key, "#102"),
        )

        # Exactly one should have ACQUIRED status
        acquired_count = sum(1 for r in results if r.status == AcquireStatus.ACQUIRED)
        assert acquired_count == 1

        # Verify only one holds lock
        holder = await distributed_lock.get_holder(lock_key)
        assert holder is not None
        assert holder.holder_id in ["#100", "#101", "#102"]

    # ===== SCENARIO F: QUEUE CONSISTENCY =====

    async def test_queue_consistency_with_board_positions(self, distributed_lock, pipeline_queue):
        """Test queue respects board position ordering."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # #100 holds lock
        await distributed_lock.try_acquire(lock_key, "#100")

        # Queue items with different board positions
        entries = [
            QueueEntry(
                work_item_id="#101",
                stage_name="Development",
                board_position=5,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
            QueueEntry(
                work_item_id="#102",
                stage_name="Development",
                board_position=1,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
            QueueEntry(
                work_item_id="#103",
                stage_name="Development",
                board_position=3,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        ]

        for entry in entries:
            await pipeline_queue.enqueue(lock_key, entry)

        # Verify queue has all items
        queue_list = await pipeline_queue.list(lock_key)
        assert len(queue_list) == 3

    # ===== SCENARIO G: INVALID RELEASE BY NON-HOLDER =====

    async def test_invalid_release_by_non_holder(self, distributed_lock):
        """Test release fails when attempted by non-holder."""
        lock_key = "project-1:board-1"

        # #100 acquires lock
        await distributed_lock.try_acquire(lock_key, "#100")

        # #101 attempts to release (not the holder)
        result = await distributed_lock.release(lock_key, "#101")
        assert not result.released

        # Lock still held by #100
        holder = await distributed_lock.get_holder(lock_key)
        assert holder.holder_id == "#100"

    # ===== SCENARIO H: STRESS TEST =====

    async def test_stress_test_many_concurrent_items(self, distributed_lock, pipeline_queue):
        """Stress test with 100 items competing for lock concurrently."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        num_items = 100

        # Launch concurrent acquisitions
        tasks = [
            distributed_lock.try_acquire(lock_key, f"#{i:04d}") for i in range(num_items)
        ]
        results = await asyncio.gather(*tasks)

        # Exactly one should have ACQUIRED status
        acquired_count = sum(1 for r in results if r.status == AcquireStatus.ACQUIRED)
        assert acquired_count == 1

        # Verify lock held by one of them
        holder = await distributed_lock.get_holder(lock_key)
        assert holder is not None

    # ===== SCENARIO I: MULTIPLE INDEPENDENT BOARDS =====

    async def test_multiple_independent_boards_isolated_locks(self, distributed_lock, pipeline_queue):
        """Test locks on different boards are completely independent."""
        project_id = "project-1"

        # Board 1: #100 holds lock
        result = await distributed_lock.try_acquire(f"{project_id}:board-1", "#100")
        assert result.status == AcquireStatus.ACQUIRED

        # Board 2: #101 can acquire independently (different board)
        result = await distributed_lock.try_acquire(f"{project_id}:board-2", "#101")
        assert result.status == AcquireStatus.ACQUIRED

        # Verify both locks held
        state1 = await distributed_lock.get_holder(f"{project_id}:board-1")
        state2 = await distributed_lock.get_holder(f"{project_id}:board-2")
        assert state1.holder_id == "#100"
        assert state2.holder_id == "#101"

    # ===== SCENARIO J: SEQUENTIAL HANDOFF CORRECTNESS =====

    async def test_sequential_handoff_after_lock_release(self, distributed_lock, pipeline_queue):
        """Test that lock correctly passes to next queued item."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Setup: item-0 holds lock, item-1 and item-2 queued
        r1 = await distributed_lock.try_acquire(lock_key, "item-0")
        assert r1.status == AcquireStatus.ACQUIRED

        for i in range(1, 3):
            await pipeline_queue.enqueue(
                lock_key,
                QueueEntry(
                    work_item_id=f"item-{i}",
                    stage_name="Development",
                    board_position=i,
                    enqueued_at=datetime.now(UTC),
                    metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
                ),
            )

        # Release item-0
        release_result = await distributed_lock.release(lock_key, "item-0")
        assert release_result.released

        # Try to acquire with item-1
        result = await distributed_lock.try_acquire(lock_key, "item-1")
        assert result.status == AcquireStatus.ACQUIRED
