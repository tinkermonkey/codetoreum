"""Unit tests for BoardPollingService."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from codetoreum.application.board_polling_service import (
    BoardPollingService,
    BoardState,
)
from codetoreum.domain.events import WorkItemColumnChanged
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.board_service import (
    BoardColumn,
    IBoardService,
    ProjectBoard,
    WorkItemPosition,
)
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)


@pytest.fixture
def mock_board_service():
    """Create a mock board service."""
    return AsyncMock(spec=IBoardService)


@pytest.fixture
def event_bus():
    """Create an event bus for testing."""
    return EventBus()


@pytest.fixture
def polling_service(mock_board_service, event_bus):
    """Create a polling service with mocked dependencies."""
    return BoardPollingService(
        board_service=mock_board_service,
        event_bus=event_bus,
        poll_interval_seconds=1,
    )


class TestDetectChanges:
    """Tests for _detect_changes method."""

    def test_detect_changes_identifies_moved_items(self, polling_service):
        """Test that _detect_changes identifies work items that changed columns."""
        previous_state = BoardState(
            board_id="board-1",
            item_columns={
                "item-1": "Backlog",
                "item-2": "Backlog",
                "item-3": "In Progress",
            },
        )

        current_state = BoardState(
            board_id="board-1",
            item_columns={
                "item-1": "In Progress",  # Moved!
                "item-2": "Backlog",  # No change
                "item-3": "Done",  # Moved!
            },
        )

        changes = polling_service._detect_changes(previous_state, current_state)

        assert len(changes) == 2
        assert {"work_item_id": "item-1", "from_column": "Backlog", "to_column": "In Progress"} in changes
        assert {"work_item_id": "item-3", "from_column": "In Progress", "to_column": "Done"} in changes

    def test_detect_changes_ignores_new_items(self, polling_service):
        """Test that new items (not in previous state) are not reported as changes."""
        previous_state = BoardState(
            board_id="board-1",
            item_columns={
                "item-1": "Backlog",
            },
        )

        current_state = BoardState(
            board_id="board-1",
            item_columns={
                "item-1": "Backlog",
                "item-2": "In Progress",  # New item
            },
        )

        changes = polling_service._detect_changes(previous_state, current_state)

        # New items should not be reported as changes
        assert len(changes) == 0

    def test_detect_changes_empty_previous_state(self, polling_service):
        """Test change detection when previous state is empty."""
        previous_state = BoardState(
            board_id="board-1",
            item_columns={},
        )

        current_state = BoardState(
            board_id="board-1",
            item_columns={
                "item-1": "In Progress",
            },
        )

        changes = polling_service._detect_changes(previous_state, current_state)

        # No previous state means no changes to report
        assert len(changes) == 0

    def test_detect_changes_no_changes(self, polling_service):
        """Test change detection when nothing has changed."""
        state = BoardState(
            board_id="board-1",
            item_columns={
                "item-1": "Backlog",
                "item-2": "In Progress",
            },
        )

        changes = polling_service._detect_changes(state, state)

        assert len(changes) == 0

    def test_detect_changes_multiple_columns(self, polling_service):
        """Test change detection across multiple columns."""
        previous_state = BoardState(
            board_id="board-1",
            item_columns={
                "item-1": "Backlog",
                "item-2": "In Progress",
                "item-3": "Review",
                "item-4": "Done",
            },
        )

        current_state = BoardState(
            board_id="board-1",
            item_columns={
                "item-1": "In Progress",  # Backlog -> In Progress
                "item-2": "Review",  # In Progress -> Review
                "item-3": "Done",  # Review -> Done
                "item-4": "Done",  # No change
            },
        )

        changes = polling_service._detect_changes(previous_state, current_state)

        assert len(changes) == 3
        assert {"work_item_id": "item-1", "from_column": "Backlog", "to_column": "In Progress"} in changes
        assert {"work_item_id": "item-2", "from_column": "In Progress", "to_column": "Review"} in changes
        assert {"work_item_id": "item-3", "from_column": "Review", "to_column": "Done"} in changes


class TestEnableDisableBoard:
    """Tests for enable_board and disable_board methods."""

    def test_enable_board_adds_to_enabled_set(self, polling_service):
        """Test that enable_board adds board to polling set."""
        polling_service.enable_board("proj-1", "board-1")

        assert "proj-1:board-1" in polling_service._enabled_boards

    def test_disable_board_removes_from_enabled_set(self, polling_service):
        """Test that disable_board removes board from polling set."""
        polling_service.enable_board("proj-1", "board-1")
        polling_service.disable_board("proj-1", "board-1")

        assert "proj-1:board-1" not in polling_service._enabled_boards

    def test_disable_board_non_existent_board(self, polling_service):
        """Test disabling a board that was never enabled."""
        # Should not raise an error
        polling_service.disable_board("proj-1", "board-1")

        assert "proj-1:board-1" not in polling_service._enabled_boards

    def test_enable_multiple_boards(self, polling_service):
        """Test enabling multiple boards."""
        polling_service.enable_board("proj-1", "board-1")
        polling_service.enable_board("proj-1", "board-2")
        polling_service.enable_board("proj-2", "board-1")

        assert "proj-1:board-1" in polling_service._enabled_boards
        assert "proj-1:board-2" in polling_service._enabled_boards
        assert "proj-2:board-1" in polling_service._enabled_boards


class TestPollingServiceLifecycle:
    """Tests for service start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_begins_polling(self, polling_service):
        """Test that start() begins the polling task."""
        assert polling_service._running is False
        assert polling_service._poll_task is None

        await polling_service.start()

        assert polling_service._running is True
        assert polling_service._poll_task is not None

        await polling_service.stop()

    @pytest.mark.asyncio
    async def test_start_when_already_running(self, polling_service):
        """Test calling start() when service is already running."""
        await polling_service.start()
        first_task = polling_service._poll_task

        await polling_service.start()  # Second start

        assert polling_service._poll_task is first_task

        await polling_service.stop()

    @pytest.mark.asyncio
    async def test_stop_stops_polling(self, polling_service):
        """Test that stop() gracefully stops the polling loop."""
        await polling_service.start()
        assert polling_service._running is True

        await polling_service.stop()

        assert polling_service._running is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, polling_service):
        """Test calling stop() when service is not running."""
        # Should not raise
        await polling_service.stop()
        assert polling_service._running is False


class TestPollingIntegration:
    """Integration tests for the polling loop."""

    @pytest.mark.asyncio
    async def test_polling_detects_column_changes(
        self, polling_service, mock_board_service, event_bus
    ):
        """Test that polling loop detects and emits change events."""
        # Setup mock board state
        column1 = BoardColumn(id="col-1", name="Backlog", position=0, work_item_ids=["item-1"])
        column2 = BoardColumn(id="col-2", name="In Progress", position=1, work_item_ids=[])
        board = ProjectBoard(
            id="board-1", name="Test Board", project_id="proj-1", columns=[column1, column2]
        )

        item_pos = WorkItemPosition(
            work_item_id="item-1", column_name="Backlog", position=0
        )

        mock_board_service.get_board.return_value = board
        mock_board_service.get_items_in_column.side_effect = [
            [item_pos],  # First poll: Backlog
            [],  # First poll: In Progress
        ]

        # Initialize state with first poll
        await polling_service._poll_board("proj-1", "board-1")

        # Now change the state - item moved to In Progress
        item_pos_moved = WorkItemPosition(
            work_item_id="item-1", column_name="In Progress", position=0
        )
        column1_empty = BoardColumn(id="col-1", name="Backlog", position=0, work_item_ids=[])
        column2_with_item = BoardColumn(
            id="col-2", name="In Progress", position=1, work_item_ids=["item-1"]
        )
        board_updated = ProjectBoard(
            id="board-1", name="Test Board", project_id="proj-1",
            columns=[column1_empty, column2_with_item]
        )
        mock_board_service.get_board.return_value = board_updated
        mock_board_service.get_items_in_column.side_effect = [
            [],  # Second poll: Backlog (empty now)
            [item_pos_moved],  # Second poll: In Progress
        ]

        # Track events
        events_received = []

        async def capture_event(event):
            events_received.append(event)

        event_bus.subscribe("WorkItemColumnChanged", capture_event)

        # Second poll should detect the change
        await polling_service._poll_board("proj-1", "board-1")

        # Verify event was emitted
        assert len(events_received) == 1
        event = events_received[0]
        assert isinstance(event, WorkItemColumnChanged)
        assert event.payload["work_item_id"] == "item-1"
        assert event.payload["from_column"] == "Backlog"
        assert event.payload["to_column"] == "In Progress"
        assert event.payload["moved_by"] == "HUMAN"
        assert event.payload["board_id"] == "board-1"
        assert event.payload["project_id"] == "proj-1"

    @pytest.mark.asyncio
    async def test_polling_loop_continues_on_error(
        self, polling_service, mock_board_service
    ):
        """Test that polling loop continues even when board service fails."""
        from codetoreum.ports.exceptions import ExternalServiceError

        # First call raises error, second succeeds
        mock_board_service.get_board.side_effect = [
            ExternalServiceError("board_service", "Service error"),
            ProjectBoard(id="board-1", name="Test", project_id="proj-1", columns=[]),
        ]

        polling_service.enable_board("proj-1", "board-1")

        # Poll all boards twice - first fails, second succeeds
        await polling_service._poll_all_boards()  # Should log error but continue
        await polling_service._poll_all_boards()  # Should succeed

        # Should have called get_board twice
        assert mock_board_service.get_board.call_count == 2


class TestErrorRecovery:
    """Tests for error recovery and handling in polling service."""

    @pytest.mark.asyncio
    async def test_permanent_error_disables_board_polling(
        self, polling_service, mock_board_service
    ):
        """Test that permanent errors (AuthenticationError) disable polling for the board."""
        # Setup - board initially in state
        polling_service.enable_board("proj-1", "board-1")
        polling_service._board_states["board-1"] = BoardState(
            board_id="board-1", item_columns={}
        )

        # Mock get_board to raise AuthenticationError
        mock_board_service.get_board.side_effect = AuthenticationError("Invalid token")

        # Poll the board
        await polling_service._poll_board("proj-1", "board-1")

        # Assert - board state should be removed (polling disabled)
        assert "board-1" not in polling_service._board_states

    @pytest.mark.asyncio
    async def test_resource_not_found_disables_board_polling(
        self, polling_service, mock_board_service
    ):
        """Test that ResourceNotFoundError disables polling for the board."""
        # Setup
        polling_service.enable_board("proj-1", "board-1")
        polling_service._board_states["board-1"] = BoardState(
            board_id="board-1", item_columns={}
        )

        # Mock get_board to raise ResourceNotFoundError
        mock_board_service.get_board.side_effect = ResourceNotFoundError(
            "Board", "board-1"
        )

        # Poll the board
        await polling_service._poll_board("proj-1", "board-1")

        # Assert - board state should be removed
        assert "board-1" not in polling_service._board_states

    @pytest.mark.asyncio
    async def test_validation_error_disables_board_polling(
        self, polling_service, mock_board_service
    ):
        """Test that ValidationError disables polling for the board."""
        # Setup
        polling_service.enable_board("proj-1", "board-1")
        polling_service._board_states["board-1"] = BoardState(
            board_id="board-1", item_columns={}
        )

        # Mock get_board to raise ValidationError
        mock_board_service.get_board.side_effect = ValidationError("Invalid board ID")

        # Poll the board
        await polling_service._poll_board("proj-1", "board-1")

        # Assert - board state should be removed
        assert "board-1" not in polling_service._board_states

    @pytest.mark.asyncio
    async def test_transient_error_preserves_board_state(
        self, polling_service, mock_board_service
    ):
        """Test that transient errors (ExternalServiceError) preserve board state."""
        # Setup - initialize board state
        initial_state = BoardState(
            board_id="board-1", item_columns={"item-1": "Backlog"}
        )
        polling_service.enable_board("proj-1", "board-1")
        polling_service._board_states["board-1"] = initial_state

        # Mock get_board to raise ExternalServiceError
        mock_board_service.get_board.side_effect = ExternalServiceError(
            "BoardService", "Service temporarily unavailable"
        )

        # Poll the board
        await polling_service._poll_board("proj-1", "board-1")

        # Assert - board state should still exist (will retry next interval)
        assert "board-1" in polling_service._board_states
        assert polling_service._board_states["board-1"] == initial_state

    @pytest.mark.asyncio
    async def test_recovery_after_transient_error(
        self, polling_service, mock_board_service
    ):
        """Test that polling recovers successfully after a transient error."""
        # Setup - initialize board state
        column1 = BoardColumn(
            id="col-1", name="Backlog", position=0, work_item_ids=["item-1"]
        )
        board = ProjectBoard(
            id="board-1", name="Test Board", project_id="proj-1", columns=[column1]
        )
        item_pos = WorkItemPosition(
            work_item_id="item-1", column_name="Backlog", position=0
        )

        polling_service.enable_board("proj-1", "board-1")
        polling_service._board_states["board-1"] = BoardState(
            board_id="board-1", item_columns={"item-1": "Backlog"}
        )

        # First poll - transient error
        mock_board_service.get_board.side_effect = ExternalServiceError(
            "BoardService", "Network timeout"
        )
        await polling_service._poll_board("proj-1", "board-1")

        # Assert - state preserved
        assert "board-1" in polling_service._board_states

        # Second poll - service recovered
        mock_board_service.get_board.side_effect = None
        mock_board_service.get_board.return_value = board
        mock_board_service.get_items_in_column.return_value = [item_pos]

        await polling_service._poll_board("proj-1", "board-1")

        # Assert - polling succeeded and state updated
        assert "board-1" in polling_service._board_states
        assert mock_board_service.get_board.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_boards_independent_error_handling(
        self, polling_service, mock_board_service
    ):
        """Test that error on one board doesn't affect other boards."""
        # Setup two boards
        polling_service.enable_board("proj-1", "board-1")
        polling_service.enable_board("proj-1", "board-2")
        polling_service._board_states["board-1"] = BoardState(
            board_id="board-1", item_columns={}
        )
        polling_service._board_states["board-2"] = BoardState(
            board_id="board-2", item_columns={}
        )

        # Mock get_board to fail for board-1 but succeed for board-2
        def get_board_side_effect(project_id, board_id):
            if board_id == "board-1":
                raise AuthenticationError("Auth failed")
            return ProjectBoard(
                id=board_id, name="Board 2", project_id=project_id, columns=[]
            )

        mock_board_service.get_board.side_effect = get_board_side_effect
        mock_board_service.get_items_in_column.return_value = []

        # Poll both boards
        await polling_service._poll_board("proj-1", "board-1")
        await polling_service._poll_board("proj-1", "board-2")

        # Assert - board-1 removed, board-2 still active
        assert "board-1" not in polling_service._board_states
        assert "board-2" in polling_service._board_states

    @pytest.mark.asyncio
    async def test_error_during_get_items_in_column(
        self, polling_service, mock_board_service
    ):
        """Test error handling when get_items_in_column fails."""
        # Setup
        column1 = BoardColumn(
            id="col-1", name="Backlog", position=0, work_item_ids=["item-1"]
        )
        board = ProjectBoard(
            id="board-1", name="Test Board", project_id="proj-1", columns=[column1]
        )

        polling_service.enable_board("proj-1", "board-1")

        # Mock get_board succeeds, but get_items_in_column fails
        mock_board_service.get_board.return_value = board
        mock_board_service.get_items_in_column.side_effect = ExternalServiceError(
            "BoardService", "Failed to fetch items"
        )

        # Poll the board - should handle error gracefully
        await polling_service._poll_board("proj-1", "board-1")

        # Assert - no exception raised, polling can continue
        assert mock_board_service.get_board.called
