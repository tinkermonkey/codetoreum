"""In-memory pipeline lock service with event simulation for testing.

This module provides an in-memory implementation of IPipelineLockService
that manages locks on work items and includes test helper methods for
simulating lock operations via event emission.
"""

from datetime import UTC, datetime

from codetoreum.domain.events.lock_events import LockAcquiredEvent, LockReleasedEvent
from codetoreum.ports.output.pipeline_lock_service import (
    IPipelineLockService,
    PipelineLock,
)

from .mock_event_emitter import MockEventEmitter


class InMemoryPipelineLockService(MockEventEmitter, IPipelineLockService):
    """In-memory pipeline lock service with event simulation.

    Provides an in-memory implementation of IPipelineLockService that:
    1. Manages locks on work items in memory
    2. Tracks lock acquisition and queuing
    3. Emits events when locks are acquired or released
    4. Supports stale lock detection and recovery

    Intended for testing and simulation of pipeline lock management
    without external coordination services.

    Example:
        # Setup
        service = InMemoryPipelineLockService()

        # Subscribe to events
        events = []
        service.on("lock.acquired", events.append)

        # Try to acquire lock
        success, reason = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1"
        )

        # Verify
        assert success
        assert len(events) == 1
        assert events[0].work_item_id == "item-1"

        # Release lock
        await service.release_lock("proj-1", "board-1", "item-1")
    """

    def __init__(self) -> None:
        """Initialize the pipeline lock service."""
        super().__init__()
        self._locks: dict[str, PipelineLock] = {}  # key: "project_id:board_id" -> lock
        self._queue: dict[str, list[str]] = {}  # key: "project_id:board_id" -> work_item_ids

    # Query Operations

    async def get_lock(
        self,
        project_id: str,
        board_id: str
    ) -> PipelineLock | None:
        """Query current lock state for a project's board.

        Args:
            project_id: Project to query
            board_id: Board to query

        Returns:
            PipelineLock if a lock is currently held, None otherwise

        Raises:
            ValueError: Project or board doesn't exist
        """
        key = f"{project_id}:{board_id}"
        return self._locks.get(key)

    async def get_all_locks(self) -> list[PipelineLock]:
        """Retrieve all active locks across all projects and boards.

        Returns:
            List[PipelineLock]: All currently held locks
        """
        return list(self._locks.values())

    # Command Operations

    async def try_acquire_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str
    ) -> tuple[bool, str]:
        """Attempt to acquire lock for exclusive work item access.

        Args:
            project_id: Project containing the work item
            board_id: Board containing the work item
            work_item_id: Work item to lock

        Returns:
            Tuple[bool, str]:
                - (True, ""): Lock acquired successfully
                - (False, reason): Acquisition failed

        Raises:
            ValueError: Invalid parameters
        """
        if not project_id or not board_id or not work_item_id:
            msg = "project_id, board_id, and work_item_id are required"
            raise ValueError(msg)

        key = f"{project_id}:{board_id}"

        # Check if lock is already held
        if key in self._locks and self._locks[key].lock_status == "locked":
            # Add to queue
            if key not in self._queue:
                self._queue[key] = []
            self._queue[key].append(work_item_id)
            return (False, f"lock already held by {self._locks[key].locked_by_work_item}")

        # Acquire lock
        self._locks[key] = PipelineLock(
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
            locked_by_work_item=work_item_id,
            lock_acquired_at=self._get_iso_timestamp(),
            lock_status="locked"
        )

        self.emit(LockAcquiredEvent(
            type="lock.acquired",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
            acquisition_method="normal",
            timestamp=self._get_iso_timestamp(),
            source="mock"
        ))

        return (True, "lock acquired")

    async def release_lock(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str
    ) -> bool:
        """Release lock held on a work item.

        Args:
            project_id: Project containing the work item
            board_id: Board containing the work item
            work_item_id: Work item to unlock (must match holder)

        Returns:
            bool: True if lock was released, False if not held or mismatch

        Raises:
            ValueError: Invalid parameters
        """
        if not project_id or not board_id or not work_item_id:
            msg = "project_id, board_id, and work_item_id are required"
            raise ValueError(msg)

        key = f"{project_id}:{board_id}"

        if key not in self._locks or self._locks[key].locked_by_work_item != work_item_id:
            return False

        next_in_queue = None
        if key in self._queue and len(self._queue[key]) > 0:
            next_in_queue = self._queue[key].pop(0)

        del self._locks[key]

        self.emit(LockReleasedEvent(
            type="lock.released",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
            reason="completed",
            next_in_queue=next_in_queue,
            timestamp=self._get_iso_timestamp(),
            source="mock"
        ))

        return True

    # Test Helper Methods

    def simulate_lock_acquired(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        acquisition_method: str = "normal"
    ) -> None:
        """Test helper: Simulate lock acquisition event.

        Directly emits a lock acquired event without modifying internal state.

        Args:
            project_id: Project ID
            board_id: Board ID
            work_item_id: Work item ID
            acquisition_method: 'normal' or 'stale_recovery'
        """
        self.emit(LockAcquiredEvent(
            type="lock.acquired",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
            acquisition_method=acquisition_method,  # type: ignore
            timestamp=self._get_iso_timestamp(),
            source="mock"
        ))

    def simulate_lock_released(
        self,
        project_id: str,
        board_id: str,
        work_item_id: str,
        reason: str = "completed",
        next_in_queue: str | None = None
    ) -> None:
        """Test helper: Simulate lock release event.

        Directly emits a lock released event without modifying internal state.

        Args:
            project_id: Project ID
            board_id: Board ID
            work_item_id: Work item ID
            reason: Reason for release ('completed', 'exit_column', 'timeout', 'manual')
            next_in_queue: Optional next work item in queue
        """
        self.emit(LockReleasedEvent(
            type="lock.released",
            project_id=project_id,
            board_id=board_id,
            work_item_id=work_item_id,
            reason=reason,  # type: ignore
            next_in_queue=next_in_queue,
            timestamp=self._get_iso_timestamp(),
            source="mock"
        ))

    # Helper Methods

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current time as ISO 8601 timestamp."""
        return datetime.now(UTC).isoformat()
