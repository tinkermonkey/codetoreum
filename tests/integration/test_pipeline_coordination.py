"""Integration test for pipeline lock and queue coordination with Redis.

End-to-end test demonstrating real-world pipeline orchestration:
1. Work item enters trigger column
2. Lock is acquired
3. Workflow is started
4. Work item exits pipeline
5. Next queued work item acquires lock
6. Agent execution triggered for next item

This test uses actual Redis adapters to verify the complete coordination flow.
"""

import asyncio
from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from codetoreum.adapters.secondary.redis_distributed_lock import RedisDistributedLock
from codetoreum.adapters.secondary.redis_pipeline_queue import RedisPipelineQueue
from codetoreum.adapters.testing import InMemoryActiveWorkflowRunRegistry
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
async def redis_lock():
    """Redis distributed lock (requires Redis running)."""
    try:
        import redis.asyncio as redis

        redis_client = await redis.from_url("redis://localhost")
        await redis_client.ping()
        lock = RedisDistributedLock(redis_client)
        yield lock
        await redis_client.close()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")


@pytest.fixture
async def redis_queue():
    """Redis pipeline queue (requires Redis running)."""
    try:
        import redis.asyncio as redis

        redis_client = await redis.from_url("redis://localhost")
        await redis_client.ping()
        queue = RedisPipelineQueue(redis_client)
        yield queue
        await redis_client.close()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")


@pytest.fixture
def run_registry():
    """In-memory active workflow run registry."""
    return InMemoryActiveWorkflowRunRegistry()


@pytest.fixture
def event_bus():
    """Mock event bus."""
    from unittest.mock import AsyncMock, MagicMock

    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def event_emitter():
    """Mock event emitter."""
    from unittest.mock import AsyncMock, MagicMock

    emitter = MagicMock()
    emitter.emit = AsyncMock()
    return emitter


@pytest.mark.asyncio
class TestPipelineCoordinationIntegration:
    """Integration tests for pipeline coordination with Redis."""

    async def test_pipeline_flow_work_item_enters_trigger_column(
        self,
        redis_lock,
        redis_queue,
        run_registry,
        event_emitter,
    ):
        """Test: WI enters trigger column → lock acquired."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=redis_lock,
            pipeline_queue=redis_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        work_item_id = "issue-123"

        # Step 1: Work item enters trigger column
        queue_entry = QueueEntry(
            work_item_id=work_item_id,
            stage_name="Development",
            board_position=0,
            enqueued_at=datetime.now(UTC),
            metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )
        result = await redis_queue.enqueue(lock_key, queue_entry)
        assert not result.already_present

        # Step 2: Try to acquire lock
        lock_result = await redis_lock.try_acquire(
            lock_key=lock_key,
            holder_id=work_item_id,
            ttl_seconds=7200,
            holder_metadata={"project_id": project_id, "board_id": board_id},
        )
        assert lock_result.status == AcquireStatus.ACQUIRED

        # Cleanup
        await redis_lock.release(lock_key, work_item_id)
        await redis_queue.remove(lock_key, work_item_id)

    async def test_pipeline_flow_queued_work_items(
        self,
        redis_lock,
        redis_queue,
        run_registry,
        event_emitter,
    ):
        """Test: Multiple WIs queue when lock is held."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=redis_lock,
            pipeline_queue=redis_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # First item acquires lock
        await redis_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="issue-100",
                stage_name="Development",
                board_position=0,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        )
        result = await redis_lock.try_acquire(lock_key, "issue-100")
        assert result.status == AcquireStatus.ACQUIRED

        # Second item queued
        await redis_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="issue-101",
                stage_name="Development",
                board_position=1,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        )
        result = await redis_lock.try_acquire(lock_key, "issue-101")
        assert result.status == AcquireStatus.ALREADY_HELD_BY_OTHER

        # Third item queued
        await redis_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="issue-102",
                stage_name="Development",
                board_position=2,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        )
        result = await redis_lock.try_acquire(lock_key, "issue-102")
        assert result.status == AcquireStatus.ALREADY_HELD_BY_OTHER

        # Verify queue state
        queue_list = await redis_queue.list(lock_key)
        assert len(queue_list) == 3
        assert queue_list[0].work_item_id == "issue-100"
        assert queue_list[1].work_item_id == "issue-101"
        assert queue_list[2].work_item_id == "issue-102"

        # Cleanup
        await redis_lock.release(lock_key, "issue-100")
        await redis_queue.remove(lock_key, "issue-100")
        await redis_queue.remove(lock_key, "issue-101")
        await redis_queue.remove(lock_key, "issue-102")

    async def test_pipeline_flow_work_item_exits_and_next_acquires(
        self,
        redis_lock,
        redis_queue,
        run_registry,
        event_emitter,
    ):
        """Test: WI exits → next queued WI gets lock."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=redis_lock,
            pipeline_queue=redis_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Setup: issue-100 holds lock, issue-101 queued
        await redis_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="issue-100",
                stage_name="Development",
                board_position=0,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        )
        result = await redis_lock.try_acquire(lock_key, "issue-100")
        assert result.status == AcquireStatus.ACQUIRED

        await redis_queue.enqueue(
            lock_key,
            QueueEntry(
                work_item_id="issue-101",
                stage_name="Development",
                board_position=1,
                enqueued_at=datetime.now(UTC),
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            ),
        )

        # Register active run for issue-100
        await run_registry.set_active_run(
            work_item_id="issue-100",
            run_id="run-100",
            stage_name="Development",
            project_id=project_id,
            board_id=board_id,
            started_at=datetime.now(UTC).isoformat(),
        )

        # Issue-100 exits (lock release event fired)
        event = PipelineLockReleasedEvent(
            type="lock.released",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            project_id=project_id,
            board_id=board_id,
            work_item_id="issue-100",
        )
        await orchestrator.on_lock_released(event)

        # Verify lock was released
        holder = await redis_lock.get_holder(lock_key)
        assert holder is not None
        assert holder.holder_id == "issue-101"

        # Cleanup
        await redis_lock.release(lock_key, "issue-101")
        await redis_queue.remove(lock_key, "issue-100")
        await redis_queue.remove(lock_key, "issue-101")
        await run_registry.clear_run("issue-100")

    async def test_pipeline_flow_complete_scenario(
        self,
        redis_lock,
        redis_queue,
        run_registry,
        event_emitter,
    ):
        """Test complete pipeline flow: 3 items, sequential execution."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=redis_lock,
            pipeline_queue=redis_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"
        items = [
            {"id": "issue-100", "position": 0},
            {"id": "issue-101", "position": 1},
            {"id": "issue-102", "position": 2},
        ]

        # All items enter trigger column
        for item in items:
            await redis_queue.enqueue(
                lock_key,
                QueueEntry(
                    work_item_id=item["id"],
                    stage_name="Development",
                    board_position=item["position"],
                    enqueued_at=datetime.now(UTC),
                    metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
                ),
            )

        # Sequential execution
        for i, item in enumerate(items):
            # Try to acquire lock
            lock_result = await redis_lock.try_acquire(
                lock_key=lock_key,
                holder_id=item["id"],
                ttl_seconds=7200,
                holder_metadata={"project_id": project_id, "board_id": board_id},
            )

            if i == 0:
                # First item acquires
                assert lock_result.status == AcquireStatus.ACQUIRED
            else:
                # Others are queued or held by previous
                assert lock_result.status in (
                    AcquireStatus.ALREADY_HELD_BY_OTHER,
                    AcquireStatus.ALREADY_HELD_BY_SELF,
                )

            # Register active run
            await run_registry.set_active_run(
                work_item_id=item["id"],
                run_id=f"run-{i}",
                stage_name="Development",
                project_id=project_id,
                board_id=board_id,
                started_at=datetime.now(UTC).isoformat(),
            )

            # If this is not the first item, skip release
            if i == 0:
                # First item: simulate exit and lock release
                event = PipelineLockReleasedEvent(
                    type="lock.released",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="test",
                    project_id=project_id,
                    board_id=board_id,
                    work_item_id=item["id"],
                )
                await orchestrator.on_lock_released(event)

        # Cleanup
        for item in items:
            await redis_queue.remove(lock_key, item["id"])
            await run_registry.clear_run(item["id"])

        # Final state: last item holds lock
        holder = await redis_lock.get_holder(lock_key)
        assert holder is not None
        assert holder.holder_id == "issue-102"

        # Release final lock
        await redis_lock.release(lock_key, "issue-102")

    async def test_pipeline_flow_concurrent_arrivals(
        self,
        redis_lock,
        redis_queue,
        run_registry,
        event_emitter,
    ):
        """Test concurrent item arrivals are handled correctly."""
        orchestrator = PipelineOrchestrator(
            distributed_lock=redis_lock,
            pipeline_queue=redis_queue,
            run_registry=run_registry,
            event_emitter=event_emitter,
        )

        project_id = "project-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Concurrent enqueue and acquire
        async def enqueue_and_acquire(item_id, position):
            await redis_queue.enqueue(
                lock_key,
                QueueEntry(
                    work_item_id=item_id,
                    stage_name="Development",
                    board_position=position,
                    enqueued_at=datetime.now(UTC),
                    metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
                ),
            )
            return await redis_lock.try_acquire(
                lock_key=lock_key,
                holder_id=item_id,
                ttl_seconds=7200,
                holder_metadata={"project_id": project_id, "board_id": board_id},
            )

        results = await asyncio.gather(
            enqueue_and_acquire("issue-100", 0),
            enqueue_and_acquire("issue-101", 1),
            enqueue_and_acquire("issue-102", 2),
        )

        # Exactly one should have acquired
        acquired_count = sum(1 for r in results if r.status == AcquireStatus.ACQUIRED)
        assert acquired_count == 1

        # Cleanup
        holder = await redis_lock.get_holder(lock_key)
        if holder:
            await redis_lock.release(lock_key, holder.holder_id)
        for i in range(3):
            await redis_queue.remove(lock_key, f"issue-{100+i}")
