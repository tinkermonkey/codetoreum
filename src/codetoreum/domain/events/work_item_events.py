"""Work item events for vendor-agnostic integration.

Events track the lifecycle and updates to work items (issues, tasks, stories, etc.)
across different vendor platforms.

Terminology (vendor-agnostic):
- Work Item: A unit of work (issue, task, story, epic, etc.)
- Work Item ID: The identifier of a work item (issue number, key, etc.)
"""

from typing import Any, Dict, Optional
from uuid import uuid4

from .adapter_events import CodetoreumEvent


class WorkItemCreatedEvent(CodetoreumEvent):
    """Emitted when a work item is created."""

    def __init__(
        self,
        type: str = "workitem.created",
        timestamp: str = "",
        source: str = "",
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        work_item_id: str = "",
        project_id: str = "",
        title: str = "",
        initial_column: Optional[str] = None,
    ):
        super().__init__(
            type=type,
            timestamp=timestamp,
            source=source,
            correlation_id=correlation_id,
            event_id=event_id or str(uuid4()),
        )
        self.work_item_id = work_item_id
        self.project_id = project_id
        self.title = title
        self.initial_column = initial_column
        self._validate()

    def _validate(self) -> None:
        """Validate event fields."""
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
            event_id=data.get("event_id"),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            title=data.get("title", ""),
            initial_column=data.get("initial_column"),
        )


class WorkItemUpdatedEvent(CodetoreumEvent):
    """Emitted when a work item's properties are updated."""

    def __init__(
        self,
        type: str = "workitem.updated",
        timestamp: str = "",
        source: str = "",
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        work_item_id: str = "",
        project_id: str = "",
        changes: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            type=type,
            timestamp=timestamp,
            source=source,
            correlation_id=correlation_id,
            event_id=event_id or str(uuid4()),
        )
        self.work_item_id = work_item_id
        self.project_id = project_id
        self.changes = changes or {}
        self._validate()

    def _validate(self) -> None:
        """Validate event fields."""
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")

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
            event_id=data.get("event_id"),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            changes=data.get("changes", {}),
        )
