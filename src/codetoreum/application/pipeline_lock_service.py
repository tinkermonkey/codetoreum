"""Pipeline lock service combining lock and queue management.

Provides a unified API for acquiring, releasing, and managing locks with associated
queue positions. This abstraction combines IDistributedLock (for exclusive access)
and IPipelineQueue (for ordering work items).

The service handles:
- Lock acquisition attempts (returns ACQUIRED, QUEUED, or ALREADY_HELD)
- Lock release with automatic queue promotion
- Queue position tracking and updates
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class LockStatus(Enum):
    """Status of a lock acquisition attempt."""
    ACQUIRED = "acquired"  # Lock was successfully acquired
    QUEUED = "queued"  # Work item was queued (lock already held)
    ALREADY_HELD = "already_held"  # Work item already holds the lock


@dataclass(frozen=True)
class LockAcquisitionResult:
    """Result of a lock acquisition attempt."""
    status: LockStatus
    work_item_id: str
    queue_position: int | None = None  # Position in queue if QUEUED, None if ACQUIRED/ALREADY_HELD
    queue_length: int = 0  # Total length of queue after operation


@dataclass(frozen=True)
class LockReleaseResult:
    """Result of a lock release operation."""
    released_work_item_id: str  # The work item that held the lock
    next_work_item_id: str | None  # Next work item promoted from queue (if any)
    queue_length_after_release: int  # Queue length after release


class IPipelineLockService(ABC):
    """Unified pipeline lock service combining lock and queue management.

    Provides a high-level API for work item coordination with automatic
    queue promotion on lock release.
    """

    @abstractmethod
    async def try_acquire_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        board_position: int,
    ) -> LockAcquisitionResult:
        """Attempt to acquire a lock for a work item.

        If the lock is free, returns ACQUIRED. If the lock is held by another
        work item, enqueues this work item and returns QUEUED with queue position.
        If this work item already holds the lock, returns ALREADY_HELD.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            work_item_id: Work item identifier
            board_position: Position of work item on external board (used for tie-breaking)

        Returns:
            LockAcquisitionResult with status and queue information
        """

    @abstractmethod
    async def release_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
    ) -> LockReleaseResult:
        """Release a held lock and promote next queued work item.

        Atomically releases the lock and promotes the first queued work item
        (if any) to hold the lock.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            work_item_id: Work item that currently holds the lock

        Returns:
            LockReleaseResult with information about next holder

        Raises:
            ValueError: If work item doesn't hold the lock
        """

    @abstractmethod
    async def update_queue_positions(
        self,
        project_id: str,
        board_id: str,
        position_updates: dict[str, int],
    ) -> None:
        """Update queue positions for work items.

        Used when work items move on the external board to maintain queue ordering.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            position_updates: Mapping of work_item_id to new board position
        """
