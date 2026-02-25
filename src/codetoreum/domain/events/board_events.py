"""Board-related events for vendor-agnostic project board integration.

Events track changes to work items on project boards (Kanban-style boards,
project management boards, etc.) across different vendor platforms.

Terminology (vendor-agnostic):
- Column/Workflow State: The status field on a board (e.g., GitHub Project v2 field)
- Work Item: A unit of work (issue, task, story, etc.)
- Project Board: The board containing work items (GitHub Projects v2, Jira board, etc.)
"""

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class WorkItemColumnChangedEvent(CodetoreumEvent):
    """Emitted when a work item moves between columns on a board.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    This event captures the movement of a work item from one column
    (workflow state) to another, including who initiated the change
    (human, orchestrator, or unknown).

    Attributes:
        type (str): Fixed to "workitem.column_changed"
        work_item_id (str): ID of the work item that moved (e.g., issue #123)
        project_id (str): ID of the project containing the board
        board_id (str): ID of the board where the move occurred
        from_column (str): Name of the column the item left
        to_column (str): Name of the column the item entered
        moved_by (Literal["human", "orchestrator", "unknown"]): Actor who initiated the move

    Example:
        >>> event = WorkItemColumnChangedEvent(
        ...     type="workitem.column_changed",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     work_item_id="123",
        ...     project_id="proj-1",
        ...     board_id="board-1",
        ...     from_column="Backlog",
        ...     to_column="In Progress",
        ...     moved_by="human"
        ... )
        >>> event.to_column = "Done"  # ❌ Raises FrozenInstanceError
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
            moved_by=data.get("moved_by", "unknown"),
        )


@dataclass(frozen=True)
class BoardReconciledEvent(CodetoreumEvent):
    """Emitted when a board's structure is reconciled with the source system.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    This event is emitted when the adapter detects that the board's columns
    or work items have changed structurally (columns added/removed, items
    repositioned). This can be used to trigger full board re-sync if needed.

    Attributes:
        type (str): Fixed to "board.reconciled"
        project_id (str): ID of the project
        board_id (str): ID of the board
        columns_added (Tuple[str, ...]): Immutable tuple of new column names
        columns_removed (Tuple[str, ...]): Immutable tuple of deleted column names
        items_moved (int): Number of work items repositioned

    Example:
        >>> event = BoardReconciledEvent(
        ...     type="board.reconciled",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     project_id="proj-1",
        ...     board_id="board-1",
        ...     columns_added=("Review", "Done"),
        ...     columns_removed=("Archived",),
        ...     items_moved=5
        ... )
        >>> event.items_moved = 10  # ❌ Raises FrozenInstanceError
    """

    project_id: str = ""
    board_id: str = ""
    columns_added: tuple[str, ...] = ()
    columns_removed: tuple[str, ...] = ()
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
