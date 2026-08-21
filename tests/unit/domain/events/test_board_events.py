"""Unit tests for board events."""

import uuid

import pytest

from codetoreum.domain.events import (
    BoardReconciledEvent,
    WorkItemColumnChangedEvent,
    WorkItemPositionChangedEvent,
    now_iso,
)

# For immutability tests (when events become frozen dataclasses)
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    # Fallback for older Python versions or non-frozen dataclasses
    FrozenInstanceError = AttributeError  # type: ignore


class TestWorkItemColumnChangedEvent:
    """Test WorkItemColumnChangedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid column changed event."""
        timestamp = now_iso()
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=timestamp,
            source="github",
            work_item_id="123",
            project_id="proj-1",
            board_id="board-1",
            from_column="Backlog",
            to_column="In Progress",
            moved_by="human",
        )

        assert event.work_item_id == "123"
        assert event.from_column == "Backlog"
        assert event.to_column == "In Progress"
        assert event.moved_by == "human"

    def test_moved_by_orchestrator(self):
        """Test column change moved by orchestrator."""
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            board_id="board-1",
            from_column="Backlog",
            to_column="Done",
            moved_by="orchestrator",
        )

        assert event.moved_by == "orchestrator"

    def test_moved_by_unknown(self):
        """Test column change with unknown actor."""
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            board_id="board-1",
            from_column="Backlog",
            to_column="In Progress",
            moved_by="unknown",
        )

        assert event.moved_by == "unknown"

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=now_iso(),
                source="github",
                work_item_id="",  # Empty
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="In Progress",
            )

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=now_iso(),
                source="github",
                work_item_id="123",
                project_id="",  # Empty
                board_id="board-1",
                from_column="Backlog",
                to_column="In Progress",
            )

    def test_missing_board_id(self):
        """Test that board_id is required."""
        with pytest.raises(ValueError, match="board_id"):
            WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=now_iso(),
                source="github",
                work_item_id="123",
                project_id="proj-1",
                board_id="",  # Empty
                from_column="Backlog",
                to_column="In Progress",
            )

    def test_missing_from_column(self):
        """Test that from_column cannot be empty string (but can be None for initial placement)."""
        with pytest.raises(ValueError, match="from_column"):
            WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=now_iso(),
                source="github",
                work_item_id="123",
                project_id="proj-1",
                board_id="board-1",
                from_column="",  # Empty string is invalid
                to_column="In Progress",
            )

    def test_from_column_can_be_none(self):
        """Test that from_column can be None for initial placement."""
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            board_id="board-1",
            from_column=None,  # None is valid for initial placement
            to_column="Backlog",
        )
        assert event.from_column is None
        assert event.to_column == "Backlog"

    def test_missing_to_column(self):
        """Test that to_column is required."""
        with pytest.raises(ValueError, match="to_column"):
            WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=now_iso(),
                source="github",
                work_item_id="123",
                project_id="proj-1",
                board_id="board-1",
                from_column="Backlog",
                to_column="",  # Empty
            )

    def test_column_changed_serialization(self):
        """Test column changed event serialization."""
        timestamp = now_iso()
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=timestamp,
            source="github",
            correlation_id="corr-123",
            work_item_id="123",
            project_id="proj-1",
            board_id="board-1",
            from_column="Backlog",
            to_column="In Progress",
            moved_by="human",
        )

        d = event.to_dict()

        assert d["type"] == "workitem.column_changed"
        assert d["work_item_id"] == "123"
        assert d["from_column"] == "Backlog"
        assert d["to_column"] == "In Progress"
        assert d["moved_by"] == "human"

    def test_column_changed_deserialization(self):
        """Test column changed event deserialization."""
        timestamp = now_iso()
        d = {
            "type": "workitem.column_changed",
            "timestamp": timestamp,
            "source": "github",
            "correlation_id": "corr-123",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "from_column": "Backlog",
            "to_column": "In Progress",
            "moved_by": "human",
        }

        event = WorkItemColumnChangedEvent.from_dict(d)

        assert event.type == "workitem.column_changed"
        assert event.work_item_id == "123"
        assert event.from_column == "Backlog"
        assert event.to_column == "In Progress"
        assert event.moved_by == "human"

    def test_column_changed_roundtrip(self):
        """Test column changed event roundtrip serialization."""
        timestamp = now_iso()
        original = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=timestamp,
            source="github",
            correlation_id="corr-123",
            work_item_id="123",
            project_id="proj-1",
            board_id="board-1",
            from_column="Backlog",
            to_column="Done",
            moved_by="orchestrator",
        )

        d = original.to_dict()
        restored = WorkItemColumnChangedEvent.from_dict(d)

        assert restored.work_item_id == original.work_item_id
        assert restored.from_column == original.from_column
        assert restored.to_column == original.to_column
        assert restored.moved_by == original.moved_by


class TestBoardReconciledEvent:
    """Test BoardReconciledEvent."""

    def test_create_valid_event(self):
        """Test creating a valid board reconciled event."""
        timestamp = now_iso()
        event = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=timestamp,
            source="github",
            project_id="proj-1",
            board_id="board-1",
            columns_added=("New Column",),
            columns_removed=("Old Column",),
            items_moved=5,
        )

        assert event.project_id == "proj-1"
        assert event.columns_added == ("New Column",)
        assert event.columns_removed == ("Old Column",)
        assert event.items_moved == 5

    def test_board_reconciled_no_changes(self):
        """Test board reconciled with no changes."""
        event = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
        )

        assert event.columns_added == ()
        assert event.columns_removed == ()
        assert event.items_moved == 0

    def test_board_reconciled_columns_added(self):
        """Test board reconciled with added columns."""
        event = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            columns_added=("Ready", "In Review", "Done"),
            items_moved=10,
        )

        assert event.columns_added == ("Ready", "In Review", "Done")
        assert event.columns_removed == ()
        assert event.items_moved == 10

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            BoardReconciledEvent(
                type="board.reconciled",
                timestamp=now_iso(),
                source="github",
                project_id="",  # Empty
                board_id="board-1",
            )

    def test_missing_board_id(self):
        """Test that board_id is required."""
        with pytest.raises(ValueError, match="board_id"):
            BoardReconciledEvent(
                type="board.reconciled",
                timestamp=now_iso(),
                source="github",
                project_id="proj-1",
                board_id="",  # Empty
            )

    def test_board_reconciled_serialization(self):
        """Test board reconciled event serialization."""
        timestamp = now_iso()
        event = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=timestamp,
            source="github",
            project_id="proj-1",
            board_id="board-1",
            columns_added=("New",),
            columns_removed=("Old",),
            items_moved=3,
        )

        d = event.to_dict()

        assert d["project_id"] == "proj-1"
        assert d["columns_added"] == ["New"]
        assert d["columns_removed"] == ["Old"]
        assert d["items_moved"] == 3

    def test_board_reconciled_roundtrip(self):
        """Test board reconciled event roundtrip serialization."""
        timestamp = now_iso()
        original = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=timestamp,
            source="jira",
            correlation_id="corr-456",
            project_id="proj-2",
            board_id="board-2",
            columns_added=("Backlog", "Ready"),
            columns_removed=("Archived",),
            items_moved=7,
        )

        d = original.to_dict()
        restored = BoardReconciledEvent.from_dict(d)

        assert restored.project_id == original.project_id
        # Verify tuples are preserved through serialization
        assert isinstance(restored.columns_added, tuple)
        assert isinstance(restored.columns_removed, tuple)
        assert restored.columns_added == original.columns_added
        assert restored.columns_removed == original.columns_removed
        assert restored.items_moved == original.items_moved

    def test_literal_type_preserved_moved_by(self):
        """Test that Literal types are preserved for moved_by field."""
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            board_id="board-1",
            from_column="Backlog",
            to_column="In Progress",
            moved_by="orchestrator",
        )

        data = event.to_dict()
        restored = WorkItemColumnChangedEvent.from_dict(data)

        assert restored.moved_by == "orchestrator"
        assert isinstance(restored.moved_by, str)

    def test_tuple_type_preserved_in_board_reconciled(self):
        """Test that tuple types are preserved through serialization."""
        event = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            columns_added=("Col A", "Col B", "Col C"),
            columns_removed=("Old Col",),
            items_moved=5,
        )

        data = event.to_dict()
        restored = BoardReconciledEvent.from_dict(data)

        assert isinstance(restored.columns_added, tuple)
        assert isinstance(restored.columns_removed, tuple)
        assert restored.columns_added == ("Col A", "Col B", "Col C")
        assert restored.columns_removed == ("Old Col",)

    def test_uuid_format_preserved_in_board_event(self):
        """Test that UUID fields preserve format in board events."""
        event_id = str(uuid.uuid4())

        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=now_iso(),
            source="github",
            correlation_id=event_id,
            work_item_id="123",
            project_id="proj-1",
            board_id="board-1",
            from_column="Backlog",
            to_column="In Progress",
            moved_by="human",
        )

        data = event.to_dict()
        restored = WorkItemColumnChangedEvent.from_dict(data)

        assert restored.correlation_id == event_id
        uuid.UUID(restored.correlation_id)

    def test_optional_field_none_in_board_event(self):
        """Test that None values are preserved in board events."""
        # Create event with explicit None for optional fields
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=now_iso(),
            source="github",
            correlation_id=None,
            work_item_id="123",
            project_id="proj-1",
            board_id="board-1",
            from_column="Backlog",
            to_column="In Progress",
            moved_by="unknown",
        )

        data = event.to_dict()
        restored = WorkItemColumnChangedEvent.from_dict(data)

        assert restored.correlation_id is None

    def test_numeric_type_preserved_in_board_reconciled(self):
        """Test that numeric types are preserved in board events."""
        event = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            items_moved=42,
        )

        data = event.to_dict()
        restored = BoardReconciledEvent.from_dict(data)

        assert restored.items_moved == 42
        assert isinstance(restored.items_moved, int)


class TestWorkItemColumnChangedEventImmutability:
    """Test immutability of WorkItemColumnChangedEvent (frozen dataclass)."""

    def test_work_item_column_changed_event_is_frozen(self):
        """Test that WorkItemColumnChangedEvent is immutable (frozen dataclass)."""
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            board_id="board-1",
            from_column="Backlog",
            to_column="In Progress",
        )

        # Verify the event is properly created
        assert event.work_item_id == "123"
        assert event.from_column == "Backlog"
        assert event.to_column == "In Progress"

        # WorkItemColumnChangedEvent is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "456"

        with pytest.raises(FrozenInstanceError):
            event.from_column = "Done"

        with pytest.raises(FrozenInstanceError):
            event.to_column = "Review"


class TestBoardReconciledEventImmutability:
    """Test immutability of BoardReconciledEvent (frozen dataclass)."""

    def test_board_reconciled_event_is_frozen(self):
        """Test that BoardReconciledEvent is immutable (frozen dataclass)."""
        event = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            columns_added=("New Column",),
            columns_removed=("Old Column",),
        )

        # Verify the event is properly created
        assert event.board_id == "board-1"
        assert event.project_id == "proj-1"

        # BoardReconciledEvent is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.board_id = "board-2"

        with pytest.raises(FrozenInstanceError):
            event.project_id = "proj-2"

    def test_board_reconciled_event_columns_immutable(self):
        """Test that BoardReconciledEvent column tuples are immutable."""
        event = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            columns_added=("New Column",),
            columns_removed=("Old Column",),
        )

        # Verify columns are stored as tuples (immutable)
        assert isinstance(event.columns_added, tuple)
        assert isinstance(event.columns_removed, tuple)
        assert event.columns_added == ("New Column",)
        assert event.columns_removed == ("Old Column",)

        # Attempt to modify tuple should fail (tuples are immutable)
        with pytest.raises(TypeError):
            event.columns_added[0] = "Modified"  # type: ignore

    def test_board_reconciled_event_base_attributes(self):
        """Test that base event attributes are preserved."""
        timestamp = now_iso()
        event = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=timestamp,
            source="github",
            correlation_id="corr-1",
            project_id="proj-1",
            board_id="board-1",
            items_moved=3,
        )

        # Verify base attributes are set correctly
        assert event.type == "board.reconciled"
        assert event.timestamp == timestamp
        assert event.source == "github"
        assert event.correlation_id == "corr-1"
        assert event.items_moved == 3


class TestWorkItemPositionChangedEvent:
    """Test WorkItemPositionChangedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid position changed event."""
        timestamp = now_iso()
        event = WorkItemPositionChangedEvent(
            type="workitem.position_changed",
            timestamp=timestamp,
            source="mock",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            column_name="In Progress",
            old_position=2,
            new_position=1,
        )

        assert event.work_item_id == "item-1"
        assert event.project_id == "proj-1"
        assert event.board_id == "board-1"
        assert event.column_name == "In Progress"
        assert event.old_position == 2
        assert event.new_position == 1

    def test_position_change_to_end(self):
        """Test moving item to end of column."""
        event = WorkItemPositionChangedEvent(
            type="workitem.position_changed",
            timestamp=now_iso(),
            source="mock",
            work_item_id="item-3",
            project_id="proj-1",
            board_id="board-1",
            column_name="Backlog",
            old_position=0,
            new_position=5,
        )

        assert event.old_position == 0
        assert event.new_position == 5

    def test_position_change_to_start(self):
        """Test moving item to start of column."""
        event = WorkItemPositionChangedEvent(
            type="workitem.position_changed",
            timestamp=now_iso(),
            source="mock",
            work_item_id="item-2",
            project_id="proj-1",
            board_id="board-1",
            column_name="Done",
            old_position=4,
            new_position=0,
        )

        assert event.old_position == 4
        assert event.new_position == 0

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            WorkItemPositionChangedEvent(
                type="workitem.position_changed",
                timestamp=now_iso(),
                source="mock",
                work_item_id="",  # Empty
                project_id="proj-1",
                board_id="board-1",
                column_name="In Progress",
                old_position=0,
                new_position=1,
            )

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            WorkItemPositionChangedEvent(
                type="workitem.position_changed",
                timestamp=now_iso(),
                source="mock",
                work_item_id="item-1",
                project_id="",  # Empty
                board_id="board-1",
                column_name="In Progress",
                old_position=0,
                new_position=1,
            )

    def test_missing_board_id(self):
        """Test that board_id is required."""
        with pytest.raises(ValueError, match="board_id"):
            WorkItemPositionChangedEvent(
                type="workitem.position_changed",
                timestamp=now_iso(),
                source="mock",
                work_item_id="item-1",
                project_id="proj-1",
                board_id="",  # Empty
                column_name="In Progress",
                old_position=0,
                new_position=1,
            )

    def test_missing_column_name(self):
        """Test that column_name is required."""
        with pytest.raises(ValueError, match="column_name"):
            WorkItemPositionChangedEvent(
                type="workitem.position_changed",
                timestamp=now_iso(),
                source="mock",
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                column_name="",  # Empty
                old_position=0,
                new_position=1,
            )

    def test_negative_old_position(self):
        """Test that old_position cannot be negative."""
        with pytest.raises(ValueError, match="old_position must be non-negative"):
            WorkItemPositionChangedEvent(
                type="workitem.position_changed",
                timestamp=now_iso(),
                source="mock",
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                column_name="In Progress",
                old_position=-1,
                new_position=1,
            )

    def test_negative_new_position(self):
        """Test that new_position cannot be negative."""
        with pytest.raises(ValueError, match="new_position must be non-negative"):
            WorkItemPositionChangedEvent(
                type="workitem.position_changed",
                timestamp=now_iso(),
                source="mock",
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                column_name="In Progress",
                old_position=1,
                new_position=-1,
            )

    def test_equal_positions_not_allowed(self):
        """Test that old_position cannot equal new_position."""
        with pytest.raises(ValueError, match="old_position must differ from new_position"):
            WorkItemPositionChangedEvent(
                type="workitem.position_changed",
                timestamp=now_iso(),
                source="mock",
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                column_name="In Progress",
                old_position=2,
                new_position=2,
            )

    def test_position_changed_serialization(self):
        """Test position changed event serialization."""
        timestamp = now_iso()
        event = WorkItemPositionChangedEvent(
            type="workitem.position_changed",
            timestamp=timestamp,
            source="mock",
            correlation_id="corr-789",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            column_name="In Progress",
            old_position=2,
            new_position=1,
        )

        d = event.to_dict()

        assert d["type"] == "workitem.position_changed"
        assert d["work_item_id"] == "item-1"
        assert d["project_id"] == "proj-1"
        assert d["board_id"] == "board-1"
        assert d["column_name"] == "In Progress"
        assert d["old_position"] == 2
        assert d["new_position"] == 1

    def test_position_changed_deserialization(self):
        """Test position changed event deserialization."""
        timestamp = now_iso()
        d = {
            "type": "workitem.position_changed",
            "timestamp": timestamp,
            "source": "mock",
            "correlation_id": "corr-789",
            "work_item_id": "item-1",
            "project_id": "proj-1",
            "board_id": "board-1",
            "column_name": "In Progress",
            "old_position": 2,
            "new_position": 1,
        }

        event = WorkItemPositionChangedEvent.from_dict(d)

        assert event.type == "workitem.position_changed"
        assert event.work_item_id == "item-1"
        assert event.old_position == 2
        assert event.new_position == 1

    def test_position_changed_roundtrip(self):
        """Test position changed event roundtrip serialization."""
        timestamp = now_iso()
        original = WorkItemPositionChangedEvent(
            type="workitem.position_changed",
            timestamp=timestamp,
            source="mock",
            correlation_id="corr-101",
            work_item_id="item-5",
            project_id="proj-2",
            board_id="board-2",
            column_name="Review",
            old_position=3,
            new_position=0,
        )

        d = original.to_dict()
        restored = WorkItemPositionChangedEvent.from_dict(d)

        assert restored.work_item_id == original.work_item_id
        assert restored.old_position == original.old_position
        assert restored.new_position == original.new_position
        assert restored.column_name == original.column_name

    def test_position_changed_event_is_frozen(self):
        """Test that WorkItemPositionChangedEvent is immutable (frozen dataclass)."""
        event = WorkItemPositionChangedEvent(
            type="workitem.position_changed",
            timestamp=now_iso(),
            source="mock",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            column_name="In Progress",
            old_position=2,
            new_position=1,
        )

        # Verify the event is properly created
        assert event.old_position == 2
        assert event.new_position == 1

        # WorkItemPositionChangedEvent is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.old_position = 0

        with pytest.raises(FrozenInstanceError):
            event.new_position = 5

        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "item-2"
