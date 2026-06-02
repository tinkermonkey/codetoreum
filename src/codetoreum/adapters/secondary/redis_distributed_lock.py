"""RedisDistributedLock — production distributed lock primitive.

Uses Redis SET NX EX for atomic acquire/release. Emits PipelineLockAcquiredEvent
and PipelineLockReleasedEvent via an injected event bus.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from codetoreum.domain.events.lock_events import (
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
)
from codetoreum.ports.output.distributed_lock import (
    AcquireResult,
    AcquireStatus,
    IDistributedLock,
    LockHolder,
    ReleaseResult,
    ReleaseReason,
)

if TYPE_CHECKING:
    from codetoreum.infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)

_LOCK_TTL_SECONDS = 60 * 60 * 2  # 2-hour safety TTL
_KEY_PREFIX = "codetoreum:lock"


class RedisDistributedLock(IDistributedLock):
    """Redis-backed distributed lock primitive using SET NX EX."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        event_bus: "EventBus | None" = None,
        lock_ttl_seconds: int = _LOCK_TTL_SECONDS,
        key_prefix: str = _KEY_PREFIX,
    ) -> None:
        self._redis = redis_client
        self._event_bus = event_bus
        self._lock_ttl_seconds = lock_ttl_seconds
        self._key_prefix = key_prefix

    def _lock_key(self, lock_key: str) -> str:
        """Get Redis key for a lock."""
        return f"{self._key_prefix}:{lock_key}"

    def _holder_data_key(self, lock_key: str) -> str:
        """Get Redis key for holder metadata hash."""
        return f"{self._key_prefix}:holder:{lock_key}"

    async def try_acquire(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int = _LOCK_TTL_SECONDS,
        holder_metadata: dict[str, str] | None = None,
    ) -> AcquireResult:
        """Attempt to acquire the lock.

        Uses Redis SET NX EX for atomic acquire. Also stores holder metadata
        in a sibling hash for diagnostics.
        """
        redis_key = self._lock_key(lock_key)
        holder_data_key = self._holder_data_key(lock_key)
        now = datetime.now(UTC)

        # Check if lock is already held
        existing_holder = await self._redis.get(redis_key)
        if existing_holder is not None:
            try:
                existing_holder_id = existing_holder.decode("utf-8") if isinstance(existing_holder, bytes) else existing_holder
                if existing_holder_id == holder_id:
                    # Same holder re-entering (reentrant)
                    return AcquireResult(
                        status=AcquireStatus.ALREADY_HELD_BY_SELF,
                        lock_key=lock_key,
                        holder_id=holder_id,
                        acquired_at=None,
                    )
                else:
                    # Different holder holds the lock
                    return AcquireResult(
                        status=AcquireStatus.ALREADY_HELD_BY_OTHER,
                        lock_key=lock_key,
                        holder_id=existing_holder_id,
                        acquired_at=None,
                    )
            except Exception:
                logger.warning(
                    f"Failed to parse existing lock holder for {lock_key}",
                    exc_info=True,
                )
                # Treat as held by unknown
                return AcquireResult(
                    status=AcquireStatus.ALREADY_HELD_BY_OTHER,
                    lock_key=lock_key,
                    holder_id="unknown",
                    acquired_at=None,
                )

        # Try to acquire the lock atomically
        acquired = await self._redis.set(
            redis_key,
            holder_id,
            nx=True,
            ex=ttl_seconds,
        )

        if acquired:
            # Store holder metadata in sibling hash
            if holder_metadata:
                await self._redis.hset(
                    holder_data_key,
                    mapping=holder_metadata,
                )
                # Set same TTL on metadata hash
                await self._redis.expire(holder_data_key, ttl_seconds)

            # Emit event via event bus if available
            if self._event_bus:
                try:
                    event = PipelineLockAcquiredEvent(
                        type="lock.acquired",
                        timestamp=now.isoformat(),
                        source="redis_distributed_lock",
                        lock_key=lock_key,
                        holder_id=holder_id,
                        acquired_at=now,
                        holder_metadata=holder_metadata or {},
                    )
                    await self._event_bus.publish(event)
                except Exception:
                    logger.error(
                        f"Failed to publish PipelineLockAcquiredEvent for {lock_key}",
                        exc_info=True,
                    )

            return AcquireResult(
                status=AcquireStatus.ACQUIRED,
                lock_key=lock_key,
                holder_id=holder_id,
                acquired_at=now,
            )
        else:
            # Lock is held by someone else; return holder info if available
            existing = await self._redis.get(redis_key)
            holder_id_str = existing.decode("utf-8") if isinstance(existing, bytes) else str(existing)
            return AcquireResult(
                status=AcquireStatus.ALREADY_HELD_BY_OTHER,
                lock_key=lock_key,
                holder_id=holder_id_str,
                acquired_at=None,
            )

    async def release(
        self,
        lock_key: str,
        holder_id: str,
    ) -> ReleaseResult:
        """Release the lock if held by the given holder.

        Idempotent — returns success=False if not held or held by different holder.
        """
        redis_key = self._lock_key(lock_key)
        holder_data_key = self._holder_data_key(lock_key)

        # Check who holds the lock
        existing = await self._redis.get(redis_key)
        if existing is None:
            # Lock not held
            return ReleaseResult(
                released=False,
                reason=ReleaseReason.NOT_HELD,
                lock_key=lock_key,
            )

        existing_holder_id = existing.decode("utf-8") if isinstance(existing, bytes) else str(existing)
        if existing_holder_id != holder_id:
            # Held by different holder
            return ReleaseResult(
                released=False,
                reason=ReleaseReason.HELD_BY_OTHER,
                lock_key=lock_key,
            )

        # Release the lock
        try:
            await self._redis.delete(redis_key)
            await self._redis.delete(holder_data_key)

            # Emit event via event bus if available
            if self._event_bus:
                try:
                    event = PipelineLockReleasedEvent(
                        type="lock.released",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="redis_distributed_lock",
                        lock_key=lock_key,
                        released_holder_id=holder_id,
                        released_at=datetime.now(UTC),
                    )
                    await self._event_bus.publish(event)
                except Exception:
                    logger.error(
                        f"Failed to publish PipelineLockReleasedEvent for {lock_key}",
                        exc_info=True,
                    )

            return ReleaseResult(
                released=True,
                reason=None,
                lock_key=lock_key,
            )
        except Exception:
            logger.error(
                f"Failed to release lock {lock_key} for holder {holder_id}",
                exc_info=True,
            )
            raise

    async def get_holder(self, lock_key: str) -> LockHolder | None:
        """Return the current holder, or None if unlocked."""
        redis_key = self._lock_key(lock_key)
        holder_data_key = self._holder_data_key(lock_key)

        holder_id = await self._redis.get(redis_key)
        if holder_id is None:
            return None

        holder_id_str = holder_id.decode("utf-8") if isinstance(holder_id, bytes) else str(holder_id)

        # Get TTL
        ttl = await self._redis.ttl(redis_key)
        if ttl is None or ttl < 0:
            ttl = self._lock_ttl_seconds

        # Get metadata
        metadata = await self._redis.hgetall(holder_data_key)
        metadata_dict = {}
        for k, v in metadata.items():
            k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            v_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
            metadata_dict[k_str] = v_str

        # Estimate acquired_at and expires_at
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
        acquired_at = expires_at - timedelta(seconds=self._lock_ttl_seconds)

        return LockHolder(
            lock_key=lock_key,
            holder_id=holder_id_str,
            acquired_at=acquired_at,
            ttl_seconds=ttl,
            expires_at=expires_at,
            holder_metadata=metadata_dict,
        )

    async def get_all_holders(self) -> list[LockHolder]:
        """Return all currently held locks across all keys."""
        cursor = 0
        pattern = f"{self._key_prefix}:*"
        holders = []

        # Scan all keys matching pattern
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode("utf-8")

                # Skip metadata keys, only process lock keys
                if ":holder:" in key:
                    continue

                # Extract lock_key from Redis key
                if key.startswith(self._key_prefix + ":"):
                    lock_key = key[len(self._key_prefix) + 1 :]
                else:
                    continue

                holder = await self.get_holder(lock_key)
                if holder is not None:
                    holders.append(holder)

            if cursor == 0:
                break

        return holders

    async def renew(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int,
    ) -> bool:
        """Extend the TTL on a held lock."""
        redis_key = self._lock_key(lock_key)

        # Verify the holder
        existing = await self._redis.get(redis_key)
        if existing is None:
            return False

        existing_holder_id = existing.decode("utf-8") if isinstance(existing, bytes) else str(existing)
        if existing_holder_id != holder_id:
            return False

        # Update TTL
        await self._redis.expire(redis_key, ttl_seconds)
        holder_data_key = self._holder_data_key(lock_key)
        await self._redis.expire(holder_data_key, ttl_seconds)

        return True
