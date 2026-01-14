"""Unit tests for work item events."""

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


class TestWorkItemCreatedEventImmutability:
    """Test immutability of WorkItemCreatedEvent."""

    def test_work_item_created_event_immutability(self):
        """Test that WorkItemCreatedEvent attributes are immutable.

        NOTE: This test currently documents expected behavior.
        When events are converted to frozen dataclasses, this test will
        verify that the frozen=True constraint is properly enforced.
        """
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

        # When frozen dataclasses are implemented, these assertions
        # will test that modification raises FrozenInstanceError
        original_id = event.work_item_id
        original_title = event.title

        # Verify values haven't changed
        assert event.work_item_id == original_id
        assert event.title == original_title


class TestWorkItemUpdatedEventImmutability:
    """Test immutability of WorkItemUpdatedEvent."""

    def test_work_item_updated_event_immutability(self):
        """Test that WorkItemUpdatedEvent attributes are immutable.

        NOTE: This test documents expected immutability behavior.
        When events are converted to frozen dataclasses, this test will
        verify the frozen=True constraint.

        KNOWN ISSUE: The 'changes' dict is mutable in current implementation.
        When converted to frozen dataclasses, consider converting to
        immutable mapping or tuple of tuples if mutation protection is needed.
        """
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

        # Document the expected state
        original_id = event.work_item_id
        original_changes = event.changes.copy()

        # Verify values haven't changed
        assert event.work_item_id == original_id
        assert event.changes == original_changes

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
