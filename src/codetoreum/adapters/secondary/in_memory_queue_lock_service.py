"""In-memory pipeline lock service with position-based queue ordering.

This implementation is suitable for single-orchestrator deployments and
testing. It maintains lock state and a position-ordered queue in memory,
sorting by board position when items are enqueued or positions update.

Thread-safe via internal locking mechanism.
"""

import logging
import threading
from datetime import UTC, datetime

from codetoreum.application.pipeline_lock_service import (
    IPipelineLockService,
    LockAcquisitionResult,
    LockReleaseResult,
    LockStatus,
    PipelineQueueState,
    QueueEntry,
)
from codetoreum.domain.events.lock_events import (
    LockStaleDetectedEvent,
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
    WorkItemQueuedEvent,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)


class InMemoryLockService(IPipelineLockService):
    """In-memory pipeline lock service with board position-based queue ordering.

    Manages lock acquisition and release with queue ordered by board position.
    Topmost items (lowest position value) have highest priority in queue.

    Thread-safe for concurrent access via internal threading lock.

    Attributes:
        _lock_state: Dict mapping "project_id:board_id" to PipelineQueueState
        _lock: Threading lock for thread-safe access
        _event_bus: Optional event bus for emitting domain events
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        stale_threshold_seconds: int = 7200
    ) -> None:
        """Initialize empty lock service.

        Args:
            event_bus: Optional event bus for emitting lock lifecycle events
            stale_threshold_seconds: Threshold in seconds for detecting stale locks
                                   (default 7200 = 2 hours)
        """
        self._lock_state: dict[str, PipelineQueueState] = {}
        self._lock = threading.Lock()
        self._event_bus = event_bus
        self._stale_threshold_seconds = stale_threshold_seconds

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

        Raises:
            ValueError: Invalid parameters (empty strings or negative position)
        """
        # Validate inputs
        if not project_id:
            raise ValueError("project_id cannot be empty")
        if not board_id:
            raise ValueError("board_id cannot be empty")
        if not work_item_id:
            raise ValueError("work_item_id cannot be empty")
        if board_position < 0:
            raise ValueError("board_position cannot be negative")

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

            # Check for stale lock (older than threshold)
            if state.lock_holder is not None and state.lock_acquired_at is not None:
                lock_age_seconds = (datetime.now(UTC) - state.lock_acquired_at).total_seconds()
                if lock_age_seconds > self._stale_threshold_seconds:
                    # Stale lock detected - force release
                    stale_work_item_id = state.lock_holder

                    # Emit stale detected event
                    if self._event_bus:
                        stale_event = LockStaleDetectedEvent(
                            type="lock.stale_detected",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="in_memory_lock_service",
                            project_id=project_id,
                            board_id=board_id,
                            work_item_id=stale_work_item_id,
                            lock_acquired_at=state.lock_acquired_at.isoformat(),
                        )
                        try:
                            await self._event_bus.publish(stale_event)
                        except Exception:
                            logger.error(
                                f"CRITICAL: Failed to publish stale lock detected event for work_item={stale_work_item_id}, "
                                f"project={project_id}, board={board_id}. Stale lock was detected but event notification failed.",
                                exc_info=True,
                                extra={
                                    "work_item_id": stale_work_item_id,
                                    "project_id": project_id,
                                    "board_id": board_id,
                                    "event_type": "lock.stale_detected",
                                    "error_id": ErrorRegistry.ERR_PIPELINE_LOCK_ERROR,
                                }
                            )

                    # Force release stale lock and acquire for requester
                    state.lock_holder = work_item_id
                    state.lock_acquired_at = datetime.now(UTC)

                    # Emit lock acquired event with stale_recovery method
                    if self._event_bus:
                        event = PipelineLockAcquiredEvent(
                            type="pipeline.lock_acquired",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="in_memory_lock_service",
                            project_id=project_id,
                            work_item_id=work_item_id,
                            board_id=board_id,
                            queue_length_at_acquire=len(state.queue),
                        )
                        try:
                            await self._event_bus.publish(event)
                        except Exception:
                            logger.error(
                                f"CRITICAL: Failed to publish lock acquired event (stale recovery) for work_item={work_item_id}, "
                                f"project={project_id}, board={board_id}. Lock was acquired but event was lost.",
                                exc_info=True,
                                extra={
                                    "work_item_id": work_item_id,
                                    "project_id": project_id,
                                    "board_id": board_id,
                                    "event_type": "pipeline.lock_acquired",
                                    "error_id": ErrorRegistry.ERR_PIPELINE_LOCK_ERROR,
                                }
                            )

                    return LockAcquisitionResult(
                        status=LockStatus.ACQUIRED,
                        work_item_id=work_item_id,
                        queue_length=len(state.queue)
                    )

            # Try to acquire lock
            if state.lock_holder is None:
                state.lock_holder = work_item_id
                state.lock_acquired_at = datetime.now(UTC)

                # Emit lock acquired event
                if self._event_bus:
                    event = PipelineLockAcquiredEvent(
                        type="pipeline.lock_acquired",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="in_memory_lock_service",
                        project_id=project_id,
                        work_item_id=work_item_id,
                        board_id=board_id,
                        queue_length_at_acquire=len(state.queue),
                    )
                    try:
                        await self._event_bus.publish(event)
                    except Exception:
                        logger.error(
                            f"CRITICAL: Failed to publish lock acquired event for work_item={work_item_id}, "
                            f"project={project_id}, board={board_id}. Lock was acquired but event was lost.",
                            exc_info=True,
                            extra={
                                "work_item_id": work_item_id,
                                "project_id": project_id,
                                "board_id": board_id,
                                "event_type": "pipeline.lock_acquired",
                                "error_id": ErrorRegistry.ERR_PIPELINE_LOCK_ERROR,
                            }
                        )

                return LockAcquisitionResult(
                    status=LockStatus.ACQUIRED,
                    work_item_id=work_item_id,
                    queue_length=len(state.queue)
                )

            # Check if already in queue
            if any(e.work_item_id == work_item_id for e in state.queue):
                # Find current position in queue
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

            # Add to queue and sort by position
            queue_entry = QueueEntry(
                work_item_id=work_item_id,
                board_position=board_position,
                enqueued_at=datetime.now(UTC)
            )
            state.queue.append(queue_entry)

            # Sort by board position (lowest first = topmost)
            state.queue.sort(key=lambda e: e.board_position)

            # Find position of newly added item
            queue_position = next(
                i for i, e in enumerate(state.queue)
                if e.work_item_id == work_item_id
            )

            # Emit queued event
            if self._event_bus:
                event = WorkItemQueuedEvent(
                    type="workitem.queued",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="in_memory_lock_service",
                    work_item_id=work_item_id,
                    board_id=board_id,
                    queue_position=queue_position,
                )
                try:
                    await self._event_bus.publish(event)
                except Exception:
                    logger.error(
                        f"CRITICAL: Failed to publish workitem queued event for work_item={work_item_id}, "
                        f"project={project_id}, board={board_id}. Item was queued but event notification failed.",
                        exc_info=True,
                        extra={
                            "error_id": ErrorRegistry.ERR_EVENT_PUBLICATION_ERROR,
                            "work_item_id": work_item_id,
                            "project_id": project_id,
                            "board_id": board_id,
                            "queue_position": queue_position,
                            "event_type": "workitem.queued",
                        }
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
            ValueError: Invalid parameters or if work_item_id does not hold lock
        """
        # Validate inputs
        if not project_id:
            raise ValueError("project_id cannot be empty")
        if not board_id:
            raise ValueError("board_id cannot be empty")
        if not work_item_id:
            raise ValueError("work_item_id cannot be empty")

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
                state.lock_acquired_at = datetime.now(UTC)

            # Emit lock released event
            if self._event_bus:
                release_event = PipelineLockReleasedEvent(
                    type="pipeline.lock_released",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="in_memory_lock_service",
                    project_id=project_id,
                    work_item_id=work_item_id,
                    board_id=board_id,
                    next_work_item_id=next_item_id,
                )
                try:
                    await self._event_bus.publish(release_event)
                except Exception:
                    logger.error(
                        f"CRITICAL: Failed to publish lock released event for work_item={work_item_id}, "
                        f"project={project_id}, board={board_id}. Lock was released but event was lost.",
                        exc_info=True,
                        extra={
                            "error_id": ErrorRegistry.ERR_EVENT_PUBLICATION_ERROR,
                            "work_item_id": work_item_id,
                            "project_id": project_id,
                            "board_id": board_id,
                            "next_work_item_id": next_item_id,
                            "event_type": "pipeline.lock_released",
                        }
                    )

                # If next item acquired lock, emit acquisition event
                if next_item_id:
                    acquire_event = PipelineLockAcquiredEvent(
                        type="pipeline.lock_acquired",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="in_memory_lock_service",
                        project_id=project_id,
                        work_item_id=next_item_id,
                        board_id=board_id,
                        queue_length_at_acquire=len(state.queue),
                    )
                    try:
                        await self._event_bus.publish(acquire_event)
                    except Exception:
                        logger.error(
                            f"CRITICAL: Failed to publish lock acquired event (after release) for work_item={next_item_id}, "
                            f"project={project_id}, board={board_id}. Lock was acquired by next item but event was lost.",
                            exc_info=True,
                            extra={
                                "error_id": ErrorRegistry.ERR_EVENT_PUBLICATION_ERROR,
                                "work_item_id": next_item_id,
                                "project_id": project_id,
                                "board_id": board_id,
                                "event_type": "pipeline.lock_acquired",
                            }
                        )

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

        Raises:
            ValueError: Invalid parameters
        """
        # Validate inputs
        if not project_id:
            raise ValueError("project_id cannot be empty")
        if not board_id:
            raise ValueError("board_id cannot be empty")

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

        Raises:
            ValueError: Invalid parameters
        """
        # Validate inputs
        if not project_id:
            raise ValueError("project_id cannot be empty")
        if not board_id:
            raise ValueError("board_id cannot be empty")

        with self._lock:
            board_key = f"{project_id}:{board_id}"
            state = self._lock_state.get(board_key)

            if not state or not state.queue:
                return

            # Track what changed for logging
            old_order = [e.work_item_id for e in state.queue]

            # Update positions for queued items
            for entry in state.queue:
                if entry.work_item_id in updated_positions:
                    entry.board_position = updated_positions[entry.work_item_id]

            # Re-sort queue by updated positions
            state.queue.sort(key=lambda e: e.board_position)

            new_order = [e.work_item_id for e in state.queue]

            # Log changes
            if old_order != new_order:
                logger.info(
                    f"Queue reordered for {project_id}/{board_id}: "
                    f"{len(updated_positions)} items updated",
                    extra={
                        "project_id": project_id,
                        "board_id": board_id,
                        "updated_items": list(updated_positions.keys()),
                        "old_order": old_order,
                        "new_order": new_order,
                    }
                )

    def set_lock_acquired_at(
        self, project_id: str, board_id: str, timestamp: datetime
    ) -> None:
        """Test helper to manipulate lock timestamp for stale lock testing.

        Allows tests to set the lock acquisition timestamp to simulate
        locks of different ages without waiting for real time to pass.
        This enables deterministic testing of stale lock detection.

        Args:
            project_id: Project ID
            board_id: Board ID
            timestamp: Datetime to set as lock acquisition time

        Raises:
            ValueError: If lock doesn't exist for the given board
        """
        with self._lock:
            board_key = f"{project_id}:{board_id}"
            state = self._lock_state.get(board_key)

            if not state or state.lock_holder is None:
                raise ValueError(
                    f"No lock exists for {board_key}"
                )

            # Create new state with updated timestamp (immutable pattern)
            self._lock_state[board_key] = PipelineQueueState(
                project_id=state.project_id,
                board_id=state.board_id,
                lock_holder=state.lock_holder,
                lock_acquired_at=timestamp,
                queue=state.queue
            )
