"""Unit tests for PipelineOrchestrator.

Focused unit tests covering the key flows of PipelineOrchestrator:
- Initial-acquire flow: lock acquired, item removed from queue
- Queue-grant flow: lock released, next queued item acquires lock
- Release-cycles-through-queue: sequential lock passing through multiple items
- Orphan-startup-scan: detection and cleanup of orphaned locks
- Duplicate event delivery idempotency: handling repeated events safely
"""

from datetime import UTC, datetime
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.application.event_handlers.pipeline_orchestrator import (
    PipelineOrchestrator,
)
from codetoreum.domain.events.lock_events import (
    LockStuckEvent,
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
)
from codetoreum.ports.output.distributed_lock import AcquireStatus, IDistributedLock
from codetoreum.ports.output.pipeline_queue import IPipelineQueue, QueueEntry


@pytest.fixture
def mock_lock() -> MagicMock:
    """Create a mock IDistributedLock."""
    mock = MagicMock(spec=IDistributedLock)
    # Make async methods return coroutines
    mock.try_acquire = AsyncMock()
    mock.release = AsyncMock()
    mock.get_holder = AsyncMock()
    mock.get_all_holders = AsyncMock()
    mock.renew = AsyncMock()
    return mock


@pytest.fixture
def mock_queue() -> MagicMock:
    """Create a mock IPipelineQueue."""
    mock = MagicMock(spec=IPipelineQueue)
    # Make async methods return coroutines
    mock.enqueue = AsyncMock()
    mock.peek = AsyncMock()
    mock.pop = AsyncMock()
    mock.remove = AsyncMock()
    mock.contains = AsyncMock()
    mock.length = AsyncMock()
    mock.list = AsyncMock()
    mock.position_of = AsyncMock()
    return mock


@pytest.fixture
def mock_run_registry() -> MagicMock:
    """Create a mock IActiveWorkflowRunRegistry."""
    mock = MagicMock()
    mock.get_active_run = AsyncMock()
    mock.set_active_run = AsyncMock()
    mock.clear_run = AsyncMock()
    return mock


@pytest.fixture
def mock_event_emitter() -> MagicMock:
    """Create a mock IEventEmitter."""
    mock = MagicMock()
    mock.emit = MagicMock()
    mock.on = MagicMock()
    mock.off = MagicMock()
    return mock


@pytest.fixture
def mock_orphan_scan_registry() -> MagicMock:
    """Create a mock IOrphanScanRegistry."""
    mock = MagicMock()
    mock.record_scan = AsyncMock()
    return mock


@pytest.mark.asyncio
class TestPipelineOrchestratorInitialAcquire:
    """Tests for the initial-acquire flow when lock is acquired."""

    async def test_on_lock_acquired_removes_holder_from_queue(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that on_lock_acquired removes holder from queue."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        work_item_id = "item-1"

        # Setup: item is in queue
        mock_queue.contains.return_value = True

        event = PipelineLockAcquiredEvent(
            type="lock.acquired",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
        )

        await orchestrator.on_lock_acquired(event)

        # Verify queue.contains was called
        mock_queue.contains.assert_called_once_with(f"{project_id}:{board_id}", work_item_id)

        # Verify queue.remove was called
        mock_queue.remove.assert_called_once_with(f"{project_id}:{board_id}", work_item_id)

    async def test_on_lock_acquired_idempotent_when_not_in_queue(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that on_lock_acquired is idempotent when item not in queue."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        # Setup: item is NOT in queue
        mock_queue.contains.return_value = False

        event = PipelineLockAcquiredEvent(
            type="lock.acquired",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id="project-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        await orchestrator.on_lock_acquired(event)

        # Remove should not be called since item wasn't in queue
        mock_queue.remove.assert_not_called()

    async def test_on_lock_acquired_emits_alert_on_queue_removal_failure(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that on_lock_acquired emits LockStuckEvent on queue removal failure."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        work_item_id = "item-1"

        # Setup: item is in queue, but remove fails
        mock_queue.contains.return_value = True
        mock_queue.remove.side_effect = RuntimeError("Queue service error")

        event = PipelineLockAcquiredEvent(
            type="lock.acquired",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
        )

        await orchestrator.on_lock_acquired(event)

        # Verify alert was emitted
        mock_event_emitter.emit.assert_called_once()
        emitted_event = mock_event_emitter.emit.call_args[0][0]
        assert isinstance(emitted_event, LockStuckEvent)
        assert emitted_event.work_item_id == work_item_id

    async def test_on_lock_acquired_handles_queue_contains_error_gracefully(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that on_lock_acquired handles queue.contains errors gracefully."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        # Setup: queue.contains raises error
        mock_queue.contains.side_effect = RuntimeError("Queue service error")

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

        # Verify remove was not called
        mock_queue.remove.assert_not_called()


@pytest.mark.asyncio
class TestPipelineOrchestratorQueueGrant:
    """Tests for the queue-grant flow when lock is released."""

    async def test_on_lock_released_grants_lock_to_next_item(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that on_lock_released grants lock to next queued item and removes it from queue."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        next_item_id = "item-2"

        # Setup: next item is peeked from queue
        next_entry = QueueEntry(
            work_item_id=next_item_id,
            stage_name="Development",
            board_position=0,
            enqueued_at=datetime.now(UTC),
            metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )
        mock_queue.peek.return_value = next_entry

        # Setup: lock acquisition succeeds for next item
        from codetoreum.ports.output.distributed_lock import AcquireResult
        mock_lock.try_acquire.return_value = AcquireResult(
            status=AcquireStatus.ACQUIRED,
            lock_key=lock_key,
            holder_id=next_item_id,
            acquired_at=datetime.now(UTC),
        )

        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-1",
        )

        await orchestrator.on_lock_released(event)

        # Verify try_acquire was called with next item
        mock_lock.try_acquire.assert_called_once()
        call_args = mock_lock.try_acquire.call_args
        assert call_args[1]["holder_id"] == next_item_id

        # Verify remove was called to remove next item from queue
        mock_queue.remove.assert_called_once_with(lock_key, next_item_id)

    async def test_on_lock_released_no_queued_items(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that on_lock_released returns early when queue is empty."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        # Setup: queue is empty
        mock_queue.peek.return_value = None

        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id="project-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        await orchestrator.on_lock_released(event)

        # Verify try_acquire was NOT called
        mock_lock.try_acquire.assert_not_called()

    async def test_on_lock_released_emits_alert_on_lock_acquisition_failure(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that on_lock_released emits LockStuckEvent on lock acquisition failure."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        next_item_id = "item-2"

        # Setup: next item is peeked from queue
        next_entry = QueueEntry(
            work_item_id=next_item_id,
            stage_name="Development",
            board_position=0,
            enqueued_at=datetime.now(UTC),
            metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )
        mock_queue.peek.return_value = next_entry

        # Setup: lock acquisition fails
        mock_lock.try_acquire.side_effect = RuntimeError("Lock service error")

        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-1",
        )

        await orchestrator.on_lock_released(event)

        # Verify alert was emitted
        mock_event_emitter.emit.assert_called_once()
        emitted_event = mock_event_emitter.emit.call_args[0][0]
        assert isinstance(emitted_event, LockStuckEvent)
        assert emitted_event.work_item_id == next_item_id

    async def test_on_lock_released_emits_alert_on_queue_removal_failure_after_grant(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that on_lock_released emits LockStuckEvent on queue removal failure after grant."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        next_item_id = "item-2"

        # Setup: next item is peeked from queue
        next_entry = QueueEntry(
            work_item_id=next_item_id,
            stage_name="Development",
            board_position=0,
            enqueued_at=datetime.now(UTC),
            metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )
        mock_queue.peek.return_value = next_entry

        # Setup: lock acquisition succeeds but queue removal fails
        from codetoreum.ports.output.distributed_lock import AcquireResult
        mock_lock.try_acquire.return_value = AcquireResult(
            status=AcquireStatus.ACQUIRED,
            lock_key=lock_key,
            holder_id=next_item_id,
            acquired_at=datetime.now(UTC),
        )
        mock_queue.remove.side_effect = RuntimeError("Queue service error")

        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-1",
        )

        await orchestrator.on_lock_released(event)

        # Verify alert was emitted
        mock_event_emitter.emit.assert_called_once()
        emitted_event = mock_event_emitter.emit.call_args[0][0]
        assert isinstance(emitted_event, LockStuckEvent)
        assert emitted_event.work_item_id == next_item_id


@pytest.mark.asyncio
class TestPipelineOrchestratorReleaseCycle:
    """Tests for sequential lock passing through multiple queued items."""

    async def test_release_cycles_through_queue_sequence(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that locks cycle through queued items in sequence."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Simulate: item-1 releases, item-2 acquires, then item-2 releases, item-3 acquires

        from codetoreum.ports.output.distributed_lock import AcquireResult

        # First release cycle: item-1 -> item-2
        item2_entry = QueueEntry(
            work_item_id="item-2",
            stage_name="Development",
            board_position=0,
            enqueued_at=datetime.now(UTC),
            metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )

        mock_queue.peek.side_effect = [item2_entry, None]  # item-2 on first call, None on second
        mock_lock.try_acquire.return_value = AcquireResult(
            status=AcquireStatus.ACQUIRED,
            lock_key=lock_key,
            holder_id="item-2",
            acquired_at=datetime.now(UTC),
        )

        event1 = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-1",
        )

        await orchestrator.on_lock_released(event1)

        # Verify item-2 got the lock
        assert mock_lock.try_acquire.call_count == 1
        assert mock_queue.remove.call_count == 1

    async def test_duplicate_release_events_handled_safely(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that duplicate release events are handled idempotently."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"

        # Setup: queue empty (no next item)
        mock_queue.peek.return_value = None

        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="item-1",
        )

        # Process same event twice
        await orchestrator.on_lock_released(event)
        await orchestrator.on_lock_released(event)

        # Should complete without error
        mock_lock.try_acquire.assert_not_called()


@pytest.mark.asyncio
class TestPipelineOrchestratorOrphanRecovery:
    """Tests for orphan lock detection and recovery on startup."""

    async def test_on_startup_releases_orphaned_locks(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
        mock_orphan_scan_registry,
    ):
        """Test that on_startup detects and releases orphaned locks."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
            orphan_scan_registry=mock_orphan_scan_registry,
        )

        from codetoreum.ports.output.distributed_lock import LockHolder

        # Setup: two locks held, no active runs for them
        lock1 = LockHolder(
            lock_key="project-1:board-1",
            holder_id="item-1",
            acquired_at=datetime.now(UTC),
            ttl_seconds=7200,
            expires_at=datetime.now(UTC),
            holder_metadata=MappingProxyType({}),
        )
        lock2 = LockHolder(
            lock_key="project-1:board-2",
            holder_id="item-2",
            acquired_at=datetime.now(UTC),
            ttl_seconds=7200,
            expires_at=datetime.now(UTC),
            holder_metadata=MappingProxyType({}),
        )

        mock_lock.get_all_holders.return_value = [lock1, lock2]
        mock_run_registry.get_active_run.return_value = None  # No active runs

        from codetoreum.ports.output.distributed_lock import ReleaseResult
        mock_lock.release.return_value = ReleaseResult(released=True, reason=None, lock_key="project-1:board-1")

        await orchestrator.on_startup()

        # Verify all locks were released
        assert mock_lock.release.call_count == 2

        # Verify scan was recorded
        mock_orphan_scan_registry.record_scan.assert_called_once()
        scan_call = mock_orphan_scan_registry.record_scan.call_args
        assert scan_call[1]["locks_scanned"] == 2
        assert scan_call[1]["orphaned_locks_found"] == 2
        assert scan_call[1]["orphaned_locks_released"] == 2

    async def test_on_startup_preserves_active_locks(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
        mock_orphan_scan_registry,
    ):
        """Test that on_startup preserves locks with active runs."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
            orphan_scan_registry=mock_orphan_scan_registry,
        )

        from codetoreum.ports.output.distributed_lock import LockHolder

        # Setup: one lock held with an active run
        lock1 = LockHolder(
            lock_key="project-1:board-1",
            holder_id="item-1",
            acquired_at=datetime.now(UTC),
            ttl_seconds=7200,
            expires_at=datetime.now(UTC),
            holder_metadata=MappingProxyType({}),
        )

        mock_lock.get_all_holders.return_value = [lock1]
        mock_run_registry.get_active_run.return_value = {
            "work_item_id": "item-1",
            "run_id": "run-1",
        }  # Active run exists

        await orchestrator.on_startup()

        # Verify lock was NOT released
        mock_lock.release.assert_not_called()

        # Verify scan was recorded with no orphans
        mock_orphan_scan_registry.record_scan.assert_called_once()
        scan_call = mock_orphan_scan_registry.record_scan.call_args
        assert scan_call[1]["locks_scanned"] == 1
        assert scan_call[1]["orphaned_locks_found"] == 0
        assert scan_call[1]["orphaned_locks_released"] == 0

    async def test_on_startup_handles_errors_gracefully(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
        mock_orphan_scan_registry,
    ):
        """Test that on_startup handles errors and records them."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
            orphan_scan_registry=mock_orphan_scan_registry,
        )

        # Setup: lock service raises error
        mock_lock.get_all_holders.side_effect = RuntimeError("Lock service error")

        await orchestrator.on_startup()

        # Verify error was recorded
        mock_orphan_scan_registry.record_scan.assert_called_once()
        scan_call = mock_orphan_scan_registry.record_scan.call_args
        assert scan_call[1]["locks_scanned"] == 0
        assert scan_call[1]["errors"] == ("Startup orphan scan failed",)


@pytest.mark.asyncio
class TestPipelineOrchestratorIdempotency:
    """Tests for idempotent event handling."""

    async def test_duplicate_lock_acquired_events_idempotent(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that duplicate lock acquired events are handled idempotently."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        # Setup: item not in queue
        mock_queue.contains.return_value = False

        event = PipelineLockAcquiredEvent(
            type="lock.acquired",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id="project-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        # Process same event multiple times
        await orchestrator.on_lock_acquired(event)
        await orchestrator.on_lock_acquired(event)
        await orchestrator.on_lock_acquired(event)

        # Should complete without error
        mock_queue.remove.assert_not_called()

    async def test_event_type_dispatch_handles_unexpected_events(
        self,
        mock_lock,
        mock_queue,
        mock_run_registry,
        mock_event_emitter,
    ):
        """Test that handle() method correctly dispatches events."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=mock_queue,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter,
        )

        # Setup: queue empty
        mock_queue.contains.return_value = False

        event = PipelineLockAcquiredEvent(
            type="lock.acquired",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id="project-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        # Call handle() which should dispatch to on_lock_acquired
        await orchestrator.handle(event)

        # Verify correct handler was called
        mock_queue.contains.assert_called()
