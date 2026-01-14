"""Unit tests for board events."""

import pytest

from codetoreum.domain.events import (
    BoardReconciledEvent,
    WorkItemColumnChangedEvent,
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
        """Test that from_column is required."""
        with pytest.raises(ValueError, match="from_column"):
            WorkItemColumnChangedEvent(
                type="workitem.column_changed",
                timestamp=now_iso(),
                source="github",
                work_item_id="123",
                project_id="proj-1",
                board_id="board-1",
                from_column="",  # Empty
                to_column="In Progress",
            )

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
        assert restored.columns_added == original.columns_added
        assert restored.columns_removed == original.columns_removed
        assert restored.items_moved == original.items_moved


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
            event.work_item_id = "456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.from_column = "Done"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.to_column = "Review"  # type: ignore


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
            columns_added=["New Column"],
            columns_removed=["Old Column"],
        )

        # Verify the event is properly created
        assert event.board_id == "board-1"
        assert event.project_id == "proj-1"

        # BoardReconciledEvent is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.board_id = "board-2"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.project_id = "proj-2"  # type: ignore

    def test_board_reconciled_event_columns_immutable(self):
        """Test that BoardReconciledEvent column tuples are immutable."""
        event = BoardReconciledEvent(
            type="board.reconciled",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            columns_added=["New Column"],
            columns_removed=["Old Column"],
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
