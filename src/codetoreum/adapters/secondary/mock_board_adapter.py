"""In-memory board adapter with event simulation for testing.

This module provides a mock implementation of IBoardService that stores
board structure and state in memory, and includes test helper methods
for simulating board changes via event emission.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from codetoreum.domain.events.board_events import (
    BoardReconciledEvent,
    WorkItemColumnChangedEvent,
)
from codetoreum.ports.output.board_service import (
    BoardConfig,
    BoardColumn,
    IBoardService,
    ProjectBoard,
    ReconciliationResult,
    WorkItemPosition,
    MovedByType,
)
from codetoreum.ports.output.monitoring import (
    IMonitoredService,
    MonitoringConfig,
    MonitoringState,
    MonitoringStatus,
)

from .mock_event_emitter import MockEventEmitter


class MockBoardAdapter(MockEventEmitter, IBoardService):
    """In-memory board adapter with event simulation.

    Provides a mock implementation of IBoardService that:
    1. Stores boards and columns in memory
    2. Tracks work item positions
    3. Emits events when board state changes
    4. Provides test helper methods for event simulation

    Intended for testing and simulation without external board systems
    (GitHub Projects v2, Jira, Trello, etc.).

    Example:
        # Setup
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        adapter.current_board = "board-1"
        adapter.add_board("proj-1", "board-1", ["Backlog", "In Progress", "Done"])
        adapter.add_work_item("item-1", "Backlog")

        # Subscribe to events
        events = []
        adapter.on("workitem.column_changed", events.append)

        # Simulate column change
        adapter.simulate_column_change("item-1", "Backlog", "In Progress")

        # Verify
        assert len(events) == 1
        assert events[0].to_column == "In Progress"
    """

    def __init__(self) -> None:
        """Initialize the board adapter."""
        super().__init__()
        self._boards: Dict[str, ProjectBoard] = {}  # key: "project_id:board_id"
        self._item_positions: Dict[str, Tuple[str, str, int]] = {}  # item_id -> (board_id, column_name, position)
        self._monitoring: Dict[str, MonitoringStatus] = {}  # project_id -> status
        self.current_project: Optional[str] = None
        self.current_board: Optional[str] = None

    # Query Operations

    async def get_board(self, project_id: str, board_id: str) -> ProjectBoard:
        """Retrieve board configuration and structure.

        Args:
            project_id: Project containing the board
            board_id: Board to retrieve

        Returns:
            ProjectBoard: Board with all columns

        Raises:
            ValueError: Board doesn't exist
        """
        key = f"{project_id}:{board_id}"
        if key not in self._boards:
            raise ValueError(f"Board not found: {board_id}")
        return self._boards[key]

    async def get_columns(self, board_id: str) -> List[BoardColumn]:
        """Get all columns for a board.

        Args:
            board_id: Board to query

        Returns:
            List[BoardColumn]: Columns ordered by position

        Raises:
            ValueError: Board doesn't exist
        """
        if self.current_project is None:
            raise ValueError("current_project not set")
        board = await self.get_board(self.current_project, board_id)
        return sorted(board.columns, key=lambda c: c.position)

    async def get_items_in_column(self, board_id: str, column_name: str) -> List[WorkItemPosition]:
        """Get all work items in a specific column ordered by position.

        Args:
            board_id: Board to query
            column_name: Column name

        Returns:
            List[WorkItemPosition]: Work items in the column ordered by position

        Raises:
            ValueError: Board or column doesn't exist
        """
        if self.current_project is None:
            raise ValueError("current_project not set")
        board = await self.get_board(self.current_project, board_id)
        for column in board.columns:
            if column.name == column_name:
                return [
                    WorkItemPosition(
                        work_item_id=item_id,
                        column_name=column_name,
                        position=index
                    )
                    for index, item_id in enumerate(column.work_item_ids)
                ]
        raise ValueError(f"Column not found: {column_name}")

    async def get_item_position(self, work_item_id: str) -> WorkItemPosition:
        """Get current column position of a work item.

        Args:
            work_item_id: Item to locate

        Returns:
            WorkItemPosition: Current position details

        Raises:
            ValueError: Work item not found on any board
        """
        if work_item_id not in self._item_positions:
            raise ValueError(f"Work item not in any column: {work_item_id}")
        _, column_name, position = self._item_positions[work_item_id]
        return WorkItemPosition(
            work_item_id=work_item_id,
            column_name=column_name,
            position=position
        )

    # Command Operations

    async def move_item_to_column(
        self, work_item_id: str, target_column: str, moved_by: MovedByType
    ):
        """Move work item to target column.

        Args:
            work_item_id: Item to move
            target_column: Target column name
            moved_by: Type of entity that moved the item

        Raises:
            ValueError: Work item or column doesn't exist
        """
        if work_item_id not in self._item_positions:
            raise ValueError(f"Work item not found: {work_item_id}")

        board_id, from_column, _ = self._item_positions[work_item_id]

        if self.current_project is None:
            raise ValueError("current_project not set")

        board = await self.get_board(self.current_project, board_id)

        # Validate target column exists
        target_col = None
        for col in board.columns:
            if col.name == target_column:
                target_col = col
                break
        if target_col is None:
            raise ValueError(f"Column not found: {target_column}")

        # Update item positions
        if from_column != target_column:
            # Remove from old column
            for col in board.columns:
                if col.name == from_column:
                    if work_item_id in col.work_item_ids:
                        col.work_item_ids.remove(work_item_id)
                    break

            # Add to new column
            target_col.work_item_ids.append(work_item_id)
            self._item_positions[work_item_id] = (board_id, target_column, len(target_col.work_item_ids) - 1)

            # Emit event
            self.emit(WorkItemColumnChangedEvent(
                type='workitem.column_changed',
                work_item_id=work_item_id,
                project_id=self.current_project,
                board_id=board_id,
                from_column=from_column,
                to_column=target_column,
                moved_by='orchestrator',
                timestamp=self._get_iso_timestamp(),
                source='mock'
            ))

    async def reconcile_board(self, board_id: str, config: BoardConfig) -> ReconciliationResult:
        """Reconcile board structure with expected configuration.

        Args:
            board_id: Board to reconcile
            config: Reconciliation configuration

        Returns:
            ReconciliationResult: Summary of changes made

        Raises:
            ValueError: Board doesn't exist
        """
        if self.current_project is None:
            raise ValueError("current_project not set")

        board = await self.get_board(self.current_project, board_id)

        columns_added = []
        columns_removed = []
        columns_renamed = []
        orphaned_items = []

        # Check for missing columns
        existing_names = {col.name for col in board.columns}
        for expected_col in config.expected_columns:
            if expected_col not in existing_names:
                if config.auto_create_missing:
                    # Add new column
                    new_col = BoardColumn(
                        id=f"col-{len(board.columns)}",
                        name=expected_col,
                        position=len(board.columns),
                        work_item_ids=[]
                    )
                    board.columns.append(new_col)
                    columns_added.append(expected_col)

        # Check for extra columns
        for col in board.columns:
            if col.name not in config.expected_columns:
                columns_removed.append(col.name)

        result = ReconciliationResult(
            board_id=board_id,
            columns_added=columns_added,
            columns_removed=columns_removed,
            columns_renamed=columns_renamed,
            orphaned_items=orphaned_items
        )

        self.emit(BoardReconciledEvent(
            type='board.reconciled',
            project_id=self.current_project,
            board_id=board_id,
            columns_added=result.columns_added,
            columns_removed=result.columns_removed,
            timestamp=self._get_iso_timestamp(),
            source='mock'
        ))

        return result

    # Monitoring Lifecycle

    async def start_monitoring(self, project_id: str, config: MonitoringConfig) -> None:
        """Begin monitoring for changes.

        Args:
            project_id: Project to monitor
            config: Monitoring configuration
        """
        self._monitoring[project_id] = MonitoringStatus(
            state=MonitoringState.ACTIVE,
            project_id=project_id,
            started_at=self._get_iso_timestamp()
        )

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring for changes.

        Args:
            project_id: Project to stop monitoring
        """
        if project_id in self._monitoring:
            self._monitoring[project_id].state = MonitoringState.STOPPED

    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Query current monitoring state.

        Args:
            project_id: Project to query status for

        Returns:
            MonitoringStatus with current state
        """
        return self._monitoring.get(project_id, MonitoringStatus(
            state=MonitoringState.STOPPED,
            project_id=project_id
        ))

    # Test Helper Methods

    def add_board(self, project_id: str, board_id: str, columns: List[str]) -> None:
        """Test helper: Create a board with specified columns.

        Args:
            project_id: Project containing the board
            board_id: Board ID
            columns: List of column names in order
        """
        key = f"{project_id}:{board_id}"
        self._boards[key] = ProjectBoard(
            id=board_id,
            name=f"Board {board_id}",
            project_id=project_id,
            columns=[
                BoardColumn(
                    id=f"col-{i}",
                    name=col,
                    position=i,
                    work_item_ids=[]
                )
                for i, col in enumerate(columns)
            ]
        )

    def add_work_item(
        self,
        work_item_id: str,
        column: str,
        board_id: Optional[str] = None
    ) -> None:
        """Test helper: Place work item in column.

        Args:
            work_item_id: Work item to add
            column: Column name
            board_id: Board ID (uses current_board if not provided)
        """
        board_id = board_id or self.current_board
        if board_id is None:
            raise ValueError("board_id must be provided or current_board must be set")

        self._item_positions[work_item_id] = (board_id, column, 0)

        # Add to column's work_item_ids list
        if self.current_project is None:
            raise ValueError("current_project must be set")

        try:
            board = self._boards.get(f"{self.current_project}:{board_id}")
            if board:
                for col in board.columns:
                    if col.name == column:
                        col.work_item_ids.append(work_item_id)
                        break
        except Exception:
            pass  # Silently continue for test helpers

    def simulate_column_change(
        self,
        work_item_id: str,
        from_column: str,
        to_column: str,
        moved_by: str = 'human'
    ) -> None:
        """Test helper: Simulate column change event.

        Simulates a work item moving from one column to another without
        requiring actual board service interaction.

        Args:
            work_item_id: Item that moved
            from_column: Source column name
            to_column: Target column name
            moved_by: Who initiated the change ('human', 'orchestrator')
        """
        if self.current_project is None:
            raise ValueError("current_project must be set")
        if self.current_board is None:
            raise ValueError("current_board must be set")

        # Update position if item exists
        if work_item_id in self._item_positions:
            board_id, _, position = self._item_positions[work_item_id]
            self._item_positions[work_item_id] = (board_id, to_column, position)

        self.emit(WorkItemColumnChangedEvent(
            type='workitem.column_changed',
            work_item_id=work_item_id,
            project_id=self.current_project,
            board_id=self.current_board,
            from_column=from_column,
            to_column=to_column,
            moved_by=moved_by,  # type: ignore
            timestamp=self._get_iso_timestamp(),
            source='mock'
        ))

    # Helper Methods

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current time as ISO 8601 timestamp."""
        return datetime.now(timezone.utc).isoformat()
