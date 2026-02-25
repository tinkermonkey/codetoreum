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


@dataclass
class BoardColumn:
    """Represents a column (lane) on a project board.

    Attributes:
        id: Unique identifier for the column in the external system
        name: Display name (e.g., "Backlog", "In Progress", "Done")
        position: Ordinal position (0 = leftmost/first)
        work_item_ids: IDs of work items currently in this column
    """

    id: str
    name: str
    position: int
    work_item_ids: list[str]


@dataclass
class WorkItemPosition:
    """Position of a work item within a board column.

    Attributes:
        work_item_id: Unique identifier of the work item
        column_name: Name of the column containing the item
        position: Position within the column (0 = top/first)
    """

    work_item_id: str
    column_name: str
    position: int


@dataclass
class ProjectBoard:
    """Represents a project board with all columns and structure.

    Attributes:
        id: Unique identifier for the board
        name: Display name
        project_id: Project this board belongs to
        columns: All columns on the board, ordered by position
    """

    id: str
    name: str
    project_id: str
    columns: list[BoardColumn]


@dataclass
class ColumnMovementResult:
    """Result of moving a work item between columns.

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


@dataclass
class ReconciliationResult:
    """Result of board reconciliation operation.

    Tracks what changes were made when reconciling board structure
    to expected configuration (adding missing columns, removing extras, etc.).

    Attributes:
        board_id: ID of the board that was reconciled
        columns_added: Names of columns that were created
        columns_removed: Names of columns that were deleted
        columns_renamed: List of (old_name, new_name) tuples for renamed columns
        orphaned_items: Work item IDs that were in deleted columns
    """

    board_id: str
    columns_added: list[str]
    columns_removed: list[str]
    columns_renamed: list[tuple[str, str]]
    orphaned_items: list[str]


@dataclass
class BoardConfig:
    """Configuration for board reconciliation.

    Specifies the desired board structure and behavior when differences
    are found between expected and actual state.

    Attributes:
        board_id: Board to reconcile
        expected_columns: List of column names that should exist, in order
        auto_create_missing: If True, create missing columns.
                            If False, only report differences.
    """

    board_id: str
    expected_columns: list[str]
    auto_create_missing: bool = True


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
    async def get_items_in_column(
        self, board_id: str, column_name: str
    ) -> list[WorkItemPosition]:
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
    async def reconcile_board(
        self, board_id: str, config: "BoardConfig"
    ) -> ReconciliationResult:
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
