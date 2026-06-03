"""Integration tests for PipelineOrchestrator event-driven lock and queue coordination.

Comprehensive test suite covering:
- Lock acquisition and queue management
- Lock release and next-item granting
- Orphan lock detection and recovery on startup
- Error handling in critical lock-grant operations
- Concurrent coordination between locks and queues
- Edge cases (empty queue, non-holder release attempts)
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.testing import (
    InMemoryActiveWorkflowRunRegistry,
    InMemoryDistributedLock,
    InMemoryOrphanScanRegistry,
    InMemoryPipelineQueue,
)
from codetoreum.application.event_handlers.pipeline_orchestrator import (
    PipelineOrchestrator,
)
from codetoreum.domain.events.lock_events import (
    LockStuckEvent,
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.distributed_lock import AcquireStatus
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.pipeline_queue import QueueEntry


@pytest.fixture
def event_bus():
    """Mock event bus for capturing published events."""
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


@pytest.fixture
def run_registry():
    """In-memory active workflow run registry."""
    return InMemoryActiveWorkflowRunRegistry()


@pytest.fixture
def orphan_scan_registry():
    """In-memory orphan scan registry."""
    return InMemoryOrphanScanRegistry()


@pytest.fixture
def event_emitter():
    """Mock event emitter for capturing alert events."""
    emitter = MagicMock(spec=IEventEmitter)
    emitter.emit = MagicMock()
    emitter.on = MagicMock()
    emitter.off = MagicMock()
    return emitter


@pytest.mark.asyncio
class TestPipelineOrchestratorLockAcquisition:
    """Tests for lock acquisition and queue handling."""

    async def test_lock_acquired_removes_holder_from_queue(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_emitter,
        event_bus,
    ):
        """Test that on_lock_acquired removes holder from queue if present."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        work_item_id = "item-1"

        # Enqueue the item first
        await pipeline_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id=work_item_id,
                stage_name="Development",
                board_position=0,
                enqueued_at=datetime.now(UTC),
                metadata={"project_id": project_id, "board_id": board_id},
            ),
        )
        assert await pipeline_queue.contains(lock_key, work_item_id)

        # Trigger lock acquisition event
        event = PipelineLockAcquiredEvent(
            type="lock.acquired",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
        )
        await orchestrator.on_lock_acquired(event)

        # Verify item was removed from queue
        assert not await pipeline_queue.contains(lock_key, work_item_id)

    async def test_lock_acquired_idempotent_when_not_in_queue(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_emitter,
    ):
        """Test on_lock_acquired is idempotent when item not in queue."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        work_item_id = "item-1"

        # Item not in queue, but event fired
        event = PipelineLockAcquiredEvent(
            type="lock.acquired",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
        )

        # Should not raise
        await orchestrator.on_lock_acquired(event)


@pytest.mark.asyncio
class TestPipelineOrchestratorLockRelease:
    """Tests for lock release and next-item granting."""

    async def test_lock_released_grants_lock_to_next_item(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_emitter,
    ):
        """Test that on_lock_released successfully grants lock to and removes next item from queue."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        queue_key = lock_key

        # Setup: item-1 holds lock
        await distributed_lock.try_acquire(lock_key, "item-1")

        # Enqueue item-2 and item-3
        await pipeline_queue.enqueue(
            queue_key,
            QueueEntry(
                work_item_id="item-2",
                stage_name="Development",
                board_position=0,
                enqueued_at=datetime.now(UTC),
                metadata={"project_id": project_id, "board_id": board_id},
            ),
        )
        await pipeline_queue.enqueue(
            queue_key,
            QueueEntry(
                work_item_id="item-3",
                stage_name="Development",
                board_position=1,
                enqueued_at=datetime.now(UTC),
                metadata={"project_id": project_id, "board_id": board_id},
            ),
        )

        # Verify item-2 is in queue
        assert await pipeline_queue.contains(queue_key, "item-2")

        # Release the lock for item-1
        await distributed_lock.release(lock_key, "item-1")

        # Trigger lock release event for item-1
        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-1",
        )
        await orchestrator.on_lock_released(event)

        # Verify item-2 got the lock and was removed from queue
        holder = await distributed_lock.get_holder(lock_key)
        assert holder is not None
        assert holder.holder_id == "item-2"
        assert not await pipeline_queue.contains(queue_key, "item-2")

        # Verify item-3 is still in queue
        assert await pipeline_queue.contains(queue_key, "item-3")

    async def test_lock_released_error_handling_does_not_block(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_emitter,
    ):
        """Test that lock release errors are logged but handled gracefully."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Setup: item-1 holds lock
        await distributed_lock.try_acquire(lock_key, "item-1")

        # Mock pipeline_queue to raise an error on peek
        original_peek = pipeline_queue.peek
        peek_called = False

        async def mock_peek_raises(*args):
            nonlocal peek_called
            peek_called = True
            raise RuntimeError("Queue service error")

        pipeline_queue.peek = mock_peek_raises

        # Trigger lock release event
        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-1",
        )

        # Should not raise despite error
        await orchestrator.on_lock_released(event)
        assert peek_called

        # Restore original method
        pipeline_queue.peek = original_peek


@pytest.mark.asyncio
class TestPipelineOrchestratorErrorHandling:
    """Tests for error handling in critical operations."""

    async def test_lock_acquired_emits_alert_on_queue_removal_failure(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_emitter,
    ):
        """Test on_lock_acquired emits LockStuckEvent if queue removal fails."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        queue_key = lock_key
        work_item_id = "item-1"

        # Enqueue the item
        await pipeline_queue.enqueue(
            queue_key,
            QueueEntry(
                work_item_id=work_item_id,
                stage_name="Development",
                board_position=0,
                enqueued_at=datetime.now(UTC),
                metadata={"project_id": project_id, "board_id": board_id},
            ),
        )

        # Mock queue to raise error on remove
        original_remove = pipeline_queue.remove

        async def mock_remove_raises(*args):
            raise RuntimeError("Queue service error")

        pipeline_queue.remove = mock_remove_raises

        event = PipelineLockAcquiredEvent(
            type="lock.acquired",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
        )

        # Should not raise despite error
        await orchestrator.on_lock_acquired(event)

        # Verify LockStuckEvent was emitted
        event_emitter.emit.assert_called_once()
        emitted_event = event_emitter.emit.call_args[0][0]
        assert isinstance(emitted_event, LockStuckEvent)
        assert emitted_event.work_item_id == work_item_id

        # Restore
        pipeline_queue.remove = original_remove

    async def test_lock_acquired_handles_queue_error_gracefully(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_emitter,
    ):
        """Test on_lock_acquired logs errors but continues."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        # Mock queue to raise error on contains
        original_contains = pipeline_queue.contains

        async def mock_contains_raises(*args):
            raise RuntimeError("Queue error")

        pipeline_queue.contains = mock_contains_raises

        event = PipelineLockAcquiredEvent(
            type="lock.acquired",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id="project-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        # Should not raise
        await orchestrator.on_lock_acquired(event)

        # Restore
        pipeline_queue.contains = original_contains

    async def test_lock_released_emits_alert_on_lock_acquisition_failure(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_emitter,
    ):
        """Test on_lock_released emits LockStuckEvent if lock acquisition fails for next item."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        queue_key = lock_key
        work_item_id = "item-1"
        next_item_id = "item-2"

        # Setup: item-1 holds lock
        await distributed_lock.try_acquire(lock_key, work_item_id)

        # Enqueue item-2
        await pipeline_queue.enqueue(
            queue_key,
            QueueEntry(
                work_item_id=next_item_id,
                stage_name="Development",
                board_position=0,
                enqueued_at=datetime.now(UTC),
                metadata={"project_id": project_id, "board_id": board_id},
            ),
        )

        # Mock distributed_lock to raise error on try_acquire
        original_try_acquire = distributed_lock.try_acquire

        async def mock_try_acquire_raises(*args, **kwargs):
            raise RuntimeError("Lock service error")

        distributed_lock.try_acquire = mock_try_acquire_raises

        # Release the lock for item-1
        await distributed_lock.release(lock_key, work_item_id)

        # Trigger lock release event
        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
        )

        # Should not raise despite error
        await orchestrator.on_lock_released(event)

        # Verify LockStuckEvent was emitted with the next item's ID
        event_emitter.emit.assert_called_once()
        emitted_event = event_emitter.emit.call_args[0][0]
        assert isinstance(emitted_event, LockStuckEvent)
        assert emitted_event.work_item_id == next_item_id

        # Restore
        distributed_lock.try_acquire = original_try_acquire

    async def test_lock_released_emits_alert_on_queue_removal_failure_after_acquire(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_emitter,
    ):
        """Test on_lock_released emits LockStuckEvent if queue removal fails after successful lock grant."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        queue_key = lock_key
        work_item_id = "item-1"
        next_item_id = "item-2"

        # Setup: item-1 holds lock
        await distributed_lock.try_acquire(lock_key, work_item_id)

        # Enqueue item-2
        await pipeline_queue.enqueue(
            queue_key,
            QueueEntry(
                work_item_id=next_item_id,
                stage_name="Development",
                board_position=0,
                enqueued_at=datetime.now(UTC),
                metadata={"project_id": project_id, "board_id": board_id},
            ),
        )

        # Mock queue to raise error on remove (called after successful lock grant)
        original_remove = pipeline_queue.remove
        remove_called = False

        async def mock_remove_raises(*args):
            nonlocal remove_called
            remove_called = True
            raise RuntimeError("Queue service error")

        pipeline_queue.remove = mock_remove_raises

        # Release the lock for item-1
        await distributed_lock.release(lock_key, work_item_id)

        # Trigger lock release event
        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
        )

        # Should not raise despite queue removal error
        await orchestrator.on_lock_released(event)

        # Verify remove was called (lock was granted, then removal failed)
        assert remove_called

        # Verify LockStuckEvent was emitted
        event_emitter.emit.assert_called_once()
        emitted_event = event_emitter.emit.call_args[0][0]
        assert isinstance(emitted_event, LockStuckEvent)
        assert emitted_event.work_item_id == next_item_id

        # Restore
        pipeline_queue.remove = original_remove


@pytest.mark.asyncio
class TestPipelineOrchestratorConcurrency:
    """Tests for concurrent coordination scenarios."""

    async def test_concurrent_lock_acquisitions_on_same_board(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_emitter,
    ):
        """Test concurrent lock acquisition events are handled safely."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"

        # Trigger concurrent lock acquisition events
        events = [
            PipelineLockAcquiredEvent(
                type="lock.acquired",
                timestamp=datetime.now(UTC).isoformat(),
                source="test",
                project_id=project_id,
                board_id=board_id,
                work_item_id=f"item-{i}",
            )
            for i in range(5)
        ]

        # Process concurrently
        await asyncio.gather(*[orchestrator.on_lock_acquired(e) for e in events])

        # All should complete without error


@pytest.mark.asyncio
class TestPipelineOrchestratorOrphanRecovery:
    """Tests for orphan lock detection and recovery on startup."""

    async def test_on_startup_releases_orphaned_locks(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        orphan_scan_registry,
        event_emitter,
    ):
        """Test that on_startup detects and releases orphaned locks."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
            orphan_scan_registry=orphan_scan_registry,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Create locks that have no active runs (orphaned)
        await distributed_lock.try_acquire(lock_key, "item-1", ttl_seconds=7200)
        await distributed_lock.try_acquire(f"{project_id}:board-2", "item-2", ttl_seconds=7200)

        # Verify locks are held
        assert (await distributed_lock.get_holder(lock_key)) is not None
        assert (await distributed_lock.get_holder(f"{project_id}:board-2")) is not None

        # Run startup scan
        await orchestrator.on_startup()

        # Verify orphaned locks were released
        assert (await distributed_lock.get_holder(lock_key)) is None
        assert (await distributed_lock.get_holder(f"{project_id}:board-2")) is None

        # Verify scan was recorded
        scan_result = await orphan_scan_registry.get_last_scan()
        assert scan_result is not None
        assert scan_result.orphaned_locks_found == 2
        assert scan_result.orphaned_locks_released == 2

    async def test_on_startup_preserves_active_locks(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        orphan_scan_registry,
        event_emitter,
    ):
        """Test that on_startup preserves locks with active runs."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
            orphan_scan_registry=orphan_scan_registry,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        work_item_id = "item-1"

        # Create a lock and register an active run for it
        await distributed_lock.try_acquire(lock_key, work_item_id)
        await run_registry.set_active_run(
            work_item_id=work_item_id,
            run_id="run-1",
            stage_name="Development",
            project_id=project_id,
            board_id=board_id,
            started_at=datetime.now(UTC).isoformat(),
        )

        # Run startup scan
        await orchestrator.on_startup()

        # Verify lock is still held (not released)
        holder = await distributed_lock.get_holder(lock_key)
        assert holder is not None
        assert holder.holder_id == work_item_id

        # Verify scan was recorded with no orphans
        scan_result = await orphan_scan_registry.get_last_scan()
        assert scan_result is not None
        assert scan_result.orphaned_locks_found == 0
        assert scan_result.orphaned_locks_released == 0

    async def test_on_startup_handles_errors_gracefully(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        orphan_scan_registry,
        event_emitter,
    ):
        """Test that on_startup handles errors and records them."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
            orphan_scan_registry=orphan_scan_registry,
        )

        # Mock distributed_lock to raise an error
        original_get_all = distributed_lock.get_all_holders

        async def mock_get_all_raises(*args):
            raise RuntimeError("Lock service error")

        distributed_lock.get_all_holders = mock_get_all_raises

        # Should not raise
        await orchestrator.on_startup()

        # Verify error was recorded
        scan_result = await orphan_scan_registry.get_last_scan()
        assert scan_result is not None
        assert scan_result.errors is not None
        assert len(scan_result.errors) > 0

        # Restore
        distributed_lock.get_all_holders = original_get_all
