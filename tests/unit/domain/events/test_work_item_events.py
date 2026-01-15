"""Unit tests for work item events."""

import uuid
import pytest

from codetoreum.domain.events import (
    WorkItemCreatedEvent,
    WorkItemUpdatedEvent,
    now_iso,
)

# For immutability tests (when events become frozen dataclasses)
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    # Fallback for older Python versions or non-frozen dataclasses
    FrozenInstanceError = AttributeError  # type: ignore


class TestWorkItemCreatedEvent:
    """Test WorkItemCreatedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid work item created event."""
        event = WorkItemCreatedEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            title="Add user authentication",
            initial_column="Backlog",
        )

        assert event.work_item_id == "123"
        assert event.title == "Add user authentication"
        assert event.initial_column == "Backlog"

    def test_work_item_created_without_initial_column(self):
        """Test work item created without initial column."""
        event = WorkItemCreatedEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            title="Fix bug in login",
        )

        assert event.initial_column is None

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            WorkItemCreatedEvent(
                type="workitem.created",
                timestamp=now_iso(),
                source="github",
                work_item_id="",  # Empty
                project_id="proj-1",
                title="Test",
            )

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            WorkItemCreatedEvent(
                type="workitem.created",
                timestamp=now_iso(),
                source="github",
                work_item_id="123",
                project_id="",  # Empty
                title="Test",
            )

    def test_missing_title(self):
        """Test that title is required."""
        with pytest.raises(ValueError, match="title"):
            WorkItemCreatedEvent(
                type="workitem.created",
                timestamp=now_iso(),
                source="github",
                work_item_id="123",
                project_id="proj-1",
                title="",  # Empty
            )

    def test_work_item_created_serialization(self):
        """Test work item created event serialization."""
        event = WorkItemCreatedEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
            correlation_id="corr-1",
            work_item_id="123",
            project_id="proj-1",
            title="New feature",
            initial_column="Backlog",
        )

        d = event.to_dict()

        assert d["work_item_id"] == "123"
        assert d["title"] == "New feature"
        assert d["initial_column"] == "Backlog"

    def test_work_item_created_roundtrip(self):
        """Test work item created event roundtrip."""
        timestamp = now_iso()
        original = WorkItemCreatedEvent(
            type="workitem.created",
            timestamp=timestamp,
            source="jira",
            work_item_id="456",
            project_id="proj-2",
            title="Critical bug fix",
            initial_column="In Progress",
        )

        d = original.to_dict()
        restored = WorkItemCreatedEvent.from_dict(d)

        assert restored.work_item_id == original.work_item_id
        assert restored.title == original.title
        assert restored.initial_column == original.initial_column


class TestWorkItemUpdatedEvent:
    """Test WorkItemUpdatedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid work item updated event."""
        changes = {
            "labels": ["bug", "critical"],
            "priority": 5,
            "assignee": "alice",
        }

        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            changes=changes,
        )

        assert event.work_item_id == "123"
        assert event.changes["labels"] == ["bug", "critical"]
        assert event.changes["priority"] == 5

    def test_work_item_updated_single_change(self):
        """Test work item updated with single field change."""
        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            changes={"status": "In Progress"},
        )

        assert event.changes == {"status": "In Progress"}

    def test_work_item_updated_no_changes(self):
        """Test work item updated with empty changes dict."""
        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            changes={},
        )

        assert event.changes == {}

    def test_work_item_updated_default_empty_changes(self):
        """Test work item updated defaults to empty changes dict."""
        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
        )

        assert event.changes == {}

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            WorkItemUpdatedEvent(
                type="workitem.updated",
                timestamp=now_iso(),
                source="github",
                work_item_id="",  # Empty
                project_id="proj-1",
                changes={"status": "Done"},
            )

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            WorkItemUpdatedEvent(
                type="workitem.updated",
                timestamp=now_iso(),
                source="github",
                work_item_id="123",
                project_id="",  # Empty
                changes={"status": "Done"},
            )

    def test_work_item_updated_complex_changes(self):
        """Test work item updated with complex changes."""
        changes = {
            "title": "Updated title",
            "description": "New description",
            "labels": ["feature", "enhancement"],
            "priority": 8,
            "custom_field": {"nested": "value"},
        }

        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            changes=changes,
        )

        assert event.changes["custom_field"]["nested"] == "value"

    def test_work_item_updated_serialization(self):
        """Test work item updated event serialization."""
        changes = {
            "labels": ["bug"],
            "priority": 5,
        }

        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            correlation_id="corr-2",
            work_item_id="123",
            project_id="proj-1",
            changes=changes,
        )

        d = event.to_dict()

        assert d["work_item_id"] == "123"
        assert d["changes"]["priority"] == 5

    def test_work_item_updated_roundtrip(self):
        """Test work item updated event roundtrip."""
        timestamp = now_iso()
        changes = {
            "assignee": "bob",
            "status": "Review",
        }

        original = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=timestamp,
            source="jira",
            work_item_id="456",
            project_id="proj-2",
            changes=changes,
        )

        d = original.to_dict()
        restored = WorkItemUpdatedEvent.from_dict(d)

        assert restored.work_item_id == original.work_item_id
        assert restored.changes == original.changes

    def test_work_item_updated_with_null_values(self):
        """Test work item updated with null/None values."""
        changes = {
            "assignee": None,
            "due_date": None,
            "description": "New description",
        }

        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            changes=changes,
        )

        assert event.changes["assignee"] is None
        assert event.changes["due_date"] is None

    def test_uuid_format_preserved_in_roundtrip(self):
        """Test that UUID fields preserve format through serialization."""
        event_id = str(uuid.uuid4())

        event = WorkItemCreatedEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
            correlation_id=event_id,
            work_item_id="123",
            project_id="proj-1",
            title="UUID Test",
        )

        data = event.to_dict()
        restored = WorkItemCreatedEvent.from_dict(data)

        assert restored.correlation_id == event_id
        # Verify it's still a valid UUID
        uuid.UUID(restored.correlation_id)

    def test_optional_field_none_vs_missing_roundtrip(self):
        """Test that None and missing values are distinguished correctly."""
        # Explicit None for initial_column
        event1 = WorkItemCreatedEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            title="Test",
            initial_column=None,
        )

        data1 = event1.to_dict()
        assert "initial_column" in data1
        assert data1["initial_column"] is None

        restored1 = WorkItemCreatedEvent.from_dict(data1)
        assert restored1.initial_column is None

    def test_literal_type_preserved_in_updated_event(self):
        """Test that Literal types are preserved through serialization."""
        changes = {"status": "In Progress"}

        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            changes=changes,
        )

        data = event.to_dict()
        restored = WorkItemUpdatedEvent.from_dict(data)

        assert restored.changes["status"] == "In Progress"
        assert isinstance(restored.changes["status"], str)

    def test_complex_nested_changes_roundtrip(self):
        """Test that complex nested structures preserve types."""
        changes = {
            "metadata": {
                "priority": 5,
                "tags": ["bug", "urgent"],
                "estimates": [8, 13, 21],
                "nested": {"key": "value"},
            }
        }

        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            changes=changes,
        )

        data = event.to_dict()
        restored = WorkItemUpdatedEvent.from_dict(data)

        assert restored.changes["metadata"]["priority"] == 5
        assert restored.changes["metadata"]["tags"] == ["bug", "urgent"]
        assert restored.changes["metadata"]["estimates"] == [8, 13, 21]
        assert restored.changes["metadata"]["nested"]["key"] == "value"


class TestWorkItemCreatedEventImmutability:
    """Test immutability of WorkItemCreatedEvent (frozen dataclass)."""

    def test_work_item_created_event_is_frozen(self):
        """Test that WorkItemCreatedEvent is immutable (frozen dataclass)."""
        event = WorkItemCreatedEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            title="Add user authentication",
            initial_column="Backlog",
        )

        # Verify the event is properly created
        assert event.work_item_id == "123"
        assert event.title == "Add user authentication"
        assert event.initial_column == "Backlog"

        # WorkItemCreatedEvent is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.title = "Different title"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.initial_column = "In Progress"  # type: ignore


class TestWorkItemUpdatedEventImmutability:
    """Test immutability of WorkItemUpdatedEvent (frozen dataclass)."""

    def test_work_item_updated_event_is_frozen(self):
        """Test that WorkItemUpdatedEvent is immutable (frozen dataclass)."""
        changes = {"status": "In Progress", "priority": 5}

        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            changes=changes,
        )

        # Verify the event is properly created
        assert event.work_item_id == "123"
        assert event.changes["status"] == "In Progress"

        # WorkItemUpdatedEvent is a frozen dataclass, so attempting to modify
        # field attributes should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.changes = {"status": "Done"}  # type: ignore

    def test_work_item_updated_event_changes_dict_limitation(self):
        """Test that changes dict is mutable (known limitation).

        KNOWN ISSUE: The 'changes' dict is mutable even in a frozen dataclass
        because the dataclass is frozen by reference, not by value. The dict
        object itself can be mutated though the field reference cannot be changed.

        This is documented as a known limitation. For future enhancement,
        consider using frozendict or converting to tuple of tuples if deep
        immutability is required for the changes mapping.
        """
        changes = {"status": "In Progress"}

        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            changes=changes,
        )

        # The dict field itself cannot be reassigned
        with pytest.raises(FrozenInstanceError):
            event.changes = {}  # type: ignore

        # But the dict contents CAN be mutated (known limitation)
        # This is documented but not prevented
        original_status = event.changes.get("status")
        assert original_status == "In Progress"
        # Verify the changes dict is still intact (no mutations were made)
        assert event.changes == {"status": "In Progress"}

    def test_work_item_updated_changes_dict_structure(self):
        """Test structure of changes dict for proper immutability handling.

        When implementing frozen dataclasses, ensure nested mutable types
        in the changes dict are handled appropriately (consider converting
        to immutable structures or documenting the limitation).
        """
        changes = {
            "labels": ["bug", "critical"],
            "custom": {"nested": "value"},
            "priority": 5,
        }

        event = WorkItemUpdatedEvent(
            type="workitem.updated",
            timestamp=now_iso(),
            source="github",
            work_item_id="123",
            project_id="proj-1",
            changes=changes,
        )

        # Verify complex changes are preserved
        assert isinstance(event.changes["labels"], (list, tuple))
        assert isinstance(event.changes["custom"], (dict, tuple))
        assert event.changes["priority"] == 5
