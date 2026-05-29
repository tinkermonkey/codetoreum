"""RedisPipelineLockService — persistence-grade IPipelineLockService.

Replaces ``InMemoryLockService`` for production deployments where lock state
MUST survive server restart and MUST coordinate across multiple Codetoreum
instances. The in-memory implementation remains the simulation default.

Wire format
-----------
For each ``(project_id, board_id)`` pair the adapter uses two keys:

- ``codetoreum:pipeline:lock:{project_id}:{board_id}`` — a JSON-encoded
  :class:`LockHolder` record stored with ``SET ... NX`` and a generous TTL
  (default 2 hours) as a safety net against orphan locks from instances
  that exited uncleanly.
- ``codetoreum:pipeline:queue:{project_id}:{board_id}`` — a Sorted Set whose
  members are ``work_item_id``s and whose scores are board positions
  (lowest score wins). ``ZADD ... NX`` enqueues; ``ZPOPMIN`` pops the head.

Both operations are atomic against the Redis server. The acquire/release
sequence uses no Lua scripting today; single-shot ``SET NX`` + ``ZPOPMIN``
is sufficient because the adapter assumes one logical caller per board per
moment (work items are dispatched serially within an instance by
BoardColumnEventHandler). If multi-instance concurrent acquisition becomes
common, replace the multi-step paths with Lua scripts.

Resilience
----------
INV-11: no retry/circuit-breaker logic in this adapter. Redis call failures
propagate; the resilience decorator (when one is added for this slot) will
wrap them.

Events
------
The adapter emits ``LockAcquiredEvent`` and ``LockReleasedEvent`` on
acquisition and release respectively via an injected ``EventBus``. Stale
lock detection and watchdog-driven ``StaleLockDetectedEvent`` are NOT
implemented in this initial cut — that requires a periodic task that
scans ``get_all_locks()`` and is best owned by a separate watchdog
service. The TTL on the lock key is the only stale-protection mechanism
today.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from codetoreum.application.pipeline_lock_service import (
    IQueuedPipelineLockService,
    LockAcquisitionResult,
    LockReleaseResult,
    LockStatus,
    PipelineQueueState,
    QueueEntry,
)
from codetoreum.domain.events.lock_events import LockAcquiredEvent, LockReleasedEvent
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.pipeline_lock_service import (
    IPipelineLockService,
    PipelineLock,
)

if TYPE_CHECKING:
    from codetoreum.infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)

_LOCK_TTL_SECONDS = 60 * 60 * 2  # 2-hour safety TTL on the lock key itself.
_KEY_PREFIX = "codetoreum:pipeline"


@dataclass
class LockHolder:
    """Wire-format record stored at the lock key."""

    work_item_id: str
    acquired_at: str  # ISO 8601 string

    def to_json(self) -> str:
        return json.dumps({"work_item_id": self.work_item_id, "acquired_at": self.acquired_at})

    @classmethod
    def from_json(cls, raw: str | bytes) -> LockHolder:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return cls(work_item_id=data["work_item_id"], acquired_at=data["acquired_at"])


@dataclass
class _MinimalEventEmitterImpl:
    """In-process IEventEmitter implementation used to satisfy the lock port.

    The lock port inherits from IEventEmitter for legacy reasons. The Redis
    adapter delivers its lock events through the injected EventBus, not
    through this emitter — but the IEventEmitter interface still needs
    methods. Subscribers attached here run synchronously when a domain
    event is emitted via ``emit()``.
    """

    handlers: dict[str, list] = field(default_factory=dict)

    def on(self, event_type: str, handler) -> None:  # type: ignore[no-untyped-def]
        self.handlers.setdefault(event_type, []).append(handler)

    def off(self, event_type: str, handler) -> None:  # type: ignore[no-untyped-def]
        bucket = self.handlers.get(event_type, [])
        try:
            bucket.remove(handler)
        except ValueError:
            # Subscriber was not registered; per IEventEmitter contract this
            # should raise ValueError. Keep behavior parity.
            raise

    def emit(self, event) -> None:  # type: ignore[no-untyped-def]
        for h in self.handlers.get(getattr(event, "type", ""), []):
            try:
                h(event)
            except Exception:
                logger.error(
                    f"Handler {h} failed for event type {getattr(event, 'type', None)}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )


class RedisPipelineLockService(IPipelineLockService, IQueuedPipelineLockService):
    """Redis-backed pipeline lock service with sorted-set queueing."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        event_bus: EventBus | None = None,
        lock_ttl_seconds: int = _LOCK_TTL_SECONDS,
        key_prefix: str = _KEY_PREFIX,
    ) -> None:
        self._redis = redis_client
        self._event_bus = event_bus
        self._lock_ttl_seconds = lock_ttl_seconds
        self._key_prefix = key_prefix
        self._emitter = _MinimalEventEmitterImpl()

    # ----- IEventEmitter -----
    def on(self, event_type: str, handler) -> None:  # type: ignore[no-untyped-def]
        self._emitter.on(event_type, handler)

    def off(self, event_type: str, handler) -> None:  # type: ignore[no-untyped-def]
        self._emitter.off(event_type, handler)

    def emit(self, event) -> None:  # type: ignore[no-untyped-def]
        self._emitter.emit(event)

    # ----- Key helpers -----
    def _lock_key(self, project_id: str, board_id: str) -> str:
        return f"{self._key_prefix}:lock:{project_id}:{board_id}"

    def _queue_key(self, project_id: str, board_id: str) -> str:
        return f"{self._key_prefix}:queue:{project_id}:{board_id}"

    def _scoped_key(self, project_id: str, board_id: str) -> str:
        """Stable identifier used by ``get_all_lock_states()`` callers."""
        return f"{project_id}:{board_id}"

    # ----- IQueuedPipelineLockService -----
    async def try_acquire_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        board_position: int,
    ) -> LockAcquisitionResult:
        lock_key = self._lock_key(project_id, board_id)
        queue_key = self._queue_key(project_id, board_id)
        now = datetime.now(UTC)

        # First, check whether THIS work item already holds the lock.
        raw_holder = await self._redis.get(lock_key)
        if raw_holder is not None:
            try:
                existing = LockHolder.from_json(raw_holder)
            except Exception:
                logger.warning(
                    f"Corrupt lock holder JSON for {lock_key}; treating as not held",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )
                existing = None
            if existing and existing.work_item_id == work_item_id:
                return LockAcquisitionResult(
                    status=LockStatus.ALREADY_HELD,
                    work_item_id=work_item_id,
                    queue_position=None,
                    queue_length=await self._redis.zcard(queue_key),
                )

        # Try SETNX with TTL. SET key value NX EX ttl is atomic.
        holder = LockHolder(work_item_id=work_item_id, acquired_at=now.isoformat())
        acquired = await self._redis.set(
            lock_key,
            holder.to_json(),
            nx=True,
            ex=self._lock_ttl_seconds,
        )
        if acquired:
            await self._publish_lock_acquired(project_id, board_id, work_item_id, now)
            return LockAcquisitionResult(
                status=LockStatus.ACQUIRED,
                work_item_id=work_item_id,
                queue_position=None,
                queue_length=await self._redis.zcard(queue_key),
            )

        # Lock is held by another; enqueue.
        # ZADD NX: only add if not already in queue.
        await self._redis.zadd(queue_key, {work_item_id: float(board_position)}, nx=True)
        # Compute the position by rank.
        rank = await self._redis.zrank(queue_key, work_item_id)
        queue_length = await self._redis.zcard(queue_key)
        return LockAcquisitionResult(
            status=LockStatus.QUEUED,
            work_item_id=work_item_id,
            queue_position=rank if rank is not None else None,
            queue_length=queue_length,
        )

    async def release_lock(self, project_id: str, board_id: str, work_item_id: str) -> LockReleaseResult:
        lock_key = self._lock_key(project_id, board_id)
        queue_key = self._queue_key(project_id, board_id)

        raw_holder = await self._redis.get(lock_key)
        if raw_holder is None:
            raise ValueError(f"Cannot release lock for {project_id}:{board_id}: no lock held")
        existing = LockHolder.from_json(raw_holder)
        if existing.work_item_id != work_item_id:
            raise ValueError(f"Cannot release lock for {work_item_id}: held by {existing.work_item_id}")

        # Delete the lock.
        await self._redis.delete(lock_key)
        await self._publish_lock_released(project_id, board_id, work_item_id)

        # Pop the queue head (atomic).
        popped = await self._redis.zpopmin(queue_key, count=1)
        next_work_item_id: str | None = None
        if popped:
            member, _score = popped[0]
            if isinstance(member, bytes):
                member = member.decode("utf-8")
            next_work_item_id = member
            # Grant the lock to the popped work item.
            now = datetime.now(UTC)
            new_holder = LockHolder(work_item_id=next_work_item_id, acquired_at=now.isoformat())
            await self._redis.set(
                lock_key,
                new_holder.to_json(),
                nx=True,
                ex=self._lock_ttl_seconds,
            )
            await self._publish_lock_acquired(project_id, board_id, next_work_item_id, now)

        return LockReleaseResult(
            released_work_item_id=work_item_id,
            next_work_item_id=next_work_item_id,
            queue_length_after_release=await self._redis.zcard(queue_key),
        )

    async def get_queue_state(self, project_id: str, board_id: str) -> PipelineQueueState:
        lock_key = self._lock_key(project_id, board_id)
        queue_key = self._queue_key(project_id, board_id)

        raw_holder = await self._redis.get(lock_key)
        holder_id: str | None = None
        acquired_at: datetime | None = None
        if raw_holder is not None:
            try:
                h = LockHolder.from_json(raw_holder)
                holder_id = h.work_item_id
                acquired_at = datetime.fromisoformat(h.acquired_at)
            except Exception:
                logger.warning(
                    f"Corrupt lock holder JSON for {lock_key}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )

        members = await self._redis.zrange(queue_key, 0, -1, withscores=True)
        queue: list[QueueEntry] = []
        for m, s in members:
            if isinstance(m, bytes):
                m = m.decode("utf-8")
            queue.append(QueueEntry(work_item_id=m, board_position=int(s), enqueued_at=datetime.now(UTC)))

        return PipelineQueueState(
            board_id=board_id,
            project_id=project_id,
            lock_holder=holder_id,
            lock_acquired_at=acquired_at,
            queue=queue,
        )

    async def update_queue_positions(
        self,
        project_id: str,
        board_id: str,
        updated_positions: dict[str, int],
    ) -> None:
        queue_key = self._queue_key(project_id, board_id)
        if not updated_positions:
            return
        # ZADD with XX: only update existing members, do not insert new ones.
        # mapping must be {member: score}
        await self._redis.zadd(
            queue_key,
            {wid: float(pos) for wid, pos in updated_positions.items()},
            xx=True,
        )

    # ----- IPipelineLockService -----
    async def get_lock(self, project_id: str, board_id: str) -> PipelineLock | None:
        lock_key = self._lock_key(project_id, board_id)
        raw_holder = await self._redis.get(lock_key)
        if raw_holder is None:
            return None
        h = LockHolder.from_json(raw_holder)
        return PipelineLock(
            project_id=project_id,
            board_id=board_id,
            work_item_id=h.work_item_id,
            locked_by_work_item=h.work_item_id,
            lock_acquired_at=h.acquired_at,
            lock_status="locked",
        )

    async def get_all_locks(self) -> list[PipelineLock]:
        pattern = f"{self._key_prefix}:lock:*"
        # SCAN is preferred over KEYS in production.
        locks: list[PipelineLock] = []
        async for key in self._redis.scan_iter(match=pattern):
            if isinstance(key, bytes):
                key_str = key.decode("utf-8")
            else:
                key_str = key
            # Format: codetoreum:pipeline:lock:{project_id}:{board_id}
            parts = key_str.split(":")
            if len(parts) < 5:
                continue
            project_id = parts[3]
            board_id = parts[4]
            raw_holder = await self._redis.get(key_str)
            if raw_holder is None:
                continue
            h = LockHolder.from_json(raw_holder)
            locks.append(
                PipelineLock(
                    project_id=project_id,
                    board_id=board_id,
                    work_item_id=h.work_item_id,
                    locked_by_work_item=h.work_item_id,
                    lock_acquired_at=h.acquired_at,
                    lock_status="locked",
                )
            )
        return locks

    async def get_all_lock_states(self) -> dict[str, PipelineQueueState]:
        pattern = f"{self._key_prefix}:lock:*"
        out: dict[str, PipelineQueueState] = {}
        async for key in self._redis.scan_iter(match=pattern):
            if isinstance(key, bytes):
                key_str = key.decode("utf-8")
            else:
                key_str = key
            parts = key_str.split(":")
            if len(parts) < 5:
                continue
            project_id = parts[3]
            board_id = parts[4]
            state = await self.get_queue_state(project_id, board_id)
            out[self._scoped_key(project_id, board_id)] = state
        return out

    # ----- Internal: event publishing -----
    async def _publish_lock_acquired(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        acquired_at: datetime,  # kept for symmetry with caller; events do not carry the timestamp directly
    ) -> None:
        if self._event_bus is None:
            return
        try:
            event = LockAcquiredEvent(
                project_id=project_id,
                board_id=board_id,
                work_item_id=work_item_id,
            )
            await self._event_bus.publish(event)
        except Exception:
            logger.error(
                "Failed to publish LockAcquiredEvent",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )

    async def _publish_lock_released(self, project_id: str, board_id: str, work_item_id: str) -> None:
        if self._event_bus is None:
            return
        try:
            event = LockReleasedEvent(
                project_id=project_id,
                board_id=board_id,
                work_item_id=work_item_id,
            )
            await self._event_bus.publish(event)
        except Exception:
            logger.error(
                "Failed to publish LockReleasedEvent",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )


__all__ = ["RedisPipelineLockService", "LockHolder"]
