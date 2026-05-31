"""In-memory board adapter with event simulation for testing.

This module provides a mock implementation of IBoardService that stores
board structure and state in memory, and includes test helper methods
for simulating board changes via event emission and tracking movement history.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from codetoreum.domain.events.board_events import (
    BoardReconciledEvent,
    WorkItemColumnChangedEvent,
    WorkItemPositionChangedEvent,
)
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.board_service import (
    BoardColumn,
    BoardConfig,
    IBoardService,
    MovedByType,
    ProjectBoard,
    ReconciliationResult,
    WorkItemPosition,
)
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.monitoring import (
    MonitoringConfig,
    MonitoringState,
    MonitoringStatus,
)

if TYPE_CHECKING:
    from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
    from codetoreum.ports.output.board_service import ColumnMovementResult

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
    from_column: str | None
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
        await adapter.add_item_to_column("item-1", "Backlog", MovedByType.HUMAN)

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

    def __init__(self, event_emitter: IEventEmitter | None = None, clock: "SimulationClock | None" = None) -> None:
        """Initialize the board adapter.

        Args:
            event_emitter: Optional IEventEmitter for emitting domain events
            clock: Optional SimulationClock for deterministic time in tests
                   If provided, timestamps use simulation clock; otherwise uses wall clock
        """
        self._boards: dict[str, ProjectBoard] = {}  # key: "project_id:board_id"
        self._item_positions: dict[str, tuple[str, str, int]] = {}  # item_id -> (board_id, column_name, position)
        self._item_column_entries: dict[str, datetime] = {}  # item_id -> entered_column_at timestamp
        self._board_project_map: dict[str, str] = {}  # board_id -> project_id
        self._monitoring: dict[str, MonitoringStatus] = {}  # project_id -> status
        self._movement_log: list[MovementEvent] = []  # Audit trail of all movements
        self._lock = asyncio.Lock()  # Async-safe lock for concurrent operations
        self._event_listeners: dict[str, list] = {}  # Event type -> list of handlers
        self._event_emitter = event_emitter
        self._event_bus: Any | None = None  # Central event bus for publishing to handlers
        self._clock = clock
        self.current_project: str | None = None
        self.current_board: str | None = None

    # ===== Event Bus and Emitter Management =====

    @property
    def event_bus(self) -> Any | None:
        """Get the event bus for publishing domain events."""
        return self._event_bus

    @event_bus.setter
    def event_bus(self, bus: Any | None) -> None:
        """Set the event bus for publishing domain events."""
        self._event_bus = bus

    # ===== Event Emitter Implementation =====

    def on(self, event_type: str, handler) -> None:
        """Register event listener."""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(handler)

    def off(self, event_type: str, handler) -> None:
        """Unregister event listener."""
        if event_type in self._event_listeners:
            self._event_listeners[event_type] = [h for h in self._event_listeners[event_type] if h != handler]

    def _emit_to_listeners_and_emitter(self, event) -> None:
        """Emit event to local listeners and event emitter.

        This helper method contains the common logic for both emit() and emit_async(),
        reducing code duplication.

        Args:
            event: Domain event to emit
        """
        event_type = getattr(event, "type", event.__class__.__name__)

        # Emit to local listeners (synchronous)
        if event_type in self._event_listeners:
            for handler in self._event_listeners[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler: {e}", exc_info=True)

        # Emit to local event emitter if provided (synchronous)
        if self._event_emitter:
            try:
                self._event_emitter.emit(event)
            except Exception as e:
                logger.error(f"Error emitting to event emitter: {e}", exc_info=True)

    async def _publish_to_event_bus_async(self, event) -> None:
        """Publish event to central event bus asynchronously.

        Args:
            event: Domain event to publish

        Raises:
            Exception: If event bus publish fails
        """
        if self._event_bus:
            await self._event_bus.publish(event)

    async def emit_async(self, event) -> None:
        """Emit event asynchronously with full event bus integration.

        This is the async version of emit() that properly awaits event bus publishing.
        Use this from async methods to ensure events are fully processed before returning.

        Args:
            event: Domain event to emit
        """
        # Emit to local listeners and emitter
        self._emit_to_listeners_and_emitter(event)

        # Publish to central event bus if provided (awaitable)
        if self._event_bus:
            try:
                await self._publish_to_event_bus_async(event)
            except Exception as e:
                logger.warning(f"Failed to publish event to event_bus: {e}")

    def emit(self, event) -> None:
        """Emit event to all registered listeners and event emitter.

        Emits to:
        1. Local event listeners (for backwards compatibility)
        2. Event emitter (for capturing in tests)
        3. Central event bus (for domain event distribution to handlers)
        """
        # Emit to local listeners and emitter
        self._emit_to_listeners_and_emitter(event)

        # Publish to central event bus if provided (for handler subscription)
        if self._event_bus:
            try:
                # Check if we're in an async context
                try:
                    asyncio.get_running_loop()
                    # Create a task but add a callback to log errors
                    task = asyncio.create_task(self._publish_to_event_bus_async(event))

                    def log_error(t):
                        if t.exception():
                            logger.error(f"Event bus publish failed: {t.exception()}")

                    task.add_done_callback(log_error)
                except RuntimeError:
                    # No running loop - can't publish to async event bus
                    logger.debug("No async event loop running, skipping event bus publish")
            except Exception as e:
                logger.warning(f"Failed to schedule event bus publish: {e}")

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
        async with self._lock:
            key = f"{project_id}:{board_id}"
            if key not in self._boards:
                msg = f"Board not found: {board_id}"
                raise ValueError(msg)
            return self._boards[key]

    async def get_columns(self, board_id: str) -> list[BoardColumn]:
        """Get all columns for a board.

        Args:
            board_id: Board to query

        Returns:
            List[BoardColumn]: Columns ordered by position

        Raises:
            ValueError: Board doesn't exist
        """
        if self.current_project is None:
            msg = "current_project not set"
            raise ValueError(msg)
        board = await self.get_board(self.current_project, board_id)
        return sorted(board.columns, key=lambda c: c.position)

    async def get_items_in_column(self, board_id: str, column_name: str) -> list[WorkItemPosition]:
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
            msg = "current_project not set"
            raise ValueError(msg)
        board = await self.get_board(self.current_project, board_id)
        async with self._lock:
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
        msg = "Column"
        raise ResourceNotFoundError(msg, column_name)

    async def get_item_position(self, work_item_id: str) -> WorkItemPosition:
        """Get current column position of a work item.

        Args:
            work_item_id: Item to locate

        Returns:
            WorkItemPosition: Current position details

        Raises:
            ResourceNotFoundError: Work item not found on any board
        """
        async with self._lock:
            if work_item_id not in self._item_positions:
                msg = "Work item"
                raise ResourceNotFoundError(msg, work_item_id)
            _, column_name, position = self._item_positions[work_item_id]
            entered_at = self._item_column_entries.get(work_item_id)
            return WorkItemPosition(
                work_item_id=work_item_id,
                column_name=column_name,
                position=position,
                entered_column_at=entered_at,
            )

    # ===== Command Operations =====

    async def move_item_to_column(
        self, work_item_id: str, target_column: str, moved_by: MovedByType
    ) -> "ColumnMovementResult":
        """Move work item to target column with automatic position recalculation.

        When an item is moved from one column to another:
        1. The item is removed from the source column
        2. All items in the source column after the removed position shift down by 1
        3. WorkItemPositionChangedEvent is emitted for each shifted sibling item
        4. The item is appended to the target column at the end
        5. WorkItemColumnChangedEvent is emitted for the moved item

        Note: The moved item itself does not emit a WorkItemPositionChangedEvent since
        its position in the target column (end of column) is not part of the recalculation.
        Cross-column moves are captured solely by WorkItemColumnChangedEvent.

        Args:
            work_item_id: Item to move
            target_column: Target column name
            moved_by: Type of entity that moved the item (HUMAN or ORCHESTRATOR)

        Returns:
            ColumnMovementResult: Details of the movement operation

        Raises:
            ResourceNotFoundError: Work item or target column doesn't exist
            ValueError: current_project not set
        """
        from codetoreum.ports.output.board_service import ColumnMovementResult

        async with self._lock:
            if work_item_id not in self._item_positions:
                msg = "Work item"
                raise ResourceNotFoundError(msg, work_item_id)

            board_id, from_column, _ = self._item_positions[work_item_id]

            # Resolve project_id: use board_project_map for multi-project support,
            # falling back to current_project for backwards compatibility
            project_id = self._board_project_map.get(board_id) or self.current_project
            if project_id is None:
                msg = "current_project not set"
                raise ValueError(msg)

        board = await self.get_board(project_id, board_id)

        pending_events: list = []

        async with self._lock:
            # Validate target column exists
            target_col = None
            for col in board.columns:
                if col.name == target_column:
                    target_col = col
                    break
            if target_col is None:
                msg = "Column"
                raise ResourceNotFoundError(msg, target_column)

            # Update item positions
            if from_column != target_column:
                # Remove from old column
                removed_position = None
                for col in board.columns:
                    if col.name == from_column:
                        if work_item_id in col.work_item_ids:
                            removed_position = col.work_item_ids.index(work_item_id)
                            # Create new work_item_ids tuple with item removed
                            new_items = list(col.work_item_ids)
                            new_items.remove(work_item_id)
                            object.__setattr__(col, "work_item_ids", tuple(new_items))
                            # Recalculate positions of remaining items after the removed position
                            for i in range(removed_position, len(col.work_item_ids)):
                                item_id = col.work_item_ids[i]
                                if item_id in self._item_positions:
                                    board_id_stored, col_name, old_pos = self._item_positions[item_id]
                                    self._item_positions[item_id] = (board_id_stored, col_name, i)
                                    # Collect position change event for sibling items (emitted after lock release)
                                    pending_events.append(
                                        WorkItemPositionChangedEvent(
                                            type="workitem.position_changed",
                                            work_item_id=item_id,
                                            project_id=project_id,
                                            board_id=board_id,
                                            column_name=col_name,
                                            old_position=old_pos,
                                            new_position=i,
                                            timestamp=self._get_iso_timestamp(),
                                            source="mock",
                                        )
                                    )
                        break

                # Add to new column
                new_items = list(target_col.work_item_ids)
                new_items.append(work_item_id)
                object.__setattr__(target_col, "work_item_ids", tuple(new_items))
                self._item_positions[work_item_id] = (
                    board_id,
                    target_column,
                    len(target_col.work_item_ids) - 1,
                )
                # Track when item entered this column (for SLA monitoring)
                self._item_column_entries[work_item_id] = self._get_utc_datetime()

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

                # Collect column changed event (emitted after lock release to prevent deadlock:
                # event bus handlers call board methods that re-acquire this lock)
                pending_events.append(
                    WorkItemColumnChangedEvent(
                        type="workitem.column_changed",
                        work_item_id=work_item_id,
                        project_id=project_id,
                        board_id=board_id,
                        from_column=from_column,
                        to_column=target_column,
                        moved_by=cast("Literal['human', 'orchestrator', 'unknown']", moved_by.value),
                        timestamp=self._get_iso_timestamp(),
                        source="mock",
                    )
                )

        # Emit all collected events outside the lock to prevent deadlock.
        # Event bus handlers (e.g. BoardColumnEventHandler) call board methods that
        # re-acquire self._lock; emitting inside the lock causes asyncio.Lock deadlock.
        for event in pending_events:
            await self.emit_async(event)

        return ColumnMovementResult(
            work_item_id=work_item_id,
            from_column=from_column,
            to_column=target_column,
            moved_by=moved_by,
            timestamp=self._get_iso_timestamp(),
        )

    async def add_item_to_column(
        self, work_item_id: str, target_column: str, moved_by: MovedByType
    ) -> "ColumnMovementResult":
        """Add newly created work item to initial column.

        Places a newly created work item in its initial column. This differs from
        move_item_to_column in that it's the item's first placement, not a transition.

        Args:
            work_item_id: Item to place (must be newly created)
            target_column: Target column name (e.g., "Backlog")
            moved_by: Type of entity initiating the placement (HUMAN or ORCHESTRATOR)

        Returns:
            ColumnMovementResult: Details of the placement operation

        Raises:
            ResourceNotFoundError: Work item or target column doesn't exist
            ValueError: current_project not set
        """
        from codetoreum.ports.output.board_service import ColumnMovementResult

        async with self._lock:
            # For newly created items, they should already be tracked by the board
            # This is just placing them in the initial column
            if work_item_id not in self._item_positions:
                # Create initial entry if not exists
                # Get current_project
                if self.current_project is None:
                    msg = "current_project not set"
                    raise ValueError(msg)

                # Find a board for this project
                board_id = None
                for bid, pid in self._board_project_map.items():
                    if pid == self.current_project:
                        board_id = bid
                        break

                if not board_id:
                    msg = "No board found for project"
                    raise ResourceNotFoundError(msg, self.current_project)

                # Create initial position
                self._item_positions[work_item_id] = (board_id, target_column, 0)
            else:
                board_id, _, _ = self._item_positions[work_item_id]

            # Resolve project_id
            project_id = self._board_project_map.get(board_id) or self.current_project
            if project_id is None:
                msg = "current_project not set"
                raise ValueError(msg)

        board = await self.get_board(project_id, board_id)

        async with self._lock:
            # Validate target column exists
            target_col = None
            for col in board.columns:
                if col.name == target_column:
                    target_col = col
                    break
            if target_col is None:
                msg = "Column"
                raise ResourceNotFoundError(msg, target_column)

            # Add item to the target column's work_item_ids tuple
            new_items = list(target_col.work_item_ids)
            new_items.append(work_item_id)
            object.__setattr__(target_col, "work_item_ids", tuple(new_items))

            # Update item position to the target column
            position = len(target_col.work_item_ids) - 1
            self._item_positions[work_item_id] = (board_id, target_column, position)

            # Track when item entered this column (for SLA monitoring)
            self._item_column_entries[work_item_id] = self._get_utc_datetime()

            # Note: We do NOT log initial placement as a movement (movement log is for column transitions)
            # Only actual moves between columns are logged in movement_log

        # Emit event asynchronously (for event handlers/listeners to process)
        # Use the async version to ensure event bus publishing completes before returning
        await self.emit_async(
            WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                work_item_id=work_item_id,
                project_id=project_id,
                board_id=board_id,
                from_column=None,
                to_column=target_column,
                moved_by=cast("Literal['human', 'orchestrator', 'unknown']", moved_by.value),
                timestamp=self._get_iso_timestamp(),
                source="mock",
            )
        )

        return ColumnMovementResult(
            work_item_id=work_item_id,
            from_column=None,  # Item didn't come from anywhere, this is initial placement
            to_column=target_column,
            moved_by=moved_by,
            timestamp=self._get_iso_timestamp(),
        )

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
            msg = "current_project not set"
            raise ValueError(msg)

        board = await self.get_board(self.current_project, board_id)

        async with self._lock:
            columns_added: list[str] = []
            columns_removed: list[str] = []
            columns_renamed: list[tuple[str, str]] = []
            orphaned_items: list[str] = []

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
                            work_item_ids=(),
                        )
                        new_columns = list(board.columns)
                        new_columns.append(new_col)
                        object.__setattr__(board, "columns", tuple(new_columns))
                        columns_added.append(expected_col)

            # Check for extra columns
            for col in board.columns:
                if col.name not in config.expected_columns:
                    columns_removed.append(col.name)

            result = ReconciliationResult(
                board_id=board_id,
                columns_added=tuple(columns_added),
                columns_removed=tuple(columns_removed),
                columns_renamed=tuple(columns_renamed),
                orphaned_items=tuple(orphaned_items),
            )

        # Emit outside the lock to prevent deadlock (event bus handlers re-acquire board lock)
        await self.emit_async(
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
        async with self._lock:
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
        async with self._lock:
            if project_id in self._monitoring:
                status = self._monitoring[project_id]
                stopped_status = MonitoringStatus(
                    state=MonitoringState.STOPPED,
                    project_id=status.project_id,
                    started_at=status.started_at,
                    error_message=status.error_message,
                )
                self._monitoring[project_id] = stopped_status

    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Query current monitoring state.

        Args:
            project_id: Project to query status for

        Returns:
            MonitoringStatus with current state
        """
        async with self._lock:
            return self._monitoring.get(
                project_id,
                MonitoringStatus(state=MonitoringState.STOPPED, project_id=project_id),
            )

    # ===== Test Helper Methods =====

    def create_board(
        self,
        project_id: str,
        board_id: str,
        board_name: str,
        column_names: list[str],
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
        # Use a workaround for sync context: directly access protected state
        # This is safe because create_board is only called from test setup (no concurrency)
        key = f"{project_id}:{board_id}"
        self._boards[key] = ProjectBoard(
            id=board_id,
            name=board_name,
            project_id=project_id,
            columns=tuple(
                BoardColumn(
                    id=f"col-{i}",
                    name=col,
                    position=i,
                    work_item_ids=(),
                )
                for i, col in enumerate(column_names)
            ),
        )
        # Register board -> project mapping for multi-project support
        self._board_project_map[board_id] = project_id

    def seed_item_to_column(
        self,
        board_id: str,
        column_name: str,
        work_item_id: str,
        position: int | None = None,
    ) -> None:
        """Test helper: Place work item in column at specific position.

        Args:
            board_id: Board ID
            column_name: Target column name
            work_item_id: Work item to add
            position: Position in column (defaults to end of column)

        Raises:
            ValueError: Board, column, or project context doesn't exist

        Example:
            adapter.seed_item_to_column("board-1", "Backlog", "item-1", position=0)
        """
        if self.current_project is None:
            msg = "current_project not set"
            raise ValueError(msg)

        # Use direct access (no lock needed in test setup context)
        # Find the board containing this column
        board = None
        project_id = self.current_project
        if project_id:
            key = f"{project_id}:{board_id}"
            board = self._boards.get(key)

        if board is None:
            msg = f"Board {board_id} not found in project {project_id}"
            raise ValueError(msg)

        # Find the target column
        target_column = None
        for col in board.columns:
            if col.name == column_name:
                target_column = col
                break

        if target_column is None:
            msg = f"Column {column_name} not found in board {board_id}"
            raise ValueError(msg)

        # Insert work item at specified position
        if position is None:
            position = len(target_column.work_item_ids)

        # Create new work_item_ids tuple with item inserted at position
        new_items = list(target_column.work_item_ids)
        new_items.insert(position, work_item_id)
        object.__setattr__(target_column, "work_item_ids", tuple(new_items))
        self._item_positions[work_item_id] = (board_id, column_name, position)
        # Track when item entered this column (for SLA monitoring)
        self._item_column_entries[work_item_id] = self._get_utc_datetime()

        # Update positions of items after insertion
        for i in range(position + 1, len(target_column.work_item_ids)):
            item_id = target_column.work_item_ids[i]
            if item_id in self._item_positions:
                board_id_stored, current_col_name, old_pos = self._item_positions[item_id]
                self._item_positions[item_id] = (board_id_stored, current_col_name, i)
                # Emit position change event for shifted items
                self.emit(
                    WorkItemPositionChangedEvent(
                        type="workitem.position_changed",
                        work_item_id=item_id,
                        project_id=self.current_project,
                        board_id=board_id,
                        column_name=current_col_name,
                        old_position=old_pos,
                        new_position=i,
                        timestamp=self._get_iso_timestamp(),
                        source="mock",
                    )
                )

    async def simulate_human_move_async(self, work_item_id: str, target_column: str) -> None:
        """Test helper: Simulate user dragging card in board UI (async version).

        Use this in async test contexts where you can await the result.
        Moves the item to the target column and emits a movement event with
        moved_by=MovedByType.HUMAN.

        Args:
            work_item_id: Item that moved
            target_column: Target column name

        Raises:
            ValueError: Work item or column doesn't exist

        Example:
            await adapter.simulate_human_move_async("item-1", "In Progress")
        """
        if self.current_project is None:
            msg = "current_project not set"
            raise ValueError(msg)

        await self.move_item_to_column(work_item_id, target_column, MovedByType.HUMAN)

    def simulate_human_move(self, work_item_id: str, target_column: str) -> None:
        """Test helper: Simulate user dragging card in board UI (sync version).

        Use this in synchronous test contexts. Cannot be called from async contexts
        (use simulate_human_move_async instead).

        Moves the item to the target column and emits a movement event with
        moved_by=MovedByType.HUMAN.

        Args:
            work_item_id: Item that moved
            target_column: Target column name

        Raises:
            ValueError: Work item or column doesn't exist
            RuntimeError: If called from async context

        Example:
            adapter.simulate_human_move("item-1", "In Progress")
        """
        if self.current_project is None:
            msg = "current_project not set"
            raise ValueError(msg)

        # Check if we're in an async context
        try:
            asyncio.get_running_loop()
            # We're in async context - don't allow sync call
            msg = (
                "Cannot call sync simulate_human_move from async context. "
                "Use 'await simulate_human_move_async(...)' instead."
            )
            raise RuntimeError(msg)
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                # No loop running, create one
                asyncio.run(self.move_item_to_column(work_item_id, target_column, MovedByType.HUMAN))
            else:
                # Re-raise if it's our error message
                raise

    def assert_item_in_column(self, work_item_id: str, expected_column: str) -> None:
        """Test helper: Assert work item is in expected column.

        Args:
            work_item_id: Item to check
            expected_column: Expected column name

        Raises:
            AssertionError: If item is not in expected column

        Example:
            adapter.assert_item_in_column("item-1", "In Progress")
        """
        # Direct access for test assertions (no concurrent modification expected)
        actual = None
        if work_item_id in self._item_positions:
            _, actual, _ = self._item_positions[work_item_id]

        if actual != expected_column:
            msg = f"Expected work item {work_item_id} in column '{expected_column}', found in column '{actual}'"
            raise AssertionError(msg)

    def get_movement_history(self, work_item_id: str) -> list[MovementEvent]:
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
        # Direct access for test helpers (snapshot read, no concurrent modification expected)
        return [m for m in self._movement_log if m.work_item_id == work_item_id]

    def get_all_movements(self) -> list[MovementEvent]:
        """Test helper: Get complete movement audit trail for board.

        Returns all movements on the board in chronological order.

        Returns:
            List[MovementEvent]: All movements in chronological order

        Example:
            all_movements = adapter.get_all_movements()
            assert len(all_movements) >= 1
        """
        # Direct access for test helpers (snapshot read, no concurrent modification expected)
        return list(self._movement_log)

    def clear_movement_log(self) -> None:
        """Test helper: Clear movement history for cleanup.

        Useful between test cases to reset the audit trail.

        Example:
            adapter.clear_movement_log()
        """
        # Direct access for test cleanup (no concurrent modification expected)
        self._movement_log.clear()

    def set_item_column_silent(
        self,
        work_item_id: str,
        from_column: str,
        to_column: str,
        board_id: str,
        project_id: str,
    ) -> None:
        """Update item column without emitting events. For test fixture setup only.

        Used when a test needs to pre-position an item in a column before triggering
        an HTTP event (which represents an external system notification that the move
        already happened), without triggering the event handlers a second time.
        """
        key = f"{project_id}:{board_id}"
        board = self._boards.get(key)
        if board is None:
            return

        for col in board.columns:
            if col.name == from_column and work_item_id in col.work_item_ids:
                new_items = list(col.work_item_ids)
                new_items.remove(work_item_id)
                object.__setattr__(col, "work_item_ids", tuple(new_items))
                break

        new_position = 0
        for col in board.columns:
            if col.name == to_column:
                new_items = list(col.work_item_ids)
                new_items.append(work_item_id)
                object.__setattr__(col, "work_item_ids", tuple(new_items))
                new_position = len(new_items) - 1
                break

        self._item_positions[work_item_id] = (board_id, to_column, new_position)

    async def get_all_boards(self) -> list[ProjectBoard]:
        """Get all boards across all projects.

        Returns all boards managed by this service, including structure and items.
        Used for cross-board queries like SLA monitoring.

        Returns:
            List[ProjectBoard]: All boards with columns and items
        """
        async with self._lock:
            return list(self._boards.values())

    async def get_board_items(self, project_id: str, board_id: str) -> list[WorkItemPosition]:
        """Get all work items on a board with their column positions and entry times.

        Returns all items across all columns on the specified board,
        including their current column, position, and entry timestamp.

        Args:
            project_id: Project containing the board
            board_id: Board to query

        Returns:
            List[WorkItemPosition]: All items with column, position, and entry time
        """
        board = await self.get_board(project_id, board_id)
        items = []

        async with self._lock:
            for column in board.columns:
                for position, work_item_id in enumerate(column.work_item_ids):
                    entered_at = self._item_column_entries.get(work_item_id)
                    items.append(
                        WorkItemPosition(
                            work_item_id=work_item_id,
                            column_name=column.name,
                            position=position,
                            entered_column_at=entered_at,
                        )
                    )

        return items

    # ===== Helper Methods =====

    def _get_iso_timestamp(self) -> str:
        """Get current time as ISO 8601 timestamp."""
        if self._clock:
            return self._clock.now().isoformat()
        return datetime.now(UTC).isoformat()

    def _get_utc_datetime(self) -> datetime:
        """Get current time as UTC datetime.

        Uses simulation clock if available (for deterministic testing),
        otherwise uses wall clock time.
        """
        if self._clock:
            return self._clock.now()
        return datetime.now(UTC)
