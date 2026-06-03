"""Tests for RedisPipelineQueue implementation.

Tests the Redis-backed pipeline queue adapter, including:
- Enqueue/dequeue FIFO semantics
- Idempotency of operations
- Metadata preservation
- Event emission
- Edge cases and concurrent access patterns
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.secondary.redis_pipeline_queue import RedisPipelineQueue
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.pipeline_queue import IPipelineQueue, QueueEntry
from tests.unit.ports.output.test_pipeline_queue_contract import TestPipelineQueueContract


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        """Initialize mock Redis storage."""
        self._data: dict[str, bytes] = {}
        self._sorted_sets: dict[str, dict[str, float]] = {}
        self._hashes: dict[str, dict[str, bytes]] = {}

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        """Mock Redis ZADD operation."""
        if key not in self._sorted_sets:
            self._sorted_sets[key] = {}
        count = 0
        for member, score in mapping.items():
            if member not in self._sorted_sets[key]:
                count += 1
            self._sorted_sets[key][member] = score
        return count

    async def zrank(self, key: str, member: str) -> int | None:
        """Mock Redis ZRANK operation."""
        if key not in self._sorted_sets:
            return None
        if member not in self._sorted_sets[key]:
            return None
        # Sort by score and find rank
        sorted_members = sorted(
            self._sorted_sets[key].items(),
            key=lambda x: x[1],
        )
        for rank, (m, _) in enumerate(sorted_members):
            if m == member:
                return rank
        return None

    async def zrange(
        self,
        key: str,
        start: int,
        stop: int,
        withscores: bool = False,
    ) -> list:
        """Mock Redis ZRANGE operation."""
        if key not in self._sorted_sets:
            return []
        # Sort by score
        sorted_items = sorted(
            self._sorted_sets[key].items(),
            key=lambda x: x[1],
        )
        # Handle negative indices like Redis does
        if stop == -1:
            result = sorted_items[start:]
        else:
            result = sorted_items[start : stop + 1]
        if not withscores:
            return [m for m, _ in result]
        return result

    async def zpopmin(self, key: str, count: int = 1) -> list:
        """Mock Redis ZPOPMIN operation."""
        if key not in self._sorted_sets:
            return []
        # Sort by score and get minimum count items
        sorted_items = sorted(
            self._sorted_sets[key].items(),
            key=lambda x: x[1],
        )
        result = sorted_items[:count]
        # Remove from set
        for member, _ in result:
            del self._sorted_sets[key][member]
        return result

    async def zrem(self, key: str, member: str) -> int:
        """Mock Redis ZREM operation."""
        if key not in self._sorted_sets:
            return 0
        if member in self._sorted_sets[key]:
            del self._sorted_sets[key][member]
            return 1
        return 0

    async def zcard(self, key: str) -> int:
        """Mock Redis ZCARD operation."""
        if key not in self._sorted_sets:
            return 0
        return len(self._sorted_sets[key])

    async def hset(self, key: str, *args, mapping: dict | None = None, **kwargs) -> int:
        """Mock Redis HSET operation.

        Supports both:
        - hset(key, mapping={field: value, ...})
        - hset(key, field, value)
        """
        if key not in self._hashes:
            self._hashes[key] = {}
        count = 0

        if mapping is not None:
            # Called with mapping parameter
            for k, v in mapping.items():
                if isinstance(k, str):
                    k = k.encode("utf-8")
                if isinstance(v, str):
                    v = v.encode("utf-8")
                if k not in self._hashes[key]:
                    count += 1
                self._hashes[key][k] = v
        elif len(args) == 2:
            # Called with field, value positional args
            field, value = args
            if isinstance(field, str):
                field = field.encode("utf-8")
            if isinstance(value, str):
                value = value.encode("utf-8")
            if field not in self._hashes[key]:
                count += 1
            self._hashes[key][field] = value
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

    async def hdel(self, key: str, field: str) -> int:
        """Mock Redis HDEL operation."""
        if isinstance(field, str):
            field = field.encode("utf-8")
        hash_data = self._hashes.get(key, {})
        if field in hash_data:
            del hash_data[field]
            return 1
        return 0

    async def delete(self, key: str) -> int:
        """Mock Redis DELETE operation."""
        deleted = 0
        if key in self._data:
            del self._data[key]
            deleted = 1
        if key in self._sorted_sets:
            del self._sorted_sets[key]
            deleted = 1
        if key in self._hashes:
            del self._hashes[key]
            deleted = 1
        return deleted


@pytest.mark.asyncio
class TestRedisPipelineQueue(TestPipelineQueueContract):
    """Tests for RedisPipelineQueue using contract tests."""

    async def create_queue(self) -> IPipelineQueue:
        """Create a RedisPipelineQueue with mock Redis."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        return RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

    @pytest.mark.asyncio
    async def test_enqueue_emits_event(self):
        """Test that enqueue emits WorkItemQueuedEvent."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, {"board_id": "board-1"})

        await queue.enqueue("queue-1", entry)

        event_bus.publish.assert_called_once()
        event = event_bus.publish.call_args[0][0]
        assert event.work_item_id == "item-1"
        assert event.board_id == "board-1"

    @pytest.mark.asyncio
    async def test_pop_emits_event(self):
        """Test that pop emits WorkItemDequeuedEvent."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, {"board_id": "board-1"})
        await queue.enqueue("queue-1", entry)

        event_bus.reset_mock()
        await queue.pop("queue-1")

        event_bus.publish.assert_called_once()
        event = event_bus.publish.call_args[0][0]
        assert event.work_item_id == "item-1"
        assert event.reason == "popped"

    @pytest.mark.asyncio
    async def test_remove_emits_event(self):
        """Test that remove emits WorkItemDequeuedEvent."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, {"board_id": "board-1"})
        await queue.enqueue("queue-1", entry)

        event_bus.reset_mock()
        await queue.remove("queue-1", "item-1")

        event_bus.publish.assert_called_once()
        event = event_bus.publish.call_args[0][0]
        assert event.work_item_id == "item-1"
        assert event.reason == "removed"

    @pytest.mark.asyncio
    async def test_board_position_ordering(self):
        """Test that items are ordered by board_position (score), not enqueue order."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 100, now, {}))
        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 10, now, {}))
        await queue.enqueue("queue-1", QueueEntry("item-3", "In Progress", 50, now, {}))

        entries = await queue.list("queue-1")

        assert len(entries) == 3
        assert entries[0].work_item_id == "item-2"
        assert entries[1].work_item_id == "item-3"
        assert entries[2].work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_peek_and_pop_consistent_ordering(self):
        """Test that peek and pop return items in same order."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, {}))
        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 1, now, {}))

        peeked = await queue.peek("queue-1")
        popped = await queue.pop("queue-1")

        assert peeked.work_item_id == popped.work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_metadata_preserved_through_lifecycle(self):
        """Test that metadata is preserved through enqueue, peek, pop."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        metadata = {
            "project_id": "proj-123",
            "board_id": "board-456",
            "custom_key": "custom_value",
        }
        entry = QueueEntry("item-1", "In Progress", 0, now, metadata)

        await queue.enqueue("queue-1", entry)

        peeked = await queue.peek("queue-1")
        assert peeked.metadata == metadata

        popped = await queue.pop("queue-1")
        assert popped.metadata == metadata

    @pytest.mark.asyncio
    async def test_stage_name_preserved(self):
        """Test that stage_name is preserved."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "Code Review", 0, now, {})

        await queue.enqueue("queue-1", entry)
        result = await queue.peek("queue-1")

        assert result.stage_name == "Code Review"

    @pytest.mark.asyncio
    async def test_enqueued_at_preserved(self):
        """Test that enqueued_at timestamp is preserved."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        original_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        entry = QueueEntry("item-1", "In Progress", 0, original_time, {})

        await queue.enqueue("queue-1", entry)
        result = await queue.peek("queue-1")

        assert result.enqueued_at == original_time

    @pytest.mark.asyncio
    async def test_position_tracking_after_removal(self):
        """Test that positions are updated correctly after removal."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, {}))
        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 1, now, {}))
        await queue.enqueue("queue-1", QueueEntry("item-3", "In Progress", 2, now, {}))

        await queue.remove("queue-1", "item-2")

        pos1 = await queue.position_of("queue-1", "item-1")
        pos3 = await queue.position_of("queue-1", "item-3")

        assert pos1 == 0
        assert pos3 == 1

    @pytest.mark.asyncio
    async def test_large_queue_performance(self):
        """Test handling of large queue."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)

        # Enqueue 100 items
        for i in range(100):
            entry = QueueEntry(f"item-{i}", "In Progress", i, now, {})
            await queue.enqueue("queue-1", entry)

        length = await queue.length("queue-1")
        assert length == 100

        # Pop all items and verify FIFO order
        for i in range(100):
            popped = await queue.pop("queue-1")
            assert popped.work_item_id == f"item-{i}"

    @pytest.mark.asyncio
    async def test_remove_nonexistent_with_event_bus(self):
        """Test that event bus doesn't fail when removing nonexistent item."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        result = await queue.remove("queue-1", "nonexistent")

        assert result is False
        event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_uses_board_id_from_metadata(self):
        """Test that event uses board_id from metadata."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, {"board_id": "board-456"})

        await queue.enqueue("queue-1", entry)

        event_bus.publish.assert_called_once()
        event = event_bus.publish.call_args[0][0]
        assert event.board_id == "board-456"

    @pytest.mark.asyncio
    async def test_peek_handles_missing_metadata_gracefully(self):
        """Test that peek() handles missing metadata by emitting corruption event."""
        from codetoreum.domain.events.queue_events import QueueMetadataCorruptionEvent

        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, {"board_id": "board-456"})

        # Enqueue normally
        await queue.enqueue("queue-1", entry)

        # Clear the event bus calls
        event_bus.reset_mock()

        # Manually corrupt the metadata by removing it
        meta_key = f"codetoreum:queue:meta:queue-1"
        redis._hashes[meta_key] = {}

        # peek() should handle the missing metadata and emit a corruption event
        result = await queue.peek("queue-1")

        # Should return a partial entry (not None)
        assert result is not None
        assert result.work_item_id == "item-1"
        assert result.stage_name == ""  # Empty fallback
        assert result.board_position == 0

        # Should emit QueueMetadataCorruptionEvent
        event_bus.publish.assert_called_once()
        published_event = event_bus.publish.call_args[0][0]
        assert isinstance(published_event, QueueMetadataCorruptionEvent)
        assert published_event.work_item_id == "item-1"
        assert "not found" in published_event.error_details

    @pytest.mark.asyncio
    async def test_peek_handles_corrupt_json_metadata(self):
        """Test that peek() handles unparseable JSON metadata gracefully."""
        from codetoreum.domain.events.queue_events import QueueMetadataCorruptionEvent

        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, {"board_id": "board-456"})

        # Enqueue normally
        await queue.enqueue("queue-1", entry)

        # Clear the event bus calls
        event_bus.reset_mock()

        # Manually corrupt the metadata JSON
        # Note: MockRedis stores hashes with bytes keys when set via hset
        meta_key = f"codetoreum:queue:meta:queue-1"
        redis._hashes[meta_key][b"item-1"] = b"{ invalid json"

        # peek() should handle the corrupted JSON
        result = await queue.peek("queue-1")

        # Should return a partial entry (not None)
        assert result is not None
        assert result.work_item_id == "item-1"
        assert result.stage_name == ""  # Empty fallback
        assert result.board_position == 0

        # Should emit QueueMetadataCorruptionEvent
        event_bus.publish.assert_called_once()
        published_event = event_bus.publish.call_args[0][0]
        assert isinstance(published_event, QueueMetadataCorruptionEvent)
        assert published_event.work_item_id == "item-1"
        assert "JSON" in published_event.error_details or "decode" in published_event.error_details

    @pytest.mark.asyncio
    async def test_peek_with_corruption_does_not_return_none(self):
        """Test that peek() never returns None when items exist, even with corruption."""
        redis = MockRedis()
        event_bus = AsyncMock(spec=EventBus)
        queue = RedisPipelineQueue(redis_client=redis, event_bus=event_bus)

        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, {})

        # Enqueue an item
        await queue.enqueue("queue-1", entry)

        # Corrupt the metadata
        meta_key = f"codetoreum:queue:meta:queue-1"
        redis._hashes[meta_key][b"item-1"] = b"corrupted"

        # peek() should NOT return None - the queue is not blocked
        result = await queue.peek("queue-1")

        # Item must not return None, preventing silent pipeline blockage
        assert result is not None
        assert result.work_item_id == "item-1"

        # The queue still has the item (not removed)
        length = await queue.length("queue-1")
        assert length == 1
