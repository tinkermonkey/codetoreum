"""Pipeline queue service port interface for board-based queue management.

This interface defines contracts for managing work item queues in pipeline trigger
columns. Queue operations are separate from lock semantics - this interface focuses
on queue ordering based on board position (source of truth).

Key Features:
- Queue entry management with board position tracking
- Queue synchronization with board column state
- Priority ordering by board position (topmost = highest priority)
- Status tracking for waiting vs active items

Queue Architecture:
Queue entries track work items waiting to acquire pipeline locks. Each entry
includes the board position (positionInColumn) which determines execution order.
Queue is synced with board state before selecting next item to ensure order
matches current board layout.

Immutability:
Queue entries in external data structures should be treated as read-only once
returned from port methods. Implementations may mutate internal state structures
but should never expose mutable external references.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class QueueEntry:
    """Represents a work item in the pipeline queue.

    Tracks a work item waiting to acquire or actively holding a pipeline lock.
    Board position is used to determine execution order - the topmost item in
    a column has the highest priority.

    Attributes:
        work_item_id: Unique identifier of the work item
        position_in_column: Current position in board column (0 = topmost, highest priority)
        status: Queue status - 'waiting' (queued, not holding lock) or 'active' (holds lock)
        queued_at: ISO 8601 timestamp when item was added to queue
        last_position_check: ISO 8601 timestamp when position was last synced with board
    """

    work_item_id: str
    position_in_column: int
    status: str  # 'waiting' or 'active'
    queued_at: datetime
    last_position_check: datetime


class IPipelineQueueService(ABC):
    """Port interface for pipeline queue management.

    This interface handles queue operations separate from lock semantics.
    Queue ordering is determined by board position (source of truth), not
    insertion order or queue length. This enables users to reprioritize work
    by dragging cards in the UI, with queue order automatically reflecting
    the new positions.

    Queue Storage:
    - Queue is stored per pipeline identified by (project_id, board_id)
    - Each queue entry tracks a work item's board position and queue status
    - Queues are synced with board state before selecting next item

    Priority Ordering:
    - Queue items sorted by positionInColumn ascending (lowest = highest priority)
    - Item with positionInColumn=0 (topmost in column) executes next
    - Board position is source of truth - synced before selection

    Status Values:
    - 'waiting': Work item is in queue, waiting for lock
    - 'active': Work item holds the pipeline lock

    Example:
        # Check if item is in any queue
        in_queue = await service.is_item_in_queue("item-123")

        # Add item to queue when it enters trigger column
        await service.enqueue_item("item-123", "In Progress", now)

        # Get next item before granting lock
        next_item = await service.get_next_waiting_item("proj-1", "board-1")
        if next_item:
            # Grant lock to top-priority item
            await service.mark_item_active("item-123")

        # Sync queue when board changes (manual reordering, item removed, etc.)
        await service.sync_queue_with_board("proj-1", "board-1", "In Progress")
    """

    @abstractmethod
    async def is_item_in_queue(self, work_item_id: str) -> bool:
        """Check if a work item is currently in any queue.

        Checks if the work item exists in any pipeline queue, regardless of
        queue status (waiting or active).

        Args:
            work_item_id: Work item identifier to check

        Returns:
            bool: True if item is in any queue, False otherwise

        Raises:
            ValidationError: Invalid work_item_id
        """
        pass

    @abstractmethod
    async def enqueue_item(
        self, work_item_id: str, column: str, timestamp: datetime
    ) -> None:
        """Add a work item to the queue for a pipeline.

        Creates a new queue entry with status='waiting'. The column parameter
        is used to determine which project and board the item belongs to
        (assumes pipeline scope is (project_id, board_id) derived from column).

        Initial position_in_column should be fetched from board service.

        Args:
            work_item_id: Work item identifier
            column: Board column name (used to determine project_id/board_id)
            timestamp: Time when item was queued (ISO 8601 or datetime object)

        Raises:
            ValidationError: Invalid parameters
            ResourceNotFoundError: Column or board doesn't exist
            DuplicateError: Item already exists in queue
        """
        pass

    @abstractmethod
    async def mark_item_active(self, work_item_id: str) -> None:
        """Mark a queued item as active (holding the lock).

        Changes item status from 'waiting' to 'active', indicating it now
        holds the pipeline lock. Does not remove from queue - the item
        remains tracked until lock is released.

        Args:
            work_item_id: Work item that acquired the lock

        Raises:
            ValidationError: Invalid work_item_id
            NotFoundError: Item not in queue
            InvalidStateError: Item already marked active
        """
        pass

    @abstractmethod
    async def get_next_waiting_item(
        self, project_id: str, board_id: str
    ) -> Optional[QueueEntry]:
        """Get the next waiting item from the queue based on board position.

        Before selecting the next item, this method syncs with the board state
        to ensure queue order matches current board position order. This is
        essential because:

        1. Users can manually reorder cards in the UI
        2. Items can be moved out of the trigger column
        3. New items can be added to the trigger column

        After syncing, queue entries are sorted by position_in_column in
        ascending order (lowest position = highest priority). This method
        returns the waiting item with the lowest position_in_column value
        (topmost in column = highest priority).

        Args:
            project_id: Project identifier
            board_id: Board identifier

        Returns:
            QueueEntry with lowest position_in_column (highest priority),
            or None if no waiting items in queue.

            The returned entry has status='waiting' (not active).

        Raises:
            ValidationError: Invalid parameters
            ResourceNotFoundError: Project or board doesn't exist
        """
        pass

    @abstractmethod
    async def sync_queue_with_board(
        self, project_id: str, board_id: str, column: str
    ) -> None:
        """Synchronize queue state with current board column state.

        Ensures queue entries match the actual work items in the trigger column.
        Performs three operations in sequence:

        1. **Removal**: Remove queue entries for work items no longer in the
           trigger column (user moved item out, or item was deleted)

        2. **Addition**: Add queue entries for work items newly discovered in
           the trigger column (user moved item in, or new item created)

        3. **Update**: Update position_in_column for existing queue entries
           based on current board API data, and update last_position_check
           timestamp

        After sync, queue order should match board column order.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            column: Board column name to sync with

        Raises:
            ValidationError: Invalid parameters
            ResourceNotFoundError: Project, board, or column doesn't exist
            ExternalServiceError: Board service communication failure
        """
        pass
