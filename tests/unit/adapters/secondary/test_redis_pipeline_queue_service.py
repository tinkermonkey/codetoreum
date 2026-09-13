"""Tests for RedisPipelineQueueService Redis-backed implementation.

Tests verify:
1. Contract compliance (inherited from TestPipelineQueueServiceContract)
2. Redis-specific data model correctness
3. Event emission with correct source
4. Metadata corruption handling
5. Cross-pipeline membership lookup via reverse index
6. Graceful degradation on board service failures
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.secondary.redis_pipeline_queue_service import RedisPipelineQueueService
from codetoreum.domain.events.queue_events import (
    QueueItemAddedEvent,
    QueueItemRemovedEvent,
    QueueMetadataCorruptionEvent,
    QueuePositionChangedEvent,
)
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.pipeline_queue_service import (
    DuplicateQueueEntryError,
    InvalidQueueStateError,
    QueueItemNotFoundError,
    QueueStatus,
    QueueValidationError,
)
from tests.unit.ports.output.test_pipeline_queue_service_contract import (
    TestPipelineQueueServiceContract,
)


class MockPipeline:
    """Mock Redis pipeline for transactional operations."""

    def __init__(self, redis_client):
        self._redis = redis_client
        self._commands = []

    def zadd(self, key: str, mapping: dict) -> "MockPipeline":
        """Buffer ZADD command (async but returned synchronously for chaining)."""
        self._commands.append(("zadd", (key, mapping)))
        # Return a coroutine-like object that resolves to self
        return self._async_return(self)

    def hset(self, key: str, field_or_mapping, value=None) -> "MockPipeline":
        """Buffer HSET command (async but returned synchronously for chaining)."""
        self._commands.append(("hset", (key, field_or_mapping, value)))
        return self._async_return(self)

    def hdel(self, key: str, *fields) -> "MockPipeline":
        """Buffer HDEL command (async but returned synchronously for chaining)."""
        self._commands.append(("hdel", (key, fields)))
        return self._async_return(self)

    def sadd(self, key: str, *members) -> "MockPipeline":
        """Buffer SADD command (async but returned synchronously for chaining)."""
        self._commands.append(("sadd", (key, members)))
        return self._async_return(self)

    def zrem(self, key: str, *members) -> "MockPipeline":
        """Buffer ZREM command (async but returned synchronously for chaining)."""
        self._commands.append(("zrem", (key, members)))
        return self._async_return(self)

    @staticmethod
    def _async_return(value):
        """Helper to return a value that can be awaited (returns self)."""
        async def _awaitable():
            return value
        return _awaitable()

    async def execute(self):
        """Execute all buffered commands."""
        results = []
        for cmd, args in self._commands:
            if cmd == "zadd":
                result = await self._redis.zadd(args[0], args[1])
                results.append(result)
            elif cmd == "hset":
                result = await self._redis.hset(args[0], args[1], args[2])
                results.append(result)
            elif cmd == "hdel":
                result = await self._redis.hdel(args[0], *args[1])
                results.append(result)
            elif cmd == "sadd":
                result = await self._redis.sadd(args[0], *args[1])
                results.append(result)
            elif cmd == "zrem":
                result = await self._redis.zrem(args[0], *args[1])
                results.append(result)
        return results


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self._data = {}  # Main data storage

    def pipeline(self, transaction=False):
        """Create a mock pipeline for transactional operations."""
        return MockPipeline(self)

    async def zadd(self, key: str, mapping: dict) -> int:
        """Mock ZADD - add to sorted set."""
        if key not in self._data:
            self._data[key] = {}
        added = 0
        for member, score in mapping.items():
            if member not in self._data[key]:
                added += 1
            self._data[key][member] = score
        return added

    async def zrem(self, key: str, *members) -> int:
        """Mock ZREM - remove from sorted set."""
        if key not in self._data:
            return 0
        removed = 0
        for member in members:
            if member in self._data[key]:
                del self._data[key][member]
                removed += 1
        return removed

    async def zrange(self, key: str, start: int, stop: int, withscores=False) -> list:
        """Mock ZRANGE - get items from sorted set."""
        if key not in self._data:
            return []
        items = sorted(self._data[key].items(), key=lambda x: x[1])
        if withscores:
            return items
        return [item[0] for item in items]

    async def zscore(self, key: str, member: str) -> float | None:
        """Mock ZSCORE - get score of member."""
        if key in self._data and member in self._data[key]:
            return float(self._data[key][member])
        return None

    async def zrank(self, key: str, member: str) -> int | None:
        """Mock ZRANK - get rank of member."""
        if key not in self._data:
            return None
        items = sorted(self._data[key].items(), key=lambda x: x[1])
        for i, (member_name, _) in enumerate(items):
            if member_name == member:
                return i
        return None

    async def zpopmin(self, key: str, count: int = 1) -> list:
        """Mock ZPOPMIN - pop minimum scoring members."""
        if key not in self._data:
            return []
        items = sorted(self._data[key].items(), key=lambda x: x[1])[:count]
        for member, _ in items:
            del self._data[key][member]
        return items

    async def hexists(self, key: str, field: str) -> bool:
        """Mock HEXISTS - check if hash field exists."""
        if key not in self._data:
            return False
        return field in self._data[key]

    async def hset(self, key: str, field_or_mapping, value=None) -> int:
        """Mock HSET - set hash field."""
        if key not in self._data:
            self._data[key] = {}
        if isinstance(field_or_mapping, dict):
            self._data[key].update(field_or_mapping)
            return len(field_or_mapping)
        self._data[key][field_or_mapping] = value
        return 1

    async def hget(self, key: str, field: str):
        """Mock HGET - get hash field."""
        if key in self._data and field in self._data[key]:
            value = self._data[key][field]
            return value.encode() if isinstance(value, str) else value
        return None

    async def hdel(self, key: str, *fields) -> int:
        """Mock HDEL - delete hash fields."""
        if key not in self._data:
            return 0
        deleted = 0
        for field in fields:
            if field in self._data[key]:
                del self._data[key][field]
                deleted += 1
        return deleted

    async def sadd(self, key: str, *members) -> int:
        """Mock SADD - add to set."""
        if key not in self._data:
            self._data[key] = set()
        if not isinstance(self._data[key], set):
            self._data[key] = set()
        added = 0
        for member in members:
            if member not in self._data[key]:
                added += 1
            self._data[key].add(member)
        return added

    async def smembers(self, key: str) -> set:
        """Mock SMEMBERS - get all set members."""
        if key in self._data and isinstance(self._data[key], set):
            return self._data[key]
        return set()

    async def srem(self, key: str, *members) -> int:
        """Mock SREM - remove from set."""
        if key not in self._data or not isinstance(self._data[key], set):
            return 0
        removed = 0
        for member in members:
            if member in self._data[key]:
                self._data[key].discard(member)
                removed += 1
        return removed


class MockEventEmitter:
    """Mock event emitter for testing."""

    def __init__(self):
        self.events = []

    def emit(self, event):
        """Emit an event."""
        self.events.append(event)


class MockBoardService:
    """Mock board service for testing."""

    def __init__(self):
        self.columns = {}

    async def get_board(self, project_id: str, board_id: str):
        """Get board with mocked columns."""
        board = MagicMock()
        board_key = f"{project_id}:{board_id}"

        # Return pre-configured columns or empty
        if board_key in self.columns:
            board.columns = self.columns[board_key]
        else:
            board.columns = []
        return board

    def set_column(self, project_id: str, board_id: str, column_name: str, work_item_ids: list):
        """Set column items for testing."""
        board_key = f"{project_id}:{board_id}"
        if board_key not in self.columns:
            self.columns[board_key] = []
        else:
            # Remove existing column with same name
            self.columns[board_key] = [c for c in self.columns[board_key] if c.name != column_name]

        col = MagicMock()
        col.name = column_name
        col.work_item_ids = work_item_ids
        self.columns[board_key].append(col)


class TestRedisPipelineQueueService(TestPipelineQueueServiceContract):
    """Verify RedisPipelineQueueService satisfies IPipelineQueueService contract."""

    async def create_service(self):
        """Create RedisPipelineQueueService instance for testing."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        return RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

    # ===== Redis-specific tests =====

    @pytest.mark.asyncio
    async def test_enqueue_emits_queue_item_added_event(self):
        """Enqueuing item should emit QueueItemAddedEvent."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        await service.enqueue_item("proj-1", "board-1", "item-123", position_in_column=0, timestamp=now)

        # Check event was emitted
        assert len(event_emitter.events) == 1
        event = event_emitter.events[0]
        assert isinstance(event, QueueItemAddedEvent)
        assert event.item_id == "item-123"
        assert event.source == "redis_pipeline_queue_service"
        assert event.queue_name == "proj-1:board-1"

    @pytest.mark.asyncio
    async def test_remove_emits_queue_item_removed_event(self):
        """Removing item should emit QueueItemRemovedEvent."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        await service.enqueue_item("proj-1", "board-1", "item-123", position_in_column=0, timestamp=now)
        event_emitter.events.clear()

        await service.remove_from_queue("item-123")

        # Check event was emitted
        assert len(event_emitter.events) == 1
        event = event_emitter.events[0]
        assert isinstance(event, QueueItemRemovedEvent)
        assert event.item_id == "item-123"
        assert event.source == "redis_pipeline_queue_service"

    @pytest.mark.asyncio
    async def test_mark_item_active_emits_no_event(self):
        """Marking item active should emit no event."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        await service.enqueue_item("proj-1", "board-1", "item-123", position_in_column=0, timestamp=now)
        event_emitter.events.clear()

        await service.mark_item_active("item-123")

        # No event should be emitted
        assert len(event_emitter.events) == 0

    @pytest.mark.asyncio
    async def test_mark_item_active_raises_already_active(self):
        """Marking already-active item should raise InvalidQueueStateError."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        await service.enqueue_item("proj-1", "board-1", "item-123", position_in_column=0, timestamp=now)
        await service.mark_item_active("item-123")

        with pytest.raises(InvalidQueueStateError):
            await service.mark_item_active("item-123")

    @pytest.mark.asyncio
    async def test_mark_item_active_raises_not_found(self):
        """Marking non-existent item should raise QueueItemNotFoundError."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        with pytest.raises(QueueItemNotFoundError):
            await service.mark_item_active("nonexistent")

    @pytest.mark.asyncio
    async def test_is_item_in_queue_uses_reverse_index(self):
        """is_item_in_queue should work across multiple pipelines via reverse index."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        # Add same item to two different pipelines
        await service.enqueue_item("proj-1", "board-1", "item-123", position_in_column=0, timestamp=now)
        await service.enqueue_item("proj-2", "board-2", "item-456", position_in_column=0, timestamp=now)

        # Both items should be found
        assert await service.is_item_in_queue("item-123") is True
        assert await service.is_item_in_queue("item-456") is True
        assert await service.is_item_in_queue("nonexistent") is False

    @pytest.mark.asyncio
    async def test_sync_queue_adds_new_items(self):
        """sync_queue_with_board should add items newly present in column."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        # Set up board with items in column
        board_service.set_column("proj-1", "board-1", "TODO", ["item-1", "item-2", "item-3"])

        # Sync should discover all items
        await service.sync_queue_with_board("proj-1", "board-1", "TODO")

        entries = await service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 3
        assert {e.work_item_id for e in entries} == {"item-1", "item-2", "item-3"}

    @pytest.mark.asyncio
    async def test_sync_queue_removes_old_items(self):
        """sync_queue_with_board should remove items no longer in column."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        # Manually add items to queue
        await service.enqueue_item("proj-1", "board-1", "item-1", position_in_column=0, timestamp=now)
        await service.enqueue_item("proj-1", "board-1", "item-2", position_in_column=1, timestamp=now)
        await service.enqueue_item("proj-1", "board-1", "item-3", position_in_column=2, timestamp=now)

        # Set up board with only some items in column
        board_service.set_column("proj-1", "board-1", "TODO", ["item-1", "item-3"])

        # Clear events from enqueuing
        event_emitter.events.clear()

        # Sync should remove item-2
        await service.sync_queue_with_board("proj-1", "board-1", "TODO")

        entries = await service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 2
        assert {e.work_item_id for e in entries} == {"item-1", "item-3"}

    @pytest.mark.asyncio
    async def test_sync_queue_updates_positions(self):
        """sync_queue_with_board should update positions to match board."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        # Manually add items to queue with positions
        await service.enqueue_item("proj-1", "board-1", "item-1", position_in_column=0, timestamp=now)
        await service.enqueue_item("proj-1", "board-1", "item-2", position_in_column=1, timestamp=now)
        await service.enqueue_item("proj-1", "board-1", "item-3", position_in_column=2, timestamp=now)

        # Change board order
        board_service.set_column("proj-1", "board-1", "TODO", ["item-3", "item-1", "item-2"])

        # Clear events from enqueuing
        event_emitter.events.clear()

        # Sync should update positions
        await service.sync_queue_with_board("proj-1", "board-1", "TODO")

        entries = await service.get_queue_entries("proj-1", "board-1")
        # Should be sorted by position (which is now updated)
        assert entries[0].work_item_id == "item-3"
        assert entries[0].position_in_column == 0
        assert entries[1].work_item_id == "item-1"
        assert entries[1].position_in_column == 1
        assert entries[2].work_item_id == "item-2"
        assert entries[2].position_in_column == 2

        # Position change events should be emitted
        position_change_events = [e for e in event_emitter.events if isinstance(e, QueuePositionChangedEvent)]
        assert len(position_change_events) > 0

    @pytest.mark.asyncio
    async def test_sync_queue_gracefully_handles_board_service_failure(self):
        """sync_queue_with_board should not raise on board service failure."""
        redis_client = MockRedis()
        board_service = AsyncMock()
        board_service.get_board.side_effect = Exception("Board service error")
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        # This should not raise
        await service.sync_queue_with_board("proj-1", "board-1", "TODO")

    @pytest.mark.asyncio
    async def test_sync_queue_gracefully_handles_missing_column(self):
        """sync_queue_with_board should not raise when column not found."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        # Don't set up any columns
        # This should not raise
        await service.sync_queue_with_board("proj-1", "board-1", "NONEXISTENT")

    @pytest.mark.asyncio
    async def test_get_queue_entries_emits_corruption_event_on_missing_metadata(self):
        """get_queue_entries should emit corruption event and return best-effort entry for missing metadata."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        # Manually corrupt the queue by adding item to sorted set but not metadata
        queue_key = service._queue_key("proj-1", "board-1")
        await redis_client.zadd(queue_key, {"item-1": 0.0})

        # Get entries should return best-effort entry and emit corruption event
        event_emitter.events.clear()
        entries = await service.get_queue_entries("proj-1", "board-1")

        assert len(entries) == 1
        assert entries[0].work_item_id == "item-1"
        assert entries[0].position_in_column == 0
        assert entries[0].status == QueueStatus.WAITING
        corruption_events = [e for e in event_emitter.events if isinstance(e, QueueMetadataCorruptionEvent)]
        assert len(corruption_events) == 1
        assert corruption_events[0].work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_get_queue_entries_emits_corruption_event_on_malformed_metadata(self):
        """get_queue_entries should emit corruption event and return best-effort entry for malformed JSON."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        # Manually corrupt the queue with bad JSON
        queue_key = service._queue_key("proj-1", "board-1")
        meta_key = service._metadata_key("proj-1", "board-1")
        await redis_client.zadd(queue_key, {"item-1": 0.0})
        await redis_client.hset(meta_key, "item-1", "not valid json")

        # Get entries should return best-effort entry and emit corruption event
        event_emitter.events.clear()
        entries = await service.get_queue_entries("proj-1", "board-1")

        assert len(entries) == 1
        assert entries[0].work_item_id == "item-1"
        assert entries[0].position_in_column == 0
        assert entries[0].status == QueueStatus.WAITING
        corruption_events = [e for e in event_emitter.events if isinstance(e, QueueMetadataCorruptionEvent)]
        assert len(corruption_events) == 1
        assert corruption_events[0].work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_duplicate_enqueue_raises_error(self):
        """Enqueuing same item twice should raise DuplicateQueueEntryError."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        await service.enqueue_item("proj-1", "board-1", "item-123", position_in_column=0, timestamp=now)

        with pytest.raises(DuplicateQueueEntryError):
            await service.enqueue_item("proj-1", "board-1", "item-123", position_in_column=1, timestamp=now)

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_false(self):
        """Removing non-existent item should return False."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        result = await service.remove_from_queue("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_key_prefix_isolation(self):
        """Services with different key prefixes should not interfere."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter1 = MockEventEmitter()
        event_emitter2 = MockEventEmitter()

        service1 = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter1,
            key_prefix="qsvc-1",
        )

        service2 = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter2,
            key_prefix="qsvc-2",
        )

        now = datetime.now(UTC)
        await service1.enqueue_item("proj-1", "board-1", "item-1", position_in_column=0, timestamp=now)
        await service2.enqueue_item("proj-1", "board-1", "item-2", position_in_column=0, timestamp=now)

        # Items should not interfere
        entries1 = await service1.get_queue_entries("proj-1", "board-1")
        entries2 = await service2.get_queue_entries("proj-1", "board-1")

        assert len(entries1) == 1
        assert entries1[0].work_item_id == "item-1"

        assert len(entries2) == 1
        assert entries2[0].work_item_id == "item-2"

    # ===== Restart Durability Tests =====

    @pytest.mark.asyncio
    async def test_restart_durability_queued_item_survives(self):
        """Verify a queued item survives process restart in Redis."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        # Enqueue a work item
        await service.enqueue_item("proj-1", "board-1", "item-123", position_in_column=0, timestamp=now)

        # Verify item is in queue before "restart"
        assert await service.is_item_in_queue("item-123") is True
        entries = await service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 1
        assert entries[0].work_item_id == "item-123"

        # Simulate process restart by creating new service with same Redis client
        new_service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=MockEventEmitter(),
        )

        # Verify item still in queue after "restart"
        assert await new_service.is_item_in_queue("item-123") is True
        entries = await new_service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 1
        assert entries[0].work_item_id == "item-123"
        assert entries[0].status == QueueStatus.WAITING
        assert entries[0].position_in_column == 0

    @pytest.mark.asyncio
    async def test_restart_durability_multiple_items_preserve_order(self):
        """Verify multiple queued items survive restart and maintain order."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        # Enqueue multiple items out of order
        await service.enqueue_item("proj-1", "board-1", "item-3", position_in_column=2, timestamp=now)
        await service.enqueue_item("proj-1", "board-1", "item-1", position_in_column=0, timestamp=now)
        await service.enqueue_item("proj-1", "board-1", "item-2", position_in_column=1, timestamp=now)

        # Verify order before restart
        entries_before = await service.get_queue_entries("proj-1", "board-1")
        assert len(entries_before) == 3
        assert [e.work_item_id for e in entries_before] == ["item-1", "item-2", "item-3"]
        assert [e.position_in_column for e in entries_before] == [0, 1, 2]

        # Simulate process restart
        new_service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=MockEventEmitter(),
        )

        # Verify order after restart
        entries_after = await new_service.get_queue_entries("proj-1", "board-1")
        assert len(entries_after) == 3
        assert [e.work_item_id for e in entries_after] == ["item-1", "item-2", "item-3"]
        assert [e.position_in_column for e in entries_after] == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_restart_durability_marked_active_item_preserved(self):
        """Verify marked-active items survive restart with status preserved."""
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        await service.enqueue_item("proj-1", "board-1", "item-1", position_in_column=0, timestamp=now)
        await service.enqueue_item("proj-1", "board-1", "item-2", position_in_column=1, timestamp=now)

        # Mark first item as active
        await service.mark_item_active("item-1")

        # Verify status before restart
        entries_before = await service.get_queue_entries("proj-1", "board-1")
        assert entries_before[0].work_item_id == "item-1"
        assert entries_before[0].status == QueueStatus.ACTIVE
        assert entries_before[1].work_item_id == "item-2"
        assert entries_before[1].status == QueueStatus.WAITING

        # Simulate process restart
        new_service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=MockEventEmitter(),
        )

        # Verify status after restart
        entries_after = await new_service.get_queue_entries("proj-1", "board-1")
        assert entries_after[0].work_item_id == "item-1"
        assert entries_after[0].status == QueueStatus.ACTIVE
        assert entries_after[1].work_item_id == "item-2"
        assert entries_after[1].status == QueueStatus.WAITING

    # ===== PipelineQueueServiceAdapter No-Duplicate-Events Tests =====

    @pytest.mark.asyncio
    async def test_adapter_no_duplicate_events_on_enqueue(self):
        """Verify PipelineQueueServiceAdapter doesn't emit duplicate events on enqueue."""
        from types import MappingProxyType

        from codetoreum.adapters.secondary.pipeline_queue_service_adapter import (
            PipelineQueueServiceAdapter,
        )
        from codetoreum.ports.output.pipeline_queue import QueueEntry

        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        adapter = PipelineQueueServiceAdapter(service)

        now = datetime.now(UTC)
        entry = QueueEntry(
            work_item_id="item-1",
            stage_name="ready",
            board_position=0,
            enqueued_at=now,
            metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
        )

        # Clear events and enqueue through adapter
        event_emitter.events.clear()
        result = await adapter.enqueue("proj-1:board-1", entry)

        # Verify enqueue succeeded
        assert result.already_present is False

        # Verify exactly ONE QueueItemAddedEvent emitted (from service, not adapter)
        added_events = [e for e in event_emitter.events if isinstance(e, QueueItemAddedEvent)]
        assert len(added_events) == 1
        assert added_events[0].item_id == "item-1"
        assert added_events[0].source == "redis_pipeline_queue_service"

    @pytest.mark.asyncio
    async def test_adapter_no_duplicate_events_on_remove(self):
        """Verify PipelineQueueServiceAdapter doesn't emit duplicate events on remove."""
        from types import MappingProxyType

        from codetoreum.adapters.secondary.pipeline_queue_service_adapter import (
            PipelineQueueServiceAdapter,
        )
        from codetoreum.ports.output.pipeline_queue import QueueEntry

        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        adapter = PipelineQueueServiceAdapter(service)

        now = datetime.now(UTC)
        entry = QueueEntry(
            work_item_id="item-1",
            stage_name="ready",
            board_position=0,
            enqueued_at=now,
            metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
        )

        # Enqueue first
        await adapter.enqueue("proj-1:board-1", entry)
        event_emitter.events.clear()

        # Remove through adapter
        result = await adapter.remove("proj-1:board-1", "item-1")

        # Verify removal succeeded
        assert result is True

        # Verify exactly ONE QueueItemRemovedEvent emitted (from service, not adapter)
        removed_events = [e for e in event_emitter.events if isinstance(e, QueueItemRemovedEvent)]
        assert len(removed_events) == 1
        assert removed_events[0].item_id == "item-1"
        assert removed_events[0].source == "redis_pipeline_queue_service"

    # ===== Orphan Recovery Integration Tests =====

    @pytest.mark.asyncio
    async def test_restart_with_held_lock_and_queued_items(self):
        """End-to-end restart scenario: held lock, process restart, orphan-recovery scan.

        This test verifies acceptance criterion 3: enqueue a work item while a pipeline lock
        is held, terminate the process, restart it, and confirm (a) the queue entry survives
        with correct ordering, and (b) PipelineOrchestrator.on_startup()'s orphan-recovery
        scan detects and releases the orphaned lock, allowing the surviving queue entry to
        become the next lock holder.
        """
        from types import MappingProxyType

        from codetoreum.adapters.secondary.pipeline_queue_service_adapter import (
            PipelineQueueServiceAdapter,
        )
        from codetoreum.application.event_handlers.pipeline_orchestrator import (
            PipelineOrchestrator,
        )
        from codetoreum.ports.output.distributed_lock import IDistributedLock, LockHolder, ReleaseResult

        # Phase 1: Original process - enqueue items with lock held
        redis_client = MockRedis()
        board_service = MockBoardService()
        event_emitter = MockEventEmitter()

        queue_service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=event_emitter,
        )

        now = datetime.now(UTC)
        project_id = "proj-1"
        board_id = "board-1"
        lock_key = f"{project_id}:{board_id}"

        # Enqueue multiple items
        await queue_service.enqueue_item(project_id, board_id, "item-1", position_in_column=0, timestamp=now)
        await queue_service.enqueue_item(project_id, board_id, "item-2", position_in_column=1, timestamp=now)
        await queue_service.enqueue_item(project_id, board_id, "item-3", position_in_column=2, timestamp=now)

        # Verify items are queued
        entries_before = await queue_service.get_queue_entries(project_id, board_id)
        assert len(entries_before) == 3
        assert [e.work_item_id for e in entries_before] == ["item-1", "item-2", "item-3"]

        # Simulate a lock being held by item-1 (orphaned because no active run)
        mock_lock = MagicMock(spec=IDistributedLock)
        mock_lock.try_acquire = AsyncMock()
        mock_lock.release = AsyncMock()
        mock_lock.get_all_holders = AsyncMock()

        # Setup: one lock held by item-1, no active runs
        lock_holder = LockHolder(
            lock_key=lock_key,
            holder_id="item-1",
            acquired_at=now,
            ttl_seconds=7200,
            expires_at=now,
            holder_metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )
        mock_lock.get_all_holders.return_value = [lock_holder]

        # Release will succeed
        mock_lock.release.return_value = ReleaseResult(released=True, reason=None, lock_key=lock_key)

        # Mock run registry with no active runs
        mock_run_registry = MagicMock()
        mock_run_registry.get_active_run = AsyncMock(return_value=None)

        mock_event_emitter_orch = MagicMock()
        mock_event_emitter_orch.emit = MagicMock()

        # Phase 2: Process restart - create new instances with same Redis
        new_queue_service = RedisPipelineQueueService(
            redis_client=redis_client,
            board_service=board_service,
            event_emitter=MockEventEmitter(),
        )

        # Verify queue entries survived restart
        entries_after = await new_queue_service.get_queue_entries(project_id, board_id)
        assert len(entries_after) == 3
        assert [e.work_item_id for e in entries_after] == ["item-1", "item-2", "item-3"]

        # Phase 3: on_startup() detects orphaned lock and releases it
        # Create adapter to bridge IPipelineQueueService to IPipelineQueue
        queue_adapter = PipelineQueueServiceAdapter(new_queue_service)

        # Create PipelineOrchestrator with mock lock/registry and adapted queue
        orchestrator = PipelineOrchestrator(
            distributed_lock=mock_lock,
            pipeline_queue=queue_adapter,
            run_registry=mock_run_registry,
            event_emitter=mock_event_emitter_orch,
        )

        # Run the orphan-recovery scan
        await orchestrator.on_startup()

        # Phase 4: Verify outcomes
        # 1. Orphaned lock was detected and released
        mock_lock.get_all_holders.assert_called_once()
        mock_lock.release.assert_called_once_with(lock_key=lock_key, holder_id="item-1")

        # 2. Queue entries still exist and are retrievable
        entries_final = await new_queue_service.get_queue_entries(project_id, board_id)
        assert len(entries_final) == 3
        assert [e.work_item_id for e in entries_final] == ["item-1", "item-2", "item-3"]

        # 3. The surviving queue entry is still available for the next lock holder to claim
        next_entry = await queue_adapter.peek(lock_key)
        assert next_entry is not None
        assert next_entry.work_item_id == "item-1"  # First item in queue (after restart)
