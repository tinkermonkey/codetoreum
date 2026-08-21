"""Contract tests for IPipelineQueue interface.

These abstract tests define the contract that all IPipelineQueue
implementations must satisfy. Subclasses provide specific implementations
to test via create_queue().
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from codetoreum.ports.output.pipeline_queue import IPipelineQueue, QueueEntry


class TestPipelineQueueContract(ABC):
    """Abstract contract tests for IPipelineQueue implementations.

    Subclasses must implement create_queue() to provide a concrete
    IPipelineQueue implementation to test.

    These tests verify:
    - Queue enqueue/dequeue semantics
    - FIFO ordering and position tracking
    - Idempotency of operations
    - Metadata preservation
    - Edge cases and error handling
    """

    @abstractmethod
    async def create_queue(self) -> IPipelineQueue:
        """Create and return an IPipelineQueue instance for testing."""

    # ===== enqueue Tests =====

    @pytest.mark.asyncio
    async def test_enqueue_single_item(self):
        """Enqueuing an item should succeed."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry(
            work_item_id="item-1",
            stage_name="In Progress",
            board_position=0,
            enqueued_at=now,
            metadata=MappingProxyType({"key": "value"}),
        )

        result = await queue.enqueue("queue-1", entry)

        assert result.position == 0
        assert result.already_present is False

    @pytest.mark.asyncio
    async def test_enqueue_idempotent(self):
        """Enqueuing same item twice should be idempotent."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry(
            work_item_id="item-1",
            stage_name="In Progress",
            board_position=0,
            enqueued_at=now,
            metadata={},
        )

        result1 = await queue.enqueue("queue-1", entry)
        result2 = await queue.enqueue("queue-1", entry)

        assert result1.already_present is False
        assert result2.already_present is True
        assert result2.position == 0

    @pytest.mark.asyncio
    async def test_enqueue_multiple_items_fifo_order(self):
        """Items should be ordered FIFO."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        entry1 = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))
        entry2 = QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({}))
        entry3 = QueueEntry("item-3", "In Progress", 2, now, MappingProxyType({}))

        result1 = await queue.enqueue("queue-1", entry1)
        result2 = await queue.enqueue("queue-1", entry2)
        result3 = await queue.enqueue("queue-1", entry3)

        assert result1.position == 0
        assert result2.position == 1
        assert result3.position == 2

    @pytest.mark.asyncio
    async def test_enqueue_returns_position(self):
        """Enqueue should return correct position."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        entry1 = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))
        entry2 = QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({}))

        result1 = await queue.enqueue("queue-1", entry1)
        result2 = await queue.enqueue("queue-1", entry2)

        assert result1.position == 0
        assert result2.position == 1

    @pytest.mark.asyncio
    async def test_enqueue_preserves_metadata(self):
        """Metadata should be preserved."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        metadata = {"project_id": "proj-1", "board_id": "board-1"}
        entry = QueueEntry("item-1", "In Progress", 0, now, metadata)

        await queue.enqueue("queue-1", entry)
        entries = await queue.list("queue-1")

        assert entries[0].metadata == metadata

    # ===== peek Tests =====

    @pytest.mark.asyncio
    async def test_peek_empty_queue_returns_none(self):
        """Peeking empty queue should return None."""
        queue = await self.create_queue()

        result = await queue.peek("queue-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_peek_returns_head(self):
        """Peek should return head entry."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))

        await queue.enqueue("queue-1", entry)
        result = await queue.peek("queue-1")

        assert result is not None
        assert result.work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_peek_does_not_remove(self):
        """Peek should not remove entry."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))

        await queue.enqueue("queue-1", entry)
        await queue.peek("queue-1")
        length = await queue.length("queue-1")

        assert length == 1

    @pytest.mark.asyncio
    async def test_peek_multiple_items_returns_head(self):
        """Peek with multiple items should return first."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({})))

        result = await queue.peek("queue-1")

        assert result.work_item_id == "item-1"

    # ===== pop Tests =====

    @pytest.mark.asyncio
    async def test_pop_empty_queue_returns_none(self):
        """Popping empty queue should return None."""
        queue = await self.create_queue()

        result = await queue.pop("queue-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_pop_returns_head(self):
        """Pop should return head entry."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))

        await queue.enqueue("queue-1", entry)
        result = await queue.pop("queue-1")

        assert result is not None
        assert result.work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_pop_removes_entry(self):
        """Pop should remove entry from queue."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))

        await queue.enqueue("queue-1", entry)
        await queue.pop("queue-1")
        length = await queue.length("queue-1")

        assert length == 0

    @pytest.mark.asyncio
    async def test_pop_fifo_order(self):
        """Pop should return items in FIFO order."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-3", "In Progress", 2, now, MappingProxyType({})))

        r1 = await queue.pop("queue-1")
        r2 = await queue.pop("queue-1")
        r3 = await queue.pop("queue-1")

        assert r1.work_item_id == "item-1"
        assert r2.work_item_id == "item-2"
        assert r3.work_item_id == "item-3"

    # ===== contains Tests =====

    @pytest.mark.asyncio
    async def test_contains_returns_false_for_empty_queue(self):
        """Contains should return False for empty queue."""
        queue = await self.create_queue()

        result = await queue.contains("queue-1", "item-1")

        assert result is False

    @pytest.mark.asyncio
    async def test_contains_returns_true_for_enqueued_item(self):
        """Contains should return True for enqueued item."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))

        await queue.enqueue("queue-1", entry)
        result = await queue.contains("queue-1", "item-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_contains_returns_false_for_removed_item(self):
        """Contains should return False after removal."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))

        await queue.enqueue("queue-1", entry)
        await queue.remove("queue-1", "item-1")
        result = await queue.contains("queue-1", "item-1")

        assert result is False

    # ===== remove Tests =====

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_false(self):
        """Removing nonexistent item should return False."""
        queue = await self.create_queue()

        result = await queue.remove("queue-1", "item-1")

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_existing_returns_true(self):
        """Removing existing item should return True."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))

        await queue.enqueue("queue-1", entry)
        result = await queue.remove("queue-1", "item-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_remove_idempotent(self):
        """Removing twice should be idempotent."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))

        await queue.enqueue("queue-1", entry)
        await queue.remove("queue-1", "item-1")
        result = await queue.remove("queue-1", "item-1")

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_from_middle(self):
        """Removing from middle should work."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-3", "In Progress", 2, now, MappingProxyType({})))

        await queue.remove("queue-1", "item-2")

        entries = await queue.list("queue-1")
        assert len(entries) == 2
        assert entries[0].work_item_id == "item-1"
        assert entries[1].work_item_id == "item-3"

    # ===== length Tests =====

    @pytest.mark.asyncio
    async def test_length_empty_queue(self):
        """Length should be 0 for empty queue."""
        queue = await self.create_queue()

        length = await queue.length("queue-1")

        assert length == 0

    @pytest.mark.asyncio
    async def test_length_tracks_additions(self):
        """Length should increase with additions."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        assert await queue.length("queue-1") == 0

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({})))
        assert await queue.length("queue-1") == 1

        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({})))
        assert await queue.length("queue-1") == 2

    @pytest.mark.asyncio
    async def test_length_tracks_removals(self):
        """Length should decrease with removals."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({})))

        assert await queue.length("queue-1") == 2

        await queue.pop("queue-1")
        assert await queue.length("queue-1") == 1

    # ===== list Tests =====

    @pytest.mark.asyncio
    async def test_list_empty_queue(self):
        """List should return empty list for empty queue."""
        queue = await self.create_queue()

        result = await queue.list("queue-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_list_returns_all_entries(self):
        """List should return all entries."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({})))

        result = await queue.list("queue-1")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_fifo_order(self):
        """List should return entries in FIFO order."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-3", "In Progress", 2, now, MappingProxyType({})))

        result = await queue.list("queue-1")

        assert result[0].work_item_id == "item-1"
        assert result[1].work_item_id == "item-2"
        assert result[2].work_item_id == "item-3"

    # ===== position_of Tests =====

    @pytest.mark.asyncio
    async def test_position_of_nonexistent_returns_none(self):
        """Position of nonexistent item should be None."""
        queue = await self.create_queue()

        result = await queue.position_of("queue-1", "item-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_position_of_head(self):
        """Position of head should be 0."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({})))
        result = await queue.position_of("queue-1", "item-1")

        assert result == 0

    @pytest.mark.asyncio
    async def test_position_of_middle(self):
        """Position of middle item should be correct."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({})))
        await queue.enqueue("queue-1", QueueEntry("item-3", "In Progress", 2, now, MappingProxyType({})))

        result = await queue.position_of("queue-1", "item-2")

        assert result == 1

    # ===== Independent Queues Tests =====

    @pytest.mark.asyncio
    async def test_independent_queue_keys(self):
        """Different queue keys should be independent."""
        queue = await self.create_queue()
        now = datetime.now(UTC)

        await queue.enqueue("queue-1", QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({})))
        await queue.enqueue("queue-2", QueueEntry("item-2", "In Progress", 0, now, MappingProxyType({})))

        result1 = await queue.list("queue-1")
        result2 = await queue.list("queue-2")

        assert len(result1) == 1
        assert len(result2) == 1
        assert result1[0].work_item_id == "item-1"
        assert result2[0].work_item_id == "item-2"

    # ===== Queue Entry Immutability Tests =====

    @pytest.mark.asyncio
    async def test_queue_entries_are_immutable(self):
        """Queue entries should be immutable (frozen dataclasses)."""
        queue = await self.create_queue()
        now = datetime.now(UTC)
        entry = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))

        await queue.enqueue("queue-1", entry)
        entries = await queue.list("queue-1")
        returned_entry = entries[0]

        # Attempt to modify should fail
        with pytest.raises((AttributeError, TypeError, Exception)):
            returned_entry.work_item_id = "modified"
