"""Unit tests for InMemoryQueueService implementation.

Tests cover:
- Basic queue operations (enqueue, dequeue, status checks)
- Board position ordering and synchronization
- Immutability of queue entries
- Thread-safe concurrent operations
- Error handling and validation
- Edge cases
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.testing.in_memory_queue_service import InMemoryQueueService
from codetoreum.ports.output.board_service import (
    BoardColumn,
    IBoardService,
    ProjectBoard,
)
from codetoreum.ports.output.pipeline_queue_service import (
    DuplicateQueueEntryError,
    InvalidQueueStateError,
    QueueItemNotFoundError,
    QueueStatus,
    QueueValidationError,
)


@pytest.fixture
def queue_service():
    """Fixture to create a fresh InMemoryQueueService for each test."""
    return InMemoryQueueService()


@pytest.fixture
def queue_service_with_board():
    """Fixture to create queue service with mock board service."""
    board_service = AsyncMock(spec=IBoardService)
    return InMemoryQueueService(board_service=board_service), board_service


class TestEnqueueOperations:
    """Tests for enqueue_item method."""

    @pytest.mark.asyncio
    async def test_enqueue_item_creates_waiting_entry(self, queue_service):
        """Enqueuing item should create entry with status='waiting'."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            position_in_column=0,
            timestamp=now,
        )

        entries = await queue_service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 1
        assert entries[0].work_item_id == "item-1"
        assert entries[0].status == QueueStatus.WAITING
        assert entries[0].position_in_column == 0

    @pytest.mark.asyncio
    async def test_enqueue_item_is_frozen_immutable(self, queue_service):
        """Queue entries should be frozen dataclasses (immutable)."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            position_in_column=0,
            timestamp=now,
        )

        entries = await queue_service.get_queue_entries("proj-1", "board-1")
        entry = entries[0]

        # Attempt to modify should raise FrozenInstanceError
        with pytest.raises(Exception):  # FrozenInstanceError
            entry.status = "active"

    @pytest.mark.asyncio
    async def test_enqueue_duplicate_item_raises_error(self, queue_service):
        """Enqueuing same item twice should raise DuplicateQueueEntryError."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            position_in_column=0,
            timestamp=now,
        )

        with pytest.raises(DuplicateQueueEntryError, match="already in queue"):
            await queue_service.enqueue_item(
                project_id="proj-1",
                board_id="board-1",
                work_item_id="item-1",
                position_in_column=1,
                timestamp=now,
            )

    @pytest.mark.asyncio
    async def test_enqueue_empty_project_id_raises_error(self, queue_service):
        """Enqueue with empty project_id should raise QueueValidationError."""
        now = datetime.now(UTC)

        with pytest.raises(QueueValidationError, match="project_id cannot be empty"):
            await queue_service.enqueue_item(
                project_id="",
                board_id="board-1",
                work_item_id="item-1",
                position_in_column=0,
                timestamp=now,
            )

    @pytest.mark.asyncio
    async def test_enqueue_negative_position_raises_error(self, queue_service):
        """Enqueue with negative position should raise QueueValidationError."""
        now = datetime.now(UTC)

        with pytest.raises(QueueValidationError, match="position_in_column cannot be negative"):
            await queue_service.enqueue_item(
                project_id="proj-1",
                board_id="board-1",
                work_item_id="item-1",
                position_in_column=-1,
                timestamp=now,
            )

    @pytest.mark.asyncio
    async def test_enqueue_with_string_timestamp_converts(self, queue_service):
        """Enqueue should accept ISO 8601 string timestamp."""
        timestamp_str = "2025-01-15T10:30:00+00:00"

        await queue_service.enqueue_item(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            position_in_column=0,
            timestamp=timestamp_str,
        )

        entries = await queue_service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 1
        assert entries[0].queued_at is not None


class TestPositionOrdering:
    """Tests for position-based queue ordering."""

    @pytest.mark.asyncio
    async def test_queue_sorted_by_position_ascending(self, queue_service):
        """Queue should be sorted by position (lowest first = highest priority)."""
        now = datetime.now(UTC)

        # Enqueue items out of order
        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-3", position_in_column=2, timestamp=now
        )
        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-2", position_in_column=1, timestamp=now
        )

        entries = await queue_service.get_queue_entries("proj-1", "board-1")

        # Should be sorted by position
        assert entries[0].work_item_id == "item-1"
        assert entries[1].work_item_id == "item-2"
        assert entries[2].work_item_id == "item-3"
        assert entries[0].position_in_column == 0
        assert entries[1].position_in_column == 1
        assert entries[2].position_in_column == 2

    @pytest.mark.asyncio
    async def test_get_next_waiting_item_returns_highest_priority(self, queue_service):
        """get_next_waiting_item should return item with lowest position."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-2", position_in_column=2, timestamp=now
        )
        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )

        next_item = await queue_service.get_next_waiting_item("proj-1", "board-1")

        assert next_item is not None
        assert next_item.work_item_id == "item-1"
        assert next_item.position_in_column == 0

    @pytest.mark.asyncio
    async def test_get_next_waiting_item_skips_active_items(self, queue_service):
        """get_next_waiting_item should skip items with status='active'."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-2", position_in_column=1, timestamp=now
        )

        # Mark first as active
        await queue_service.mark_item_active("item-1")

        # Next waiting should be item-2
        next_item = await queue_service.get_next_waiting_item("proj-1", "board-1")
        assert next_item.work_item_id == "item-2"

    @pytest.mark.asyncio
    async def test_get_next_waiting_item_returns_none_when_empty(self, queue_service):
        """get_next_waiting_item should return None when queue is empty."""
        result = await queue_service.get_next_waiting_item("proj-1", "board-1")
        assert result is None


class TestStatusManagement:
    """Tests for item status management."""

    @pytest.mark.asyncio
    async def test_mark_item_active_changes_status(self, queue_service):
        """mark_item_active should change status to ACTIVE."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )

        await queue_service.mark_item_active("item-1")

        entries = await queue_service.get_queue_entries("proj-1", "board-1")
        assert entries[0].status == QueueStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_mark_item_active_not_found_raises_error(self, queue_service):
        """mark_item_active with non-existent item should raise QueueItemNotFoundError."""
        with pytest.raises(QueueItemNotFoundError, match="not found in any queue"):
            await queue_service.mark_item_active("nonexistent-item")

    @pytest.mark.asyncio
    async def test_mark_item_active_twice_raises_error(self, queue_service):
        """mark_item_active twice should raise InvalidQueueStateError."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )

        await queue_service.mark_item_active("item-1")

        with pytest.raises(InvalidQueueStateError, match="already marked active"):
            await queue_service.mark_item_active("item-1")


class TestRemovalOperations:
    """Tests for remove_from_queue method."""

    @pytest.mark.asyncio
    async def test_remove_from_queue_success(self, queue_service):
        """Removing existing item should succeed and return True."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )

        result = await queue_service.remove_from_queue("item-1")

        assert result is True
        entries = await queue_service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_remove_from_queue_not_found(self, queue_service):
        """Removing non-existent item should return False."""
        result = await queue_service.remove_from_queue("nonexistent-item")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_from_queue_empty_id_raises_error(self, queue_service):
        """Removing with empty item_id should raise QueueValidationError."""
        with pytest.raises(QueueValidationError, match="work_item_id cannot be empty"):
            await queue_service.remove_from_queue("")


class TestQueueQueries:
    """Tests for queue query methods."""

    @pytest.mark.asyncio
    async def test_is_item_in_queue_true(self, queue_service):
        """is_item_in_queue should return True for queued items."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )

        result = await queue_service.is_item_in_queue("item-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_item_in_queue_false(self, queue_service):
        """is_item_in_queue should return False for non-queued items."""
        result = await queue_service.is_item_in_queue("nonexistent-item")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_item_in_queue_after_removal(self, queue_service):
        """is_item_in_queue should return False after item is removed."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await queue_service.remove_from_queue("item-1")

        result = await queue_service.is_item_in_queue("item-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_queue_entries_returns_copy(self, queue_service):
        """get_queue_entries should return a copy, not original list."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )

        entries1 = await queue_service.get_queue_entries("proj-1", "board-1")
        entries2 = await queue_service.get_queue_entries("proj-1", "board-1")

        # Should be equal but not the same object
        assert entries1 == entries2
        assert entries1 is not entries2

    @pytest.mark.asyncio
    async def test_get_queue_entries_empty_board(self, queue_service):
        """get_queue_entries for non-existent board should return empty list."""
        entries = await queue_service.get_queue_entries("proj-1", "board-1")
        assert entries == []


class TestBoardSynchronization:
    """Tests for sync_queue_with_board method."""

    @pytest.mark.asyncio
    async def test_sync_queue_with_board_no_service(self, queue_service):
        """sync_queue_with_board should handle missing board service gracefully."""
        # Without board service, sync should just return (no-op)
        await queue_service.sync_queue_with_board(
            "proj-1", "board-1", "In Progress"
        )
        # Should not raise

    @pytest.mark.asyncio
    async def test_sync_queue_with_board_removes_items_not_in_column(
        self, queue_service_with_board
    ):
        """Sync should remove queue entries for items no longer in column."""
        service, board_service = queue_service_with_board
        now = datetime.now(UTC)

        # Setup initial queue
        await service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await service.enqueue_item(
            "proj-1", "board-1", "item-2", position_in_column=1, timestamp=now
        )

        # Setup board to only have item-2
        board = ProjectBoard(
            id="board-1",
            name="Test Board",
            project_id="proj-1",
            columns=[
                BoardColumn(
                    id="col-1",
                    name="In Progress",
                    position=0,
                    work_item_ids=["item-2"],
                )
            ],
        )
        board_service.get_board.return_value = board

        # Sync
        await service.sync_queue_with_board("proj-1", "board-1", "In Progress")

        # item-1 should be removed, item-2 should remain
        entries = await service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 1
        assert entries[0].work_item_id == "item-2"

    @pytest.mark.asyncio
    async def test_sync_queue_with_board_adds_new_items(
        self, queue_service_with_board
    ):
        """Sync should add queue entries for items newly discovered in column."""
        service, board_service = queue_service_with_board
        now = datetime.now(UTC)

        # Setup initial queue with only item-1
        await service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )

        # Setup board with items-1 and item-2
        board = ProjectBoard(
            id="board-1",
            name="Test Board",
            project_id="proj-1",
            columns=[
                BoardColumn(
                    id="col-1",
                    name="In Progress",
                    position=0,
                    work_item_ids=["item-1", "item-2"],
                )
            ],
        )
        board_service.get_board.return_value = board

        # Sync
        await service.sync_queue_with_board("proj-1", "board-1", "In Progress")

        # Both items should be in queue
        entries = await service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 2
        item_ids = {e.work_item_id for e in entries}
        assert item_ids == {"item-1", "item-2"}

    @pytest.mark.asyncio
    async def test_sync_queue_with_board_updates_positions(
        self, queue_service_with_board
    ):
        """Sync should update position_in_column based on board state."""
        service, board_service = queue_service_with_board
        now = datetime.now(UTC)

        # Setup initial queue (old positions)
        await service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await service.enqueue_item(
            "proj-1", "board-1", "item-2", position_in_column=1, timestamp=now
        )

        # Setup board with different positions (item-2 moved to top)
        board = ProjectBoard(
            id="board-1",
            name="Test Board",
            project_id="proj-1",
            columns=[
                BoardColumn(
                    id="col-1",
                    name="In Progress",
                    position=0,
                    work_item_ids=["item-2", "item-1"],  # Reversed order
                )
            ],
        )
        board_service.get_board.return_value = board

        # Sync
        await service.sync_queue_with_board("proj-1", "board-1", "In Progress")

        # Positions should be updated
        entries = await service.get_queue_entries("proj-1", "board-1")
        # item-2 should now be at position 0 (highest priority)
        assert entries[0].work_item_id == "item-2"
        assert entries[0].position_in_column == 0
        assert entries[1].work_item_id == "item-1"
        assert entries[1].position_in_column == 1



class TestConcurrency:
    """Tests for thread-safe operations."""

    @pytest.mark.asyncio
    async def test_concurrent_enqueue_operations(self, queue_service):
        """Multiple concurrent enqueues should be thread-safe."""
        import asyncio

        now = datetime.now(UTC)

        async def enqueue_item(item_id, position):
            await queue_service.enqueue_item(
                "proj-1", "board-1", item_id, position, now
            )

        # Simulate concurrent operations
        await asyncio.gather(
            enqueue_item("item-1", 0),
            enqueue_item("item-2", 1),
            enqueue_item("item-3", 2),
        )

        entries = await queue_service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 3


class TestMultipleQueues:
    """Tests for managing multiple independent queues."""

    @pytest.mark.asyncio
    async def test_independent_project_queues(self, queue_service):
        """Queues should be independent per project."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await queue_service.enqueue_item(
            "proj-2", "board-1", "item-2", position_in_column=0, timestamp=now
        )

        entries_proj1 = await queue_service.get_queue_entries("proj-1", "board-1")
        entries_proj2 = await queue_service.get_queue_entries("proj-2", "board-1")

        assert len(entries_proj1) == 1
        assert len(entries_proj2) == 1
        assert entries_proj1[0].work_item_id == "item-1"
        assert entries_proj2[0].work_item_id == "item-2"

    @pytest.mark.asyncio
    async def test_independent_board_queues(self, queue_service):
        """Queues should be independent per board."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await queue_service.enqueue_item(
            "proj-1", "board-2", "item-2", position_in_column=0, timestamp=now
        )

        entries_board1 = await queue_service.get_queue_entries("proj-1", "board-1")
        entries_board2 = await queue_service.get_queue_entries("proj-1", "board-2")

        assert len(entries_board1) == 1
        assert len(entries_board2) == 1
        assert entries_board1[0].work_item_id == "item-1"
        assert entries_board2[0].work_item_id == "item-2"

    @pytest.mark.asyncio
    async def test_is_item_in_queue_searches_all_queues(self, queue_service):
        """is_item_in_queue should search across all queues."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await queue_service.enqueue_item(
            "proj-2", "board-2", "item-2", position_in_column=0, timestamp=now
        )

        assert await queue_service.is_item_in_queue("item-1") is True
        assert await queue_service.is_item_in_queue("item-2") is True
        assert await queue_service.is_item_in_queue("item-3") is False


class TestTestHelpers:
    """Tests for test helper methods."""

    @pytest.mark.asyncio
    async def test_get_queue_state_for_testing(self, queue_service):
        """Test helper should return queue length and entries."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )

        length, entries = queue_service.get_queue_state_for_testing("proj-1", "board-1")

        assert length == 1
        assert len(entries) == 1

    @pytest.mark.asyncio
    async def test_clear_queue_for_testing(self, queue_service):
        """Test helper clear_queue_for_testing should clear specific queue."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await queue_service.enqueue_item(
            "proj-1", "board-2", "item-2", position_in_column=0, timestamp=now
        )

        queue_service.clear_queue_for_testing("proj-1", "board-1")

        entries_board1 = await queue_service.get_queue_entries("proj-1", "board-1")
        entries_board2 = await queue_service.get_queue_entries("proj-1", "board-2")

        assert len(entries_board1) == 0
        assert len(entries_board2) == 1

    @pytest.mark.asyncio
    async def test_clear_all_queues_for_testing(self, queue_service):
        """Test helper clear_all_queues_for_testing should clear all queues."""
        now = datetime.now(UTC)

        await queue_service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await queue_service.enqueue_item(
            "proj-2", "board-2", "item-2", position_in_column=0, timestamp=now
        )

        queue_service.clear_all_queues_for_testing()

        entries_proj1 = await queue_service.get_queue_entries("proj-1", "board-1")
        entries_proj2 = await queue_service.get_queue_entries("proj-2", "board-2")

        assert len(entries_proj1) == 0
        assert len(entries_proj2) == 0
