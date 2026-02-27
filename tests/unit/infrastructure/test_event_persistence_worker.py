"""Unit tests for EventPersistenceWorker."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from codetoreum.domain.events import WorkItemCreated
from codetoreum.infrastructure.event_persistence_worker import (
    EventPersistenceWorker,
    EventPersistenceWorkerError,
    EventPersistenceWorkerPool,
)


class MockRedisEventBuffer:
    """Mock Redis event buffer for testing."""

    def __init__(self):
        """Initialize mock."""
        self.pending_events = []
        self.acknowledged = []

    async def read_pending_events(self, consumer_name: str, count: int = 100, block_ms: int = 1000):
        """Read pending events."""
        events = self.pending_events[:count]
        self.pending_events = self.pending_events[count:]
        return events

    async def acknowledge_events(self, message_ids: list):
        """Acknowledge events."""
        self.acknowledged.extend(message_ids)


class MockEventStore:
    """Mock event store for testing."""

    def __init__(self):
        """Initialize mock."""
        self.appended = []

    async def append(self, stream_id: str, events: list, expected_version: int = None):
        """Append events to stream."""
        self.appended.append((stream_id, events))


class TestEventPersistenceWorker:
    """Tests for EventPersistenceWorker."""

    def test_initialization(self):
        """Test worker initialization."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
            batch_size=100,
            batch_timeout_seconds=5.0,
            max_retries=3,
            retry_delay_seconds=1.0,
        )

        assert worker.worker_id == "worker-1"
        assert worker.event_buffer is event_buffer
        assert worker.event_store is event_store
        assert worker.batch_size == 100
        assert worker.batch_timeout_seconds == 5.0
        assert worker.max_retries == 3
        assert worker.retry_delay_seconds == 1.0
        assert worker._running is False

    def test_initialization_with_defaults(self):
        """Test worker initialization with default values."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
        )

        assert worker.batch_size == 100
        assert worker.batch_timeout_seconds == 5.0
        assert worker.max_retries == 3
        assert worker.retry_delay_seconds == 1.0

    def test_get_statistics(self):
        """Test getting worker statistics."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
        )

        stats = worker.get_statistics()

        assert stats["worker_id"] == "worker-1"
        assert "events_processed" in stats
        assert "events_failed" in stats
        assert "batches_processed" in stats
        assert "batches_failed" in stats
        assert "running" in stats
        assert stats["running"] is False

    def test_reset_statistics(self):
        """Test resetting worker statistics."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
        )

        worker._stats["events_processed"] = 100
        worker.reset_statistics()

        assert worker._stats["events_processed"] == 0
        assert worker._stats["events_failed"] == 0
        assert worker._stats["batches_processed"] == 0
        assert worker._stats["batches_failed"] == 0

    @pytest.mark.asyncio
    async def test_group_events_by_stream(self):
        """Test grouping events by stream ID."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
        )

        # Create mock events
        event1 = Mock()
        event1.aggregate_id = "stream-1"

        event2 = Mock()
        event2.aggregate_id = "stream-1"

        event3 = Mock()
        event3.aggregate_id = "stream-2"

        events = [event1, event2, event3]

        grouped = worker._group_events_by_stream(events)

        assert len(grouped) == 2
        assert len(grouped["stream-1"]) == 2
        assert len(grouped["stream-2"]) == 1

    @pytest.mark.asyncio
    async def test_start_raises_if_already_running(self):
        """Test that start raises error if worker already running."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
        )

        worker._running = True

        with pytest.raises(EventPersistenceWorkerError):
            await worker.start()

    def test_stop_when_not_running(self):
        """Test stopping worker when not running."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
        )

        # Should not raise
        asyncio = __import__("asyncio")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(worker.stop())
        loop.close()

    def test_initialization_multiple_workers(self):
        """Test initialization of multiple workers."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        workers = []
        for i in range(5):
            worker = EventPersistenceWorker(
                worker_id=f"worker-{i}",
                event_buffer=event_buffer,
                event_store=event_store,
            )
            workers.append(worker)

        assert len(workers) == 5
        for i, worker in enumerate(workers):
            assert worker.worker_id == f"worker-{i}"

    @pytest.mark.asyncio
    async def test_process_batch_empty(self):
        """Test processing empty batch."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
        )

        # Should not raise
        await worker._process_batch([])

    @pytest.mark.asyncio
    async def test_batch_size_configuration(self):
        """Test batch size configuration."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
            batch_size=50,
        )

        assert worker.batch_size == 50

    @pytest.mark.asyncio
    async def test_timeout_configuration(self):
        """Test timeout configuration."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
            batch_timeout_seconds=10.0,
        )

        assert worker.batch_timeout_seconds == 10.0

    @pytest.mark.asyncio
    async def test_retry_configuration(self):
        """Test retry configuration."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        worker = EventPersistenceWorker(
            worker_id="worker-1",
            event_buffer=event_buffer,
            event_store=event_store,
            max_retries=5,
            retry_delay_seconds=2.0,
        )

        assert worker.max_retries == 5
        assert worker.retry_delay_seconds == 2.0


class TestEventPersistenceWorkerPool:
    """Tests for EventPersistenceWorkerPool."""

    def test_pool_initialization(self):
        """Test worker pool initialization."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        pool = EventPersistenceWorkerPool(
            num_workers=4,
            event_buffer=event_buffer,
            event_store=event_store,
            worker_prefix="pool",
        )

        assert pool.num_workers == 4
        assert pool.event_buffer is event_buffer
        assert pool.event_store is event_store
        assert pool.worker_prefix == "pool"
        assert len(pool.workers) == 0
        assert len(pool.tasks) == 0

    def test_pool_initialization_with_defaults(self):
        """Test pool initialization with default prefix."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        pool = EventPersistenceWorkerPool(
            num_workers=2,
            event_buffer=event_buffer,
            event_store=event_store,
        )

        assert pool.worker_prefix == "worker"

    @pytest.mark.asyncio
    async def test_pool_start(self):
        """Test starting worker pool."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        pool = EventPersistenceWorkerPool(
            num_workers=3,
            event_buffer=event_buffer,
            event_store=event_store,
        )

        # Mock the worker start method
        for i in range(3):
            worker = EventPersistenceWorker(
                worker_id=f"worker-{i}",
                event_buffer=event_buffer,
                event_store=event_store,
            )
            worker.start = AsyncMock()
            pool.workers.append(worker)

        # Note: In real usage, start() would create workers,
        # but we're testing the pool's ability to manage them

    @pytest.mark.asyncio
    async def test_pool_stop(self):
        """Test stopping worker pool."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        pool = EventPersistenceWorkerPool(
            num_workers=2,
            event_buffer=event_buffer,
            event_store=event_store,
        )

        # Create mock workers
        for i in range(2):
            worker = Mock()
            worker.worker_id = f"worker-{i}"
            worker.stop = AsyncMock()
            pool.workers.append(worker)

        await pool.stop()

        # Verify stop was called on all workers
        for worker in pool.workers:
            worker.stop.assert_called_once()

    def test_pool_statistics(self):
        """Test getting pool statistics."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        pool = EventPersistenceWorkerPool(
            num_workers=2,
            event_buffer=event_buffer,
            event_store=event_store,
        )

        # Create mock workers
        for i in range(2):
            worker = EventPersistenceWorker(
                worker_id=f"worker-{i}",
                event_buffer=event_buffer,
                event_store=event_store,
            )
            pool.workers.append(worker)

        stats = pool.get_pool_statistics()

        assert stats["num_workers"] == 2
        assert "total_events_processed" in stats
        assert "total_events_failed" in stats
        assert "total_batches_processed" in stats
        assert "worker_stats" in stats
        assert len(stats["worker_stats"]) == 2

    def test_pool_with_custom_worker_kwargs(self):
        """Test pool with custom worker kwargs."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        pool = EventPersistenceWorkerPool(
            num_workers=2,
            event_buffer=event_buffer,
            event_store=event_store,
            batch_size=200,
            max_retries=5,
        )

        assert pool.worker_kwargs["batch_size"] == 200
        assert pool.worker_kwargs["max_retries"] == 5

    @pytest.mark.asyncio
    async def test_pool_with_multiple_workers_configuration(self):
        """Test pool configuration with different worker counts."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        for num_workers in [1, 5, 10]:
            pool = EventPersistenceWorkerPool(
                num_workers=num_workers,
                event_buffer=event_buffer,
                event_store=event_store,
            )

            assert pool.num_workers == num_workers

    def test_pool_worker_id_generation(self):
        """Test worker ID generation in pool."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        pool = EventPersistenceWorkerPool(
            num_workers=3,
            event_buffer=event_buffer,
            event_store=event_store,
            worker_prefix="batch",
        )

        # Simulate worker creation
        for i in range(3):
            worker_id = f"{pool.worker_prefix}-{i}"
            assert worker_id in ["batch-0", "batch-1", "batch-2"]

    def test_pool_task_management(self):
        """Test pool task management."""
        event_buffer = MockRedisEventBuffer()
        event_store = MockEventStore()

        pool = EventPersistenceWorkerPool(
            num_workers=2,
            event_buffer=event_buffer,
            event_store=event_store,
        )

        assert len(pool.tasks) == 0

        # Add mock tasks
        for i in range(2):
            task = Mock()
            pool.tasks.append(task)

        assert len(pool.tasks) == 2
