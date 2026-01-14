"""Board-related events for vendor-agnostic project board integration.

Events track changes to work items on project boards (Kanban-style boards,
project management boards, etc.) across different vendor platforms.

Terminology (vendor-agnostic):
- Column/Workflow State: The status field on a board (e.g., GitHub Project v2 field)
- Work Item: A unit of work (issue, task, story, etc.)
- Project Board: The board containing work items (GitHub Projects v2, Jira board, etc.)
"""

from dataclasses import dataclass
from typing import Literal, Optional, Tuple
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class WorkItemColumnChangedEvent(CodetoreumEvent):
    """Emitted when a work item moves between columns on a board.

    This event captures the movement of a work item from one column
    (workflow state) to another, including who initiated the change
    (human, orchestrator, or unknown).

    Attributes:
        type: Fixed to "workitem.column_changed"
        work_item_id: ID of the work item that moved (e.g., issue #123)
        project_id: ID of the project containing the board
        board_id: ID of the board where the move occurred
        from_column: Name of the column the item left
        to_column: Name of the column the item entered
        moved_by: Actor who initiated the move ("human", "orchestrator", "unknown")
    """

    work_item_id: str = ""
    project_id: str = ""
    board_id: str = ""
    from_column: str = ""
    to_column: str = ""
    moved_by: Literal["human", "orchestrator", "unknown"] = "unknown"

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.board_id:
            raise ValueError("board_id is required")
        if not self.from_column:
            raise ValueError("from_column is required")
        if not self.to_column:
            raise ValueError("to_column is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "board_id": self.board_id,
            "from_column": self.from_column,
            "to_column": self.to_column,
            "moved_by": self.moved_by,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemColumnChangedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "workitem.column_changed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            from_column=data.get("from_column", ""),
            to_column=data.get("to_column", ""),
            moved_by=data.get("moved_by", "unknown"),  # type: ignore
        )


@dataclass(frozen=True)
class BoardReconciledEvent(CodetoreumEvent):
    """Emitted when a board's structure is reconciled with the source system.

    This event is emitted when the adapter detects that the board's columns
    or work items have changed structurally (columns added/removed, items
    repositioned). This can be used to trigger full board re-sync if needed.

    Attributes:
        type: Fixed to "board.reconciled"
        project_id: ID of the project
        board_id: ID of the board
        columns_added: Tuple of new column names (immutable)
        columns_removed: Tuple of deleted column names (immutable)
        items_moved: Number of work items repositioned
    """

    project_id: str = ""
    board_id: str = ""
    columns_added: Tuple[str, ...] = ()
    columns_removed: Tuple[str, ...] = ()
    items_moved: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization and convert lists to tuples."""
        super().__post_init__()
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.board_id:
            raise ValueError("board_id is required")
        # Convert lists to tuples for immutability
        if isinstance(self.columns_added, list):
            object.__setattr__(self, "columns_added", tuple(self.columns_added))
        if isinstance(self.columns_removed, list):
            object.__setattr__(self, "columns_removed", tuple(self.columns_removed))

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "project_id": self.project_id,
            "board_id": self.board_id,
            "columns_added": list(self.columns_added),
            "columns_removed": list(self.columns_removed),
            "items_moved": self.items_moved,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BoardReconciledEvent":
        """Deserialize from dictionary."""
        columns_added = data.get("columns_added", [])
        columns_removed = data.get("columns_removed", [])
        return cls(
            type=data.get("type", "board.reconciled"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            columns_added=tuple(columns_added) if columns_added else (),
            columns_removed=tuple(columns_removed) if columns_removed else (),
            items_moved=data.get("items_moved", 0),
        )
