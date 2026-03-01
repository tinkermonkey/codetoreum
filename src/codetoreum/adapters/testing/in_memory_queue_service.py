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
from collections.abc import Callable
from datetime import UTC, datetime

from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.events.queue_events import (
    QueueItemAddedEvent,
    QueueItemRemovedEvent,
    QueuePositionChangedEvent,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.board_service import IBoardService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.pipeline_queue_service import (
    DuplicateQueueEntryError,
    InvalidQueueStateError,
    IPipelineQueueService,
    NonNegativeInt,
    PipelineQueueEntry,
    QueueItemNotFoundError,
    QueueStatus,
    QueueValidationError,
)

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
        board_service: IBoardService | None = None,
        time_source: Callable[[], datetime] | None = None,
        event_emitter: IEventEmitter | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        """Initialize empty queue service.

        Args:
            board_service: Optional IBoardService for queue synchronization with board state
            time_source: Optional callable returning datetime.datetime for deterministic time
                        manipulation in simulation testing. Defaults to datetime.now(timezone.utc)
            event_emitter: Optional IEventEmitter for emitting domain events. Defaults to MockEventEmitter
            event_bus: Optional EventBus for subscribing to domain events (e.g., WorkItemColumnChangedEvent)
        """
        self._queues: dict[str, list[PipelineQueueEntry]] = {}
        self._board_positions: dict[str, list[str]] = {}  # For set_board_order test helper
        self._operations_log: list[dict] = []  # Audit log for test verification
        self._lock = threading.Lock()
        self._board_service = board_service
        self._time_source = time_source or (lambda: datetime.now(UTC))
        self._event_emitter = event_emitter or MockEventEmitter()
        self._event_bus = event_bus

        # Subscribe to board position changes if event bus provided
        if self._event_bus:
            self._event_bus.subscribe("WorkItemColumnChangedEvent", self._handle_board_position_change)

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
            QueueValidationError: Invalid work_item_id
        """
        if not work_item_id:
            msg = "work_item_id cannot be empty"
            raise QueueValidationError(msg)

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

        Creates a new queue entry with status=QueueStatus.WAITING. If item is already
        in queue, raises DuplicateQueueEntryError.

        Args:
            project_id: Project identifier for the pipeline
            board_id: Board identifier for the pipeline
            work_item_id: Work item identifier
            position_in_column: Position in board column (0 = topmost, highest priority)
            timestamp: Time when item was queued

        Raises:
            QueueValidationError: Invalid parameters
            DuplicateQueueEntryError: Item already exists in queue
        """
        if not project_id:
            msg = "project_id cannot be empty"
            raise QueueValidationError(msg)
        if not board_id:
            msg = "board_id cannot be empty"
            raise QueueValidationError(msg)
        if not work_item_id:
            msg = "work_item_id cannot be empty"
            raise QueueValidationError(msg)
        if position_in_column < 0:
            msg = "position_in_column cannot be negative"
            raise QueueValidationError(msg)

        # Warn about suspiciously high positions
        if position_in_column > 1000:
            logger.warning(
                f"Unusually high position_in_column={position_in_column} for {work_item_id}. "
                f"This may indicate a bug in board position calculation.",
                extra={
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "board_id": board_id,
                    "position": position_in_column,
                },
            )

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
                msg = f"Work item {work_item_id} already in queue for {queue_key}"
                raise DuplicateQueueEntryError(msg)

            # Create new queue entry (frozen dataclass)
            entry = PipelineQueueEntry(
                project_id=project_id,
                board_id=board_id,
                work_item_id=work_item_id,
                position_in_column=NonNegativeInt(position_in_column),
                status=QueueStatus.WAITING,
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

            # Emit domain event
            # Note: source="mock" identifies this as a test/simulation event for traceability
            self._event_emitter.emit(
                QueueItemAddedEvent(
                    type="queue.item_added",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="mock",
                    queue_name=queue_key,
                    item_id=work_item_id,
                    position=position_in_column,
                    project_id=project_id,
                )
            )

    async def mark_item_active(self, work_item_id: str) -> None:
        """Mark a queued item as active (holding the lock).

        Changes item status from WAITING to ACTIVE. Item remains in queue
        until lock is released.

        Args:
            work_item_id: Work item that acquired the lock

        Raises:
            QueueValidationError: Invalid work_item_id
            QueueItemNotFoundError: Item not in queue
            InvalidQueueStateError: Item already marked active
        """
        if not work_item_id:
            msg = "work_item_id cannot be empty"
            raise QueueValidationError(msg)

        with self._lock:
            # Find the item across all queues
            for queue_key, queue in self._queues.items():
                for i, entry in enumerate(queue):
                    if entry.work_item_id == work_item_id:
                        if entry.status == QueueStatus.ACTIVE:
                            msg = f"Work item {work_item_id} is already marked active"
                            raise InvalidQueueStateError(msg)

                        # Create new entry with updated status (immutable pattern)
                        new_entry = PipelineQueueEntry(
                            project_id=entry.project_id,
                            board_id=entry.board_id,
                            work_item_id=entry.work_item_id,
                            position_in_column=entry.position_in_column,
                            status=QueueStatus.ACTIVE,
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
            msg = f"Work item {work_item_id} not found in any queue"
            raise QueueItemNotFoundError(msg)

    async def remove_from_queue(self, work_item_id: str) -> bool:
        """Remove a work item from the queue.

        Args:
            work_item_id: Work item identifier to remove

        Returns:
            bool: True if item was removed, False if not in queue

        Raises:
            QueueValidationError: Invalid work_item_id
        """
        if not work_item_id:
            msg = "work_item_id cannot be empty"
            raise QueueValidationError(msg)

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

                        # Emit domain event
                        # Note: source="mock" identifies this as a test/simulation event for traceability
                        self._event_emitter.emit(
                            QueueItemRemovedEvent(
                                type="queue.item_removed",
                                timestamp=datetime.now(UTC).isoformat(),
                                source="mock",
                                queue_name=queue_key,
                                item_id=work_item_id,
                                project_id=entry.project_id,
                            )
                        )
                        return True
            return False

    async def get_next_waiting_item(self, project_id: str, board_id: str) -> PipelineQueueEntry | None:
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
            QueueValidationError: Invalid parameters
        """
        if not project_id:
            msg = "project_id cannot be empty"
            raise QueueValidationError(msg)
        if not board_id:
            msg = "board_id cannot be empty"
            raise QueueValidationError(msg)

        with self._lock:
            queue_key = f"{project_id}:{board_id}"
            queue = self._queues.get(queue_key, [])

            if not queue:
                return None

            # Find first waiting item (queue is sorted by position)
            for entry in queue:
                if entry.status == QueueStatus.WAITING:
                    return entry

            return None

    async def get_queue_entries(self, project_id: str, board_id: str) -> list[PipelineQueueEntry]:
        """Get all queue entries for a pipeline.

        Returns all queue entries (both WAITING and ACTIVE) for the specified
        pipeline, sorted by position_in_column in ascending order.

        Args:
            project_id: Project identifier
            board_id: Board identifier

        Returns:
            List of PipelineQueueEntry sorted by position_in_column ascending,
            or empty list if no entries in queue.

        Raises:
            QueueValidationError: Invalid parameters
        """
        if not project_id:
            msg = "project_id cannot be empty"
            raise QueueValidationError(msg)
        if not board_id:
            msg = "board_id cannot be empty"
            raise QueueValidationError(msg)

        with self._lock:
            queue_key = f"{project_id}:{board_id}"
            queue = self._queues.get(queue_key, [])
            # Return a copy to prevent external modification
            return list(queue)

    async def sync_queue_with_board(self, project_id: str, board_id: str, column: str) -> None:
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
            QueueValidationError: Invalid parameters
        """
        if not project_id:
            msg = "project_id cannot be empty"
            raise QueueValidationError(msg)
        if not board_id:
            msg = "board_id cannot be empty"
            raise QueueValidationError(msg)
        if not column:
            msg = "column cannot be empty"
            raise QueueValidationError(msg)

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
                msg = f"Column {column} not found in board"
                raise ValueError(msg)

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
                queue = [entry for entry in queue if entry.work_item_id in items_in_column]

                # Step 2: Add new items discovered in column
                now = self._time_source()
                for position, work_item_id in enumerate(target_column.work_item_ids):
                    if work_item_id not in queue_item_ids:
                        # New item in column - add to queue
                        entry = PipelineQueueEntry(
                            project_id=project_id,
                            board_id=board_id,
                            work_item_id=work_item_id,
                            position_in_column=NonNegativeInt(position),
                            status=QueueStatus.WAITING,
                            queued_at=now,
                            last_position_check=now,
                        )
                        queue.append(entry)

                # Step 3: Update positions for existing items based on board state
                updated_queue = []
                for position, work_item_id in enumerate(target_column.work_item_ids):
                    # Find corresponding entry in queue
                    for entry in queue:
                        if entry.work_item_id == work_item_id:
                            # Update position and timestamp
                            updated_entry = PipelineQueueEntry(
                                project_id=entry.project_id,
                                board_id=entry.board_id,
                                work_item_id=entry.work_item_id,
                                position_in_column=NonNegativeInt(position),
                                status=entry.status,
                                queued_at=entry.queued_at,
                                last_position_check=now,
                            )
                            updated_queue.append(updated_entry)

                            # Emit position change event if position changed
                            if entry.position_in_column != position:
                                # Note: source="mock" identifies this as a test/simulation event for traceability
                                self._event_emitter.emit(
                                    QueuePositionChangedEvent(
                                        type="queue.position_changed",
                                        timestamp=datetime.now(UTC).isoformat(),
                                        source="mock",
                                        queue_name=queue_key,
                                        item_id=work_item_id,
                                        old_position=entry.position_in_column,
                                        new_position=position,
                                        project_id=project_id,
                                    )
                                )
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
                    "error_id": ErrorRegistry.ERR_PIPELINE_LOCK_ERROR,
                },
            )
            # Don't raise - allow queue to remain in current state
            # Next sync or lock operation will retry

    async def _handle_board_position_change(self, event: WorkItemColumnChangedEvent) -> None:
        """Handle board position changes by updating queue positions.

        This handler is invoked when WorkItemColumnChangedEvent is emitted by the board adapter,
        enabling automatic queue position synchronization via event subscription.

        For items moved within or to the trigger column, this handler:
        1. Removes the item from its current position in the queue
        2. Re-enqueues it at the new position (if board service available)
        3. Re-sorts the queue to maintain board position ordering

        Args:
            event: WorkItemColumnChangedEvent containing work_item_id, project_id, board_id,
                  from_column, to_column, and moved_by fields
        """
        try:
            # Step 1: Find and remove item from queue under lock (no await inside lock)
            entry_to_move = None
            queue_key = None
            with self._lock:
                queue_key = f"{event.project_id}:{event.board_id}"
                if queue_key not in self._queues:
                    return

                queue = self._queues[queue_key]

                # Find and remove item from current position
                for i, entry in enumerate(queue):
                    if entry.work_item_id == event.work_item_id:
                        entry_to_move = entry
                        queue.pop(i)
                        break

            if entry_to_move:
                # Step 2: Fetch board state OUTSIDE the lock (can await here)
                board = None
                if self._board_service and event.to_column:
                    try:
                        board = await self._board_service.get_board(event.project_id, event.board_id)
                    except Exception as board_error:
                        logger.warning(
                            f"Failed to fetch board state for position update: {board_error}. "
                            f"Item will remain removed from queue.",
                            exc_info=True,
                        )

                # Step 3: Re-enqueue and re-sort under lock (with data from outside lock)
                with self._lock:
                    queue = self._queues[queue_key]

                    if board and event.to_column:
                        # Find the target column and new position
                        target_column = None
                        new_position = None
                        for col in board.columns:
                            if col.name == event.to_column:
                                target_column = col
                                # Find the position of this work item in the column
                                try:
                                    new_position = col.work_item_ids.index(event.work_item_id)
                                except ValueError:
                                    # Item not in column - it may have been removed
                                    new_position = None
                                break

                        # If item is in the new column, re-enqueue at new position
                        if target_column and new_position is not None:
                            updated_entry = PipelineQueueEntry(
                                project_id=entry_to_move.project_id,
                                board_id=entry_to_move.board_id,
                                work_item_id=entry_to_move.work_item_id,
                                position_in_column=NonNegativeInt(new_position),
                                status=entry_to_move.status,
                                queued_at=entry_to_move.queued_at,
                                last_position_check=self._time_source(),
                            )
                            queue.append(updated_entry)

                            # Emit position change event
                            self._event_emitter.emit(
                                QueuePositionChangedEvent(
                                    type="queue.position_changed",
                                    timestamp=datetime.now(UTC).isoformat(),
                                    source="mock",
                                    queue_name=queue_key,
                                    item_id=event.work_item_id,
                                    old_position=entry_to_move.position_in_column,
                                    new_position=new_position,
                                    project_id=event.project_id,
                                )
                            )
                    # else: Item moved to a non-trigger column or no board service - keep it removed

                    # Re-sort queue by position to maintain order
                    queue.sort(key=lambda e: e.position_in_column)
                    self._queues[queue_key] = queue

                    # Log the board position change for audit trail
                    self._operations_log.append(
                        {
                            "operation": "board_position_changed",
                            "timestamp": self._time_source(),
                            "work_item_id": event.work_item_id,
                            "project_id": event.project_id,
                            "board_id": event.board_id,
                            "from_column": event.from_column,
                            "to_column": event.to_column,
                            "moved_by": event.moved_by,
                        }
                    )
        except Exception as e:
            logger.error(
                f"Failed to handle board position change for {event.work_item_id} "
                f"in {event.project_id}/{event.board_id}: {e}",
                exc_info=True,
                extra={
                    "work_item_id": event.work_item_id,
                    "project_id": event.project_id,
                    "board_id": event.board_id,
                    "from_column": event.from_column,
                    "to_column": event.to_column,
                    "error_type": type(e).__name__,
                },
            )

    # ===== Test Helper Methods =====

    def set_board_order(self, project_id: str, board_id: str, ordered_work_items: list[str]) -> None:
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
            QueueValidationError: Invalid parameters
        """
        if not project_id:
            msg = "project_id cannot be empty"
            raise QueueValidationError(msg)
        if not board_id:
            msg = "board_id cannot be empty"
            raise QueueValidationError(msg)
        if ordered_work_items is None:
            msg = "ordered_work_items cannot be None"
            raise QueueValidationError(msg)

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

    def get_operations_log(self) -> list[dict]:
        """Test helper to retrieve audit log of all operations.

        Returns a copy of the operations log containing records of all queue operations
        (set_board_order, enqueue, mark_active, remove, sync_queue) for test verification
        and debugging.

        Returns:
            List of operation records with timestamps and details
        """
        with self._lock:
            return self._operations_log.copy()

    def get_queue_state_for_testing(self, project_id: str, board_id: str) -> tuple[int, list[PipelineQueueEntry]]:
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
