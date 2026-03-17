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
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if not self.from_column:
            msg = "from_column is required"
            raise ValueError(msg)
        if not self.to_column:
            msg = "to_column is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "board_id": self.board_id,
                "from_column": self.from_column,
                "to_column": self.to_column,
                "moved_by": self.moved_by,
            }
        )
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
class WorkItemPositionChangedEvent(CodetoreumEvent):
    """Emitted when a work item's position changes within the same column.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    This event captures the positional reordering of work items within a column
    (e.g., dragging a card up or down, or automatic reordering after removals).
    It does not represent movement between columns—use WorkItemColumnChangedEvent
    for that.

    Attributes:
        type (str): Fixed to "workitem.position_changed"
        work_item_id (str): ID of the work item that was repositioned
        project_id (str): ID of the project containing the board
        board_id (str): ID of the board where the reordering occurred
        column_name (str): Name of the column where the repositioning happened
        old_position (int): Previous position in the column (0-indexed)
        new_position (int): New position in the column (0-indexed)

    Example:
        >>> event = WorkItemPositionChangedEvent(
        ...     type="workitem.position_changed",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock",
        ...     work_item_id="123",
        ...     project_id="proj-1",
        ...     board_id="board-1",
        ...     column_name="In Progress",
        ...     old_position=2,
        ...     new_position=1
        ... )
        >>> event.new_position = 3  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    project_id: str = ""
    board_id: str = ""
    column_name: str = ""
    old_position: int = 0
    new_position: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if not self.column_name:
            msg = "column_name is required"
            raise ValueError(msg)
        if self.old_position < 0:
            msg = "old_position must be non-negative"
            raise ValueError(msg)
        if self.new_position < 0:
            msg = "new_position must be non-negative"
            raise ValueError(msg)
        if self.old_position == self.new_position:
            msg = "old_position must differ from new_position (position did not actually change)"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "board_id": self.board_id,
                "column_name": self.column_name,
                "old_position": self.old_position,
                "new_position": self.new_position,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemPositionChangedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "workitem.position_changed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            column_name=data.get("column_name", ""),
            old_position=data.get("old_position", 0),
            new_position=data.get("new_position", 0),
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
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        # Convert lists to tuples for immutability
        if isinstance(self.columns_added, list):
            object.__setattr__(self, "columns_added", tuple(self.columns_added))
        if isinstance(self.columns_removed, list):
            object.__setattr__(self, "columns_removed", tuple(self.columns_removed))

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "project_id": self.project_id,
                "board_id": self.board_id,
                "columns_added": list(self.columns_added),
                "columns_removed": list(self.columns_removed),
                "items_moved": self.items_moved,
            }
        )
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


@dataclass(frozen=True)
class ColumnSLAExceededEvent(CodetoreumEvent):
    """Emitted when a work item exceeds its column's SLA threshold.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    This event is emitted by the SLAExpiryWatchdog when a work item has remained
    in a column longer than the configured SLA threshold for that column.

    Attributes:
        type (str): Fixed to "column.sla_exceeded"
        work_item_id (str): ID of the work item that exceeded SLA
        project_id (str): ID of the project containing the board
        board_id (str): ID of the board where the item is located
        column_name (str): Name of the column where SLA was exceeded
        elapsed_seconds (int): Time (in seconds) the item has spent in column
        sla_threshold_seconds (int): SLA threshold (in seconds) for the column
        entered_at (str): ISO format timestamp when item entered the column

    Example:
        >>> event = ColumnSLAExceededEvent(
        ...     type="column.sla_exceeded",
        ...     timestamp="2025-01-14T12:30:00+00:00",
        ...     source="simulation",
        ...     work_item_id="123",
        ...     project_id="proj-1",
        ...     board_id="board-1",
        ...     column_name="Code Review",
        ...     elapsed_seconds=7200,
        ...     sla_threshold_seconds=3600,
        ...     entered_at="2025-01-14T10:30:00+00:00"
        ... )
        >>> event.elapsed_seconds = 5400  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    project_id: str = ""
    board_id: str = ""
    column_name: str = ""
    elapsed_seconds: int = 0
    sla_threshold_seconds: int = 0
    entered_at: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if not self.column_name:
            msg = "column_name is required"
            raise ValueError(msg)
        if self.elapsed_seconds <= 0:
            msg = "elapsed_seconds must be positive"
            raise ValueError(msg)
        if self.sla_threshold_seconds <= 0:
            msg = "sla_threshold_seconds must be positive"
            raise ValueError(msg)
        if self.elapsed_seconds <= self.sla_threshold_seconds:
            msg = "elapsed_seconds must exceed sla_threshold_seconds"
            raise ValueError(msg)
        if not self.entered_at:
            msg = "entered_at is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "board_id": self.board_id,
                "column_name": self.column_name,
                "elapsed_seconds": self.elapsed_seconds,
                "sla_threshold_seconds": self.sla_threshold_seconds,
                "entered_at": self.entered_at,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ColumnSLAExceededEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "column.sla_exceeded"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            board_id=data.get("board_id", ""),
            column_name=data.get("column_name", ""),
            elapsed_seconds=data.get("elapsed_seconds", 0),
            sla_threshold_seconds=data.get("sla_threshold_seconds", 0),
            entered_at=data.get("entered_at", ""),
        )
