"""RedisPipelineQueue — production FIFO queue for pipeline coordination.

Uses Redis sorted sets for ordering (by board position) and a sibling hash
for metadata storage. Per the IPipelineQueue port contract, callers are
responsible for emitting WorkItemQueuedEvent and WorkItemDequeuedEvent. This
adapter retains internal event emission for backward compatibility and
diagnostics, which may result in duplicate events if callers follow the
contract — consider deduplication at the event bus level or removal of
adapter-level emission in a future refactor.
"""

import json
import logging
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from codetoreum.domain.events.lock_events import (
    WorkItemDequeuedEvent,
    WorkItemQueuedEvent,
)
from codetoreum.ports.output.pipeline_queue import (
    EnqueueResult,
    IPipelineQueue,
    QueueEntry,
)

if TYPE_CHECKING:
    from codetoreum.infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)

_KEY_PREFIX = "codetoreum:queue"


class RedisPipelineQueue(IPipelineQueue):
    """Redis-backed FIFO queue using sorted sets."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        event_bus: "EventBus | None" = None,
        key_prefix: str = _KEY_PREFIX,
    ) -> None:
        self._redis = redis_client
        self._event_bus = event_bus
        self._key_prefix = key_prefix

    def _queue_key(self, queue_key: str) -> str:
        """Get Redis sorted set key for the queue."""
        return f"{self._key_prefix}:{queue_key}"

    def _metadata_key(self, queue_key: str) -> str:
        """Get Redis hash key for entry metadata."""
        return f"{self._key_prefix}:meta:{queue_key}"

    async def enqueue(
        self,
        queue_key: str,
        entry: QueueEntry,
    ) -> EnqueueResult:
        """Add an entry to the back of the queue.

        Idempotent on (queue_key, entry.work_item_id). Uses sorted set score
        (board_position) for ordering.
        """
        zset_key = self._queue_key(queue_key)
        meta_key = self._metadata_key(queue_key)

        # Check if already in queue
        rank = await self._redis.zrank(zset_key, entry.work_item_id)
        if rank is not None:
            # Already present; return idempotent result
            return EnqueueResult(
                position=rank,
                already_present=True,
            )

        # Add to sorted set (score = board_position, lower scores dequeue first)
        await self._redis.zadd(
            zset_key,
            {entry.work_item_id: float(entry.board_position)},
        )

        # Store metadata in sibling hash
        entry_metadata = {
            "stage_name": entry.stage_name,
            "enqueued_at": entry.enqueued_at.isoformat(),
        }
        # Include additional metadata
        if entry.metadata:
            entry_metadata.update(entry.metadata)

        await self._redis.hset(
            meta_key,
            entry.work_item_id,
            json.dumps(entry_metadata),
        )

        # Get new position
        new_rank = await self._redis.zrank(zset_key, entry.work_item_id)
        position = new_rank if new_rank is not None else 0

        # Emit event
        if self._event_bus:
            try:
                event = WorkItemQueuedEvent(
                    type="workitem.queued",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="redis_pipeline_queue",
                    work_item_id=entry.work_item_id,
                    board_id=entry.metadata.get("board_id", ""),
                    queue_position=position,
                )
                await self._event_bus.publish(event)
            except Exception:
                logger.error(
                    f"Failed to publish WorkItemQueuedEvent for {entry.work_item_id}",
                    exc_info=True,
                )

        return EnqueueResult(
            position=position,
            already_present=False,
        )

    async def peek(self, queue_key: str) -> QueueEntry | None:
        """Return the head entry without removing. None if empty."""
        zset_key = self._queue_key(queue_key)
        meta_key = self._metadata_key(queue_key)

        # Get head item (lowest score)
        items = await self._redis.zrange(zset_key, 0, 0, withscores=True)
        if not items:
            return None

        work_item_id, score = items[0]
        if isinstance(work_item_id, bytes):
            work_item_id = work_item_id.decode("utf-8")

        # Get metadata
        raw_meta = await self._redis.hget(meta_key, work_item_id)
        if raw_meta is None:
            return None

        try:
            meta_str = raw_meta.decode("utf-8") if isinstance(raw_meta, bytes) else raw_meta
            meta_dict = json.loads(meta_str)
        except Exception:
            logger.warning(
                f"Failed to parse metadata for {work_item_id}",
                exc_info=True,
            )
            return None

        metadata = {k: v for k, v in meta_dict.items() if k not in ("stage_name", "enqueued_at")}
        return QueueEntry(
            work_item_id=work_item_id,
            stage_name=meta_dict.get("stage_name", ""),
            board_position=int(score),
            enqueued_at=datetime.fromisoformat(meta_dict.get("enqueued_at", datetime.now(UTC).isoformat())),
            metadata=MappingProxyType(metadata),
        )

    async def pop(self, queue_key: str) -> QueueEntry | None:
        """Atomically remove and return the head entry. None if empty."""
        zset_key = self._queue_key(queue_key)
        meta_key = self._metadata_key(queue_key)

        # Get and remove head
        items = await self._redis.zpopmin(zset_key, count=1)
        if not items:
            return None

        work_item_id, score = items[0]
        if isinstance(work_item_id, bytes):
            work_item_id = work_item_id.decode("utf-8")

        # Get and remove metadata
        raw_meta = await self._redis.hget(meta_key, work_item_id)
        if raw_meta is not None:
            await self._redis.hdel(meta_key, work_item_id)

        # Parse metadata
        meta_dict = {}
        if raw_meta is not None:
            try:
                meta_str = raw_meta.decode("utf-8") if isinstance(raw_meta, bytes) else raw_meta
                meta_dict = json.loads(meta_str)
            except Exception:
                logger.warning(
                    f"Failed to parse metadata for {work_item_id}",
                    exc_info=True,
                )

        # Emit event
        if self._event_bus:
            try:
                board_id = meta_dict.get("board_id", queue_key.split(":")[1] if ":" in queue_key else "")
                event = WorkItemDequeuedEvent(
                    type="workitem.dequeued",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="redis_pipeline_queue",
                    work_item_id=work_item_id,
                    board_id=board_id or "unknown",
                    reason="popped",
                )
                await self._event_bus.publish(event)
            except Exception:
                logger.error(
                    f"Failed to publish WorkItemDequeuedEvent for {work_item_id}",
                    exc_info=True,
                )

        metadata = {k: v for k, v in meta_dict.items() if k not in ("stage_name", "enqueued_at")}
        return QueueEntry(
            work_item_id=work_item_id,
            stage_name=meta_dict.get("stage_name", ""),
            board_position=int(score),
            enqueued_at=datetime.fromisoformat(meta_dict.get("enqueued_at", datetime.now(UTC).isoformat())),
            metadata=MappingProxyType(metadata),
        )

    async def contains(self, queue_key: str, work_item_id: str) -> bool:
        """Check whether a specific work item is in the queue."""
        zset_key = self._queue_key(queue_key)
        rank = await self._redis.zrank(zset_key, work_item_id)
        return rank is not None

    async def remove(self, queue_key: str, work_item_id: str) -> bool:
        """Remove a specific entry by work_item_id. Idempotent."""
        zset_key = self._queue_key(queue_key)
        meta_key = self._metadata_key(queue_key)

        # Check if exists first
        rank = await self._redis.zrank(zset_key, work_item_id)
        if rank is None:
            return False

        # Get metadata before deletion (needed for event emission)
        entry_metadata = await self._redis.hget(meta_key, work_item_id)
        entry_data = {}
        if entry_metadata:
            import json as json_lib
            try:
                if isinstance(entry_metadata, bytes):
                    entry_metadata = entry_metadata.decode("utf-8")
                entry_data = json_lib.loads(entry_metadata)
            except Exception:
                logger.warning(f"Failed to parse metadata for {work_item_id}")

        # Remove from sorted set and metadata
        await self._redis.zrem(zset_key, work_item_id)
        await self._redis.hdel(meta_key, work_item_id)

        # Emit event
        if self._event_bus:
            try:
                board_id = entry_data.get("board_id", queue_key.split(":")[1] if ":" in queue_key else "")
                event = WorkItemDequeuedEvent(
                    type="workitem.dequeued",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="redis_pipeline_queue",
                    work_item_id=work_item_id,
                    board_id=board_id or "unknown",
                    reason="removed",
                )
                await self._event_bus.publish(event)
            except Exception:
                logger.error(
                    f"Failed to publish WorkItemDequeuedEvent for {work_item_id}",
                    exc_info=True,
                )

        return True

    async def length(self, queue_key: str) -> int:
        """Return queue depth."""
        zset_key = self._queue_key(queue_key)
        return await self._redis.zcard(zset_key)

    async def list(self, queue_key: str) -> list[QueueEntry]:
        """Return all entries in FIFO order."""
        zset_key = self._queue_key(queue_key)
        meta_key = self._metadata_key(queue_key)

        items = await self._redis.zrange(zset_key, 0, -1, withscores=True)
        result = []

        for work_item_id, score in items:
            if isinstance(work_item_id, bytes):
                work_item_id = work_item_id.decode("utf-8")

            raw_meta = await self._redis.hget(meta_key, work_item_id)
            meta_dict = {}
            if raw_meta is not None:
                try:
                    meta_str = raw_meta.decode("utf-8") if isinstance(raw_meta, bytes) else raw_meta
                    meta_dict = json.loads(meta_str)
                except Exception:
                    logger.warning(
                        f"Failed to parse metadata for {work_item_id}",
                        exc_info=True,
                    )

            metadata = {k: v for k, v in meta_dict.items() if k not in ("stage_name", "enqueued_at")}
            entry = QueueEntry(
                work_item_id=work_item_id,
                stage_name=meta_dict.get("stage_name", ""),
                board_position=int(score),
                enqueued_at=datetime.fromisoformat(meta_dict.get("enqueued_at", datetime.now(UTC).isoformat())),
                metadata=MappingProxyType(metadata),
            )
            result.append(entry)

        return result

    async def position_of(self, queue_key: str, work_item_id: str) -> int | None:
        """Return 0-indexed position of work_item_id, or None if not present."""
        zset_key = self._queue_key(queue_key)
        rank = await self._redis.zrank(zset_key, work_item_id)
        return rank
