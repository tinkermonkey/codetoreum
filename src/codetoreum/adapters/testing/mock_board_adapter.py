"""In-memory board adapter with event simulation for testing.

This module provides a mock implementation of IBoardService that stores
board structure and state in memory, and includes test helper methods
for simulating board changes via event emission and tracking movement history.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import threading
import logging

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
from codetoreum.ports.output.event_emitter import IEventEmitter

logger = logging.getLogger(__name__)


@dataclass
class MovementEvent:
    """Audit trail entry for card movements.

    Attributes:
        work_item_id: ID of the work item that was moved
        from_column: Source column name (None if item was added to board initially)
        to_column: Target column name
        moved_by: Type of entity that moved the item (HUMAN or ORCHESTRATOR)
        timestamp: ISO format datetime when the movement occurred
    """

    work_item_id: str
    from_column: Optional[str]
    to_column: str
    moved_by: MovedByType
    timestamp: datetime


class MockBoardAdapter(IBoardService):
    """In-memory board adapter with event simulation.

    Provides a mock implementation of IBoardService that:
    1. Stores boards and columns in memory
    2. Tracks work item positions
    3. Emits events when board state changes
    4. Provides test helper methods for event simulation
    5. Maintains movement history for audit trail verification
    6. Supports thread-safe concurrent operations

    Intended for testing and simulation without external board systems
    (GitHub Projects v2, Jira, Trello, etc.).

    Example:
        # Setup
        adapter = MockBoardAdapter()
        adapter.create_board("proj-1", "board-1", "My Board", ["Backlog", "In Progress", "Done"])
        adapter.add_item_to_column("board-1", "Backlog", "item-1")

        # Subscribe to events
        events = []
        adapter.on("workitem.column_changed", events.append)

        # Simulate column change
        adapter.simulate_human_move("item-1", "In Progress")

        # Verify
        assert len(events) == 1
        assert events[0].to_column == "In Progress"

        # Check movement history
        history = adapter.get_movement_history("item-1")
        assert len(history) == 1
        assert history[0].moved_by == MovedByType.HUMAN
    """

    def __init__(self) -> None:
        """Initialize the board adapter."""
        self._boards: Dict[str, ProjectBoard] = {}  # key: "project_id:board_id"
        self._item_positions: Dict[str, Tuple[str, str, int]] = {}  # item_id -> (board_id, column_name, position)
        self._monitoring: Dict[str, MonitoringStatus] = {}  # project_id -> status
        self._movement_log: List[MovementEvent] = []  # Audit trail of all movements
        self._lock = threading.Lock()  # Thread safety for concurrent operations
        self._event_listeners: Dict[str, List] = {}  # Event type -> list of handlers
        self.current_project: Optional[str] = None
        self.current_board: Optional[str] = None

    # ===== Event Emitter Implementation =====

    def on(self, event_type: str, handler) -> None:
        """Register event listener."""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(handler)

    def off(self, event_type: str, handler) -> None:
        """Unregister event listener."""
        if event_type in self._event_listeners:
            self._event_listeners[event_type] = [
                h for h in self._event_listeners[event_type] if h != handler
            ]

    def emit(self, event) -> None:
        """Emit event to all registered listeners."""
        event_type = getattr(event, 'type', event.__class__.__name__)
        if event_type in self._event_listeners:
            for handler in self._event_listeners[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler: {e}", exc_info=True)

    # ===== Query Operations =====

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
        with self._lock:
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

    async def get_items_in_column(
        self, board_id: str, column_name: str
    ) -> List[WorkItemPosition]:
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
        with self._lock:
            for column in board.columns:
                if column.name == column_name:
                    return [
                        WorkItemPosition(
                            work_item_id=item_id,
                            column_name=column_name,
                            position=index,
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
        with self._lock:
            if work_item_id not in self._item_positions:
                raise ValueError(f"Work item not in any column: {work_item_id}")
            _, column_name, position = self._item_positions[work_item_id]
            return WorkItemPosition(
                work_item_id=work_item_id, column_name=column_name, position=position
            )

    # ===== Command Operations =====

    async def move_item_to_column(
        self, work_item_id: str, target_column: str, moved_by: MovedByType
    ) -> "ColumnMovementResult":
        """Move work item to target column.

        Args:
            work_item_id: Item to move
            target_column: Target column name
            moved_by: Type of entity that moved the item (HUMAN or ORCHESTRATOR)

        Returns:
            ColumnMovementResult: Details of the movement operation

        Raises:
            ValueError: Work item or column doesn't exist
        """
        from codetoreum.ports.output.board_service import ColumnMovementResult

        with self._lock:
            if work_item_id not in self._item_positions:
                raise ValueError(f"Work item not found: {work_item_id}")

            board_id, from_column, _ = self._item_positions[work_item_id]

            if self.current_project is None:
                raise ValueError("current_project not set")

        board = await self.get_board(self.current_project, board_id)

        with self._lock:
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
                self._item_positions[work_item_id] = (
                    board_id,
                    target_column,
                    len(target_col.work_item_ids) - 1,
                )

                # Log movement
                timestamp = self._get_utc_datetime()
                movement = MovementEvent(
                    work_item_id=work_item_id,
                    from_column=from_column,
                    to_column=target_column,
                    moved_by=moved_by,
                    timestamp=timestamp,
                )
                self._movement_log.append(movement)

                # Emit event
                self.emit(
                    WorkItemColumnChangedEvent(
                        type="workitem.column_changed",
                        work_item_id=work_item_id,
                        project_id=self.current_project,
                        board_id=board_id,
                        from_column=from_column,
                        to_column=target_column,
                        moved_by=moved_by.value,  # Use enum value
                        timestamp=self._get_iso_timestamp(),
                        source="mock",
                    )
                )

        return ColumnMovementResult(
            work_item_id=work_item_id,
            from_column=from_column,
            to_column=target_column,
            moved_by=moved_by,
            timestamp=self._get_iso_timestamp(),
        )

    async def reconcile_board(
        self, board_id: str, config: BoardConfig
    ) -> ReconciliationResult:
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

        with self._lock:
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
                            work_item_ids=[],
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
                orphaned_items=orphaned_items,
            )

            self.emit(
                BoardReconciledEvent(
                    type="board.reconciled",
                    project_id=self.current_project,
                    board_id=board_id,
                    columns_added=result.columns_added,
                    columns_removed=result.columns_removed,
                    timestamp=self._get_iso_timestamp(),
                    source="mock",
                )
            )

        return result

    # ===== Monitoring Lifecycle =====

    async def start_monitoring(self, project_id: str, config: MonitoringConfig) -> None:
        """Begin monitoring for changes.

        Args:
            project_id: Project to monitor
            config: Monitoring configuration
        """
        with self._lock:
            self._monitoring[project_id] = MonitoringStatus(
                state=MonitoringState.ACTIVE,
                project_id=project_id,
                started_at=self._get_iso_timestamp(),
            )

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring for changes.

        Args:
            project_id: Project to stop monitoring
        """
        with self._lock:
            if project_id in self._monitoring:
                self._monitoring[project_id].state = MonitoringState.STOPPED

    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Query current monitoring state.

        Args:
            project_id: Project to query status for

        Returns:
            MonitoringStatus with current state
        """
        with self._lock:
            return self._monitoring.get(
                project_id,
                MonitoringStatus(
                    state=MonitoringState.STOPPED, project_id=project_id
                ),
            )

    # ===== Test Helper Methods =====

    def create_board(
        self,
        project_id: str,
        board_id: str,
        board_name: str,
        column_names: List[str],
    ) -> None:
        """Test helper: Create a board with specified columns.

        Sets up an in-memory board with the given structure.

        Args:
            project_id: Project containing the board
            board_id: Board ID
            board_name: Display name for the board
            column_names: List of column names in order

        Example:
            adapter.create_board("proj-1", "board-1", "My Board", ["Backlog", "In Progress", "Done"])
        """
        with self._lock:
            key = f"{project_id}:{board_id}"
            self._boards[key] = ProjectBoard(
                id=board_id,
                name=board_name,
                project_id=project_id,
                columns=[
                    BoardColumn(
                        id=f"col-{i}",
                        name=col,
                        position=i,
                        work_item_ids=[],
                    )
                    for i, col in enumerate(column_names)
                ],
            )

    def add_item_to_column(
        self,
        board_id: str,
        column_name: str,
        work_item_id: str,
        position: Optional[int] = None,
    ) -> None:
        """Test helper: Place work item in column at specific position.

        Args:
            board_id: Board ID
            column_name: Target column name
            work_item_id: Work item to add
            position: Position in column (defaults to end of column)

        Raises:
            ValueError: Board or column doesn't exist

        Example:
            adapter.add_item_to_column("board-1", "Backlog", "item-1", position=0)
        """
        with self._lock:
            # Find the board containing this column
            board = None
            project_id = self.current_project
            if project_id:
                key = f"{project_id}:{board_id}"
                board = self._boards.get(key)

            if board is None:
                raise ValueError(f"Board {board_id} not found in project {project_id}")

            # Find the target column
            target_column = None
            for col in board.columns:
                if col.name == column_name:
                    target_column = col
                    break

            if target_column is None:
                raise ValueError(
                    f"Column {column_name} not found in board {board_id}"
                )

            # Insert work item at specified position
            if position is None:
                position = len(target_column.work_item_ids)

            target_column.work_item_ids.insert(position, work_item_id)
            self._item_positions[work_item_id] = (board_id, column_name, position)

            # Update positions of items after insertion
            for i in range(position + 1, len(target_column.work_item_ids)):
                item_id = target_column.work_item_ids[i]
                if item_id in self._item_positions:
                    board_id_stored, col, _ = self._item_positions[item_id]
                    self._item_positions[item_id] = (board_id_stored, col, i)

    def simulate_human_move(
        self, work_item_id: str, target_column: str
    ) -> None:
        """Test helper: Simulate user dragging card in board UI.

        Moves the item to the target column and emits a movement event with
        moved_by=MovedByType.HUMAN.

        Args:
            work_item_id: Item that moved
            target_column: Target column name

        Raises:
            ValueError: Work item or column doesn't exist

        Example:
            adapter.simulate_human_move("item-1", "In Progress")
        """
        import asyncio

        if self.current_project is None:
            raise ValueError("current_project not set")

        with self._lock:
            if work_item_id not in self._item_positions:
                raise ValueError(f"Work item not found: {work_item_id}")

            board_id, from_column, _ = self._item_positions[work_item_id]

        # Run async operation
        try:
            asyncio.get_running_loop()
            # We're in an async context, schedule as task
            loop = asyncio.get_running_loop()
            loop.create_task(
                self.move_item_to_column(work_item_id, target_column, MovedByType.HUMAN)
            )
        except RuntimeError:
            # No running loop, create one
            asyncio.run(
                self.move_item_to_column(work_item_id, target_column, MovedByType.HUMAN)
            )

    def assert_item_in_column(
        self, work_item_id: str, expected_column: str
    ) -> None:
        """Test helper: Assert work item is in expected column.

        Args:
            work_item_id: Item to check
            expected_column: Expected column name

        Raises:
            AssertionError: If item is not in expected column

        Example:
            adapter.assert_item_in_column("item-1", "In Progress")
        """
        with self._lock:
            actual = None
            if work_item_id in self._item_positions:
                _, actual, _ = self._item_positions[work_item_id]

            if actual != expected_column:
                raise AssertionError(
                    f"Expected work item {work_item_id} in column '{expected_column}', "
                    f"found in column '{actual}'"
                )

    def get_movement_history(self, work_item_id: str) -> List[MovementEvent]:
        """Test helper: Get movement audit trail for work item.

        Returns all movements of this work item in chronological order.

        Args:
            work_item_id: Item to get history for

        Returns:
            List[MovementEvent]: Movements in chronological order

        Example:
            history = adapter.get_movement_history("item-1")
            assert len(history) == 2
            assert history[0].from_column == "Backlog"
            assert history[0].to_column == "In Progress"
        """
        with self._lock:
            return [
                m
                for m in self._movement_log
                if m.work_item_id == work_item_id
            ]

    def clear_movement_log(self) -> None:
        """Test helper: Clear movement history for cleanup.

        Useful between test cases to reset the audit trail.

        Example:
            adapter.clear_movement_log()
        """
        with self._lock:
            self._movement_log.clear()

    # ===== Helper Methods =====

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current time as ISO 8601 timestamp."""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _get_utc_datetime() -> datetime:
        """Get current time as UTC datetime."""
        return datetime.now(timezone.utc)
