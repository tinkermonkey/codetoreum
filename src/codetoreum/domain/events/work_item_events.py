"""Work item events for vendor-agnostic integration.

Events track the lifecycle and updates to work items (issues, tasks, stories, etc.)
across different vendor platforms.

Terminology (vendor-agnostic):
- Work Item: A unit of work (issue, task, story, epic, etc.)
- Work Item ID: The identifier of a work item (issue number, key, etc.)
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class WorkItemCreatedEvent(CodetoreumEvent):
    """Emitted when a work item is created.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "workitem.created"
        work_item_id (str): ID of the newly created work item
        project_id (str): ID of the project containing the work item
        title (str): Title or name of the work item
        initial_column (Optional[str]): Name of initial board column, None if not on board

    Example:
        >>> event = WorkItemCreatedEvent(
        ...     type="workitem.created",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     work_item_id="123",
        ...     project_id="proj-1",
        ...     title="Implement new feature"
        ... )
        >>> event.title = "Updated title"  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    project_id: str = ""
    title: str = ""
    initial_column: str | None = None
    parent_issue_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.title:
            msg = "title is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "title": self.title,
                "initial_column": self.initial_column,
                "parent_issue_id": self.parent_issue_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemCreatedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (work_item_id, project_id, title) are missing.
        """
        return cls(
            type=data.get("type", "workitem.created"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data["work_item_id"],
            project_id=data["project_id"],
            title=data["title"],
            initial_column=data.get("initial_column"),
            parent_issue_id=data.get("parent_issue_id"),
        )


@dataclass(frozen=True)
class WorkItemUpdatedEvent(CodetoreumEvent):
    """Emitted when a work item's properties are updated.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created. The `changes` dict is wrapped in MappingProxyType
    to ensure deep immutability, preventing in-place mutations that could break
    the event sourcing audit trail.

    Attributes:
        type (str): Fixed to "workitem.updated"
        work_item_id (str): ID of the updated work item
        project_id (str): ID of the project containing the work item
        changes (MappingProxyType): Immutable mapping of field names to new values.
            Wrapped in MappingProxyType to prevent in-place mutations.

    Example:
        >>> event = WorkItemUpdatedEvent(
        ...     type="workitem.updated",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     work_item_id="123",
        ...     project_id="proj-1",
        ...     changes={"status": "In Progress"}
        ... )
        >>> event.changes = {"status": "Done"}  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    project_id: str = ""
    changes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        # Wrap changes dict in MappingProxyType for deep immutability
        object.__setattr__(self, "changes", MappingProxyType(self.changes or {}))

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "changes": dict(self.changes) if self.changes else {},
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemUpdatedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (work_item_id, project_id) are missing.
        """
        return cls(
            type=data.get("type", "workitem.updated"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data["work_item_id"],
            project_id=data["project_id"],
            changes=data.get("changes", {}),
        )
