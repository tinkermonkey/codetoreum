"""Queued pipeline lock service for managing column-based workflow contention.

This application-layer service manages lock acquisition and release with queue
ordering based on work item board positions. It enables pipeline trigger columns
to serialize work item processing while maintaining positional queue ordering.

Key Features:
- Lock acquisition with queue status tracking
- Queue ordering by work item board position (topmost first)
- Lock release that grants to next queued item
- Queue position updates when cards are reordered by humans
- Full audit trail via domain events

Lock Lifecycle:
1. Work item enters pipeline trigger column
2. try_acquire_lock() called with board position
3. If available: lock granted, agent executes immediately
4. If held: work item added to queue sorted by position
5. Upon completion, work item reaches exit column
6. release_lock() called, granting lock to topmost queued item

Architecture Note:
This service (IQueuedPipelineLockService) is distinct from the port interface
IPipelineLockService found in ports/output/. This application service adds
position-based queue management on top of basic lock semantics.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LockStatus(Enum):
    """Status of lock acquisition attempt."""
    ACQUIRED = "acquired"          # Lock granted immediately
    QUEUED = "queued"              # Added to queue, waiting
    ALREADY_HELD = "already_held"  # Work item already holds lock


@dataclass
class QueueEntry:
    """Entry in pipeline lock queue.

    This is an internal mutable structure used by queue implementations to track
    work items in the queue. The board_position field is mutable to support
    reordering when users manually reorder cards in the UI. Callers should not
    directly mutate queue entries - use update_queue_positions() instead.

    Attributes:
        work_item_id: ID of work item in queue
        board_position: Position in column (mutable for reordering)
        enqueued_at: Timestamp when added to queue
    """
    work_item_id: str
    board_position: int
    enqueued_at: datetime


@dataclass
class LockAcquisitionResult:
    """Result of attempting to acquire pipeline lock.

    Attributes:
        status: ACQUIRED, QUEUED, or ALREADY_HELD
        work_item_id: ID of work item requesting lock
        queue_position: Position in queue if QUEUED, None otherwise
        queue_length: Total items in queue after operation
    """
    status: LockStatus
    work_item_id: str
    queue_position: int | None = None
    queue_length: int = 0


@dataclass
class LockReleaseResult:
    """Result of releasing pipeline lock.

    Attributes:
        released_work_item_id: ID of work item that held lock
        next_work_item_id: ID of next work item in queue, if any
        queue_length_after_release: Items remaining in queue
    """
    released_work_item_id: str
    next_work_item_id: str | None
    queue_length_after_release: int


@dataclass
class PipelineQueueState:
    """Current state of pipeline lock and queue.

    Attributes:
        board_id: Board containing pipeline
        project_id: Project containing board
        lock_holder: Work item ID currently holding lock, None if available
        lock_acquired_at: Timestamp when lock was acquired
        queue: List of QueueEntry items waiting for lock
    """
    board_id: str
    project_id: str
    lock_holder: str | None
    lock_acquired_at: datetime | None
    queue: list[QueueEntry]


class IQueuedPipelineLockService(ABC):
    """Application service for managing queued pipeline locks.

    Manages exclusive lock acquisition for pipeline trigger columns,
    queue ordering by board position, and lock release with queue
    advancement. Ensures only one work item executes in trigger columns
    at a time while respecting positional ordering.

    This is distinct from IPipelineLockService (port interface) by including
    position-based queue management.

    Example:
        # Acquire lock when work item enters trigger column
        result = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0  # Top of column
        )

        if result.status == LockStatus.ACQUIRED:
            # Execute agent immediately
            await execute_agent(item_id)
        elif result.status == LockStatus.QUEUED:
            # Wait - work item is position 3 in queue
            logger.info(f"Queued at position {result.queue_position}")

        # Release when work item reaches exit column
        release_result = await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1"
        )

        if release_result.next_work_item_id:
            # Trigger agent for next queued item
            await execute_agent(release_result.next_work_item_id)
    """

    @abstractmethod
    async def try_acquire_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        board_position: int
    ) -> LockAcquisitionResult:
        """Attempt to acquire pipeline lock.

        If lock is available, grants it immediately. If held, adds work item
        to queue ordered by board_position (lowest/topmost first).

        Args:
            project_id: Project ID
            board_id: Board ID
            work_item_id: Work item requesting lock
            board_position: Position in column (0 = topmost, highest priority)

        Returns:
            LockAcquisitionResult with status and queue information

        Raises:
            ValueError: Invalid parameters
        """

    @abstractmethod
    async def release_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str
    ) -> LockReleaseResult:
        """Release pipeline lock, grant to next queued item.

        Releases lock held by work_item_id and grants it to first item
        in queue (if any). Next item in queue is determined by board
        position ordering.

        Args:
            project_id: Project ID
            board_id: Board ID
            work_item_id: Work item releasing lock (must be lock holder)

        Returns:
            LockReleaseResult with next work item and queue length

        Raises:
            ValueError: Invalid parameters or not lock holder
        """

    @abstractmethod
    async def get_queue_state(
        self,
        project_id: str,
        board_id: str
    ) -> PipelineQueueState:
        """Get current lock holder and queue state.

        Args:
            project_id: Project ID
            board_id: Board ID

        Returns:
            PipelineQueueState with lock holder, acquisition time, and queue
        """

    @abstractmethod
    async def update_queue_positions(
        self,
        project_id: str,
        board_id: str,
        updated_positions: dict[str, int]
    ) -> None:
        """Update queue ordering when humans reorder cards in column.

        Called when cards are manually reordered in the UI. Updates board
        positions for queued items and re-sorts queue accordingly.

        Args:
            project_id: Project ID
            board_id: Board ID
            updated_positions: Dict of work_item_id -> new_board_position
        """


# Backward compatibility alias
IPipelineLockService = IQueuedPipelineLockService
