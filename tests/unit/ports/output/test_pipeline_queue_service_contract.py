"""Contract tests for IPipelineQueueService interface.

These abstract tests define the contract that all IPipelineQueueService
implementations must satisfy. Subclasses provide specific implementations
to test via create_service().
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime

import pytest

# Import FrozenInstanceError with fallback for older Python versions
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    FrozenInstanceError = AttributeError  # type: ignore

from codetoreum.ports.output.pipeline_queue_service import (
    IPipelineQueueService,
    QueueStatus,
    QueueValidationError,
)


class TestPipelineQueueServiceContract(ABC):
    """Abstract contract tests for IPipelineQueueService implementations.

    Subclasses must implement create_service() to provide a concrete
    IPipelineQueueService implementation to test.

    These tests verify:
    - Basic queue operations (enqueue, dequeue, check)
    - Board position-based ordering
    - Status management (waiting vs active)
    - Queue synchronization with board state
    - Error handling and validation
    - Edge cases and boundary conditions
    """

    @abstractmethod
    async def create_service(self) -> IPipelineQueueService:
        """Create and return an IPipelineQueueService instance for testing."""

    # ===== is_item_in_queue Tests =====

    @pytest.mark.asyncio
    async def test_is_item_in_queue_returns_false_for_empty(self):
        """is_item_in_queue should return False when queue is empty."""
        service = await self.create_service()
        result = await service.is_item_in_queue("item-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_item_in_queue_returns_true_when_enqueued(self):
        """is_item_in_queue should return True after enqueuing item."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=0, timestamp=now
        )

        result = await service.is_item_in_queue("item-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_item_in_queue_returns_false_after_removal(self):
        """is_item_in_queue should return False after removing item."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=0, timestamp=now
        )
        await service.remove_from_queue("item-123")

        result = await service.is_item_in_queue("item-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_item_in_queue_validates_empty_id(self):
        """is_item_in_queue should validate non-empty work_item_id."""
        service = await self.create_service()

        with pytest.raises(QueueValidationError):
            await service.is_item_in_queue("")

    # ===== enqueue_item Tests =====

    @pytest.mark.asyncio
    async def test_enqueue_item_creates_waiting_entry(self):
        """Enqueuing item should create entry with status='waiting'."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=0, timestamp=now
        )

        entries = await service.get_queue_entries("proj-1", "board-1")
        assert len(entries) == 1
        assert entries[0].work_item_id == "item-123"
        assert entries[0].status == QueueStatus.WAITING
        assert entries[0].position_in_column == 0

    @pytest.mark.asyncio
    async def test_enqueue_item_preserves_position(self):
        """Enqueuing item should preserve position_in_column."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=5, timestamp=now
        )

        entries = await service.get_queue_entries("proj-1", "board-1")
        assert entries[0].position_in_column == 5

    @pytest.mark.asyncio
    async def test_enqueue_item_duplicate_raises_error(self):
        """Enqueuing same item twice should raise error."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=0, timestamp=now
        )

        with pytest.raises(Exception):  # DuplicateError or RuntimeError
            await service.enqueue_item(
                "proj-1", "board-1", "item-123", position_in_column=1, timestamp=now
            )

    @pytest.mark.asyncio
    async def test_enqueue_item_validates_project_id(self):
        """enqueue_item should validate non-empty project_id."""
        service = await self.create_service()
        now = datetime.now(UTC)

        with pytest.raises(QueueValidationError):
            await service.enqueue_item(
                "", "board-1", "item-123", position_in_column=0, timestamp=now
            )

    @pytest.mark.asyncio
    async def test_enqueue_item_validates_board_id(self):
        """enqueue_item should validate non-empty board_id."""
        service = await self.create_service()
        now = datetime.now(UTC)

        with pytest.raises(QueueValidationError):
            await service.enqueue_item(
                "proj-1", "", "item-123", position_in_column=0, timestamp=now
            )

    @pytest.mark.asyncio
    async def test_enqueue_item_validates_work_item_id(self):
        """enqueue_item should validate non-empty work_item_id."""
        service = await self.create_service()
        now = datetime.now(UTC)

        with pytest.raises(QueueValidationError):
            await service.enqueue_item(
                "proj-1", "board-1", "", position_in_column=0, timestamp=now
            )

    @pytest.mark.asyncio
    async def test_enqueue_item_validates_position(self):
        """enqueue_item should validate non-negative position."""
        service = await self.create_service()
        now = datetime.now(UTC)

        with pytest.raises(QueueValidationError):
            await service.enqueue_item(
                "proj-1", "board-1", "item-123", position_in_column=-1, timestamp=now
            )

    # ===== mark_item_active Tests =====

    @pytest.mark.asyncio
    async def test_mark_item_active_changes_status(self):
        """mark_item_active should change status to 'active'."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=0, timestamp=now
        )
        await service.mark_item_active("item-123")

        entries = await service.get_queue_entries("proj-1", "board-1")
        assert entries[0].status == QueueStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_mark_item_active_not_found_raises_error(self):
        """mark_item_active should raise error for non-existent item."""
        service = await self.create_service()

        with pytest.raises(Exception):  # KeyError or NotFoundError
            await service.mark_item_active("nonexistent")

    @pytest.mark.asyncio
    async def test_mark_item_active_idempotent_or_raises_error(self):
        """mark_item_active should either be idempotent or raise on double-mark."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=0, timestamp=now
        )
        await service.mark_item_active("item-123")

        # Second call should either succeed (idempotent) or raise
        try:
            await service.mark_item_active("item-123")
        except Exception:
            pass  # Either behavior is acceptable per contract

    @pytest.mark.asyncio
    async def test_mark_item_active_validates_work_item_id(self):
        """mark_item_active should validate non-empty work_item_id."""
        service = await self.create_service()

        with pytest.raises(QueueValidationError):
            await service.mark_item_active("")

    # ===== remove_from_queue Tests =====

    @pytest.mark.asyncio
    async def test_remove_from_queue_success_returns_true(self):
        """Removing existing item should return True."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=0, timestamp=now
        )

        result = await service.remove_from_queue("item-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_from_queue_nonexistent_returns_false(self):
        """Removing non-existent item should return False."""
        service = await self.create_service()

        result = await service.remove_from_queue("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_from_queue_validates_work_item_id(self):
        """remove_from_queue should validate non-empty work_item_id."""
        service = await self.create_service()

        with pytest.raises(QueueValidationError):
            await service.remove_from_queue("")

    @pytest.mark.asyncio
    async def test_remove_from_queue_actually_removes_item(self):
        """Item should not be in queue after removal."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=0, timestamp=now
        )
        await service.remove_from_queue("item-123")

        assert await service.is_item_in_queue("item-123") is False

    # ===== get_next_waiting_item Tests =====

    @pytest.mark.asyncio
    async def test_get_next_waiting_item_returns_none_when_empty(self):
        """get_next_waiting_item should return None for empty queue."""
        service = await self.create_service()

        result = await service.get_next_waiting_item("proj-1", "board-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_next_waiting_item_returns_single_item(self):
        """get_next_waiting_item should return single waiting item."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=0, timestamp=now
        )

        result = await service.get_next_waiting_item("proj-1", "board-1")
        assert result is not None
        if result:
            assert result.work_item_id == "item-123"
            assert result.status == QueueStatus.WAITING

    @pytest.mark.asyncio
    async def test_get_next_waiting_item_returns_highest_priority(self):
        """get_next_waiting_item should return lowest position (highest priority)."""
        service = await self.create_service()
        now = datetime.now(UTC)

        # Enqueue out of order
        await service.enqueue_item(
            "proj-1", "board-1", "item-3", position_in_column=2, timestamp=now
        )
        await service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await service.enqueue_item(
            "proj-1", "board-1", "item-2", position_in_column=1, timestamp=now
        )

        result = await service.get_next_waiting_item("proj-1", "board-1")
        assert result is not None
        if result:
            assert result.work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_get_next_waiting_item_skips_active_items(self):
        """get_next_waiting_item should skip active items."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await service.enqueue_item(
            "proj-1", "board-1", "item-2", position_in_column=1, timestamp=now
        )

        await service.mark_item_active("item-1")

        result = await service.get_next_waiting_item("proj-1", "board-1")
        assert result is not None
        if result:
            assert result.work_item_id == "item-2"

    @pytest.mark.asyncio
    async def test_get_next_waiting_item_validates_project_id(self):
        """get_next_waiting_item should validate non-empty project_id."""
        service = await self.create_service()

        with pytest.raises(QueueValidationError):
            await service.get_next_waiting_item("", "board-1")

    @pytest.mark.asyncio
    async def test_get_next_waiting_item_validates_board_id(self):
        """get_next_waiting_item should validate non-empty board_id."""
        service = await self.create_service()

        with pytest.raises(QueueValidationError):
            await service.get_next_waiting_item("proj-1", "")

    # ===== get_queue_entries Tests =====

    @pytest.mark.asyncio
    async def test_get_queue_entries_returns_empty_list(self):
        """get_queue_entries should return empty list for non-existent queue."""
        service = await self.create_service()

        result = await service.get_queue_entries("proj-1", "board-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_queue_entries_returns_all_entries(self):
        """get_queue_entries should return all queue entries."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await service.enqueue_item(
            "proj-1", "board-1", "item-2", position_in_column=1, timestamp=now
        )

        result = await service.get_queue_entries("proj-1", "board-1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_queue_entries_sorted_by_position(self):
        """get_queue_entries should return entries sorted by position."""
        service = await self.create_service()
        now = datetime.now(UTC)

        # Enqueue out of order
        await service.enqueue_item(
            "proj-1", "board-1", "item-3", position_in_column=2, timestamp=now
        )
        await service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await service.enqueue_item(
            "proj-1", "board-1", "item-2", position_in_column=1, timestamp=now
        )

        result = await service.get_queue_entries("proj-1", "board-1")
        assert result[0].position_in_column == 0
        assert result[1].position_in_column == 1
        assert result[2].position_in_column == 2

    @pytest.mark.asyncio
    async def test_get_queue_entries_includes_active_items(self):
        """get_queue_entries should include both waiting and active items."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await service.mark_item_active("item-1")

        result = await service.get_queue_entries("proj-1", "board-1")
        assert len(result) == 1
        assert result[0].status == QueueStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_get_queue_entries_validates_project_id(self):
        """get_queue_entries should validate non-empty project_id."""
        service = await self.create_service()

        with pytest.raises(QueueValidationError):
            await service.get_queue_entries("", "board-1")

    @pytest.mark.asyncio
    async def test_get_queue_entries_validates_board_id(self):
        """get_queue_entries should validate non-empty board_id."""
        service = await self.create_service()

        with pytest.raises(QueueValidationError):
            await service.get_queue_entries("proj-1", "")

    # ===== sync_queue_with_board Tests =====

    @pytest.mark.asyncio
    async def test_sync_queue_with_board_validates_project_id(self):
        """sync_queue_with_board should validate non-empty project_id."""
        service = await self.create_service()

        with pytest.raises(QueueValidationError):
            await service.sync_queue_with_board("", "board-1", "In Progress")

    @pytest.mark.asyncio
    async def test_sync_queue_with_board_validates_board_id(self):
        """sync_queue_with_board should validate non-empty board_id."""
        service = await self.create_service()

        with pytest.raises(QueueValidationError):
            await service.sync_queue_with_board("proj-1", "", "In Progress")

    @pytest.mark.asyncio
    async def test_sync_queue_with_board_validates_column(self):
        """sync_queue_with_board should validate non-empty column."""
        service = await self.create_service()

        with pytest.raises(QueueValidationError):
            await service.sync_queue_with_board("proj-1", "board-1", "")

    # ===== Queue Entry Immutability Tests =====

    @pytest.mark.asyncio
    async def test_queue_entries_are_immutable(self):
        """Queue entries should be immutable (frozen dataclasses)."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-123", position_in_column=0, timestamp=now
        )

        entries = await service.get_queue_entries("proj-1", "board-1")
        entry = entries[0]

        # Attempt to modify should fail
        with pytest.raises(FrozenInstanceError):
            entry.status = QueueStatus.ACTIVE

    # ===== Multi-Queue Tests =====

    @pytest.mark.asyncio
    async def test_independent_queues_per_project(self):
        """Different projects should have independent queues."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await service.enqueue_item(
            "proj-2", "board-1", "item-2", position_in_column=0, timestamp=now
        )

        proj1_entries = await service.get_queue_entries("proj-1", "board-1")
        proj2_entries = await service.get_queue_entries("proj-2", "board-1")

        assert len(proj1_entries) == 1
        assert len(proj2_entries) == 1
        assert proj1_entries[0].work_item_id == "item-1"
        assert proj2_entries[0].work_item_id == "item-2"

    @pytest.mark.asyncio
    async def test_independent_queues_per_board(self):
        """Different boards should have independent queues."""
        service = await self.create_service()
        now = datetime.now(UTC)

        await service.enqueue_item(
            "proj-1", "board-1", "item-1", position_in_column=0, timestamp=now
        )
        await service.enqueue_item(
            "proj-1", "board-2", "item-2", position_in_column=0, timestamp=now
        )

        board1_entries = await service.get_queue_entries("proj-1", "board-1")
        board2_entries = await service.get_queue_entries("proj-1", "board-2")

        assert len(board1_entries) == 1
        assert len(board2_entries) == 1
        assert board1_entries[0].work_item_id == "item-1"
        assert board2_entries[0].work_item_id == "item-2"
