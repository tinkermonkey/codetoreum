"""In-memory pipeline lock service with position-based queue ordering.

This implementation is suitable for single-orchestrator deployments and
testing. It maintains lock state and a position-ordered queue in memory,
sorting by board position when items are enqueued or positions update.

Thread-safe via internal locking mechanism.
"""

import threading
from datetime import datetime
from typing import Dict, Optional

from codetoreum.application.pipeline_lock_service import (
    IPipelineLockService,
    LockAcquisitionResult,
    LockReleaseResult,
    LockStatus,
    PipelineQueueState,
    QueueEntry,
)


class InMemoryLockService(IPipelineLockService):
    """In-memory pipeline lock service with board position-based queue ordering.

    Manages lock acquisition and release with queue ordered by board position.
    Topmost items (lowest position value) have highest priority in queue.

    Thread-safe for concurrent access via internal threading lock.

    Attributes:
        _lock_state: Dict mapping "project_id:board_id" to PipelineQueueState
        _lock: Threading lock for thread-safe access
    """

    def __init__(self) -> None:
        """Initialize empty lock service."""
        self._lock_state: Dict[str, PipelineQueueState] = {}
        self._lock = threading.Lock()

    async def try_acquire_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        board_position: int
    ) -> LockAcquisitionResult:
        """Attempt to acquire pipeline lock.

        Synchronous operation protected by thread lock. If lock is available,
        grants it and records acquisition time. If held, adds work item to
        queue sorted by board position.

        Args:
            project_id: Project ID
            board_id: Board ID
            work_item_id: Work item requesting lock
            board_position: Position in column (0 = topmost)

        Returns:
            LockAcquisitionResult with status and queue position if QUEUED
        """
        with self._lock:
            board_key = f"{project_id}:{board_id}"

            # Initialize state if needed
            if board_key not in self._lock_state:
                self._lock_state[board_key] = PipelineQueueState(
                    board_id=board_id,
                    project_id=project_id,
                    lock_holder=None,
                    lock_acquired_at=None,
                    queue=[]
                )

            state = self._lock_state[board_key]

            # Check if already holding lock
            if state.lock_holder == work_item_id:
                return LockAcquisitionResult(
                    status=LockStatus.ALREADY_HELD,
                    work_item_id=work_item_id,
                    queue_length=len(state.queue)
                )

            # Try to acquire lock
            if state.lock_holder is None:
                state.lock_holder = work_item_id
                state.lock_acquired_at = datetime.utcnow()
                return LockAcquisitionResult(
                    status=LockStatus.ACQUIRED,
                    work_item_id=work_item_id,
                    queue_length=len(state.queue)
                )

            # Add to queue and sort by position
            queue_entry = QueueEntry(
                work_item_id=work_item_id,
                board_position=board_position,
                enqueued_at=datetime.utcnow()
            )
            state.queue.append(queue_entry)

            # Sort by board position (lowest first = topmost)
            state.queue.sort(key=lambda e: e.board_position)

            # Find position of newly added item
            queue_position = next(
                i for i, e in enumerate(state.queue)
                if e.work_item_id == work_item_id
            )

            return LockAcquisitionResult(
                status=LockStatus.QUEUED,
                work_item_id=work_item_id,
                queue_position=queue_position,
                queue_length=len(state.queue)
            )

    async def release_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str
    ) -> LockReleaseResult:
        """Release pipeline lock, grant to next queued item.

        Releases lock held by work_item_id. If queue is non-empty, grants
        lock to first item in queue and records acquisition time. If queue
        is empty, lock becomes available.

        Args:
            project_id: Project ID
            board_id: Board ID
            work_item_id: Work item releasing lock (must be lock holder)

        Returns:
            LockReleaseResult with next work item ID and queue length

        Raises:
            ValueError: If work_item_id does not hold lock
        """
        with self._lock:
            board_key = f"{project_id}:{board_id}"
            state = self._lock_state.get(board_key)

            if not state or state.lock_holder != work_item_id:
                raise ValueError(
                    f"Work item {work_item_id} does not hold lock for {board_key}"
                )

            state.lock_holder = None
            state.lock_acquired_at = None

            next_item_id = None
            if state.queue:
                next_entry = state.queue.pop(0)
                next_item_id = next_entry.work_item_id
                state.lock_holder = next_item_id
                state.lock_acquired_at = datetime.utcnow()

            return LockReleaseResult(
                released_work_item_id=work_item_id,
                next_work_item_id=next_item_id,
                queue_length_after_release=len(state.queue)
            )

    async def get_queue_state(
        self,
        project_id: str,
        board_id: str
    ) -> PipelineQueueState:
        """Get current lock holder and queue state.

        Returns copy of current queue state including lock holder, acquisition
        time, and all queued items with their positions.

        Args:
            project_id: Project ID
            board_id: Board ID

        Returns:
            PipelineQueueState with lock and queue information
        """
        with self._lock:
            board_key = f"{project_id}:{board_id}"
            if board_key not in self._lock_state:
                return PipelineQueueState(
                    board_id=board_id,
                    project_id=project_id,
                    lock_holder=None,
                    lock_acquired_at=None,
                    queue=[]
                )

            state = self._lock_state[board_key]
            # Return copy to prevent external modification
            return PipelineQueueState(
                board_id=state.board_id,
                project_id=state.project_id,
                lock_holder=state.lock_holder,
                lock_acquired_at=state.lock_acquired_at,
                queue=list(state.queue)
            )

    async def update_queue_positions(
        self,
        project_id: str,
        board_id: str,
        updated_positions: dict[str, int]
    ) -> None:
        """Update queue ordering when humans reorder cards.

        Called when cards are manually reordered in the UI. Updates board
        positions for all queued items that appear in updated_positions
        and re-sorts queue accordingly.

        Args:
            project_id: Project ID
            board_id: Board ID
            updated_positions: Dict of work_item_id -> new_board_position
        """
        with self._lock:
            board_key = f"{project_id}:{board_id}"
            state = self._lock_state.get(board_key)

            if not state or not state.queue:
                return

            # Update positions for queued items
            for entry in state.queue:
                if entry.work_item_id in updated_positions:
                    entry.board_position = updated_positions[entry.work_item_id]

            # Re-sort queue by updated positions
            state.queue.sort(key=lambda e: e.board_position)
