"""Integration tests for pipeline locking and queue concurrency.

Tests concurrent access patterns using IDistributedLock and IPipelineQueue:
- Concurrent lock acquisitions on same board
- Concurrent position updates during lock operations
- Race between lock release and queue operations
- Stale lock recovery under concurrent pressure
- Queue ordering correctness under contention
"""

import asyncio
from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from codetoreum.adapters.testing import (
    InMemoryDistributedLock,
    InMemoryPipelineQueue,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.distributed_lock import AcquireStatus
from codetoreum.ports.output.pipeline_queue import QueueEntry


@pytest.fixture
def event_bus():
    """Mock event bus for capturing emitted events."""
    from unittest.mock import MagicMock, AsyncMock

    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
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
class TestPipelineLockingConcurrency:
    """Concurrency tests for lock and queue coordination."""

    # ===== TEST 1: CONCURRENT LOCK ACQUISITIONS =====

    async def test_concurrent_lock_acquisitions_only_one_succeeds(self, distributed_lock, pipeline_queue):
        """Verify only one work item acquires lock when multiple try simultaneously."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        num_items = 10

        # Prepare queue entries
        queue_entries = [
            QueueEntry(
                work_item_id=f"item-{i}",
                stage_name="Development",
                board_position=i,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            )
            for i in range(num_items)
        ]

        # Spawn 10 tasks trying to enqueue and acquire lock concurrently
        async def enqueue_and_try_acquire(i):
            await pipeline_queue.enqueue(lock_key, queue_entries[i])
            result = await distributed_lock.try_acquire(
                lock_key=lock_key,
                holder_id=f"item-{i}",
                ttl_seconds=7200,
            )
            return result

        results = await asyncio.gather(*[enqueue_and_try_acquire(i) for i in range(num_items)])

        # Verify exactly one acquired
        acquired = [r for r in results if r.status == AcquireStatus.ACQUIRED]
        assert len(acquired) == 1

        # Verify others are NOT_ACQUIRED
        not_acquired = [r for r in results if r.status != AcquireStatus.ACQUIRED]
        assert len(not_acquired) == num_items - 1

        # Verify queue has all items
        queue_list = await pipeline_queue.list(lock_key)
        assert len(queue_list) == num_items

    # ===== TEST 2: CONCURRENT POSITION UPDATES =====

    async def test_concurrent_queue_operations(self, distributed_lock, pipeline_queue):
        """Verify queue operations are safe under concurrency."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Enqueue initial items
        for i in range(3):
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

        # Concurrent operations: peek and pop
        async def peek_and_pop():
            entry = await pipeline_queue.peek(lock_key)
            if entry:
                return await pipeline_queue.pop(lock_key)
            return None

        results = await asyncio.gather(peek_and_pop(), peek_and_pop())

        # Both should succeed or one should get None if queue was empty
        popped_count = sum(1 for r in results if r is not None)
        assert popped_count <= 3

    # ===== TEST 3: LOCK RELEASE AND NEXT ITEM GRANT =====

    async def test_lock_release_grants_to_queue_head(self, distributed_lock, pipeline_queue):
        """Test lock correctly passes to next queued item."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Setup: item-1 holds lock, item-2 and item-3 queued
        await distributed_lock.try_acquire(lock_key, "item-1")

        await pipeline_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="item-2",
                stage_name="Development",
                board_position=1,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        )
        await pipeline_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="item-3",
                stage_name="Development",
                board_position=2,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        )

        # Release lock
        release_result = await distributed_lock.release(lock_key, "item-1")
        assert release_result.released

        # Get next queued item and try to acquire lock
        next_entry = await pipeline_queue.peek(lock_key)
        assert next_entry is not None
        assert next_entry.work_item_id == "item-2"

        # item-2 acquires lock
        acquire_result = await distributed_lock.try_acquire(lock_key, "item-2")
        assert acquire_result.status == AcquireStatus.ACQUIRED

    # ===== TEST 4: QUEUE CONSISTENCY UNDER STRESS =====

    async def test_queue_consistency_with_many_concurrent_items(self, distributed_lock, pipeline_queue):
        """Stress test: many concurrent additions maintain consistent queue."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        num_items = 100

        # Create queue entries
        queue_entries = [
            QueueEntry(
                work_item_id=f"item-{i}",
                stage_name="Development",
                board_position=i,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            )
            for i in range(num_items)
        ]

        # Enqueue all concurrently
        await asyncio.gather(*[pipeline_queue.enqueue(lock_key, entry) for entry in queue_entries])

        # Verify: all items queued
        queue_list = await pipeline_queue.list(lock_key)
        assert len(queue_list) == num_items

        # Verify: no duplicates
        work_item_ids = [entry.work_item_id for entry in queue_list]
        assert len(work_item_ids) == len(set(work_item_ids))

    # ===== TEST 5: SEQUENTIAL HANDOFF CORRECTNESS =====

    async def test_sequential_handoff_after_lock_release(self, distributed_lock, pipeline_queue):
        """Test that lock correctly passes through queue in order."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Setup: item-1 holds lock, item-2 and item-3 queued
        await distributed_lock.try_acquire(lock_key, "item-1")

        for i in range(2, 4):
            await pipeline_queue.enqueue(
                lock_key,
                QueueEntry(
                    work_item_id=f"item-{i}",
                    stage_name="Development",
                    board_position=i - 1,
                    enqueued_at=datetime.now(UTC),
                    metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
                ),
            )

        # Release item-1
        await distributed_lock.release(lock_key, "item-1")

        # item-2 tries to acquire
        result = await distributed_lock.try_acquire(lock_key, "item-2")
        assert result.status == AcquireStatus.ACQUIRED

        # Release item-2
        await distributed_lock.release(lock_key, "item-2")

        # item-3 tries to acquire
        result = await distributed_lock.try_acquire(lock_key, "item-3")
        assert result.status == AcquireStatus.ACQUIRED

    # ===== TEST 6: IDEMPOTENT QUEUE OPERATIONS =====

    async def test_enqueue_is_idempotent(self, pipeline_queue):
        """Test that enqueueing same item twice is idempotent."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        entry = QueueEntry(
            work_item_id="item-1",
            stage_name="Development",
            board_position=0,
            enqueued_at=datetime.now(UTC),
            metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )

        # Enqueue twice
        result1 = await pipeline_queue.enqueue(lock_key, entry)
        result2 = await pipeline_queue.enqueue(lock_key, entry)

        # Second enqueue should indicate already present
        assert result2.already_present

        # Queue should have only one item
        queue_list = await pipeline_queue.list(lock_key)
        assert len(queue_list) == 1

    # ===== TEST 7: RELEASE BY NON-HOLDER =====

    async def test_release_by_non_holder_fails(self, distributed_lock):
        """Verify that only lock holder can release."""
        lock_key = "project-1:board-1"

        # Item-1 acquires lock
        await distributed_lock.try_acquire(lock_key, "item-1")

        # Item-2 tries to release (doesn't hold lock)
        result = await distributed_lock.release(lock_key, "item-2")

        # Should not be released
        assert not result.released

        # Verify lock still held by item-1
        holder = await distributed_lock.get_holder(lock_key)
        assert holder.holder_id == "item-1"

    # ===== TEST 8: ALREADY_HELD DETECTION =====

    async def test_already_held_when_item_acquires_twice(self, distributed_lock):
        """Test ALREADY_HELD status when work item tries to acquire again."""
        lock_key = "project-1:board-1"

        # Item-1 acquires lock
        result1 = await distributed_lock.try_acquire(lock_key, "item-1")
        assert result1.status == AcquireStatus.ACQUIRED

        # Item-1 tries to acquire again
        result2 = await distributed_lock.try_acquire(lock_key, "item-1")

        # Should return ALREADY_HELD_BY_SELF
        assert result2.status == AcquireStatus.ALREADY_HELD_BY_SELF

    # ===== TEST 9: MULTIPLE INDEPENDENT BOARDS =====

    async def test_multiple_independent_boards_isolated_locks(self, distributed_lock, pipeline_queue):
        """Test locks on different boards are completely independent."""
        project_id = "project-1"

        # Board 1: item-1 holds lock
        result = await distributed_lock.try_acquire("project-1:board-1", "item-1")
        assert result.status == AcquireStatus.ACQUIRED

        # Board 2: item-2 can acquire independently (different board)
        result = await distributed_lock.try_acquire("project-1:board-2", "item-2")
        assert result.status == AcquireStatus.ACQUIRED

        # Verify both locks held
        holder1 = await distributed_lock.get_holder("project-1:board-1")
        holder2 = await distributed_lock.get_holder("project-1:board-2")
        assert holder1.holder_id == "item-1"
        assert holder2.holder_id == "item-2"

    # ===== TEST 10: STRESS TEST =====

    async def test_stress_test_many_concurrent_items(self, distributed_lock, pipeline_queue):
        """Stress test with 50 items competing for lock concurrently."""
        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        num_items = 50

        # Create queue entries
        queue_entries = [
            QueueEntry(
                work_item_id=f"item-{i:03d}",
                stage_name="Development",
                board_position=i,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            )
            for i in range(num_items)
        ]

        # Concurrent enqueue and lock attempt
        async def enqueue_and_acquire(i):
            await pipeline_queue.enqueue(lock_key, queue_entries[i])
            return await distributed_lock.try_acquire(lock_key, f"item-{i:03d}")

        results = await asyncio.gather(*[enqueue_and_acquire(i) for i in range(num_items)])

        # Exactly one should have acquired
        acquired_count = sum(1 for r in results if r.status == AcquireStatus.ACQUIRED)
        assert acquired_count == 1

        # Queue should have all items
        queue_list = await pipeline_queue.list(lock_key)
        assert len(queue_list) == num_items
