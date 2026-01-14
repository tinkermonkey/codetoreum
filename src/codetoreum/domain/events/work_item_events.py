"""Work item events for vendor-agnostic integration.

Events track the lifecycle and updates to work items (issues, tasks, stories, etc.)
across different vendor platforms.

Terminology (vendor-agnostic):
- Work Item: A unit of work (issue, task, story, epic, etc.)
- Work Item ID: The identifier of a work item (issue number, key, etc.)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class WorkItemCreatedEvent(CodetoreumEvent):
    """Emitted when a work item is created."""

    work_item_id: str = ""
    project_id: str = ""
    title: str = ""
    initial_column: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.title:
            raise ValueError("title is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "title": self.title,
            "initial_column": self.initial_column,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemCreatedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "workitem.created"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            title=data.get("title", ""),
            initial_column=data.get("initial_column"),
        )


@dataclass(frozen=True)
class WorkItemUpdatedEvent(CodetoreumEvent):
    """Emitted when a work item's properties are updated.

    Note: The `changes` dict is mutable, but the field reference is immutable (frozen).
    This is an intentional exception to allow flexible change tracking while maintaining
    immutability of the event itself and preventing field reassignment.
    """

    work_item_id: str = ""
    project_id: str = ""
    changes: Dict[str, Any] = field(default_factory=dict)  # type: ignore

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        # Ensure changes dict is initialized
        if self.changes is None:
            object.__setattr__(self, "changes", {})

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "changes": self.changes or {},
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemUpdatedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "workitem.updated"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            changes=data.get("changes", {}),
        )
