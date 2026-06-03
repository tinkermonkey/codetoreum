"""RedisDistributedLock — production distributed lock primitive.

Uses Redis SET NX EX for atomic acquire/release. Per the IDistributedLock port
contract, callers are responsible for emitting PipelineLockAcquiredEvent and
PipelineLockReleasedEvent. This adapter retains internal event emission for
backward compatibility and diagnostics, which may result in duplicate events
if callers follow the contract — consider deduplication at the event bus level
or removal of adapter-level emission in a future refactor.
"""

import logging
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
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
    ReleaseReason,
    ReleaseResult,
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

    async def _finalize_acquisition(
        self,
        lock_key: str,
        holder_id: str,
        holder_data_key: str,
        ttl_seconds: int,
        holder_metadata: dict[str, str] | None,
        now: datetime,
    ) -> AcquireResult:
        """Finalize a successful lock acquisition.

        Stores holder metadata, emits event, and returns AcquireResult.
        Extracted to eliminate duplication in try_acquire retry path.
        """
        # Store holder metadata in sibling hash, including acquired_at timestamp
        # This ensures we can later retrieve the actual acquisition time even after renewal
        metadata_to_store = holder_metadata.copy() if holder_metadata else {}
        metadata_to_store["acquired_at"] = now.isoformat()

        await self._redis.hset(
            holder_data_key,
            mapping=metadata_to_store,
        )
        # Set same TTL on metadata hash
        await self._redis.expire(holder_data_key, ttl_seconds)

        # Emit event via event bus if available
        if self._event_bus:
            try:
                metadata = holder_metadata or {}
                event = PipelineLockAcquiredEvent(
                    type="pipeline.lock_acquired",
                    timestamp=now.isoformat(),
                    source="redis_distributed_lock",
                    project_id=metadata.get("project_id", ""),
                    work_item_id=holder_id,
                    board_id=metadata.get("board_id", ""),
                    queue_length_at_acquire=int(metadata.get("queue_length_at_acquire", 0)),
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

        # Try to acquire the lock atomically first (SET NX EX)
        acquired = await self._redis.set(
            redis_key,
            holder_id,
            nx=True,
            ex=ttl_seconds,
        )

        if acquired:
            return await self._finalize_acquisition(
                lock_key, holder_id, holder_data_key, ttl_seconds, holder_metadata, now
            )

        # Lock acquisition failed; inspect who holds it
        existing_holder = await self._redis.get(redis_key)
        if existing_holder is None:
            # Lock was released or expired between SET NX check and read.
            # Retry SET NX once since the lock is now free.
            acquired = await self._redis.set(
                redis_key,
                holder_id,
                nx=True,
                ex=ttl_seconds,
            )
            if acquired:
                return await self._finalize_acquisition(
                    lock_key, holder_id, holder_data_key, ttl_seconds, holder_metadata, now
                )
            # Retry also failed, meaning another holder acquired it
            # Fall through to check who holds it now
            existing_holder = await self._redis.get(redis_key)

        # Guard against race where lock expires between retry and GET
        if existing_holder is None:
            return AcquireResult(
                status=AcquireStatus.ALREADY_HELD_BY_OTHER,
                lock_key=lock_key,
                holder_id="unknown",
                acquired_at=None,
            )

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
            # Different holder holds the lock
            return AcquireResult(
                status=AcquireStatus.ALREADY_HELD_BY_OTHER,
                lock_key=lock_key,
                holder_id=existing_holder_id,
                acquired_at=None,
            )
        except (UnicodeDecodeError, AttributeError):
            logger.warning(
                f"Failed to parse existing lock holder for {lock_key}",
                exc_info=True,
            )
            return AcquireResult(
                status=AcquireStatus.ALREADY_HELD_BY_OTHER,
                lock_key=lock_key,
                holder_id="unknown",
                acquired_at=None,
            )

    async def release(
        self,
        lock_key: str,
        holder_id: str,
    ) -> ReleaseResult:
        """Release the lock if held by the given holder.

        Idempotent — returns success=False if not held or held by different holder.
        Uses Lua script for atomicity to prevent TOCTOU races.
        """
        redis_key = self._lock_key(lock_key)
        holder_data_key = self._holder_data_key(lock_key)

        # Read holder metadata BEFORE executing Lua script, so we capture
        # the original metadata before another process can acquire and overwrite it
        holder_data_dict = await self._redis.hgetall(holder_data_key)
        holder_data = {}
        for k, v in holder_data_dict.items():
            k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            v_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
            holder_data[k_str] = v_str

        # Lua script for atomic release: if holder matches, delete the lock
        lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
        """

        try:
            # Register and execute Lua script
            result = await self._redis.eval(lua_script, 1, redis_key, holder_id)

            if not result:
                # Check if lock exists but held by different holder
                existing = await self._redis.get(redis_key)
                if existing is None:
                    return ReleaseResult(
                        released=False,
                        reason=ReleaseReason.NOT_HELD,
                        lock_key=lock_key,
                    )
                return ReleaseResult(
                    released=False,
                    reason=ReleaseReason.HELD_BY_OTHER,
                    lock_key=lock_key,
                )

            # Lock was released successfully, also clean up metadata
            await self._redis.delete(holder_data_key)

            # Emit event via event bus if available
            if self._event_bus:
                try:
                    event = PipelineLockReleasedEvent(
                        type="pipeline.lock_released",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="redis_distributed_lock",
                        project_id=holder_data.get("project_id", ""),
                        work_item_id=holder_id,
                        board_id=holder_data.get("board_id", ""),
                        next_work_item_id=None,
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
        acquired_at_str = None
        for k, v in metadata.items():
            k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            v_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
            # Store acquired_at separately and exclude from returned metadata
            if k_str == "acquired_at":
                acquired_at_str = v_str
            else:
                metadata_dict[k_str] = v_str

        # Retrieve actual acquired_at from metadata (stored during acquisition)
        # Fall back to estimation if not present (for locks acquired before this fix)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
        if acquired_at_str:
            try:
                acquired_at = datetime.fromisoformat(acquired_at_str)
            except (ValueError, TypeError):
                # Fall back to estimation if metadata is corrupted
                acquired_at = expires_at - timedelta(seconds=self._lock_ttl_seconds)
        else:
            # Fall back to estimation for locks acquired before this fix
            acquired_at = expires_at - timedelta(seconds=self._lock_ttl_seconds)

        return LockHolder(
            lock_key=lock_key,
            holder_id=holder_id_str,
            acquired_at=acquired_at,
            ttl_seconds=ttl,
            expires_at=expires_at,
            holder_metadata=MappingProxyType(metadata_dict),
        )

    async def get_all_holders(self) -> list[LockHolder]:
        """Return all currently held locks across all keys.

        Uses per-key error handling to continue scanning even if one lock
        retrieval fails. A single Redis hiccup on one key won't fail the entire scan.
        """
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

                # Per-key error handling: skip locks with retrieval errors
                try:
                    holder = await self.get_holder(lock_key)
                    if holder is not None:
                        holders.append(holder)
                except Exception:
                    logger.warning(
                        f"Failed to retrieve holder data for lock key {lock_key}, skipping",
                        exc_info=True,
                    )
                    continue

            if cursor == 0:
                break

        return holders

    async def renew(
        self,
        lock_key: str,
        holder_id: str,
        ttl_seconds: int,
    ) -> bool:
        """Extend the TTL on a held lock.

        Uses Lua script for atomicity to prevent TOCTOU race where lock
        could be released and re-acquired by another holder between verification
        and TTL update.
        """
        redis_key = self._lock_key(lock_key)
        holder_data_key = self._holder_data_key(lock_key)

        # Lua script for atomic renew: if holder matches, extend TTL on both lock and metadata
        lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                redis.call("expire", KEYS[1], ARGV[2])
                redis.call("expire", KEYS[2], ARGV[2])
                return 1
            else
                return 0
            end
        """

        try:
            result = await self._redis.eval(lua_script, 2, redis_key, holder_data_key, holder_id, ttl_seconds)
            return bool(result)
        except Exception:
            logger.error(
                f"Failed to renew lock {lock_key} for holder {holder_id}",
                exc_info=True,
            )
            raise
