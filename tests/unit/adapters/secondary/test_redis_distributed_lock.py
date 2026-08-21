"""Tests for RedisDistributedLock implementation.

Tests the Redis-backed distributed lock adapter, including:
- Lock acquisition and release
- Metadata handling on release
- Event emission
- TOCTOU race condition prevention (Lua script atomicity)
- Contract compliance via TestDistributedLockContract
"""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.secondary.redis_distributed_lock import (
    RedisDistributedLock,
    ReleaseReason,
)
from codetoreum.domain.events.lock_events import (
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
)
from codetoreum.infrastructure.event_bus import EventBus
from tests.unit.ports.output.test_distributed_lock_contract import TestDistributedLockContract


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        """Initialize mock Redis storage."""
        self._data: dict[str, bytes] = {}
        self._hashes: dict[str, dict[bytes, bytes]] = {}
        self._ttl: dict[str, int] = {}  # Track TTL in seconds for each key

    async def get(self, key: str) -> bytes | None:
        """Mock Redis GET operation."""
        return self._data.get(key)

    async def set(self, key: str, value: bytes | str, ex: int | None = None, nx: bool = False, px: int | None = None) -> str | None:
        """Mock Redis SET operation."""
        # If NX (only set if not exists), check if key already exists
        if nx and key in self._data:
            return None
        if isinstance(value, str):
            value = value.encode("utf-8")
        self._data[key] = value
        # Set TTL if provided
        if ex is not None:
            self._ttl[key] = ex
        return "OK"

    async def delete(self, key: str) -> int:
        """Mock Redis DELETE operation."""
        deleted = 0
        if key in self._data:
            del self._data[key]
            deleted = 1
        if key in self._hashes:
            del self._hashes[key]
            deleted = 1
        # Clean up TTL if it exists
        if key in self._ttl:
            del self._ttl[key]
        return deleted

    async def hset(self, key: str, mapping: dict) -> int:
        """Mock Redis HSET operation."""
        if key not in self._hashes:
            self._hashes[key] = {}
        count = 0
        for k, v in mapping.items():
            if isinstance(k, str):
                k = k.encode("utf-8") if isinstance(k, str) else k
            if isinstance(v, str):
                v = v.encode("utf-8") if isinstance(v, str) else v
            self._hashes[key][k] = v
            count += 1
        return count

    async def hgetall(self, key: str) -> dict:
        """Mock Redis HGETALL operation."""
        return self._hashes.get(key, {})

    async def hget(self, key: str, field: str) -> bytes | None:
        """Mock Redis HGET operation."""
        field_bytes = field.encode("utf-8") if isinstance(field, str) else field
        hash_data = self._hashes.get(key, {})
        return hash_data.get(field_bytes)

    async def eval(self, script: str, numkeys: int, *keys_and_args) -> int:
        """Mock Redis EVAL for Lua script.

        Handles two patterns:
        1. Release script (1 key): if holder matches, delete key and return 1
        2. Renew script (2 keys): if holder matches, expire both keys and return 1
        """
        # Extract keys and arguments
        keys = keys_and_args[:numkeys]
        args = keys_and_args[numkeys:]

        if numkeys < 1:
            return 0

        # Get holder_id from first argument
        holder_id = args[0] if args else None
        if isinstance(holder_id, bytes):
            holder_id = holder_id.decode("utf-8")

        # Get current value of first key
        key1 = keys[0]
        current_value_bytes = self._data.get(key1)
        current_value_str = current_value_bytes.decode("utf-8") if isinstance(current_value_bytes, bytes) else None

        # Check if holder matches
        if current_value_str != holder_id:
            return 0

        # Release script (1 key): delete the lock key
        if numkeys == 1:
            if key1 in self._data:
                del self._data[key1]
            # Clean up TTL
            if key1 in self._ttl:
                del self._ttl[key1]
            return 1

        # Renew script (2 keys): expire both lock key and metadata key
        if numkeys == 2:
            ttl_seconds = args[1] if len(args) > 1 else None
            if ttl_seconds is not None:
                # Set TTL for both keys (simulating redis.call("expire", ...))
                if isinstance(ttl_seconds, bytes):
                    ttl_seconds = int(ttl_seconds.decode("utf-8"))
                else:
                    ttl_seconds = int(ttl_seconds)

                key2 = keys[1]
                self._ttl[key1] = ttl_seconds
                self._ttl[key2] = ttl_seconds
            return 1

        return 0

    async def expire(self, key: str, seconds: int) -> int:
        """Mock Redis EXPIRE operation."""
        # Set TTL for the key
        if key in self._data or key in self._hashes:
            self._ttl[key] = seconds
            return 1
        return 0

    async def ttl(self, key: str) -> int:
        """Mock Redis TTL operation."""
        # Return the stored TTL in seconds, or -2 if key doesn't exist
        if key in self._data or key in self._hashes:
            return self._ttl.get(key, -1)
        return -2

    async def scan(self, cursor: int, match: str | None = None, count: int = 100) -> tuple[int, list[str]]:
        """Mock Redis SCAN operation."""
        import fnmatch
        if match:
            keys = [k for k in self._data.keys() if fnmatch.fnmatch(k, match)]
        else:
            keys = list(self._data.keys())
        return (0, keys)


@pytest.mark.asyncio
class TestRedisDistributedLock(TestDistributedLockContract):
    """Tests for RedisDistributedLock."""

    async def create_lock(self):
        """Create a RedisDistributedLock with mock Redis for testing."""
        redis = MockRedis()
        return RedisDistributedLock(redis_client=redis)

    async def test_metadata_read_before_deletion(self):
        """Test that metadata is read BEFORE being deleted.

        This is the critical bug fix: line 210 was reading after delete,
        resulting in empty dict. After fix, line 210 reads first, then 207 deletes.
        """
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        lock = RedisDistributedLock(redis_client=redis, event_bus=event_bus)

        lock_key = "test:lock"
        redis_key = lock._lock_key(lock_key)
        holder_data_key = lock._holder_data_key(lock_key)
        holder_id = "wi-123"

        # Set up lock (simulating successful acquisition)
        await redis.set(redis_key, holder_id)
        metadata = {
            "project_id": "proj-1",
            "work_item_id": "wi-123",
            "board_id": "board-1",
            "queue_length_at_acquire": "5",
        }
        await redis.hset(holder_data_key, metadata)

        # Release the lock
        result = await lock.release(lock_key, holder_id=holder_id)

        # Verify lock was released
        assert result.released is True
        assert result.lock_key == lock_key

        # Verify metadata was extracted and event was emitted with correct fields
        event_bus.publish.assert_called_once()
        call_args = event_bus.publish.call_args
        event = call_args[0][0]

        # Verify event has the correct metadata fields
        assert isinstance(event, PipelineLockReleasedEvent)
        assert event.project_id == "proj-1"
        assert event.work_item_id == "wi-123"
        assert event.board_id == "board-1"

        # Verify metadata was actually deleted after being read
        remaining_data = await redis.hgetall(holder_data_key)
        assert remaining_data == {}

    async def test_acquire_lock_success(self):
        """Test successful lock acquisition."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        lock = RedisDistributedLock(redis_client=redis, event_bus=event_bus)

        lock_key = "test:lock"
        holder_id = "test-holder"
        metadata = {
            "project_id": "proj-1",
            "work_item_id": "wi-123",
            "board_id": "board-1",
            "queue_length_at_acquire": "3",
        }

        result = await lock.try_acquire(lock_key, holder_id, ttl_seconds=3600, holder_metadata=metadata)

        from codetoreum.ports.output.distributed_lock import AcquireStatus
        assert result.status == AcquireStatus.ACQUIRED
        assert result.lock_key == lock_key

        # Verify lock value is set
        redis_key = lock._lock_key(lock_key)
        stored_holder = await redis.get(redis_key)
        assert stored_holder == holder_id.encode("utf-8")

        # Verify metadata is stored
        holder_data_key = lock._holder_data_key(lock_key)
        stored_metadata = await redis.hgetall(holder_data_key)
        assert stored_metadata is not None

    async def test_release_lock_not_held_by_caller(self):
        """Test release fails if lock is not held by the caller."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        lock = RedisDistributedLock(redis_client=redis, event_bus=event_bus)

        lock_key = "test:lock"
        redis_key = lock._lock_key(lock_key)

        # Set lock held by someone else
        await redis.set(redis_key, "other-holder")

        # Try to release as different holder
        result = await lock.release(lock_key, holder_id="my-holder")

        assert result.released is False
        assert result.reason == ReleaseReason.HELD_BY_OTHER
        assert result.lock_key == lock_key

        # Verify lock still exists
        stored_holder = await redis.get(redis_key)
        assert stored_holder is not None

    async def test_release_lock_not_found(self):
        """Test release when lock doesn't exist."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        lock = RedisDistributedLock(redis_client=redis, event_bus=event_bus)

        lock_key = "nonexistent:lock"

        result = await lock.release(lock_key, holder_id="some-holder")

        assert result.released is False
        assert result.reason == ReleaseReason.NOT_HELD
        assert result.lock_key == lock_key

    async def test_metadata_construction_with_fields(self):
        """Test that metadata fields are properly used when constructing events."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        lock = RedisDistributedLock(redis_client=redis, event_bus=event_bus)

        lock_key = "test:lock"
        holder_id = "test-holder"
        metadata = {
            "project_id": "proj-123",
            "work_item_id": "wi-456",
            "board_id": "board-789",
            "queue_length_at_acquire": "2",
        }

        # Acquire lock
        await lock.try_acquire(lock_key, holder_id, ttl_seconds=3600, holder_metadata=metadata)

        # Reset mock to isolate this test (ignore acquire event)
        event_bus.reset_mock()

        # Store metadata (normally done during acquire, but we're manually storing)
        redis_key = lock._lock_key(lock_key)
        holder_data_key = lock._holder_data_key(lock_key)
        await redis.hset(holder_data_key, metadata)

        # Release lock
        result = await lock.release(lock_key, holder_id=holder_id)

        # Verify the event was emitted with correct metadata
        assert result.released is True
        event_bus.publish.assert_called_once()
        event = event_bus.publish.call_args[0][0]

        assert event.project_id == "proj-123"
        assert event.work_item_id == holder_id  # work_item_id comes from holder_id parameter, not metadata
        assert event.board_id == "board-789"

    async def test_acquired_at_preserved_after_renewal(self):
        """Test that acquired_at timestamp stays accurate even after lock renewal.

        This verifies the fix for: "acquired_at estimates from TTL are inaccurate after renewal".
        When a lock is renewed with renew(), the TTL extends but the original acquired_at
        should remain unchanged.
        """
        redis = MockRedis()
        lock = RedisDistributedLock(redis_client=redis)

        lock_key = "test:lock"
        holder_id = "test-holder"
        ttl_seconds = 3600

        # Acquire lock
        result1 = await lock.try_acquire(lock_key, holder_id, ttl_seconds=ttl_seconds)
        acquired_time = result1.acquired_at

        # Get holder immediately after acquisition
        holder1 = await lock.get_holder(lock_key)
        assert holder1 is not None
        assert holder1.acquired_at == acquired_time

        # Wait a bit (simulate some time passing), then renew the lock
        await asyncio.sleep(0.1)
        renew_result = await lock.renew(lock_key, holder_id, ttl_seconds=7200)
        assert renew_result is True

        # Get holder after renewal - acquired_at should still be the original time
        holder2 = await lock.get_holder(lock_key)
        assert holder2 is not None
        # The acquired_at should be the same as before renewal
        assert holder2.acquired_at == acquired_time, (
            f"acquired_at changed after renewal: "
            f"before={acquired_time}, after={holder2.acquired_at}"
        )

    async def test_get_all_holders_continues_on_per_key_error(self):
        """Test that get_all_holders continues scanning even if one lock retrieval fails.

        This verifies the fix for: "get_all_holders has no per-key error handling".
        A Redis hiccup on one key should not prevent scanning of other keys.
        """
        redis = MockRedis()
        lock = RedisDistributedLock(redis_client=redis)

        # Set up three locks
        lock_key_1 = "test:lock:1"
        lock_key_2 = "test:lock:2"
        lock_key_3 = "test:lock:3"
        holder_id_1 = "holder-1"
        holder_id_2 = "holder-2"
        holder_id_3 = "holder-3"

        await lock.try_acquire(lock_key_1, holder_id_1, ttl_seconds=3600)
        await lock.try_acquire(lock_key_2, holder_id_2, ttl_seconds=3600)
        await lock.try_acquire(lock_key_3, holder_id_3, ttl_seconds=3600)

        # Simulate a retrieval error on lock_key_2 by patching get_holder
        original_get_holder = lock.get_holder
        call_count = 0

        async def failing_get_holder(key):
            nonlocal call_count
            call_count += 1
            if key == lock_key_2:
                # Simulate a transient error on lock_key_2
                raise RuntimeError("Simulated Redis error on lock_key_2")
            return await original_get_holder(key)

        lock.get_holder = failing_get_holder

        # get_all_holders should not raise, but should skip the failed key
        all_holders = await lock.get_all_holders()

        # Should have returned 2 holders (1 and 3), skipping the failed one (2)
        assert len(all_holders) == 2
        holder_ids = {h.holder_id for h in all_holders}
        assert holder_ids == {holder_id_1, holder_id_3}
        assert holder_id_2 not in holder_ids
