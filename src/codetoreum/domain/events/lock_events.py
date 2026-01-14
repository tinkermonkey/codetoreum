"""Pipeline lock events for managing work item state transitions.

Events track the acquisition, holding, and release of locks on work items
as they progress through the pipeline.

Terminology (vendor-agnostic):
- Lock: A claim on a work item that prevents concurrent modifications
- Stale Lock: A lock that hasn't been updated/renewed within a timeout period
"""

from dataclasses import dataclass
from typing import Literal, Optional
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class LockAcquiredEvent(CodetoreumEvent):
    """Emitted when a lock is acquired on a work item."""

    project_id: str = ""
    board_id: str = ""
    work_item_id: str = ""
    acquisition_method: Literal["normal", "stale_recovery"] = "normal"

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.board_id:
            raise ValueError("board_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "project_id": self.project_id,
            "board_id": self.board_id,
            "work_item_id": self.work_item_id,
            "acquisition_method": self.acquisition_method,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LockAcquiredEvent":
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
            acquisition_method=data.get("acquisition_method", "normal"),  # type: ignore
        )


@dataclass(frozen=True)
class LockReleasedEvent(CodetoreumEvent):
    """Emitted when a lock is released from a work item."""

    project_id: str = ""
    board_id: str = ""
    work_item_id: str = ""
    reason: Literal["completed", "exit_column", "timeout", "manual"] = "completed"
    next_in_queue: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.board_id:
            raise ValueError("board_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "project_id": self.project_id,
            "board_id": self.board_id,
            "work_item_id": self.work_item_id,
            "reason": self.reason,
            "next_in_queue": self.next_in_queue,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LockReleasedEvent":
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
            reason=data.get("reason", "completed"),  # type: ignore
            next_in_queue=data.get("next_in_queue"),
        )


@dataclass(frozen=True)
class LockStaleDetectedEvent(CodetoreumEvent):
    """Emitted when a stale lock is detected."""

    project_id: str = ""
    board_id: str = ""
    work_item_id: str = ""
    lock_acquired_at: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.board_id:
            raise ValueError("board_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.lock_acquired_at:
            raise ValueError("lock_acquired_at is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "project_id": self.project_id,
            "board_id": self.board_id,
            "work_item_id": self.work_item_id,
            "lock_acquired_at": self.lock_acquired_at,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LockStaleDetectedEvent":
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

    Distinct from LockAcquiredEvent - this is specific to the application-layer
    pipeline lock service which manages position-based queue ordering.
    """

    project_id: str = ""
    work_item_id: str = ""
    board_id: str = ""
    queue_length_at_acquire: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.board_id:
            raise ValueError("board_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "project_id": self.project_id,
            "work_item_id": self.work_item_id,
            "board_id": self.board_id,
            "queue_length_at_acquire": self.queue_length_at_acquire,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineLockAcquiredEvent":
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

    Distinct from LockReleasedEvent - this is specific to the application-layer
    pipeline lock service which manages position-based queue ordering.
    """

    project_id: str = ""
    work_item_id: str = ""
    board_id: str = ""
    next_work_item_id: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.board_id:
            raise ValueError("board_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "project_id": self.project_id,
            "work_item_id": self.work_item_id,
            "board_id": self.board_id,
            "next_work_item_id": self.next_work_item_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineLockReleasedEvent":
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
class WorkItemQueuedEvent(CodetoreumEvent):
    """Emitted when a work item is added to pipeline lock queue.

    Indicates that a work item could not acquire the lock immediately
    and has been added to the position-based queue.
    """

    work_item_id: str = ""
    board_id: str = ""
    queue_position: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.board_id:
            raise ValueError("board_id is required")
        if self.queue_position < 0:
            raise ValueError("queue_position must be non-negative")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "work_item_id": self.work_item_id,
            "board_id": self.board_id,
            "queue_position": self.queue_position,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemQueuedEvent":
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
