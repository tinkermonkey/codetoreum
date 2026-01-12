"""Board-related events for vendor-agnostic project board integration.

Events track changes to work items on project boards (Kanban-style boards,
project management boards, etc.) across different vendor platforms.

Terminology (vendor-agnostic):
- Column/Workflow State: The status field on a board (e.g., GitHub Project v2 field)
- Work Item: A unit of work (issue, task, story, etc.)
- Project Board: The board containing work items (GitHub Projects v2, Jira board, etc.)
"""

from typing import List, Literal, Optional
from uuid import uuid4

from .adapter_events import CodetoreumEvent


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

    def __init__(
        self,
        type: str = "workitem.column_changed",
        timestamp: str = "",
        source: str = "",
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        work_item_id: str = "",
        project_id: str = "",
        board_id: str = "",
        from_column: str = "",
        to_column: str = "",
        moved_by: Literal["human", "orchestrator", "unknown"] = "unknown",
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
        self.board_id = board_id
        self.from_column = from_column
        self.to_column = to_column
        self.moved_by = moved_by
        self._validate()

    def _validate(self) -> None:
        """Validate event fields."""
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
            event_id=data.get("event_id"),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            from_column=data.get("from_column", ""),
            to_column=data.get("to_column", ""),
            moved_by=data.get("moved_by", "unknown"),  # type: ignore
        )


class BoardReconciledEvent(CodetoreumEvent):
    """Emitted when a board's structure is reconciled with the source system.

    This event is emitted when the adapter detects that the board's columns
    or work items have changed structurally (columns added/removed, items
    repositioned). This can be used to trigger full board re-sync if needed.

    Attributes:
        type: Fixed to "board.reconciled"
        project_id: ID of the project
        board_id: ID of the board
        columns_added: List of new column names
        columns_removed: List of deleted column names
        items_moved: Number of work items repositioned
    """

    def __init__(
        self,
        type: str = "board.reconciled",
        timestamp: str = "",
        source: str = "",
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        project_id: str = "",
        board_id: str = "",
        columns_added: Optional[List[str]] = None,
        columns_removed: Optional[List[str]] = None,
        items_moved: int = 0,
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
        self.columns_added = columns_added or []
        self.columns_removed = columns_removed or []
        self.items_moved = items_moved
        self._validate()

    def _validate(self) -> None:
        """Validate event fields."""
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.board_id:
            raise ValueError("board_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "project_id": self.project_id,
            "board_id": self.board_id,
            "columns_added": self.columns_added or [],
            "columns_removed": self.columns_removed or [],
            "items_moved": self.items_moved,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BoardReconciledEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "board.reconciled"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id"),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            columns_added=data.get("columns_added"),
            columns_removed=data.get("columns_removed"),
            items_moved=data.get("items_moved", 0),
        )
