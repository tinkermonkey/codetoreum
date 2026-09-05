"""Tests for PipelineQueueServiceAdapter.

Tests the adapter's implementation of IPipelineQueue interface by delegating
to an IPipelineQueueService. Verifies all methods (enqueue, peek, pop, length,
list, position_of) are properly implemented and handle edge cases.
"""

from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from codetoreum.adapters.secondary.pipeline_queue_service_adapter import PipelineQueueServiceAdapter
from codetoreum.adapters.testing.in_memory_queue_service import InMemoryQueueService
from codetoreum.ports.output.pipeline_queue import QueueEntry
from codetoreum.ports.output.pipeline_queue_service import DuplicateQueueEntryError


@pytest.fixture
async def queue_service():
    """Create an in-memory queue service for testing."""
    service = InMemoryQueueService()
    # No setup needed; service starts empty
    return service


@pytest.fixture
async def adapter(queue_service):
    """Create a PipelineQueueServiceAdapter wrapping the test service."""
    return PipelineQueueServiceAdapter(queue_service)


@pytest.mark.asyncio
async def test_enqueue_adds_item(adapter, queue_service):
    """enqueue() should add item to the queue."""
    queue_key = "proj-1:board-1"
    entry = QueueEntry(
        work_item_id="item-1",
        stage_name="ready",
        board_position=0,
        enqueued_at=datetime.now(UTC),
        metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
    )

    result = await adapter.enqueue(queue_key, entry)

    assert result.already_present is False
    assert result.position == 0
    assert await queue_service.is_item_in_queue("item-1")


@pytest.mark.asyncio
async def test_enqueue_idempotent(adapter, queue_service):
    """enqueue() should be idempotent on duplicate work_item_id."""
    queue_key = "proj-1:board-1"
    entry = QueueEntry(
        work_item_id="item-1",
        stage_name="ready",
        board_position=0,
        enqueued_at=datetime.now(UTC),
        metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
    )

    # First enqueue succeeds
    result1 = await adapter.enqueue(queue_key, entry)
    assert result1.already_present is False

    # Second enqueue returns already_present=True
    result2 = await adapter.enqueue(queue_key, entry)
    assert result2.already_present is True
    assert result2.position == 0


@pytest.mark.asyncio
async def test_enqueue_invalid_queue_key(adapter):
    """enqueue() should raise ValueError for invalid queue_key format."""
    queue_key = "invalid-no-colon"
    entry = QueueEntry(
        work_item_id="item-1",
        stage_name="ready",
        board_position=0,
        enqueued_at=datetime.now(UTC),
        metadata=MappingProxyType({}),
    )

    with pytest.raises(ValueError, match="Invalid queue_key format"):
        await adapter.enqueue(queue_key, entry)


@pytest.mark.asyncio
async def test_peek_returns_head(adapter):
    """peek() should return the head entry without removing it."""
    queue_key = "proj-1:board-1"
    now = datetime.now(UTC)
    entry1 = QueueEntry(
        work_item_id="item-1",
        stage_name="ready",
        board_position=0,
        enqueued_at=now,
        metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
    )
    entry2 = QueueEntry(
        work_item_id="item-2",
        stage_name="ready",
        board_position=1,
        enqueued_at=now,
        metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
    )

    await adapter.enqueue(queue_key, entry1)
    await adapter.enqueue(queue_key, entry2)

    # Peek should return head without removing
    peeked = await adapter.peek(queue_key)
    assert peeked is not None
    assert peeked.work_item_id == "item-1"

    # Item should still be there after peek
    length = await adapter.length(queue_key)
    assert length == 2


@pytest.mark.asyncio
async def test_peek_empty_queue(adapter):
    """peek() should return None for empty queue."""
    queue_key = "proj-1:board-1"

    result = await adapter.peek(queue_key)

    assert result is None


@pytest.mark.asyncio
async def test_peek_invalid_queue_key(adapter):
    """peek() should raise ValueError for invalid queue_key format."""
    queue_key = "invalid-no-colon"

    with pytest.raises(ValueError, match="Invalid queue_key format"):
        await adapter.peek(queue_key)


@pytest.mark.asyncio
async def test_pop_removes_and_returns_head(adapter):
    """pop() should atomically remove and return the head entry."""
    queue_key = "proj-1:board-1"
    now = datetime.now(UTC)
    entry1 = QueueEntry(
        work_item_id="item-1",
        stage_name="ready",
        board_position=0,
        enqueued_at=now,
        metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
    )
    entry2 = QueueEntry(
        work_item_id="item-2",
        stage_name="ready",
        board_position=1,
        enqueued_at=now,
        metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
    )

    await adapter.enqueue(queue_key, entry1)
    await adapter.enqueue(queue_key, entry2)

    # Pop should remove and return head
    popped = await adapter.pop(queue_key)
    assert popped is not None
    assert popped.work_item_id == "item-1"

    # Queue should now have only item-2
    length = await adapter.length(queue_key)
    assert length == 1
    peek_result = await adapter.peek(queue_key)
    assert peek_result.work_item_id == "item-2"


@pytest.mark.asyncio
async def test_pop_empty_queue(adapter):
    """pop() should return None for empty queue."""
    queue_key = "proj-1:board-1"

    result = await adapter.pop(queue_key)

    assert result is None


@pytest.mark.asyncio
async def test_pop_invalid_queue_key(adapter):
    """pop() should raise ValueError for invalid queue_key format."""
    queue_key = "invalid-no-colon"

    with pytest.raises(ValueError, match="Invalid queue_key format"):
        await adapter.pop(queue_key)


@pytest.mark.asyncio
async def test_length_returns_queue_depth(adapter):
    """length() should return the number of items in the queue."""
    queue_key = "proj-1:board-1"
    now = datetime.now(UTC)

    # Empty queue
    length = await adapter.length(queue_key)
    assert length == 0

    # Add items
    for i in range(3):
        entry = QueueEntry(
            work_item_id=f"item-{i}",
            stage_name="ready",
            board_position=i,
            enqueued_at=now,
            metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
        )
        await adapter.enqueue(queue_key, entry)

    length = await adapter.length(queue_key)
    assert length == 3


@pytest.mark.asyncio
async def test_length_invalid_queue_key(adapter):
    """length() should raise ValueError for invalid queue_key format."""
    queue_key = "invalid-no-colon"

    with pytest.raises(ValueError, match="Invalid queue_key format"):
        await adapter.length(queue_key)


@pytest.mark.asyncio
async def test_list_returns_all_entries(adapter):
    """list() should return all entries in FIFO order."""
    queue_key = "proj-1:board-1"
    now = datetime.now(UTC)
    entries = []

    # Add entries
    for i in range(3):
        entry = QueueEntry(
            work_item_id=f"item-{i}",
            stage_name="ready",
            board_position=i,
            enqueued_at=now,
            metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
        )
        await adapter.enqueue(queue_key, entry)
        entries.append(entry)

    # List should return all entries
    listed = await adapter.list(queue_key)
    assert len(listed) == 3
    assert [e.work_item_id for e in listed] == ["item-0", "item-1", "item-2"]


@pytest.mark.asyncio
async def test_list_empty_queue(adapter):
    """list() should return empty list for empty queue."""
    queue_key = "proj-1:board-1"

    result = await adapter.list(queue_key)

    assert result == []


@pytest.mark.asyncio
async def test_list_invalid_queue_key(adapter):
    """list() should raise ValueError for invalid queue_key format."""
    queue_key = "invalid-no-colon"

    with pytest.raises(ValueError, match="Invalid queue_key format"):
        await adapter.list(queue_key)


@pytest.mark.asyncio
async def test_position_of_returns_position(adapter):
    """position_of() should return the 0-indexed position of an item."""
    queue_key = "proj-1:board-1"
    now = datetime.now(UTC)

    # Add entries
    for i in range(3):
        entry = QueueEntry(
            work_item_id=f"item-{i}",
            stage_name="ready",
            board_position=i,
            enqueued_at=now,
            metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
        )
        await adapter.enqueue(queue_key, entry)

    # Check positions
    assert await adapter.position_of(queue_key, "item-0") == 0
    assert await adapter.position_of(queue_key, "item-1") == 1
    assert await adapter.position_of(queue_key, "item-2") == 2


@pytest.mark.asyncio
async def test_position_of_nonexistent_returns_none(adapter):
    """position_of() should return None for nonexistent item."""
    queue_key = "proj-1:board-1"

    result = await adapter.position_of(queue_key, "nonexistent-item")

    assert result is None


@pytest.mark.asyncio
async def test_position_of_invalid_queue_key(adapter):
    """position_of() should raise ValueError for invalid queue_key format."""
    queue_key = "invalid-no-colon"

    with pytest.raises(ValueError, match="Invalid queue_key format"):
        await adapter.position_of(queue_key, "item-1")


@pytest.mark.asyncio
async def test_contains_returns_true_for_queued_item(adapter):
    """contains() should return True for items in the queue."""
    queue_key = "proj-1:board-1"
    entry = QueueEntry(
        work_item_id="item-1",
        stage_name="ready",
        board_position=0,
        enqueued_at=datetime.now(UTC),
        metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
    )

    await adapter.enqueue(queue_key, entry)

    assert await adapter.contains(queue_key, "item-1") is True


@pytest.mark.asyncio
async def test_contains_returns_false_for_nonexistent_item(adapter):
    """contains() should return False for items not in the queue."""
    queue_key = "proj-1:board-1"

    result = await adapter.contains(queue_key, "nonexistent-item")

    assert result is False


@pytest.mark.asyncio
async def test_remove_deletes_item(adapter):
    """remove() should remove an item from the queue."""
    queue_key = "proj-1:board-1"
    entry = QueueEntry(
        work_item_id="item-1",
        stage_name="ready",
        board_position=0,
        enqueued_at=datetime.now(UTC),
        metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
    )

    await adapter.enqueue(queue_key, entry)
    result = await adapter.remove(queue_key, "item-1")

    assert result is True
    assert await adapter.contains(queue_key, "item-1") is False


@pytest.mark.asyncio
async def test_remove_nonexistent_returns_false(adapter):
    """remove() should return False for nonexistent items."""
    queue_key = "proj-1:board-1"

    result = await adapter.remove(queue_key, "nonexistent-item")

    assert result is False


@pytest.mark.asyncio
async def test_queue_key_parsing_with_colons_in_values(adapter):
    """Queue key parsing should handle project/board IDs correctly."""
    # Queue key is project_id:board_id; IDs shouldn't have colons but
    # the adapter should split on the first colon only
    queue_key = "proj:with:colons:board:with:colons"
    entry = QueueEntry(
        work_item_id="item-1",
        stage_name="ready",
        board_position=0,
        enqueued_at=datetime.now(UTC),
        metadata=MappingProxyType({}),
    )

    # This should parse "proj:with:colons" as project_id and
    # "board:with:colons" as board_id
    result = await adapter.enqueue(queue_key, entry)
    assert result.already_present is False


@pytest.mark.asyncio
async def test_multiple_queues_independent(adapter):
    """Different queue_keys should maintain independent queues."""
    entry1 = QueueEntry(
        work_item_id="item-1",
        stage_name="ready",
        board_position=0,
        enqueued_at=datetime.now(UTC),
        metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
    )
    entry2 = QueueEntry(
        work_item_id="item-2",
        stage_name="ready",
        board_position=0,
        enqueued_at=datetime.now(UTC),
        metadata=MappingProxyType({"project_id": "proj-2", "board_id": "board-2"}),
    )

    await adapter.enqueue("proj-1:board-1", entry1)
    await adapter.enqueue("proj-2:board-2", entry2)

    # Each queue should have its own item
    assert await adapter.length("proj-1:board-1") == 1
    assert await adapter.length("proj-2:board-2") == 1

    # List operations should be queue-specific
    list1 = await adapter.list("proj-1:board-1")
    list2 = await adapter.list("proj-2:board-2")
    assert len(list1) == 1
    assert len(list2) == 1
    assert list1[0].work_item_id == "item-1"
    assert list2[0].work_item_id == "item-2"

    # Position checks should be queue-specific
    assert await adapter.position_of("proj-1:board-1", "item-1") == 0
    assert await adapter.position_of("proj-2:board-2", "item-2") == 0
    assert await adapter.position_of("proj-1:board-1", "item-2") is None
    assert await adapter.position_of("proj-2:board-2", "item-1") is None


@pytest.mark.asyncio
async def test_integration_enqueue_peek_pop_sequence(adapter):
    """Integration test: enqueue multiple items, peek, and pop in sequence."""
    queue_key = "proj-1:board-1"
    now = datetime.now(UTC)

    # Enqueue three items
    for i in range(3):
        entry = QueueEntry(
            work_item_id=f"item-{i}",
            stage_name="ready",
            board_position=i,
            enqueued_at=now,
            metadata=MappingProxyType({"project_id": "proj-1", "board_id": "board-1"}),
        )
        await adapter.enqueue(queue_key, entry)

    # Verify length
    assert await adapter.length(queue_key) == 3

    # Peek should return first item without removing
    peeked = await adapter.peek(queue_key)
    assert peeked.work_item_id == "item-0"
    assert await adapter.length(queue_key) == 3

    # Pop should remove and return first item
    popped = await adapter.pop(queue_key)
    assert popped.work_item_id == "item-0"
    assert await adapter.length(queue_key) == 2

    # List should show remaining items
    items = await adapter.list(queue_key)
    assert len(items) == 2
    assert items[0].work_item_id == "item-1"
    assert items[1].work_item_id == "item-2"

    # Position checks
    assert await adapter.position_of(queue_key, "item-1") == 0
    assert await adapter.position_of(queue_key, "item-2") == 1
    assert await adapter.position_of(queue_key, "item-0") is None
