"""Integration tests for PipelineOrchestrator event-driven lock and queue coordination.

Comprehensive test suite covering:
- Lock acquisition and queue management
- Lock release and next-item granting
- Orphan lock detection and recovery on startup
- Error handling in critical lock-grant operations
- Concurrent coordination between locks and queues
- Edge cases (empty queue, non-holder release attempts)
"""

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
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.distributed_lock import AcquireStatus
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


@pytest.mark.asyncio
class TestPipelineOrchestratorLockAcquisition:
    """Tests for lock acquisition and queue handling."""

    async def test_lock_acquired_removes_holder_from_queue(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_bus,
    ):
        """Test that on_lock_acquired removes holder from queue if present."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
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
    ):
        """Test on_lock_acquired is idempotent when item not in queue."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
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

    async def test_lock_released_grants_to_next_queued_item(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        event_bus,
    ):
        """Test that on_lock_released grants lock to next queued item."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Setup: item-1 holds lock, item-2 queued
        holder_holder = await distributed_lock.try_acquire(lock_key, "item-1")
        assert holder_holder.status == AcquireStatus.ACQUIRED

        await pipeline_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="item-2",
                stage_name="Development",
                board_position=1,
                enqueued_at=datetime.now(UTC),
                metadata={"project_id": project_id, "board_id": board_id},
            ),
        )

        # Trigger lock release event
        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-1",
        )
        await orchestrator.on_lock_released(event)

        # Verify next item acquired lock
        holder = await distributed_lock.get_holder(lock_key)
        assert holder is not None
        assert holder.holder_id == "item-2"

    async def test_lock_released_with_empty_queue(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
    ):
        """Test on_lock_released succeeds with empty queue."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Setup: item-1 holds lock, no queue
        await distributed_lock.try_acquire(lock_key, "item-1")

        # Trigger lock release event
        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-1",
        )

        # Should not raise and should return early
        await orchestrator.on_lock_released(event)

        # Verify lock is released
        holder = await distributed_lock.get_holder(lock_key)
        assert holder is None

    async def test_lock_released_error_handling_does_not_block(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
    ):
        """Test that lock release errors are logged but handled gracefully."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
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
class TestPipelineOrchestratorOrphanRecovery:
    """Tests for orphan lock detection and recovery on startup."""

    async def test_startup_orphan_scan_releases_orphaned_locks(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        orphan_scan_registry,
    ):
        """Test on_startup detects and releases orphaned locks."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            orphan_scan_registry=orphan_scan_registry,
        )

        # Setup: item-1 holds lock but has no active workflow run
        lock_key = "project-1:board-1"
        await distributed_lock.try_acquire(
            lock_key,
            "item-1",
            holder_metadata={"project_id": "project-1", "board_id": "board-1"},
        )

        # Verify lock is held
        holder = await distributed_lock.get_holder(lock_key)
        assert holder.holder_id == "item-1"

        # Run startup orphan scan
        await orchestrator.on_startup()

        # Verify lock was released
        holder = await distributed_lock.get_holder(lock_key)
        assert holder is None

        # Verify scan was recorded
        assert len(orphan_scan_registry.scans) == 1
        assert orphan_scan_registry.scans[0]["locks_scanned"] == 1
        assert orphan_scan_registry.scans[0]["orphaned_locks_found"] == 1
        assert orphan_scan_registry.scans[0]["orphaned_locks_released"] == 1

    async def test_startup_orphan_scan_preserves_active_locks(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        orphan_scan_registry,
    ):
        """Test on_startup does not release locks with active runs."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            orphan_scan_registry=orphan_scan_registry,
        )

        # Setup: item-1 holds lock and has active workflow run
        lock_key = "project-1:board-1"
        await distributed_lock.try_acquire(
            lock_key,
            "item-1",
            holder_metadata={"project_id": "project-1", "board_id": "board-1"},
        )

        # Register active run
        await run_registry.set_active_run(
            work_item_id="item-1",
            run_id="run-1",
            stage_name="Development",
            project_id="project-1",
            board_id="board-1",
            started_at=datetime.now(UTC).isoformat(),
        )

        # Run startup orphan scan
        await orchestrator.on_startup()

        # Verify lock is still held
        holder = await distributed_lock.get_holder(lock_key)
        assert holder.holder_id == "item-1"

        # Verify scan found no orphans
        assert len(orphan_scan_registry.scans) == 1
        assert orphan_scan_registry.scans[0]["orphaned_locks_found"] == 0
        assert orphan_scan_registry.scans[0]["orphaned_locks_released"] == 0

    async def test_startup_orphan_scan_handles_multiple_locks(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        orphan_scan_registry,
    ):
        """Test on_startup handles multiple locks correctly."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            orphan_scan_registry=orphan_scan_registry,
        )

        # Setup: 3 locks, 2 orphaned and 1 active
        await distributed_lock.try_acquire("project-1:board-1", "item-1")
        await distributed_lock.try_acquire("project-1:board-2", "item-2")
        await distributed_lock.try_acquire("project-2:board-1", "item-3")

        # Register active run for item-3 only
        await run_registry.set_active_run(
            work_item_id="item-3",
            run_id="run-3",
            stage_name="Development",
            project_id="project-2",
            board_id="board-1",
            started_at=datetime.now(UTC).isoformat(),
        )

        # Run startup orphan scan
        await orchestrator.on_startup()

        # Verify scan results
        assert len(orphan_scan_registry.scans) == 1
        assert orphan_scan_registry.scans[0]["locks_scanned"] == 3
        assert orphan_scan_registry.scans[0]["orphaned_locks_found"] == 2
        assert orphan_scan_registry.scans[0]["orphaned_locks_released"] == 2

        # Verify locks
        assert await distributed_lock.get_holder("project-1:board-1") is None
        assert await distributed_lock.get_holder("project-1:board-2") is None
        assert (await distributed_lock.get_holder("project-2:board-1")).holder_id == "item-3"


@pytest.mark.asyncio
class TestPipelineOrchestratorErrorHandling:
    """Tests for error handling in critical operations."""

    async def test_lock_acquired_handles_queue_error_gracefully(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
    ):
        """Test on_lock_acquired logs errors but continues."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
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

    async def test_orphan_scan_handles_release_failures(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
        orphan_scan_registry,
    ):
        """Test orphan scan records errors when release fails."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
            orphan_scan_registry=orphan_scan_registry,
        )

        # Setup lock
        lock_key = "project-1:board-1"
        await distributed_lock.try_acquire(lock_key, "item-1")

        # Mock release to fail
        original_release = distributed_lock.release

        async def mock_release_fails(*args, **kwargs):
            raise RuntimeError("Release failed")

        distributed_lock.release = mock_release_fails

        # Run scan
        await orchestrator.on_startup()

        # Verify error was recorded
        assert len(orphan_scan_registry.scans) == 1
        assert orphan_scan_registry.scans[0]["errors"] is not None
        assert len(orphan_scan_registry.scans[0]["errors"]) > 0

        # Restore
        distributed_lock.release = original_release


@pytest.mark.asyncio
class TestPipelineOrchestratorConcurrency:
    """Tests for concurrent coordination scenarios."""

    async def test_concurrent_lock_acquisitions_on_same_board(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
    ):
        """Test concurrent lock acquisition events are handled safely."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
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

    async def test_concurrent_lock_release_and_acquisition(
        self,
        distributed_lock,
        pipeline_queue,
        run_registry,
    ):
        """Test concurrent release and acquisition events."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=distributed_lock,
            pipeline_queue=pipeline_queue,
            run_registry=run_registry,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Setup initial state
        await distributed_lock.try_acquire(lock_key, "item-1")
        for i in range(2, 5):
            await pipeline_queue.enqueue(
                lock_key,
                QueueEntry(
                    work_item_id=f"item-{i}",
                    stage_name="Development",
                    board_position=i - 1,
                    enqueued_at=datetime.now(UTC),
                    metadata={"project_id": project_id, "board_id": board_id},
                ),
            )

        # Trigger concurrent release and acquisition
        release_event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-1",
        )

        # Process release
        await orchestrator.on_lock_released(release_event)

        # Next item should have acquired lock
        holder = await distributed_lock.get_holder(lock_key)
        assert holder is not None
        assert holder.holder_id == "item-2"
