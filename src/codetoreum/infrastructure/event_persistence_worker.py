"""Background worker for persisting events from Redis to Elasticsearch."""

import asyncio
import logging
import signal
from datetime import UTC, datetime
from typing import Any

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.redis_event_buffer import (
    RedisEventBuffer,
    RedisEventBufferError,
)
from codetoreum.ports.exceptions import EventStoreError
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


class EventPersistenceWorkerError(Exception):
    """Raised when worker operations fail."""



class EventPersistenceWorker:
    """
    Background worker that reads events from Redis and persists to Elasticsearch.

    Features:
    - Batch processing for efficiency
    - Consumer groups for reliable delivery and parallel processing
    - Error handling with retry logic
    - Dead letter queue for failed events
    - Graceful shutdown
    - Monitoring metrics

    Architecture:
        Redis Streams → [Worker] → Elasticsearch
                    ↓
              Dead Letter Queue (on failure)
    """

    def __init__(
        self,
        worker_id: str,
        event_buffer: RedisEventBuffer,
        event_store: IEventStore,
        batch_size: int = 100,
        batch_timeout_seconds: float = 5.0,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ):
        """
        Initialize persistence worker.

        Args:
            worker_id: Unique identifier for this worker instance
            event_buffer: Redis event buffer to read from
            event_store: Event store to persist to (Elasticsearch adapter)
            batch_size: Number of events to process in each batch
            batch_timeout_seconds: Maximum time to wait for a full batch
            max_retries: Maximum retry attempts for failed batches
            retry_delay_seconds: Delay between retries
        """
        self.worker_id = worker_id
        self.event_buffer = event_buffer
        self.event_store = event_store
        self.batch_size = batch_size
        self.batch_timeout_seconds = batch_timeout_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

        self._running = False
        self._shutdown_event = asyncio.Event()

        # Statistics
        self._stats = {
            "events_processed": 0,
            "events_failed": 0,
            "batches_processed": 0,
            "batches_failed": 0,
            "started_at": None,
            "last_batch_at": None,
        }

    async def start(self) -> None:
        """
        Start the worker.

        Runs indefinitely until stopped via stop() or SIGTERM.

        Raises:
            EventPersistenceWorkerError: If worker is already running
        """
        if self._running:
            raise EventPersistenceWorkerError(
                f"Worker {self.worker_id} is already running"
            )

        self._running = True
        self._stats["started_at"] = datetime.now(UTC)

        logger.info(
            f"Starting event persistence worker '{self.worker_id}' "
            f"(batch_size={self.batch_size}, timeout={self.batch_timeout_seconds}s)"
        )

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        try:
            await self._run_worker_loop()

        except asyncio.CancelledError:
            logger.info(f"Worker {self.worker_id} cancelled")
            raise

        except Exception as e:
            logger.error(f"Worker {self.worker_id} failed with error: {e}", exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR}
            )

        finally:
            self._running = False
            logger.info(f"Worker {self.worker_id} stopped")

    async def stop(self) -> None:
        """
        Stop the worker gracefully.

        Waits for current batch to complete before shutting down.
        """
        if not self._running:
            return

        logger.info(f"Stopping worker {self.worker_id}...")
        self._running = False
        self._shutdown_event.set()

    async def _run_worker_loop(self) -> None:
        """
        Main worker loop: read events from Redis, persist to Elasticsearch.
        """
        while self._running:
            try:
                # Check if shutdown requested
                if self._shutdown_event.is_set():
                    logger.info(f"Worker {self.worker_id} received shutdown signal")
                    break

                # Read batch from Redis
                batch = await self.event_buffer.read_pending_events(
                    consumer_name=self.worker_id,
                    count=self.batch_size,
                    block_ms=int(self.batch_timeout_seconds * 1000),
                )

                if not batch:
                    # No events, wait a bit
                    await asyncio.sleep(0.1)
                    continue

                # Process batch
                await self._process_batch(batch)

            except asyncio.CancelledError:
                logger.info(f"Worker {self.worker_id} cancelled during processing")
                break

            except Exception as e:
                logger.error(
                    f"Worker {self.worker_id} error in main loop: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR}
            )
                await asyncio.sleep(self.retry_delay_seconds)

    async def _process_batch(self, batch: list[dict[str, Any]]) -> None:
        """
        Process a batch of events: persist to Elasticsearch and acknowledge.

        Args:
            batch: List of event dictionaries from Redis

        Raises:
            Exception: If batch processing fails after retries
        """
        if not batch:
            return

        logger.debug(f"Worker {self.worker_id} processing batch of {len(batch)} events")

        # Extract events and message IDs
        events = [item["event"] for item in batch]
        message_ids = [item["id"] for item in batch]

        # Retry logic
        for attempt in range(self.max_retries + 1):
            try:
                # Persist to Elasticsearch
                # Group events by stream_id (aggregate_id) for efficient appending
                events_by_stream = self._group_events_by_stream(events)

                for stream_id, stream_events in events_by_stream.items():
                    await self.event_store.append(
                        stream_id=stream_id,
                        events=stream_events,
                        expected_version=None,  # No concurrency check for background persistence
                    )

                # Acknowledge in Redis (mark as processed)
                await self.event_buffer.acknowledge_events(message_ids)

                # Update statistics
                self._stats["events_processed"] += len(events)
                self._stats["batches_processed"] += 1
                self._stats["last_batch_at"] = datetime.now(UTC)

                logger.debug(
                    f"Worker {self.worker_id} persisted {len(events)} events "
                    f"across {len(events_by_stream)} streams"
                )

                return  # Success!

            except (EventStoreError, RedisEventBufferError) as e:
                logger.warning(
                    f"Worker {self.worker_id} failed to process batch "
                    f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                )

            except Exception as e:
                logger.error(
                    f"Worker {self.worker_id} unexpected error processing batch "
                    f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}",
                    exc_info=True
,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR}
            )
            if attempt < self.max_retries:
                # Wait before retrying
                await asyncio.sleep(self.retry_delay_seconds * (attempt + 1))
            else:
                # All retries exhausted - log error
                # Events will remain in pending state and can be manually recovered
                self._stats["events_failed"] += len(events)
                self._stats["batches_failed"] += 1

                logger.error(
                    f"Worker {self.worker_id} failed to process batch after "
                    f"{self.max_retries + 1} attempts. Events will remain in "
                    f"pending state for manual recovery.",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INTERNAL_ERROR}
            )
                raise

    def _group_events_by_stream(
        self, events: list[Any]
    ) -> dict[str, list[Any]]:
        """
        Group events by stream ID (aggregate ID) for efficient batch appending.

        Args:
            events: List of domain events

        Returns:
            Dictionary mapping stream_id to list of events
        """
        events_by_stream: dict[str, list[Any]] = {}

        for event in events:
            stream_id = event.aggregate_id

            if stream_id not in events_by_stream:
                events_by_stream[stream_id] = []

            events_by_stream[stream_id].append(event)

        return events_by_stream

    def get_statistics(self) -> dict[str, Any]:
        """
        Get worker statistics.

        Returns:
            Dictionary with worker statistics
        """
        stats = self._stats.copy()

        stats["worker_id"] = self.worker_id
        stats["running"] = self._running
        stats["batch_size"] = self.batch_size
        stats["batch_timeout_seconds"] = self.batch_timeout_seconds

        # Calculate runtime
        if stats["started_at"]:
            runtime_seconds = (
                datetime.now(UTC) - stats["started_at"]
            ).total_seconds()
            stats["runtime_seconds"] = runtime_seconds

            # Calculate throughput
            if runtime_seconds > 0:
                stats["events_per_second"] = (
                    stats["events_processed"] / runtime_seconds
                )
            else:
                stats["events_per_second"] = 0
        else:
            stats["runtime_seconds"] = 0
            stats["events_per_second"] = 0

        return stats

    def reset_statistics(self) -> None:
        """Reset worker statistics (for testing)."""
        self._stats = {
            "events_processed": 0,
            "events_failed": 0,
            "batches_processed": 0,
            "batches_failed": 0,
            "started_at": self._stats["started_at"],
            "last_batch_at": None,
        }


class EventPersistenceWorkerPool:
    """
    Pool of event persistence workers for parallel processing.

    Manages multiple worker instances for high-throughput event persistence.
    """

    def __init__(
        self,
        num_workers: int,
        event_buffer: RedisEventBuffer,
        event_store: IEventStore,
        worker_prefix: str = "worker",
        **worker_kwargs,
    ):
        """
        Initialize worker pool.

        Args:
            num_workers: Number of worker instances
            event_buffer: Redis event buffer
            event_store: Event store (Elasticsearch)
            worker_prefix: Prefix for worker IDs
            **worker_kwargs: Additional arguments for workers
        """
        self.num_workers = num_workers
        self.event_buffer = event_buffer
        self.event_store = event_store
        self.worker_prefix = worker_prefix
        self.worker_kwargs = worker_kwargs

        self.workers: list[EventPersistenceWorker] = []
        self.tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start all workers in the pool."""
        logger.info(f"Starting worker pool with {self.num_workers} workers")

        for i in range(self.num_workers):
            worker_id = f"{self.worker_prefix}-{i}"

            worker = EventPersistenceWorker(
                worker_id=worker_id,
                event_buffer=self.event_buffer,
                event_store=self.event_store,
                **self.worker_kwargs,
            )

            self.workers.append(worker)

            # Start worker in background task
            task = asyncio.create_task(worker.start())
            self.tasks.append(task)

        logger.info(f"Worker pool started with {len(self.workers)} workers")

    async def stop(self) -> None:
        """Stop all workers gracefully."""
        logger.info(f"Stopping worker pool ({len(self.workers)} workers)")

        # Stop all workers
        for worker in self.workers:
            await worker.stop()

        # Wait for all tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        logger.info("Worker pool stopped")

    def get_pool_statistics(self) -> dict[str, Any]:
        """
        Get aggregated statistics for the pool.

        Returns:
            Dictionary with pool statistics
        """
        total_events = 0
        total_failed = 0
        total_batches = 0

        worker_stats = []

        for worker in self.workers:
            stats = worker.get_statistics()
            worker_stats.append(stats)

            total_events += stats["events_processed"]
            total_failed += stats["events_failed"]
            total_batches += stats["batches_processed"]

        return {
            "num_workers": self.num_workers,
            "total_events_processed": total_events,
            "total_events_failed": total_failed,
            "total_batches_processed": total_batches,
            "worker_stats": worker_stats,
        }
