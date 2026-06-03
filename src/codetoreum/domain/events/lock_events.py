"""Pipeline lock events for managing work item state transitions.

Events track the acquisition, holding, and release of locks on work items
as they progress through the pipeline.

Terminology (vendor-agnostic):
- Lock: A claim on a work item that prevents concurrent modifications
- Stale Lock: A lock that hasn't been updated/renewed within a timeout period
"""

from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class LockAcquiredEvent(CodetoreumEvent):
    """Emitted when a lock is acquired on a work item.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "lock.acquired"
        project_id (str): ID of the project
        board_id (str): ID of the board containing the work item
        work_item_id (str): ID of the work item for which the lock was acquired
        acquisition_method (Literal["normal", "stale_recovery"]): Method used to acquire lock

    Example:
        >>> event = LockAcquiredEvent(
        ...     type="lock.acquired",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     project_id="proj-1",
        ...     board_id="board-1",
        ...     work_item_id="123"
        ... )
        >>> event.acquisition_method = "stale_recovery"  # ❌ Raises FrozenInstanceError
    """

    project_id: str = ""
    board_id: str = ""
    work_item_id: str = ""
    acquisition_method: Literal["normal", "stale_recovery"] = "normal"

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "board_id": self.board_id,
                "work_item_id": self.work_item_id,
                "acquisition_method": self.acquisition_method,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LockAcquiredEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "lock.acquired"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            work_item_id=data.get("work_item_id", ""),
            acquisition_method=data.get("acquisition_method", "normal"),
        )


@dataclass(frozen=True)
class LockReleasedEvent(CodetoreumEvent):
    """Emitted when a lock is released from a work item.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "lock.released"
        project_id (str): ID of the project
        board_id (str): ID of the board containing the work item
        work_item_id (str): ID of the work item for which the lock was released
        reason (Literal["completed", "exit_column", "timeout", "manual"]): Reason for releasing lock
        next_in_queue (Optional[str]): ID of next work item in queue if any, None if queue empty

    Example:
        >>> event = LockReleasedEvent(
        ...     type="lock.released",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     project_id="proj-1",
        ...     board_id="board-1",
        ...     work_item_id="123",
        ...     reason="completed"
        ... )
        >>> event.reason = "timeout"  # ❌ Raises FrozenInstanceError
    """

    project_id: str = ""
    board_id: str = ""
    work_item_id: str = ""
    reason: Literal["completed", "exit_column", "timeout", "manual"] = "completed"
    next_in_queue: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "board_id": self.board_id,
                "work_item_id": self.work_item_id,
                "reason": self.reason,
                "next_in_queue": self.next_in_queue,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LockReleasedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "lock.released"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            work_item_id=data.get("work_item_id", ""),
            reason=data.get("reason", "completed"),
            next_in_queue=data.get("next_in_queue"),
        )


@dataclass(frozen=True)
class StaleLockDetectedEvent(CodetoreumEvent):
    """Emitted when a stale lock is detected.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "lock.stale_detected"
        project_id (str): ID of the project
        board_id (str): ID of the board containing the work item
        work_item_id (str): ID of the work item with stale lock
        lock_acquired_at (str): ISO 8601 timestamp when the lock was originally acquired

    Example:
        >>> event = StaleLockDetectedEvent(
        ...     type="lock.stale_detected",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     project_id="proj-1",
        ...     board_id="board-1",
        ...     work_item_id="123",
        ...     lock_acquired_at="2025-01-14T08:00:00+00:00"
        ... )
        >>> event.lock_acquired_at = "2025-01-14T09:00:00+00:00"  # ❌ Raises FrozenInstanceError
    """

    project_id: str = ""
    board_id: str = ""
    work_item_id: str = ""
    lock_acquired_at: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.lock_acquired_at:
            msg = "lock_acquired_at is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "board_id": self.board_id,
                "work_item_id": self.work_item_id,
                "lock_acquired_at": self.lock_acquired_at,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StaleLockDetectedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "lock.stale_detected"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            work_item_id=data.get("work_item_id", ""),
            lock_acquired_at=data.get("lock_acquired_at", ""),
        )


@dataclass(frozen=True)
class PipelineLockAcquiredEvent(CodetoreumEvent):
    """Emitted when a work item acquires a pipeline lock.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Distinct from LockAcquiredEvent - this is specific to the application-layer
    pipeline lock service which manages position-based queue ordering.

    Attributes:
        type (str): Fixed to "pipeline.lock_acquired"
        project_id (str): ID of the project
        work_item_id (str): ID of the work item acquiring the pipeline lock
        board_id (str): ID of the board containing the work item
        queue_length_at_acquire (int): Length of queue at time of acquisition

    Example:
        >>> event = PipelineLockAcquiredEvent(
        ...     type="pipeline.lock_acquired",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     project_id="proj-1",
        ...     work_item_id="123",
        ...     board_id="board-1",
        ...     queue_length_at_acquire=3
        ... )
        >>> event.queue_length_at_acquire = 5  # ❌ Raises FrozenInstanceError
    """

    project_id: str = ""
    work_item_id: str = ""
    board_id: str = ""
    queue_length_at_acquire: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "work_item_id": self.work_item_id,
                "board_id": self.board_id,
                "queue_length_at_acquire": self.queue_length_at_acquire,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineLockAcquiredEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pipeline.lock_acquired"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data.get("project_id", ""),
            work_item_id=data.get("work_item_id", ""),
            board_id=data.get("board_id", ""),
            queue_length_at_acquire=data.get("queue_length_at_acquire", 0),
        )


@dataclass(frozen=True)
class PipelineLockReleasedEvent(CodetoreumEvent):
    """Emitted when a work item releases a pipeline lock.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Distinct from LockReleasedEvent - this is specific to the application-layer
    pipeline lock service which manages position-based queue ordering.

    Attributes:
        type (str): Fixed to "pipeline.lock_released"
        project_id (str): ID of the project
        work_item_id (str): ID of the work item releasing the pipeline lock
        board_id (str): ID of the board containing the work item
        next_work_item_id (Optional[str]): ID of next work item in queue, None if queue empty

    Example:
        >>> event = PipelineLockReleasedEvent(
        ...     type="pipeline.lock_released",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     project_id="proj-1",
        ...     work_item_id="123",
        ...     board_id="board-1"
        ... )
        >>> event.next_work_item_id = "124"  # ❌ Raises FrozenInstanceError
    """

    project_id: str = ""
    work_item_id: str = ""
    board_id: str = ""
    next_work_item_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "work_item_id": self.work_item_id,
                "board_id": self.board_id,
                "next_work_item_id": self.next_work_item_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineLockReleasedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pipeline.lock_released"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data.get("project_id", ""),
            work_item_id=data.get("work_item_id", ""),
            board_id=data.get("board_id", ""),
            next_work_item_id=data.get("next_work_item_id"),
        )


@dataclass(frozen=True)
class LockStuckEvent(CodetoreumEvent):
    """Emitted when a pipeline lock is stuck due to agent triggering failure.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    The next queued work item has acquired the lock but the agent failed to
    start. Manual intervention is required to release the lock.

    Attributes:
        type (str): Fixed to "lock.stuck"
        project_id (str): ID of the project
        board_id (str): ID of the board containing the work item
        work_item_id (str): ID of the work item holding the stuck lock
        reason (str): Human-readable description of why the agent trigger failed

    Example:
        >>> event = LockStuckEvent(
        ...     type="lock.stuck",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="board_event_handler",
        ...     project_id="proj-1",
        ...     board_id="board-1",
        ...     work_item_id="123",
        ...     reason="Agent executor timed out"
        ... )
        >>> event.reason = "other"  # ❌ Raises FrozenInstanceError
    """

    project_id: str = ""
    board_id: str = ""
    work_item_id: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.reason:
            msg = "reason is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "board_id": self.board_id,
                "work_item_id": self.work_item_id,
                "reason": self.reason,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LockStuckEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (project_id, board_id, work_item_id,
                     reason) are missing.
        """
        return cls(
            type=data.get("type", "lock.stuck"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data["project_id"],
            board_id=data["board_id"],
            work_item_id=data["work_item_id"],
            reason=data["reason"],
        )


@dataclass(frozen=True)
class WorkItemQueuedEvent(CodetoreumEvent):
    """Emitted when a work item is added to pipeline lock queue.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Indicates that a work item could not acquire the lock immediately
    and has been added to the position-based queue.

    Attributes:
        type (str): Fixed to "workitem.queued"
        work_item_id (str): ID of the work item queued
        board_id (str): ID of the board containing the work item
        queue_position (int): Position in the queue (0-based, 0 = next in queue)

    Example:
        >>> event = WorkItemQueuedEvent(
        ...     type="workitem.queued",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     work_item_id="123",
        ...     board_id="board-1",
        ...     queue_position=2
        ... )
        >>> event.queue_position = 3  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    board_id: str = ""
    queue_position: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if self.queue_position < 0:
            msg = "queue_position must be non-negative"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "board_id": self.board_id,
                "queue_position": self.queue_position,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkItemQueuedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "workitem.queued"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            board_id=data.get("board_id", ""),
            queue_position=data.get("queue_position", 0),
        )


@dataclass(frozen=True)
class WorkItemDequeuedEvent(CodetoreumEvent):
    """Emitted when a work item is removed from pipeline queue.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Indicates that a work item has been popped from the queue (because its
    lock was acquired) or removed from the queue (e.g., by the lock holder
    when it acquires the lock and discovers the item still in queue).

    Attributes:
        type (str): Fixed to "workitem.dequeued"
        work_item_id (str): ID of the work item dequeued
        board_id (str): ID of the board containing the work item
        reason (Literal["popped", "removed"]): Why the item was dequeued

    Example:
        >>> event = WorkItemDequeuedEvent(
        ...     type="workitem.dequeued",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="pipeline_queue",
        ...     work_item_id="123",
        ...     board_id="board-1",
        ...     reason="popped"
        ... )
        >>> event.reason = "removed"  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    board_id: str = ""
    reason: Literal["popped", "removed"] = "popped"

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if self.reason not in ("popped", "removed"):
            msg = f"reason must be 'popped' or 'removed', got: {self.reason}"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "board_id": self.board_id,
                "reason": self.reason,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkItemDequeuedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (work_item_id, board_id, reason)
                     are missing.
        """
        return cls(
            type=data.get("type", "workitem.dequeued"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data["work_item_id"],
            board_id=data["board_id"],
            reason=data["reason"],
        )
