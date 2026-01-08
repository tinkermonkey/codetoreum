"""Pipeline lock events for managing work item state transitions.

Events track the acquisition, holding, and release of locks on work items
as they progress through the pipeline.

Terminology (vendor-agnostic):
- Lock: A claim on a work item that prevents concurrent modifications
- Stale Lock: A lock that hasn't been updated/renewed within a timeout period
"""

from typing import Literal, Optional
from uuid import uuid4

from .adapter_events import CodetoreumEvent


class LockAcquiredEvent(CodetoreumEvent):
    """Emitted when a lock is acquired on a work item."""

    def __init__(
        self,
        type: str = "lock.acquired",
        timestamp: str = "",
        source: str = "",
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        project_id: str = "",
        board_id: str = "",
        work_item_id: str = "",
        acquisition_method: Literal["normal", "stale_recovery"] = "normal",
    ):
        super().__init__(
            type=type,
            timestamp=timestamp,
            source=source,
            correlation_id=correlation_id,
            event_id=event_id or str(uuid4()),
        )
        self.project_id = project_id
        self.board_id = board_id
        self.work_item_id = work_item_id
        self.acquisition_method = acquisition_method
        self._validate()

    def _validate(self) -> None:
        """Validate event fields."""
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
            event_id=data.get("event_id"),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            work_item_id=data.get("work_item_id", ""),
            acquisition_method=data.get("acquisition_method", "normal"),  # type: ignore
        )


class LockReleasedEvent(CodetoreumEvent):
    """Emitted when a lock is released from a work item."""

    def __init__(
        self,
        type: str = "lock.released",
        timestamp: str = "",
        source: str = "",
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        project_id: str = "",
        board_id: str = "",
        work_item_id: str = "",
        reason: Literal["completed", "exit_column", "timeout", "manual"] = "completed",
        next_in_queue: Optional[str] = None,
    ):
        super().__init__(
            type=type,
            timestamp=timestamp,
            source=source,
            correlation_id=correlation_id,
            event_id=event_id or str(uuid4()),
        )
        self.project_id = project_id
        self.board_id = board_id
        self.work_item_id = work_item_id
        self.reason = reason
        self.next_in_queue = next_in_queue
        self._validate()

    def _validate(self) -> None:
        """Validate event fields."""
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
            event_id=data.get("event_id"),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            work_item_id=data.get("work_item_id", ""),
            reason=data.get("reason", "completed"),  # type: ignore
            next_in_queue=data.get("next_in_queue"),
        )


class LockStaleDetectedEvent(CodetoreumEvent):
    """Emitted when a stale lock is detected."""

    def __init__(
        self,
        type: str = "lock.stale_detected",
        timestamp: str = "",
        source: str = "",
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        project_id: str = "",
        board_id: str = "",
        work_item_id: str = "",
        lock_acquired_at: str = "",
    ):
        super().__init__(
            type=type,
            timestamp=timestamp,
            source=source,
            correlation_id=correlation_id,
            event_id=event_id or str(uuid4()),
        )
        self.project_id = project_id
        self.board_id = board_id
        self.work_item_id = work_item_id
        self.lock_acquired_at = lock_acquired_at
        self._validate()

    def _validate(self) -> None:
        """Validate event fields."""
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
            event_id=data.get("event_id"),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            work_item_id=data.get("work_item_id", ""),
            lock_acquired_at=data.get("lock_acquired_at", ""),
        )
