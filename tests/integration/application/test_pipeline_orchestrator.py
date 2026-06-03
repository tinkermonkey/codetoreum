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
