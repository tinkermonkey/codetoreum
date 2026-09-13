"""Redis-backed pipeline queue service for production durability.

This implementation provides a native IPipelineQueueService implementation backed
by Redis, ensuring queue state survives process restarts. It uses four Redis
structures per the architecture design:

1. Sorted Set (per pipeline): Maintains work item ordering by board position
2. Metadata Hash (per pipeline): Stores status, timestamps, and entry metadata
3. Reverse Index Hash (global): Maps work_item_id → pipeline coordinates for O(1) lookup
4. Pipeline Registry Set (global): Tracks all known pipelines for sync operations

The queue is independent of RedisPipelineQueue (IPipelineQueue) and uses the
queue_events.py event family via IEventEmitter, matching InMemoryQueueService
semantics.
"""

import json
import logging
from datetime import UTC, datetime

import redis.asyncio as aioredis

from codetoreum.domain.events.queue_events import (
    QueueItemAddedEvent,
    QueueItemRemovedEvent,
    QueueMetadataCorruptionEvent,
    QueuePositionChangedEvent,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.failed_event_store import IFailedEventStore
from codetoreum.ports.output.pipeline_queue_service import (
    DuplicateQueueEntryError,
    InvalidQueueStateError,
    IPipelineQueueService,
    NonNegativeInt,
    PipelineQueueEntry,
    QueueItemNotFoundError,
    QueueStatus,
    QueueValidationError,
)

logger = logging.getLogger(__name__)

_KEY_PREFIX = "codetoreum:qsvc"


class RedisPipelineQueueService(IPipelineQueueService):
    """Redis-backed pipeline queue service with board position tracking.

    Manages work item queues per pipeline (project_id, board_id) with position-based
    ordering via Redis. Queue entries are stored as frozen dataclasses and sorted by
    board position.

    Uses four Redis key structures:
    - Sorted Set per pipeline: work item ordering by position
    - Metadata Hash per pipeline: status, timestamps, entry data
    - Global Reverse Index Hash: O(1) work_item_id → pipeline lookup
    - Global Pipeline Registry Set: known pipelines for sync operations

    Features:
        - Board position-based queue ordering (lowest position = highest priority)
        - Global reverse index for cross-pipeline membership lookup
        - Graceful degradation on board service failures
        - Metadata corruption handling with event emission
        - Event emission via IEventEmitter (not EventBus)

    Concurrency Notes:
        - mark_item_active uses three sequential Redis commands (hget metadata, check status, hset update)
          without atomic guarantees. This is suitable for the current single-instance deployment model
          where only one orchestrator accesses the queue. Full atomic CAS (Lua script) is deferred to
          multi-instance deployment when multiple orchestrators may execute concurrently.
        - enqueue_item uses atomic HSETNX for reverse index + pipeline for queue data, with cleanup
          on pipeline failure to prevent orphaned entries.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        board_service: IBoardService,
        event_emitter: IEventEmitter,
        key_prefix: str = _KEY_PREFIX,
        failed_event_store: IFailedEventStore | None = None,
    ) -> None:
        """Initialize Redis-backed queue service.

        Args:
            redis_client: Redis async client
            board_service: Board service for queue synchronization
            event_emitter: Event emitter for domain events
            key_prefix: Redis key prefix (default: "codetoreum:qsvc")
            failed_event_store: Optional failure route for INV-20 compliance (forward compatibility)
        """
        self._redis = redis_client
        self._board_service = board_service
        self._event_emitter = event_emitter
        self._key_prefix = key_prefix
        self.failed_event_store = failed_event_store

    def _queue_key(self, project_id: str, board_id: str) -> str:
        """Get Redis sorted set key for a pipeline queue."""
        return f"{self._key_prefix}:{project_id}:{board_id}"

    def _metadata_key(self, project_id: str, board_id: str) -> str:
        """Get Redis hash key for pipeline metadata."""
        return f"{self._key_prefix}:meta:{project_id}:{board_id}"

    def _reverse_index_key(self) -> str:
        """Get Redis hash key for global reverse index."""
        return f"{self._key_prefix}:item-lookup"

    def _pipeline_registry_key(self) -> str:
        """Get Redis set key for pipeline registry."""
        return f"{self._key_prefix}:pipelines"

    async def is_item_in_queue(self, work_item_id: str) -> bool:
        """Check if a work item is in any queue via global reverse index.

        Uses O(1) HEXISTS on the global reverse index hash to determine
        membership across all pipelines.

        Args:
            work_item_id: Work item identifier

        Returns:
            bool: True if item is in any queue, False otherwise

        Raises:
            QueueValidationError: Invalid work_item_id
        """
        if not work_item_id:
            msg = "work_item_id cannot be empty"
            raise QueueValidationError(msg)

        reverse_index_key = self._reverse_index_key()
        exists = await self._redis.hexists(reverse_index_key, work_item_id)
        return bool(exists)

    async def enqueue_item(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        position_in_column: int,
        timestamp: datetime,
    ) -> None:
        """Add a work item to the queue for a pipeline.

        Creates a new queue entry with status=WAITING. Raises DuplicateQueueEntryError
        if item already exists in queue.

        Uses HSETNX on the reverse index for atomic duplicate detection.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            work_item_id: Work item identifier
            position_in_column: Position in board column (0 = highest priority)
            timestamp: Time when item was queued

        Raises:
            QueueValidationError: Invalid parameters
            DuplicateQueueEntryError: Item already in queue
        """
        # Input validation
        if not project_id:
            msg = "project_id cannot be empty"
            raise QueueValidationError(msg)
        if not board_id:
            msg = "board_id cannot be empty"
            raise QueueValidationError(msg)
        if not work_item_id:
            msg = "work_item_id cannot be empty"
            raise QueueValidationError(msg)
        if position_in_column < 0:
            msg = "position_in_column cannot be negative"
            raise QueueValidationError(msg)

        # Warn about suspiciously high positions
        if position_in_column > 1000:
            logger.warning(
                f"Unusually high position_in_column={position_in_column} for {work_item_id}. "
                f"This may indicate a bug in board position calculation.",
                extra={
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "board_id": board_id,
                    "position": position_in_column,
                },
            )

        # Normalize timestamp if string
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        # Prepare keys
        reverse_index_key = self._reverse_index_key()
        queue_key = self._queue_key(project_id, board_id)
        meta_key = self._metadata_key(project_id, board_id)
        pipeline_registry_key = self._pipeline_registry_key()

        # Store metadata in hash
        metadata = {
            "status": QueueStatus.WAITING.value,
            "queued_at": timestamp.isoformat(),
            "last_position_check": timestamp.isoformat(),
        }

        # Update reverse index
        pipeline_coords = f"{project_id}\x1f{board_id}"

        # Atomically check duplicate using HSETNX on reverse index
        # HSETNX returns 1 if field was set, 0 if field already existed
        dup_check = await self._redis.hsetnx(reverse_index_key, work_item_id, pipeline_coords)

        if not dup_check:
            # Field already exists - this is a duplicate
            msg = f"Work item {work_item_id} already in queue"
            raise DuplicateQueueEntryError(msg)

        # Add to queue (atomically with pipeline)
        try:
            pipe = self._redis.pipeline(transaction=True)
            await pipe.zadd(queue_key, {work_item_id: float(position_in_column)})
            await pipe.hset(meta_key, work_item_id, json.dumps(metadata))
            await pipe.sadd(pipeline_registry_key, pipeline_coords)
            await pipe.execute()
        except Exception:
            # Pipeline failed - remove orphaned reverse index entry to prevent future duplicates
            await self._redis.hdel(reverse_index_key, work_item_id)
            raise

        # Emit event
        self._emit_event(
            QueueItemAddedEvent(
                type="queue.item_added",
                timestamp=datetime.now(UTC).isoformat(),
                source="redis_pipeline_queue_service",
                queue_name=f"{project_id}:{board_id}",
                item_id=work_item_id,
                position=position_in_column,
                project_id=project_id,
            )
        )

    async def mark_item_active(self, work_item_id: str) -> None:
        """Mark a queued item as active (holding the lock).

        Changes item status from WAITING to ACTIVE. Raises QueueItemNotFoundError
        if item not found, and InvalidQueueStateError if already active or corrupted.

        Args:
            work_item_id: Work item to mark active

        Raises:
            QueueValidationError: Invalid work_item_id
            QueueItemNotFoundError: Item not in queue
            InvalidQueueStateError: Item already marked active or metadata corrupted
        """
        if not work_item_id:
            msg = "work_item_id cannot be empty"
            raise QueueValidationError(msg)

        # Look up pipeline via reverse index
        reverse_index_key = self._reverse_index_key()
        pipeline_coords = await self._redis.hget(reverse_index_key, work_item_id)

        if not pipeline_coords:
            msg = f"Work item {work_item_id} not found in any queue"
            raise QueueItemNotFoundError(msg)

        # Decode if bytes
        if isinstance(pipeline_coords, bytes):
            pipeline_coords = pipeline_coords.decode("utf-8")

        # Parse project_id\x1fboard_id
        parts = pipeline_coords.split("\x1f", maxsplit=1)
        if len(parts) != 2:
            msg = f"Invalid pipeline coordinates: {pipeline_coords}"
            raise QueueItemNotFoundError(msg)
        project_id, board_id = parts

        meta_key = self._metadata_key(project_id, board_id)

        # Get current metadata
        raw_meta = await self._redis.hget(meta_key, work_item_id)
        if not raw_meta:
            msg = f"Work item {work_item_id} metadata not found"
            raise QueueItemNotFoundError(msg)

        # Parse metadata - distinguish corruption from valid status
        try:
            meta_str = raw_meta.decode("utf-8") if isinstance(raw_meta, bytes) else raw_meta
            metadata = json.loads(meta_str)
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as e:
            # Metadata is corrupted (not a simple absence)
            msg = f"Work item {work_item_id} has corrupted metadata"
            logger.error(
                msg,
                extra={
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "board_id": board_id,
                    "error": str(e),
                    "raw_meta_type": type(raw_meta).__name__,
                },
                exc_info=True,
            )
            raise InvalidQueueStateError(msg) from e

        # Check current status
        current_status = metadata.get("status")
        if not current_status:
            msg = f"Work item {work_item_id} has missing status in metadata"
            logger.error(
                msg,
                extra={
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "board_id": board_id,
                    "metadata": metadata,
                },
            )
            raise InvalidQueueStateError(msg)

        if current_status == QueueStatus.ACTIVE.value:
            msg = f"Work item {work_item_id} is already marked active"
            raise InvalidQueueStateError(msg)

        # Validate status is valid before updating
        try:
            QueueStatus(current_status)
        except ValueError as e:
            msg = f"Work item {work_item_id} has invalid status '{current_status}'"
            logger.error(
                msg,
                extra={
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "board_id": board_id,
                    "status": current_status,
                },
            )
            raise InvalidQueueStateError(msg) from e

        # Update status to ACTIVE
        metadata["status"] = QueueStatus.ACTIVE.value
        await self._redis.hset(meta_key, work_item_id, json.dumps(metadata))

    async def remove_from_queue(self, work_item_id: str) -> bool:
        """Remove a work item from the queue.

        Args:
            work_item_id: Work item to remove

        Returns:
            bool: True if removed, False if not in queue

        Raises:
            QueueValidationError: Invalid work_item_id
        """
        if not work_item_id:
            msg = "work_item_id cannot be empty"
            raise QueueValidationError(msg)

        # Look up pipeline via reverse index
        reverse_index_key = self._reverse_index_key()
        pipeline_coords = await self._redis.hget(reverse_index_key, work_item_id)

        if not pipeline_coords:
            return False

        # Decode if bytes
        if isinstance(pipeline_coords, bytes):
            pipeline_coords = pipeline_coords.decode("utf-8")

        # Parse project_id\x1fboard_id
        parts = pipeline_coords.split("\x1f", maxsplit=1)
        if len(parts) != 2:
            return False
        project_id, board_id = parts

        queue_key = self._queue_key(project_id, board_id)
        meta_key = self._metadata_key(project_id, board_id)

        # Atomically remove from sorted set, metadata, and reverse index
        pipe = self._redis.pipeline(transaction=True)
        pipe.zrem(queue_key, work_item_id)
        pipe.hdel(meta_key, work_item_id)
        pipe.hdel(reverse_index_key, work_item_id)
        results = await pipe.execute()
        removed = results[0]

        if removed:

            # Emit event
            self._emit_event(
                QueueItemRemovedEvent(
                    type="queue.item_removed",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="redis_pipeline_queue_service",
                    queue_name=f"{project_id}:{board_id}",
                    item_id=work_item_id,
                    project_id=project_id,
                )
            )
            return True

        return False

    async def get_next_waiting_item(self, project_id: str, board_id: str) -> PipelineQueueEntry | None:
        """Get next waiting item from queue.

        Returns the waiting item with lowest position_in_column from the queue.
        Callers are responsible for calling sync_queue_with_board explicitly
        before this method to ensure the queue matches board state.

        Corrupted items are skipped to prevent double-execution of ACTIVE items.

        Args:
            project_id: Project identifier
            board_id: Board identifier

        Returns:
            PipelineQueueEntry with lowest position (highest priority),
            or None if no waiting items

        Raises:
            QueueValidationError: Invalid parameters
        """
        if not project_id:
            msg = "project_id cannot be empty"
            raise QueueValidationError(msg)
        if not board_id:
            msg = "board_id cannot be empty"
            raise QueueValidationError(msg)

        queue_key = self._queue_key(project_id, board_id)
        meta_key = self._metadata_key(project_id, board_id)

        # Get all items from sorted set (lowest score first)
        items = await self._redis.zrange(queue_key, 0, -1, withscores=True)

        for work_item_id, score in items:
            # Decode if bytes
            if isinstance(work_item_id, bytes):
                work_item_id = work_item_id.decode("utf-8")

            # Get metadata
            raw_meta = await self._redis.hget(meta_key, work_item_id)
            if not raw_meta:
                # Metadata missing - emit corruption event and skip (don't return)
                self._emit_event(
                    QueueMetadataCorruptionEvent(
                        type="queue.metadata_corruption",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="redis_pipeline_queue_service",
                        queue_name=f"{project_id}:{board_id}",
                        work_item_id=work_item_id,
                        error_details="Metadata hash not found",
                        project_id=project_id,
                    )
                )
                # Skip corrupted item - continue to next
                logger.warning(
                    f"Skipping {work_item_id} in queue {project_id}/{board_id}: metadata missing",
                    extra={
                        "work_item_id": work_item_id,
                        "project_id": project_id,
                        "board_id": board_id,
                    },
                )
                continue

            try:
                meta_str = raw_meta.decode("utf-8") if isinstance(raw_meta, bytes) else raw_meta
                metadata = json.loads(meta_str)
            except Exception as e:
                # Metadata corrupt - emit event and skip (don't return)
                self._emit_event(
                    QueueMetadataCorruptionEvent(
                        type="queue.metadata_corruption",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="redis_pipeline_queue_service",
                        queue_name=f"{project_id}:{board_id}",
                        work_item_id=work_item_id,
                        error_details=f"Failed to parse metadata: {type(e).__name__}: {e!s}",
                        project_id=project_id,
                    )
                )
                # Skip corrupted item - continue to next
                logger.warning(
                    f"Skipping {work_item_id} in queue {project_id}/{board_id}: metadata corrupted ({type(e).__name__})",
                    extra={
                        "work_item_id": work_item_id,
                        "project_id": project_id,
                        "board_id": board_id,
                    },
                )
                continue

            # Check if waiting
            if metadata.get("status") == QueueStatus.WAITING.value:
                # Found next waiting item
                try:
                    return self._reconstruct_entry(
                        project_id, board_id, work_item_id, int(score), metadata
                    )
                except ValueError as e:
                    # Status is invalid - emit corruption event and skip
                    self._emit_event(
                        QueueMetadataCorruptionEvent(
                            type="queue.metadata_corruption",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="redis_pipeline_queue_service",
                            queue_name=f"{project_id}:{board_id}",
                            work_item_id=work_item_id,
                            error_details=f"Invalid status value: {metadata.get('status')}",
                            project_id=project_id,
                        )
                    )
                    logger.warning(
                        f"Skipping {work_item_id} in queue {project_id}/{board_id}: {str(e)}",
                        extra={
                            "work_item_id": work_item_id,
                            "project_id": project_id,
                            "board_id": board_id,
                        },
                    )
                    continue

        return None

    async def get_queue_entries(self, project_id: str, board_id: str) -> list[PipelineQueueEntry]:
        """Get all queue entries for a pipeline.

        Returns all entries (both WAITING and ACTIVE), sorted by position_in_column
        in ascending order (lowest position = highest priority).

        Corrupted entries are skipped to prevent returning entries with
        incorrect status (e.g., ACTIVE entries defaulting to WAITING).

        Args:
            project_id: Project identifier
            board_id: Board identifier

        Returns:
            List of PipelineQueueEntry sorted by position ascending

        Raises:
            QueueValidationError: Invalid parameters
        """
        if not project_id:
            msg = "project_id cannot be empty"
            raise QueueValidationError(msg)
        if not board_id:
            msg = "board_id cannot be empty"
            raise QueueValidationError(msg)

        queue_key = self._queue_key(project_id, board_id)
        meta_key = self._metadata_key(project_id, board_id)

        # Get all items from sorted set
        items = await self._redis.zrange(queue_key, 0, -1, withscores=True)

        entries = []
        for work_item_id, score in items:
            # Decode if bytes
            if isinstance(work_item_id, bytes):
                work_item_id = work_item_id.decode("utf-8")

            # Get metadata
            raw_meta = await self._redis.hget(meta_key, work_item_id)

            if not raw_meta:
                # Metadata missing - emit corruption event and skip (don't include)
                self._emit_event(
                    QueueMetadataCorruptionEvent(
                        type="queue.metadata_corruption",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="redis_pipeline_queue_service",
                        queue_name=f"{project_id}:{board_id}",
                        work_item_id=work_item_id,
                        error_details="Metadata hash not found",
                        project_id=project_id,
                    )
                )
                logger.warning(
                    f"Skipping {work_item_id} in queue {project_id}/{board_id}: metadata missing",
                    extra={
                        "work_item_id": work_item_id,
                        "project_id": project_id,
                        "board_id": board_id,
                    },
                )
                continue

            try:
                meta_str = raw_meta.decode("utf-8") if isinstance(raw_meta, bytes) else raw_meta
                metadata = json.loads(meta_str)
            except Exception as e:
                # Metadata corrupt - emit event and skip (don't include)
                self._emit_event(
                    QueueMetadataCorruptionEvent(
                        type="queue.metadata_corruption",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="redis_pipeline_queue_service",
                        queue_name=f"{project_id}:{board_id}",
                        work_item_id=work_item_id,
                        error_details=f"Failed to parse metadata: {type(e).__name__}: {e!s}",
                        project_id=project_id,
                    )
                )
                logger.warning(
                    f"Skipping {work_item_id} in queue {project_id}/{board_id}: metadata corrupted ({type(e).__name__})",
                    extra={
                        "work_item_id": work_item_id,
                        "project_id": project_id,
                        "board_id": board_id,
                    },
                )
                continue

            try:
                entry = self._reconstruct_entry(
                    project_id, board_id, work_item_id, int(score), metadata
                )
                entries.append(entry)
            except ValueError as e:
                # Status is invalid - emit corruption event and skip
                self._emit_event(
                    QueueMetadataCorruptionEvent(
                        type="queue.metadata_corruption",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="redis_pipeline_queue_service",
                        queue_name=f"{project_id}:{board_id}",
                        work_item_id=work_item_id,
                        error_details=f"Invalid status value: {metadata.get('status')}",
                        project_id=project_id,
                    )
                )
                logger.warning(
                    f"Skipping {work_item_id} in queue {project_id}/{board_id}: {str(e)}",
                    extra={
                        "work_item_id": work_item_id,
                        "project_id": project_id,
                        "board_id": board_id,
                    },
                )
                continue

        return entries

    async def sync_queue_with_board(self, project_id: str, board_id: str, column: str) -> None:
        """Synchronize queue with current board column state.

        Performs three operations:
        1. Removes entries for items no longer in column
        2. Adds entries for newly discovered items in column
        3. Updates position and timestamp for existing entries

        Gracefully handles exceptions without raising, matching InMemoryQueueService.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            column: Board column name to sync with

        Raises:
            QueueValidationError: Invalid parameters
        """
        if not project_id:
            msg = "project_id cannot be empty"
            raise QueueValidationError(msg)
        if not board_id:
            msg = "board_id cannot be empty"
            raise QueueValidationError(msg)
        if not column:
            msg = "column cannot be empty"
            raise QueueValidationError(msg)

        try:
            # Get current board state
            board = await self._board_service.get_board(project_id, board_id)

            # Find the target column
            target_column = None
            for col in board.columns:
                if col.name == column:
                    target_column = col
                    break

            if not target_column:
                # Column not found - log but continue gracefully
                logger.warning(
                    f"Column {column} not found in board {project_id}/{board_id}",
                    extra={
                        "project_id": project_id,
                        "board_id": board_id,
                        "column": column,
                    },
                )
                return

            queue_key = self._queue_key(project_id, board_id)
            meta_key = self._metadata_key(project_id, board_id)
            reverse_index_key = self._reverse_index_key()

            # Get items currently in queue
            queue_items = await self._redis.zrange(queue_key, 0, -1)
            queue_item_ids = {
                item.decode("utf-8") if isinstance(item, bytes) else item for item in queue_items
            }

            # Get items in column
            items_in_column = set(target_column.work_item_ids)

            now = datetime.now(UTC)

            # Step 1: Remove items no longer in column (atomic per item)
            items_to_remove = queue_item_ids - items_in_column
            if items_to_remove:
                pipe = self._redis.pipeline(transaction=True)
                for item_id in items_to_remove:
                    pipe.zrem(queue_key, item_id)
                    pipe.hdel(meta_key, item_id)
                    pipe.hdel(reverse_index_key, item_id)
                await pipe.execute()

            # Step 2 & 3: Add/update items in column
            for position, work_item_id in enumerate(target_column.work_item_ids):
                raw_meta = await self._redis.hget(meta_key, work_item_id)

                if work_item_id in queue_item_ids:
                    # Item exists - update position and timestamp
                    if raw_meta:
                        try:
                            meta_str = raw_meta.decode("utf-8") if isinstance(raw_meta, bytes) else raw_meta
                            metadata = json.loads(meta_str)
                            old_position = int(
                                await self._redis.zscore(queue_key, work_item_id) or 0
                            )
                        except Exception as e:
                            # Metadata corrupt - emit corruption event and skip update
                            self._emit_event(
                                QueueMetadataCorruptionEvent(
                                    type="queue.metadata_corruption",
                                    timestamp=now.isoformat(),
                                    source="redis_pipeline_queue_service",
                                    queue_name=f"{project_id}:{board_id}",
                                    work_item_id=work_item_id,
                                    error_details=f"Failed to parse metadata during sync: {type(e).__name__}: {e!s}",
                                    project_id=project_id,
                                )
                            )
                            logger.warning(
                                f"Skipping position update for {work_item_id} in queue {project_id}/{board_id}: metadata corrupted ({type(e).__name__})",
                                extra={
                                    "work_item_id": work_item_id,
                                    "project_id": project_id,
                                    "board_id": board_id,
                                },
                            )
                            continue
                    else:
                        # Metadata missing - emit corruption event and skip update
                        self._emit_event(
                            QueueMetadataCorruptionEvent(
                                type="queue.metadata_corruption",
                                timestamp=now.isoformat(),
                                source="redis_pipeline_queue_service",
                                queue_name=f"{project_id}:{board_id}",
                                work_item_id=work_item_id,
                                error_details="Metadata hash not found during sync",
                                project_id=project_id,
                            )
                        )
                        logger.warning(
                            f"Skipping position update for {work_item_id} in queue {project_id}/{board_id}: metadata missing",
                            extra={
                                "work_item_id": work_item_id,
                                "project_id": project_id,
                                "board_id": board_id,
                            },
                        )
                        continue

                    # Update position and timestamp (atomically)
                    metadata["last_position_check"] = now.isoformat()
                    pipe = self._redis.pipeline(transaction=True)
                    pipe.zadd(queue_key, {work_item_id: float(position)})
                    pipe.hset(meta_key, work_item_id, json.dumps(metadata))
                    await pipe.execute()

                    # Emit position change event if position changed
                    if old_position != position:
                        self._emit_event(
                            QueuePositionChangedEvent(
                                type="queue.position_changed",
                                timestamp=now.isoformat(),
                                source="redis_pipeline_queue_service",
                                queue_name=f"{project_id}:{board_id}",
                                item_id=work_item_id,
                                old_position=old_position,
                                new_position=position,
                                project_id=project_id,
                            )
                        )
                else:
                    # New item - add to queue (atomically)
                    metadata = {
                        "status": QueueStatus.WAITING.value,
                        "queued_at": now.isoformat(),
                        "last_position_check": now.isoformat(),
                    }
                    pipeline_coords = f"{project_id}\x1f{board_id}"
                    pipe = self._redis.pipeline(transaction=True)
                    pipe.zadd(queue_key, {work_item_id: float(position)})
                    pipe.hset(meta_key, work_item_id, json.dumps(metadata))
                    pipe.hset(reverse_index_key, work_item_id, pipeline_coords)
                    pipe.sadd(self._pipeline_registry_key(), pipeline_coords)
                    await pipe.execute()

        except Exception as e:
            # Graceful degradation: log error but don't fail
            logger.error(
                f"Failed to sync queue with board for {project_id}/{board_id}/{column}. "
                f"Queue will remain in current state until next sync attempt.",
                exc_info=True,
                extra={
                    "project_id": project_id,
                    "board_id": board_id,
                    "column": column,
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_PIPELINE_LOCK_ERROR,
                },
            )

    def _reconstruct_entry(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        position: int,
        metadata: dict,
    ) -> PipelineQueueEntry:
        """Reconstruct a PipelineQueueEntry from Redis data.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            work_item_id: Work item identifier
            position: Position score from sorted set
            metadata: Metadata dict from hash (must contain valid "status" key)

        Returns:
            PipelineQueueEntry instance

        Raises:
            ValueError: If status is missing or invalid
        """
        try:
            queued_at_str = metadata.get("queued_at", datetime.now(UTC).isoformat())
            queued_at = (
                datetime.fromisoformat(queued_at_str)
                if isinstance(queued_at_str, str)
                else queued_at_str
            )
        except Exception:
            queued_at = datetime.now(UTC)

        try:
            last_check_str = metadata.get("last_position_check", datetime.now(UTC).isoformat())
            last_position_check = (
                datetime.fromisoformat(last_check_str)
                if isinstance(last_check_str, str)
                else last_check_str
            )
        except Exception:
            last_position_check = datetime.now(UTC)

        # Status is required and must be valid - don't silently default to WAITING
        status_str = metadata.get("status")
        if not status_str:
            msg = f"Work item {work_item_id} has missing status in metadata"
            logger.error(
                msg,
                extra={
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "board_id": board_id,
                    "metadata": metadata,
                },
            )
            raise ValueError(msg)

        try:
            status = QueueStatus(status_str)
        except ValueError as e:
            msg = f"Work item {work_item_id} has invalid status '{status_str}' in metadata"
            logger.error(
                msg,
                extra={
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "board_id": board_id,
                    "status": status_str,
                },
            )
            raise ValueError(msg) from e

        return PipelineQueueEntry(
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
            position_in_column=NonNegativeInt(position),
            status=status,
            queued_at=queued_at,
            last_position_check=last_position_check,
        )

    def _emit_event(self, event) -> None:
        """Emit an event via IEventEmitter with error handling.

        Wraps emission in try/except to prevent event publishing failures
        from crashing queue operations.

        Args:
            event: Domain event to emit
        """
        try:
            self._event_emitter.emit(event)
        except Exception:
            logger.error(
                f"Failed to emit event {type(event).__name__}",
                exc_info=True,
            )
