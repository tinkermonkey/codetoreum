"""Board service port interface with event emission.

This interface defines contracts for project board management, including
board structure queries, work item movement, and board reconciliation.

Project boards organize work items into columns/lanes representing workflow
stages (e.g., Backlog, In Progress, Review, Done). Boards are vendor-agnostic
abstractions over GitHub Projects v2, Trello, JIRA boards, etc.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from .event_emitter import IEventEmitter
from .monitoring import IMonitoredService


class MovedByType(Enum):
    """Type of entity that moved a work item between columns."""

    HUMAN = "human"
    ORCHESTRATOR = "orchestrator"


@dataclass(frozen=True)
class BoardColumn:
    """Represents a column (lane) on a project board.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Work item IDs are converted
    to a tuple for true immutability - the dataclass is only shallowly frozen when
    fields contain mutable types, so we enforce deep immutability via conversion.

    Attributes:
        id: Unique identifier for the column in the external system
        name: Display name (e.g., "Backlog", "In Progress", "Done")
        position: Ordinal position (0 = leftmost/first)
        work_item_ids: IDs of work items currently in this column
    """

    id: str
    name: str
    position: int
    work_item_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.id, str) or not self.id:
            msg = "id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        # Explicitly reject bool (subclass of int)
        if isinstance(self.position, bool):
            msg = "position must be a non-negative integer, got bool"
            raise ValueError(msg)

        if not isinstance(self.position, int) or self.position < 0:
            msg = "position must be a non-negative integer"
            raise ValueError(msg)

        # Coerce list to tuple for deep immutability
        if isinstance(self.work_item_ids, list):
            object.__setattr__(self, "work_item_ids", tuple(self.work_item_ids))

        if not isinstance(self.work_item_ids, tuple):
            msg = "work_item_ids must be a list or tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(item_id, str) for item_id in self.work_item_ids):
            msg = "all work_item_ids must be strings"
            raise ValueError(msg)


@dataclass(frozen=True)
class WorkItemPosition:
    """Position of a work item within a board column.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        work_item_id: Unique identifier of the work item
        column_name: Name of the column containing the item
        position: Position within the column (0 = top/first)
        entered_column_at: Timestamp when item entered current column (for SLA tracking)
    """

    work_item_id: str
    column_name: str
    position: int
    entered_column_at: "datetime | None" = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.work_item_id, str) or not self.work_item_id:
            msg = "work_item_id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.column_name, str) or not self.column_name:
            msg = "column_name must be a non-empty string"
            raise ValueError(msg)

        # Explicitly reject bool (subclass of int)
        if isinstance(self.position, bool):
            msg = "position must be a non-negative integer, got bool"
            raise ValueError(msg)

        if not isinstance(self.position, int) or self.position < 0:
            msg = "position must be a non-negative integer"
            raise ValueError(msg)

        # Validate optional SLA tracking field
        if self.entered_column_at is not None:
            from datetime import datetime

            if not isinstance(self.entered_column_at, datetime):
                msg = "entered_column_at must be None or a datetime instance"
                raise ValueError(msg)


@dataclass(frozen=True)
class ProjectBoard:
    """Represents a project board with all columns and structure.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Columns are converted to
    a tuple for true immutability - the dataclass is only shallowly frozen when
    fields contain mutable types, so we enforce deep immutability via conversion.

    Attributes:
        id: Unique identifier for the board
        name: Display name
        project_id: Project this board belongs to
        columns: All columns on the board, ordered by position
    """

    id: str
    name: str
    project_id: str
    columns: tuple[BoardColumn, ...]

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.id, str) or not self.id:
            msg = "id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.project_id, str) or not self.project_id:
            msg = "project_id must be a non-empty string"
            raise ValueError(msg)

        # Coerce list to tuple for deep immutability
        if isinstance(self.columns, list):
            object.__setattr__(self, "columns", tuple(self.columns))

        if not isinstance(self.columns, tuple):
            msg = "columns must be a list or tuple of BoardColumn instances"
            raise ValueError(msg)

        if not all(isinstance(col, BoardColumn) for col in self.columns):
            msg = "all columns must be BoardColumn instances"
            raise ValueError(msg)


@dataclass(frozen=True)
class ColumnMovementResult:
    """Result of moving a work item between columns.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        work_item_id: ID of the work item that was moved
        from_column: Name of the source column (None if item was not on a board)
        to_column: Name of the target column
        moved_by: Type of entity that initiated the move (HUMAN or ORCHESTRATOR)
        timestamp: ISO format timestamp of when the move occurred
    """

    work_item_id: str
    from_column: str | None
    to_column: str
    moved_by: MovedByType
    timestamp: str

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.work_item_id, str) or not self.work_item_id:
            msg = "work_item_id must be a non-empty string"
            raise ValueError(msg)

        if self.from_column is not None:
            if not isinstance(self.from_column, str) or not self.from_column:
                msg = "from_column must be a non-empty string or None"
                raise ValueError(msg)

        if not isinstance(self.to_column, str) or not self.to_column:
            msg = "to_column must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.moved_by, MovedByType):
            msg = "moved_by must be a MovedByType instance"
            raise ValueError(msg)

        if not isinstance(self.timestamp, str) or not self.timestamp:
            msg = "timestamp must be a non-empty string"
            raise ValueError(msg)


@dataclass(frozen=True)
class ReconciliationResult:
    """Result of board reconciliation operation.

    Tracks what changes were made when reconciling board structure
    to expected configuration (adding missing columns, removing extras, etc.).
    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Lists are converted to
    tuples for true immutability.

    Attributes:
        board_id: ID of the board that was reconciled
        columns_added: Names of columns that were created
        columns_removed: Names of columns that were deleted
        columns_renamed: Tuple of (old_name, new_name) tuples for renamed columns
        orphaned_items: Work item IDs that were in deleted columns
    """

    board_id: str
    columns_added: tuple[str, ...]
    columns_removed: tuple[str, ...]
    columns_renamed: tuple[tuple[str, str], ...]
    orphaned_items: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.board_id, str) or not self.board_id:
            msg = "board_id must be a non-empty string"
            raise ValueError(msg)

        # Coerce list to tuple for deep immutability
        if isinstance(self.columns_added, list):
            object.__setattr__(self, "columns_added", tuple(self.columns_added))
        if isinstance(self.columns_removed, list):
            object.__setattr__(self, "columns_removed", tuple(self.columns_removed))
        if isinstance(self.columns_renamed, list):
            object.__setattr__(self, "columns_renamed", tuple(self.columns_renamed))
        if isinstance(self.orphaned_items, list):
            object.__setattr__(self, "orphaned_items", tuple(self.orphaned_items))

        if not isinstance(self.columns_added, tuple):
            msg = "columns_added must be a list or tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(col, str) for col in self.columns_added):
            msg = "all columns_added must be strings"
            raise ValueError(msg)

        if not isinstance(self.columns_removed, tuple):
            msg = "columns_removed must be a list or tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(col, str) for col in self.columns_removed):
            msg = "all columns_removed must be strings"
            raise ValueError(msg)

        if not isinstance(self.columns_renamed, tuple):
            msg = "columns_renamed must be a list or tuple of (old_name, new_name) tuples"
            raise ValueError(msg)

        for old_name, new_name in self.columns_renamed:
            if not isinstance(old_name, str) or not isinstance(new_name, str):
                msg = "all columns_renamed tuples must contain strings"
                raise ValueError(msg)

        if not isinstance(self.orphaned_items, tuple):
            msg = "orphaned_items must be a list or tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(item_id, str) for item_id in self.orphaned_items):
            msg = "all orphaned_items must be strings"
            raise ValueError(msg)


@dataclass(frozen=True)
class BoardConfig:
    """Configuration for board reconciliation.

    Specifies the desired board structure and behavior when differences
    are found between expected and actual state.
    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Expected columns are
    converted to a tuple for true immutability.

    Attributes:
        board_id: Board to reconcile
        expected_columns: Tuple of column names that should exist, in order
        auto_create_missing: If True, create missing columns.
                            If False, only report differences.
    """

    board_id: str
    expected_columns: tuple[str, ...]
    auto_create_missing: bool = True

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.board_id, str) or not self.board_id:
            msg = "board_id must be a non-empty string"
            raise ValueError(msg)

        # Coerce list to tuple for deep immutability
        if isinstance(self.expected_columns, list):
            object.__setattr__(self, "expected_columns", tuple(self.expected_columns))

        if not isinstance(self.expected_columns, tuple):
            msg = "expected_columns must be a list or tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(col, str) and col for col in self.expected_columns):
            msg = "all expected_columns must be non-empty strings"
            raise ValueError(msg)

        if not isinstance(self.auto_create_missing, bool):
            msg = "auto_create_missing must be a boolean"
            raise ValueError(msg)


class IBoardService(IEventEmitter, IMonitoredService, ABC):
    """Board management with event emission and monitoring.

    Provides vendor-agnostic abstraction for project boards (GitHub Projects v2,
    Trello, JIRA boards, etc.). Enables:
    1. Querying board structure and work item positions
    2. Moving work items between columns
    3. Reconciling board state with expected configuration
    4. Reacting to work item movement via events

    Events emitted:
        - 'workitem.column_changed' → WorkItemColumnChangedEvent
                                      Fired when item moves between columns
        - 'board.reconciled' → BoardReconciledEvent
                              Fired after reconciliation completes
        - 'board.column_added' → New column created during reconciliation
        - 'board.column_removed' → Column deleted during reconciliation

    Example:
        async with service as svc:
            # Start monitoring for column changes
            await svc.start_monitoring(
                project_id="proj-123",
                config=MonitoringConfig(project_id="proj-123")
            )

            # Query board structure
            board = await svc.get_board("proj-123", "board-456")
            columns = await svc.get_columns("board-456")

            # Move item between columns
            result = await svc.move_item_to_column(
                "item-789", "In Progress", MovedByType.ORCHESTRATOR
            )

            # Reconcile board
            reconcile_result = await svc.reconcile_board(
                "board-456",
                BoardConfig(
                    board_id="board-456",
                    expected_columns=["Backlog", "In Progress", "Review", "Done"],
                    auto_create_missing=True
                )
            )
    """

    # Query Operations

    @abstractmethod
    async def get_board(self, project_id: str, board_id: str) -> ProjectBoard:
        """Retrieve board configuration and structure.

        Returns the board with all columns and current work item positions.

        Args:
            project_id: Project containing the board
            board_id: Board to retrieve

        Returns:
            ProjectBoard: Board with all columns

        Raises:
            ProjectNotFoundError: Project doesn't exist
            ResourceNotFoundError: Board doesn't exist
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    async def get_columns(self, board_id: str) -> list[BoardColumn]:
        """Get all columns for a board.

        Returns columns in order of their position on the board.

        Args:
            board_id: Board to query

        Returns:
            List[BoardColumn]: Columns ordered by position (0 = first)

        Raises:
            ResourceNotFoundError: Board doesn't exist
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    async def get_items_in_column(self, board_id: str, column_name: str) -> list[WorkItemPosition]:
        """Get all work items in a specific column ordered by position.

        Args:
            board_id: Board to query
            column_name: Column name (e.g., "In Progress")

        Returns:
            List[WorkItemPosition]: Work items in the column ordered by position (0 = first)

        Raises:
            ResourceNotFoundError: Board or column doesn't exist
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    async def get_item_position(self, work_item_id: str) -> WorkItemPosition:
        """Get current column position of a work item.

        Returns which column the item is in and its position within that column.

        Args:
            work_item_id: Item to locate

        Returns:
            WorkItemPosition: Current position details

        Raises:
            ResourceNotFoundError: Work item not found on any board
            ExternalServiceError: Service communication failure
        """

    # Command Operations

    @abstractmethod
    async def move_item_to_column(
        self, work_item_id: str, target_column: str, moved_by: MovedByType
    ) -> ColumnMovementResult:
        """Move work item to target column.

        Moves the item to the specified column on its board.
        If the item is already in that column, no change is made.

        Args:
            work_item_id: Item to move
            target_column: Target column name (e.g., "In Progress")
            moved_by: Type of entity initiating the move (HUMAN or ORCHESTRATOR)

        Returns:
            ColumnMovementResult: Details of the movement operation

        Raises:
            ResourceNotFoundError: Work item or target column doesn't exist
            ValidationError: Invalid target column
            ExternalServiceError: Service communication failure

        Events:
            Emits 'workitem.column_changed' event with source and target columns
        """

    @abstractmethod
    async def reconcile_board(self, board_id: str, config: "BoardConfig") -> ReconciliationResult:
        """Reconcile board structure with expected configuration.

        Compares actual board structure to expected columns. If differences found:
        - Creates missing columns (if auto_create_missing=True)
        - Reports extra columns
        - Returns what was changed

        Used to ensure boards stay in expected state as they evolve.

        Args:
            board_id: Board to reconcile
            config: Reconciliation configuration

        Returns:
            ReconciliationResult: Summary of changes made

        Raises:
            ResourceNotFoundError: Board doesn't exist
            ValidationError: Invalid column names or config
            ExternalServiceError: Service communication failure

        Events:
            Emits 'board.reconciled' event with changes made
        """

    @abstractmethod
    async def get_all_boards(self) -> list[ProjectBoard]:
        """Get all boards across all projects.

        Returns all boards managed by this service, including structure and items.
        Used for cross-board queries like SLA monitoring.

        Returns:
            List[ProjectBoard]: All boards with columns and items

        Raises:
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    async def get_board_items(self, project_id: str, board_id: str) -> list[WorkItemPosition]:
        """Get all work items on a board with their column positions and entry times.

        Returns all items across all columns on the specified board,
        including their current column, position, and entry timestamp.

        Args:
            project_id: Project containing the board
            board_id: Board to query

        Returns:
            List[WorkItemPosition]: All items with column, position, and entry time

        Raises:
            ResourceNotFoundError: Board doesn't exist
            ExternalServiceError: Service communication failure
        """
