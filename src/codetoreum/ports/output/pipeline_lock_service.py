"""Pipeline lock service port interface with event emission.

This interface defines contracts for managing locks on work items as they
progress through the pipeline, enabling safe exclusive execution of work
and preventing concurrent modifications.

Pipeline locks ensure that only one process (agent, manual user, etc.)
can work on a work item at a time, essential for coordination in a
multi-agent orchestration system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from .event_emitter import IEventEmitter


class LockStateInfo(Protocol):
    """Protocol for lock state information returned by get_all_lock_states().

    Defines the contract for objects returned by IPipelineLockService.get_all_lock_states().
    Both simple lock states and complex queue states must implement this interface.

    This protocol allows different implementations to return different concrete types
    (LockState, PipelineQueueState, etc.) as long as they provide these two fields
    for watchdogs and monitoring tools.
    """

    @property
    def lock_holder(self) -> str | None:
        """Current lock holder ID or None if lock is not held."""
        ...

    @property
    def lock_acquired_at(self) -> datetime | None:
        """Datetime when lock was acquired or None if not held."""
        ...


@dataclass(frozen=True)
class PipelineLock:
    """Represents a lock held on a work item.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        project_id: Project containing the locked work item
        board_id: Board containing the locked work item
        work_item_id: Locked work item
        locked_by_work_item: Identifier of who/what holds the lock
                            (usually a work_item_id or agent_id)
        lock_acquired_at: ISO 8601 timestamp when lock was acquired
        lock_status: Current lock state (locked, unlocked)
    """

    project_id: str
    board_id: str
    work_item_id: str
    locked_by_work_item: str
    lock_acquired_at: str
    lock_status: Literal["locked", "unlocked"]

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.project_id, str) or not self.project_id:
            msg = "project_id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.board_id, str) or not self.board_id:
            msg = "board_id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.work_item_id, str) or not self.work_item_id:
            msg = "work_item_id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.locked_by_work_item, str) or not self.locked_by_work_item:
            msg = "locked_by_work_item must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.lock_acquired_at, str) or not self.lock_acquired_at:
            msg = "lock_acquired_at must be a non-empty string"
            raise ValueError(msg)

        if self.lock_status not in ("locked", "unlocked"):
            msg = f"lock_status must be 'locked' or 'unlocked', got: {self.lock_status}"
            raise ValueError(msg)


class IPipelineLockService(IEventEmitter, ABC):
    """Pipeline lock management with event emission.

    Provides mechanisms to coordinate exclusive access to work items
    as they progress through a multi-stage workflow. This prevents
    concurrent modifications and ensures work items are processed by
    only one agent/process at a time.

    The lock service is project-wide (not work-item-specific like discussions).
    It manages locks across all work items in a project's pipeline.

    Events emitted:
        - 'lock.acquired' → LockAcquiredEvent
                           When lock is successfully acquired
        - 'lock.released' → LockReleasedEvent
                           When lock is released
        - 'lock.stale_detected' → StaleLockDetectedEvent
                                 When a lock hasn't been updated in too long

    Lock Lifecycle:
        1. try_acquire_lock() → Returns (success, reason)
        2. Process work on the item while holding lock
        3. release_lock() → Frees lock for next process

    Stale Lock Recovery:
        Locks that haven't been updated beyond a timeout threshold are
        considered stale and can be forcibly released. This handles
        scenarios where a process crashed while holding a lock.

    Example:
        async with service as svc:
            # Try to acquire lock
            success, reason = await svc.try_acquire_lock(
                project_id="proj-123",
                board_id="board-456",
                work_item_id="item-789"
            )

            if success:
                try:
                    # Do work on the item
                    await process_item("item-789")
                finally:
                    # Always release when done
                    await svc.release_lock(
                        project_id="proj-123",
                        board_id="board-456",
                        work_item_id="item-789"
                    )
            else:
                # Handle lock acquisition failure
                print(f"Could not acquire lock: {reason}")

            # Query all locks
            all_locks = await svc.get_all_locks()
    """

    # Query Operations

    @abstractmethod
    async def get_lock(self, project_id: str, board_id: str) -> PipelineLock | None:
        """Query current lock state for a project's board.

        Returns the active lock if one exists, or None if no lock is held.

        Args:
            project_id: Project to query
            board_id: Board to query

        Returns:
            PipelineLock if a lock is currently held, None otherwise

        Raises:
            ResourceNotFoundError: Project or board doesn't exist
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    async def get_all_locks(self) -> list[PipelineLock]:
        """Retrieve all active locks across all projects and boards.

        Useful for operational visibility and detecting lock contention.

        Returns:
            List[PipelineLock]: All currently held locks

        Raises:
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    def get_all_lock_states(self) -> dict[str, LockStateInfo]:
        """Return all pipeline lock states for monitoring and diagnostics.

        Intended for internal tools (watchdogs, dashboards) that need detailed
        lock state without waiting for async operations. This method provides
        immediate access to current lock state including acquisition times.

        Returns:
            dict[str, LockStateInfo]: Mapping of lock keys to lock state objects
                                     Key format: "project_id:board_id"
                                     Values conform to LockStateInfo protocol with:
                                     - lock_holder: Current lock holder ID or None
                                     - lock_acquired_at: Datetime when lock was acquired or None

        Note:
            This is a synchronous method for performance-critical monitoring
            operations (e.g., stale lock detection in watchdogs). The returned
            dict should contain thread-safe snapshots of lock states.

            Different implementations may return different concrete types
            (LockState, PipelineQueueState, etc.) as long as they conform
            to the LockStateInfo protocol.
        """

    # Command Operations

    @abstractmethod
    async def try_acquire_lock(self, project_id: str, board_id: str, work_item_id: str) -> tuple[bool, str]:
        """Attempt to acquire lock for exclusive work item access.

        Tries to acquire a lock on the work item. If successful, the caller
        can proceed with exclusive access. If unsuccessful, returns reason
        explaining why (e.g., "lock already held by X").

        Returns a tuple (success: bool, reason: str) rather than raising
        exceptions to enable graceful handling of lock contention.

        Args:
            project_id: Project containing the work item
            board_id: Board containing the work item
            work_item_id: Work item to lock

        Returns:
            Tuple[bool, str]:
                - (True, ""): Lock acquired successfully
                - (False, reason): Acquisition failed
                  Reasons include:
                  - "lock already held by work_item_X" (already locked)
                  - "project not found"
                  - "board not found"
                  - "work item not found"

        Raises:
            ValidationError: Invalid parameters
            ExternalServiceError: Service communication failure

        Events:
            Emits 'lock.acquired' event on success with acquisition_method='normal'
            If a stale lock is detected and forcibly released, emits that event
            with acquisition_method='stale_recovery'
        """

    @abstractmethod
    async def release_lock(self, project_id: str, board_id: str, work_item_id: str) -> bool:
        """Release lock held on a work item.

        Releases the lock if it's currently held by this work_item_id.
        If the lock is held by someone else or doesn't exist, returns False.

        Args:
            project_id: Project containing the work item
            board_id: Board containing the work item
            work_item_id: Work item to unlock (must match holder)

        Returns:
            bool: True if lock was released, False if not held or mismatch

        Raises:
            ValidationError: Invalid parameters
            ExternalServiceError: Service communication failure

        Events:
            Emits 'lock.released' event on successful release
        """
