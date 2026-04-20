"""Unit tests for WorkItem PR and discussion field extensions.

Tests cover:
- Adding pr_id and discussion_id fields to WorkItem
- Fields default to None
- No AttributeError when accessing fields
- Fields are preserved through create() factory
- Fields are preserved through from_events() reconstruction
"""

import pytest

from codetoreum.domain.work_item import WorkItem, WorkItemPriority


class TestWorkItemPRAndDiscussionFields:
    """Tests for PR and discussion fields on WorkItem."""

    def test_create_without_pr_or_discussion(self):
        """Test creating work item without PR or discussion."""
        item = WorkItem.create(
            title="Task 1",
            description="Do something",
            project_id="proj-123",
        )
        assert item.pr_id is None
        assert item.discussion_id is None

    def test_create_with_pr_id(self):
        """Test creating work item with PR ID."""
        item = WorkItem.create(
            title="Task 1",
            description="Do something",
            project_id="proj-123",
            pr_id="pr-456",
        )
        assert item.pr_id == "pr-456"
        assert item.discussion_id is None

    def test_create_with_discussion_id(self):
        """Test creating work item with discussion ID."""
        item = WorkItem.create(
            title="Task 1",
            description="Do something",
            project_id="proj-123",
            discussion_id="disc-789",
        )
        assert item.pr_id is None
        assert item.discussion_id == "disc-789"

    def test_create_with_both_ids(self):
        """Test creating work item with both PR and discussion IDs."""
        item = WorkItem.create(
            title="Task 1",
            description="Do something",
            project_id="proj-123",
            pr_id="pr-456",
            discussion_id="disc-789",
        )
        assert item.pr_id == "pr-456"
        assert item.discussion_id == "disc-789"

    def test_fields_accessible_without_attribute_error(self):
        """Test accessing fields never raises AttributeError."""
        item = WorkItem.create(
            title="Task 1",
            description="Do something",
            project_id="proj-123",
        )
        # Should not raise AttributeError
        pr_id = item.pr_id
        discussion_id = item.discussion_id
        assert pr_id is None
        assert discussion_id is None

    def test_fields_preserved_in_from_events(self):
        """Test fields are preserved through event reconstruction."""
        original = WorkItem.create(
            title="Task 1",
            description="Do something",
            project_id="proj-123",
            pr_id="pr-456",
            discussion_id="disc-789",
        )
        reconstructed = WorkItem.from_events(original.get_pending_events())

        # Since from_events reconstructs from the creation event, the fields should be set
        # from the event payload
        assert reconstructed.pr_id == "pr-456"
        assert reconstructed.discussion_id == "disc-789"

    def test_create_all_parameters(self):
        """Test creating with all parameters including PR/discussion."""
        item = WorkItem.create(
            title="Task 1",
            description="Do something",
            project_id="proj-123",
            labels=["bug", "urgent"],
            priority=WorkItemPriority.HIGH,
            external_id="ext-123",
            external_url="https://example.com/123",
            pr_id="pr-456",
            discussion_id="disc-789",
        )
        assert item.pr_id == "pr-456"
        assert item.discussion_id == "disc-789"
        assert item.external_id == "ext-123"
        assert item.priority == WorkItemPriority.HIGH
