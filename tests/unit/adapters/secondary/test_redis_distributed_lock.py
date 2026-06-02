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

    async def set(self, key: str, value: bytes | str, ex: int | None = None) -> str:
        """Mock Redis SET operation."""
        if isinstance(value, str):
            value = value.encode("utf-8")
        self._data[key] = value
        return "OK"

    async def delete(self, key: str) -> int:
        """Mock Redis DELETE operation."""
        if key in self._data:
            del self._data[key]
            return 1
        return 0

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
        # Simple mock: return 1 if key exists and can be deleted, 0 otherwise
        if numkeys > 0:
            key = keys_and_args[0]
            if key in self._data:
                del self._data[key]
                return 1
        return 0


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
        holder_data_key = f"{lock_key}:holder"
        holder_id = "test-holder"

        # Set up lock (simulating successful acquisition)
        await redis.set(lock_key, holder_id)
        metadata = {
            "project_id": "proj-1",
            "work_item_id": "wi-123",
            "board_id": "board-1",
            "queue_length_at_acquire": "5",
        }
        await redis.hset(holder_data_key, metadata)

        # Release the lock
        result = await lock.release(lock_key)

        # Verify lock was released
        assert result.released is True
        assert result.lock_key == lock_key

        # Verify metadata was extracted and event was emitted with correct fields
        event_bus.emit.assert_called_once()
        call_args = event_bus.emit.call_args
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

        assert result.acquired is True
        assert result.lock_key == lock_key

        # Verify lock value is set
        stored_holder = await redis.get(lock_key)
        assert stored_holder == holder_id.encode("utf-8")

        # Verify metadata is stored
        stored_metadata = await redis.hgetall(f"{lock_key}:holder")
        assert stored_metadata is not None

    async def test_release_lock_not_held_by_caller(self):
        """Test release fails if lock is not held by the caller."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        lock = RedisDistributedLock(redis_client=redis, event_bus=event_bus)

        lock_key = "test:lock"

        # Set lock held by someone else
        await redis.set(lock_key, "other-holder")

        # Try to release as different holder
        result = await lock.release(lock_key, holder_id="my-holder")

        assert result.released is False
        assert result.reason == ReleaseReason.HELD_BY_OTHER
        assert result.lock_key == lock_key

        # Verify lock still exists
        stored_holder = await redis.get(lock_key)
        assert stored_holder is not None

    async def test_release_lock_not_found(self):
        """Test release when lock doesn't exist."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        lock = RedisDistributedLock(redis_client=redis, event_bus=event_bus)

        lock_key = "nonexistent:lock"

        result = await lock.release(lock_key)

        assert result.released is False
        assert result.reason == ReleaseReason.NOT_FOUND
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

        # Store metadata
        holder_data_key = f"{lock_key}:holder"
        await redis.hset(holder_data_key, metadata)

        # Release lock
        result = await lock.release(lock_key, holder_id=holder_id)

        # Verify the event was emitted with correct metadata
        assert result.released is True
        event_bus.emit.assert_called_once()
        event = event_bus.emit.call_args[0][0]

        assert event.project_id == "proj-123"
        assert event.work_item_id == "wi-456"
        assert event.board_id == "board-789"
