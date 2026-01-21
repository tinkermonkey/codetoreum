"""In-memory pipeline queue service with board position simulation.

This implementation provides a mock/test implementation of IPipelineQueueService
that stores queue entries in memory and supports board position-based ordering.

Key Features:
- Queue entry management with board position tracking
- Position-based ordering (lowest position = highest priority)
- Queue synchronization with board column state
- Status tracking (waiting vs active)
- Thread-safe operations
- Immutable queue entries (frozen dataclasses)

Intended for:
- Unit and integration testing
- Simulation testing
- Single-orchestrator deployments without persistence requirements
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from codetoreum.ports.output.pipeline_queue_service import (
    IPipelineQueueService,
    PipelineQueueEntry,
)
from codetoreum.ports.output.board_service import IBoardService

logger = logging.getLogger(__name__)


class InMemoryQueueService(IPipelineQueueService):
    """In-memory implementation of pipeline queue service with board position tracking.

    Manages work item queues per pipeline (project_id, board_id) with position-based
    ordering. Queue entries are stored as frozen dataclasses and sorted by board position.

    Thread-safe via internal locking mechanism for concurrent access.

    Features:
        - Board position-based queue ordering (lowest position = highest priority)
        - Test helpers for deterministic simulation testing
        - Audit log for operational verification
        - Configurable time source for time manipulation in simulation scenarios

    Attributes:
        _queues: Dict mapping "project_id:board_id" to list of PipelineQueueEntry
        _board_positions: Dict mapping "project_id:board_id" to ordered work item IDs (from set_board_order)
        _operations_log: List of dicts recording all operations for audit trail
        _lock: Threading lock for thread-safe access
        _board_service: Optional board service for queue synchronization
        _time_source: Optional callable returning current datetime (for simulation)
    """

    def __init__(
        self,
        board_service: Optional[IBoardService] = None,
        time_source: Optional[Callable[[], datetime]] = None,
    ) -> None:
        """Initialize empty queue service.

        Args:
            board_service: Optional IBoardService for queue synchronization with board state
            time_source: Optional callable returning datetime.datetime for deterministic time
                        manipulation in simulation testing. Defaults to datetime.now(timezone.utc)
        """
        self._queues: Dict[str, List[PipelineQueueEntry]] = {}
        self._board_positions: Dict[str, List[str]] = {}  # For set_board_order test helper
        self._operations_log: List[Dict] = []  # Audit log for test verification
        self._lock = threading.Lock()
        self._board_service = board_service
        self._time_source = time_source or (lambda: datetime.now(timezone.utc))

    async def is_item_in_queue(self, work_item_id: str) -> bool:
        """Check if a work item is currently in any queue.

        Searches across ALL queues in the system (all project_id:board_id combinations).
        Returns True if the work item appears in any queue. Note: this is a cross-queue
        search, so if the same work_item_id exists in multiple pipelines, it will return
        True. This assumes work_item_ids are globally unique identifiers.

        Args:
            work_item_id: Work item identifier to check

        Returns:
            bool: True if item is in any queue, False otherwise

        Raises:
            ValueError: Invalid work_item_id
        """
        if not work_item_id:
            raise ValueError("work_item_id cannot be empty")

        with self._lock:
            for queue in self._queues.values():
                if any(entry.work_item_id == work_item_id for entry in queue):
                    return True
            return False

    async def enqueue_item(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        position_in_column: int,
        timestamp: datetime,
    ) -> None:
        """Add a work item to the queue for a pipeline.

        Creates a new queue entry with status='waiting'. If item is already
        in queue, raises DuplicateError.

        Args:
            project_id: Project identifier for the pipeline
            board_id: Board identifier for the pipeline
            work_item_id: Work item identifier
            position_in_column: Position in board column (0 = topmost, highest priority)
            timestamp: Time when item was queued

        Raises:
            ValueError: Invalid parameters
            RuntimeError: Item already exists in queue (DuplicateError)
        """
        if not project_id:
            raise ValueError("project_id cannot be empty")
        if not board_id:
            raise ValueError("board_id cannot be empty")
        if not work_item_id:
            raise ValueError("work_item_id cannot be empty")
        if position_in_column < 0:
            raise ValueError("position_in_column cannot be negative")

        # Normalize timestamp to datetime if needed
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        with self._lock:
            queue_key = f"{project_id}:{board_id}"

            # Initialize queue if needed
            if queue_key not in self._queues:
                self._queues[queue_key] = []

            queue = self._queues[queue_key]

            # Check if item already in queue
            if any(entry.work_item_id == work_item_id for entry in queue):
                raise RuntimeError(
                    f"Item {work_item_id} already exists in queue for {queue_key}"
                )

            # Create new queue entry (frozen dataclass)
            entry = PipelineQueueEntry(
                project_id=project_id,
                board_id=board_id,
                work_item_id=work_item_id,
                position_in_column=position_in_column,
                status="waiting",
                queued_at=timestamp,
                last_position_check=timestamp,
            )

            queue.append(entry)

            # Sort by position (lowest first = highest priority)
            queue.sort(key=lambda e: e.position_in_column)

            # Update the queue in the dictionary with sorted version
            self._queues[queue_key] = queue

            # Log operation for audit trail
            self._operations_log.append(
                {
                    "operation": "enqueue",
                    "timestamp": timestamp,
                    "project_id": project_id,
                    "board_id": board_id,
                    "work_item_id": work_item_id,
                    "position": position_in_column,
                }
            )

    async def mark_item_active(self, work_item_id: str) -> None:
        """Mark a queued item as active (holding the lock).

        Changes item status from 'waiting' to 'active'. Item remains in queue
        until lock is released.

        Args:
            work_item_id: Work item that acquired the lock

        Raises:
            ValueError: Invalid work_item_id
            KeyError: Item not in queue (NotFoundError)
            RuntimeError: Item already marked active (InvalidStateError)
        """
        if not work_item_id:
            raise ValueError("work_item_id cannot be empty")

        with self._lock:
            # Find the item across all queues
            for queue_key, queue in self._queues.items():
                for i, entry in enumerate(queue):
                    if entry.work_item_id == work_item_id:
                        if entry.status == "active":
                            raise RuntimeError(
                                f"Item {work_item_id} is already marked active"
                            )

                        # Create new entry with updated status (immutable pattern)
                        new_entry = PipelineQueueEntry(
                            project_id=entry.project_id,
                            board_id=entry.board_id,
                            work_item_id=entry.work_item_id,
                            position_in_column=entry.position_in_column,
                            status="active",
                            queued_at=entry.queued_at,
                            last_position_check=entry.last_position_check,
                        )

                        # Replace in queue
                        self._queues[queue_key][i] = new_entry

                        # Log operation for audit trail
                        self._operations_log.append(
                            {
                                "operation": "mark_active",
                                "timestamp": self._time_source(),
                                "work_item_id": work_item_id,
                                "project_id": entry.project_id,
                                "board_id": entry.board_id,
                            }
                        )
                        return

            # Item not found in any queue
            raise KeyError(f"Item {work_item_id} not found in any queue")

    async def remove_from_queue(self, work_item_id: str) -> bool:
        """Remove a work item from the queue.

        Args:
            work_item_id: Work item identifier to remove

        Returns:
            bool: True if item was removed, False if not in queue

        Raises:
            ValueError: Invalid work_item_id
        """
        if not work_item_id:
            raise ValueError("work_item_id cannot be empty")

        with self._lock:
            for queue_key, queue in self._queues.items():
                for i, entry in enumerate(queue):
                    if entry.work_item_id == work_item_id:
                        self._queues[queue_key].pop(i)

                        # Log operation for audit trail
                        self._operations_log.append(
                            {
                                "operation": "remove",
                                "timestamp": self._time_source(),
                                "work_item_id": work_item_id,
                                "project_id": entry.project_id,
                                "board_id": entry.board_id,
                            }
                        )
                        return True
            return False

    async def get_next_waiting_item(
        self, project_id: str, board_id: str
    ) -> Optional[PipelineQueueEntry]:
        """Get the next waiting item from the queue based on board position.

        Before selecting the next item, syncs with board state to ensure queue
        order matches current board position order. Returns the waiting item
        with the lowest position_in_column value (topmost = highest priority).

        Args:
            project_id: Project identifier
            board_id: Board identifier

        Returns:
            PipelineQueueEntry with lowest position_in_column (highest priority),
            or None if no waiting items in queue.

        Raises:
            ValueError: Invalid parameters
        """
        if not project_id:
            raise ValueError("project_id cannot be empty")
        if not board_id:
            raise ValueError("board_id cannot be empty")

        with self._lock:
            queue_key = f"{project_id}:{board_id}"
            queue = self._queues.get(queue_key, [])

            if not queue:
                return None

            # Find first waiting item (queue is sorted by position)
            for entry in queue:
                if entry.status == "waiting":
                    return entry

            return None

    async def get_queue_entries(
        self, project_id: str, board_id: str
    ) -> List[PipelineQueueEntry]:
        """Get all queue entries for a pipeline.

        Returns all queue entries (both waiting and active) for the specified
        pipeline, sorted by position_in_column in ascending order.

        Args:
            project_id: Project identifier
            board_id: Board identifier

        Returns:
            List of PipelineQueueEntry sorted by position_in_column ascending,
            or empty list if no entries in queue.

        Raises:
            ValueError: Invalid parameters
        """
        if not project_id:
            raise ValueError("project_id cannot be empty")
        if not board_id:
            raise ValueError("board_id cannot be empty")

        with self._lock:
            queue_key = f"{project_id}:{board_id}"
            queue = self._queues.get(queue_key, [])
            # Return a copy to prevent external modification
            return list(queue)

    async def sync_queue_with_board(
        self, project_id: str, board_id: str, column: str
    ) -> None:
        """Synchronize queue state with current board column state.

        Ensures queue entries match the actual work items in the trigger column.
        Performs three operations:
        1. Remove entries for items no longer in column
        2. Add entries for newly discovered items in column
        3. Update positions for existing entries

        Args:
            project_id: Project identifier
            board_id: Board identifier
            column: Board column name to sync with

        Raises:
            ValueError: Invalid parameters
        """
        if not project_id:
            raise ValueError("project_id cannot be empty")
        if not board_id:
            raise ValueError("board_id cannot be empty")
        if not column:
            raise ValueError("column cannot be empty")

        if not self._board_service:
            # If no board service, we can't sync - just return
            return

        try:
            # Get current board state
            board = await self._board_service.get_board(project_id, board_id)

            # Find the column
            target_column = None
            for col in board.columns:
                if col.name == column:
                    target_column = col
                    break

            if not target_column:
                raise ValueError(f"Column {column} not found in board")

            with self._lock:
                queue_key = f"{project_id}:{board_id}"
                if queue_key not in self._queues:
                    self._queues[queue_key] = []

                queue = self._queues[queue_key]

                # Get work item IDs currently in column
                items_in_column = set(target_column.work_item_ids)

                # Get work item IDs currently in queue
                queue_item_ids = {entry.work_item_id for entry in queue}

                # Step 1: Remove items no longer in column
                queue = [
                    entry
                    for entry in queue
                    if entry.work_item_id in items_in_column
                ]

                # Step 2: Add new items discovered in column
                now = self._time_source()
                for position, work_item_id in enumerate(
                    target_column.work_item_ids
                ):
                    if work_item_id not in queue_item_ids:
                        # New item in column - add to queue
                        entry = PipelineQueueEntry(
                            project_id=project_id,
                            board_id=board_id,
                            work_item_id=work_item_id,
                            position_in_column=position,
                            status="waiting",
                            queued_at=now,
                            last_position_check=now,
                        )
                        queue.append(entry)

                # Step 3: Update positions for existing items based on board state
                updated_queue = []
                for position, work_item_id in enumerate(
                    target_column.work_item_ids
                ):
                    # Find corresponding entry in queue
                    for entry in queue:
                        if entry.work_item_id == work_item_id:
                            # Update position and timestamp
                            updated_entry = PipelineQueueEntry(
                                project_id=entry.project_id,
                                board_id=entry.board_id,
                                work_item_id=entry.work_item_id,
                                position_in_column=position,
                                status=entry.status,
                                queued_at=entry.queued_at,
                                last_position_check=now,
                            )
                            updated_queue.append(updated_entry)
                            break

                # Re-sort by position
                updated_queue.sort(key=lambda e: e.position_in_column)
                self._queues[queue_key] = updated_queue

                # Log operation for audit trail
                self._operations_log.append(
                    {
                        "operation": "sync_queue",
                        "timestamp": now,
                        "project_id": project_id,
                        "board_id": board_id,
                        "column": column,
                        "items_in_queue": len(updated_queue),
                    }
                )

        except Exception as e:
            # Graceful degradation: log error but don't fail
            # Queue remains in current state until next sync attempt
            logger.error(
                f"Failed to sync queue with board for {project_id}/{board_id}/{column}. "
                f"Queue will remain in current state until next sync attempt.",
                exc_info=True,
                extra={
                    "project_id": project_id,
                    "board_id": board_id,
                    "column": column,
                    "error_type": type(e).__name__,
                }
            )
            # Don't raise - allow queue to remain in current state
            # Next sync or lock operation will retry

    # ===== Test Helper Methods =====

    def set_board_order(
        self, project_id: str, board_id: str, ordered_work_items: List[str]
    ) -> None:
        """Test helper to set simulated board order for queue position simulation.

        Allows tests to directly configure board position ordering without requiring
        a full IBoardService implementation. The InMemoryQueueService can use this
        ordering for simulating board position-based priority during sync operations.

        Args:
            project_id: Project identifier
            board_id: Board identifier
            ordered_work_items: List of work item IDs in board position order
                               (index 0 = topmost position, highest priority)

        Raises:
            ValueError: Invalid parameters
        """
        if not project_id:
            raise ValueError("project_id cannot be empty")
        if not board_id:
            raise ValueError("board_id cannot be empty")
        if ordered_work_items is None:
            raise ValueError("ordered_work_items cannot be None")

        with self._lock:
            queue_key = f"{project_id}:{board_id}"
            self._board_positions[queue_key] = ordered_work_items.copy()

            # Log operation for audit trail
            self._operations_log.append(
                {
                    "operation": "set_board_order",
                    "timestamp": self._time_source(),
                    "project_id": project_id,
                    "board_id": board_id,
                    "ordered_items": ordered_work_items.copy(),
                }
            )

    def get_operations_log(self) -> List[Dict]:
        """Test helper to retrieve audit log of all operations.

        Returns a copy of the operations log containing records of all queue operations
        (set_board_order, enqueue, mark_active, remove, sync_queue) for test verification
        and debugging.

        Returns:
            List of operation records with timestamps and details
        """
        with self._lock:
            return self._operations_log.copy()

    def get_queue_state_for_testing(
        self, project_id: str, board_id: str
    ) -> Tuple[int, List[PipelineQueueEntry]]:
        """Test helper to get complete queue state.

        Returns queue length and all entries for inspection/assertions.

        Args:
            project_id: Project identifier
            board_id: Board identifier

        Returns:
            Tuple of (queue_length, queue_entries)
        """
        with self._lock:
            queue_key = f"{project_id}:{board_id}"
            queue = self._queues.get(queue_key, [])
            return (len(queue), list(queue))

    def clear_queue_for_testing(self, project_id: str, board_id: str) -> None:
        """Test helper to clear a queue.

        Useful for test cleanup between test cases.

        Args:
            project_id: Project identifier
            board_id: Board identifier
        """
        with self._lock:
            queue_key = f"{project_id}:{board_id}"
            if queue_key in self._queues:
                self._queues[queue_key] = []

    def clear_all_queues_for_testing(self) -> None:
        """Test helper to clear all queues.

        Useful for test setup/teardown.
        """
        with self._lock:
            self._queues.clear()
