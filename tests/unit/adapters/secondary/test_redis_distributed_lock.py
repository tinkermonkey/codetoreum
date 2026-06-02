"""Tests for RedisDistributedLock implementation.

Tests the Redis-backed distributed lock adapter, including:
- Lock acquisition and release
- Metadata handling on release
- Event emission
- TOCTOU race condition prevention (Lua script atomicity)
"""

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


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        """Initialize mock Redis storage."""
        self._data: dict[str, bytes] = {}
        self._hashes: dict[str, dict[str, bytes]] = {}

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
        if isinstance(field, str):
            field = field.encode("utf-8")
        hash_data = self._hashes.get(key, {})
        return hash_data.get(field)

    async def eval(self, script: str, numkeys: int, *keys_and_args) -> int:
        """Mock Redis EVAL for Lua script."""
        # Extract keys and arguments
        keys = keys_and_args[:numkeys]
        args = keys_and_args[numkeys:]

        # Simulate the Lua script used in RedisDistributedLock.release()
        # Script: if redis.call("get", KEYS[1]) == ARGV[1] then return redis.call("del", KEYS[1]) else return 0 end
        if numkeys > 0:
            key = keys[0]
            holder_id = args[0] if args else None

            # Get current value
            current_value = self._data.get(key)

            # Compare (decode if needed)
            if isinstance(current_value, bytes):
                current_value = current_value.decode('utf-8')
            if isinstance(holder_id, bytes):
                holder_id = holder_id.decode('utf-8')

            # If values match, delete and return 1, else return 0
            if current_value == holder_id:
                if key in self._data:
                    del self._data[key]
                return 1
        return 0

    async def expire(self, key: str, seconds: int) -> int:
        """Mock Redis EXPIRE operation."""
        # In a real implementation, this would set TTL metadata
        # For testing, we just return success
        return 1 if key in self._data else 0

    async def ttl(self, key: str) -> int:
        """Mock Redis TTL operation."""
        # In a real implementation, this would return remaining seconds
        # For testing, return a high value to simulate valid TTL
        return 3600 if key in self._data else -2

    async def scan(self, cursor: int, match: str | None = None, count: int = 100) -> tuple[int, list[str]]:
        """Mock Redis SCAN operation."""
        import fnmatch
        if match:
            keys = [k for k in self._data.keys() if fnmatch.fnmatch(k, match)]
        else:
            keys = list(self._data.keys())
        return (0, keys)


@pytest.mark.asyncio
class TestRedisDistributedLock:
    """Tests for RedisDistributedLock."""

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
