"""Board service port interface with event emission.

This interface defines contracts for project board management, including
board structure queries, work item movement, and board reconciliation.

Project boards organize work items into columns/lanes representing workflow
stages (e.g., Backlog, In Progress, Review, Done). Boards are vendor-agnostic
abstractions over GitHub Projects v2, Trello, JIRA boards, etc.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .event_emitter import IEventEmitter
from .monitoring import IMonitoredService, MonitoringConfig


@dataclass
class Column:
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
    work_item_ids: List[str]


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
    columns: List[Column]


@dataclass
class ReconciliationResult:
    """Result of board reconciliation operation.

    Tracks what changes were made when reconciling board structure
    to expected configuration (adding missing columns, removing extras, etc.).

    Attributes:
        columns_added: IDs of columns that were created
        columns_removed: IDs of columns that were deleted
        items_moved: Number of work items repositioned
    """

    columns_added: List[str]
    columns_removed: List[str]
    items_moved: int


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
    expected_columns: List[str]
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
            await svc.move_item_to_column("item-789", "In Progress")

            # Reconcile board
            result = await svc.reconcile_board(
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
        pass

    @abstractmethod
    async def get_columns(self, board_id: str) -> List[Column]:
        """Get all columns for a board.

        Returns columns in order of their position on the board.

        Args:
            board_id: Board to query

        Returns:
            List[Column]: Columns ordered by position (0 = first)

        Raises:
            ResourceNotFoundError: Board doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def get_items_in_column(
        self, board_id: str, column_name: str
    ) -> List[str]:
        """Get all work item IDs in a specific column.

        Args:
            board_id: Board to query
            column_name: Column name (e.g., "In Progress")

        Returns:
            List[str]: Work item IDs in the column

        Raises:
            ResourceNotFoundError: Board or column doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def get_item_position(self, work_item_id: str) -> Tuple[str, int]:
        """Get current column position of a work item.

        Returns which column the item is in and its position within that column.

        Args:
            work_item_id: Item to locate

        Returns:
            Tuple[str, int]: (column_name, position_in_column)

        Raises:
            ResourceNotFoundError: Work item not found on any board
            ExternalServiceError: Service communication failure
        """
        pass

    # Command Operations

    @abstractmethod
    async def move_item_to_column(
        self, work_item_id: str, target_column: str
    ) -> None:
        """Move work item to target column.

        Moves the item to the specified column on its board.
        If the item is already in that column, no change is made.

        Args:
            work_item_id: Item to move
            target_column: Target column name (e.g., "In Progress")

        Raises:
            ResourceNotFoundError: Work item or target column doesn't exist
            ValidationError: Invalid target column
            ExternalServiceError: Service communication failure

        Events:
            Emits 'workitem.column_changed' event with source and target columns
        """
        pass

    @abstractmethod
    async def reconcile_board(self, config: BoardConfig) -> ReconciliationResult:
        """Reconcile board structure with expected configuration.

        Compares actual board structure to expected columns. If differences found:
        - Creates missing columns (if auto_create_missing=True)
        - Reports extra columns
        - Returns what was changed

        Used to ensure boards stay in expected state as they evolve.

        Args:
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
        pass
