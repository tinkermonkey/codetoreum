"""Unit tests for InMemoryTicketAdapter."""

import pytest
from datetime import datetime, timezone

from codetoreum.adapters.testing import InMemoryTicketAdapter
from codetoreum.domain.types import ProjectId, UserId, WorkItemId
from codetoreum.domain.work_item import WorkItemPriority, WorkItemStatus
from codetoreum.ports.exceptions import ResourceNotFoundError, ValidationError


@pytest.mark.asyncio
class TestInMemoryTicketAdapter:
    """Tests for InMemoryTicketAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return InMemoryTicketAdapter()

    async def test_create_work_item(self, adapter):
        """Test creating a work item."""
        work_item = await adapter.create_work_item(
            title="Test Issue",
            description="Test description",
            project_id=ProjectId("project-1"),
            labels=["bug", "high-priority"],
            priority=WorkItemPriority.HIGH,
        )

        assert work_item.title == "Test Issue"
        assert work_item.description == "Test description"
        assert work_item.status == WorkItemStatus.NEW
        assert work_item.priority == WorkItemPriority.HIGH
        assert "bug" in work_item.labels
        assert work_item.external_id == "#1"

    async def test_create_work_item_empty_title(self, adapter):
        """Test creating work item with empty title raises error."""
        with pytest.raises(ValidationError):
            await adapter.create_work_item(
                title="",
                description="Test",
                project_id=ProjectId("project-1"),
            )

    async def test_get_work_item(self, adapter):
        """Test retrieving a work item."""
        created = await adapter.create_work_item(
            title="Test",
            description="Desc",
            project_id=ProjectId("project-1"),
        )

        retrieved = await adapter.get_work_item(WorkItemId(created.id))
        assert retrieved.id == created.id
        assert retrieved.title == "Test"

    async def test_get_nonexistent_work_item(self, adapter):
        """Test getting nonexistent work item raises error."""
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.get_work_item(WorkItemId("nonexistent"))

        assert exc_info.value.resource_type == "WorkItem"

    async def test_update_work_item(self, adapter):
        """Test updating a work item."""
        work_item = await adapter.create_work_item(
            title="Original",
            description="Original desc",
            project_id=ProjectId("project-1"),
        )

        updated = await adapter.update_work_item(
            WorkItemId(work_item.id),
            {"title": "Updated", "labels": ["new-label"]},
        )

        assert updated.title == "Updated"
        assert "new-label" in updated.labels

    async def test_delete_work_item(self, adapter):
        """Test deleting a work item."""
        work_item = await adapter.create_work_item(
            title="Test",
            description="Desc",
            project_id=ProjectId("project-1"),
        )

        await adapter.delete_work_item(WorkItemId(work_item.id))

        with pytest.raises(ResourceNotFoundError):
            await adapter.get_work_item(WorkItemId(work_item.id))

    async def test_list_work_items(self, adapter):
        """Test listing work items with filters."""
        # Create multiple work items
        await adapter.create_work_item(
            title="Item 1",
            description="Desc",
            project_id=ProjectId("project-1"),
            labels=["bug"],
        )
        await adapter.create_work_item(
            title="Item 2",
            description="Desc",
            project_id=ProjectId("project-2"),
            labels=["feature"],
        )

        # List all
        all_items = await adapter.list_work_items()
        assert len(all_items) == 2

        # Filter by project
        project_items = await adapter.list_work_items(project_id=ProjectId("project-1"))
        assert len(project_items) == 1
        assert project_items[0].title == "Item 1"

        # Filter by labels
        bug_items = await adapter.list_work_items(labels=["bug"])
        assert len(bug_items) == 1

    async def test_search_work_items(self, adapter):
        """Test searching work items."""
        await adapter.create_work_item(
            title="Fix authentication bug",
            description="Users cannot log in",
            project_id=ProjectId("project-1"),
        )
        await adapter.create_work_item(
            title="Add new feature",
            description="Implement dashboard",
            project_id=ProjectId("project-1"),
        )

        # Search by title
        results = await adapter.search_work_items("authentication")
        assert len(results) == 1
        assert "authentication" in results[0].title.lower()

        # Search by description
        results = await adapter.search_work_items("dashboard")
        assert len(results) == 1

    async def test_add_comment(self, adapter):
        """Test adding comments to work item."""
        work_item = await adapter.create_work_item(
            title="Test",
            description="Desc",
            project_id=ProjectId("project-1"),
        )

        comment = await adapter.add_comment(
            WorkItemId(work_item.id),
            "This is a comment",
            author=UserId("user-1"),
        )

        assert comment.body == "This is a comment"
        assert comment.work_item_id == WorkItemId(work_item.id)

    async def test_add_empty_comment(self, adapter):
        """Test adding empty comment raises error."""
        work_item = await adapter.create_work_item(
            title="Test",
            description="Desc",
            project_id=ProjectId("project-1"),
        )

        with pytest.raises(ValidationError):
            await adapter.add_comment(
                WorkItemId(work_item.id),
                "",
            )

    async def test_get_comments(self, adapter):
        """Test retrieving comments."""
        work_item = await adapter.create_work_item(
            title="Test",
            description="Desc",
            project_id=ProjectId("project-1"),
        )

        await adapter.add_comment(WorkItemId(work_item.id), "Comment 1")
        await adapter.add_comment(WorkItemId(work_item.id), "Comment 2")

        comments = await adapter.get_comments(WorkItemId(work_item.id))
        assert len(comments) == 2

    async def test_link_work_items(self, adapter):
        """Test linking work items."""
        item1 = await adapter.create_work_item(
            title="Item 1",
            description="Desc",
            project_id=ProjectId("project-1"),
        )
        item2 = await adapter.create_work_item(
            title="Item 2",
            description="Desc",
            project_id=ProjectId("project-1"),
        )

        await adapter.link_work_items(
            WorkItemId(item1.id),
            WorkItemId(item2.id),
            "blocks",
        )

        related = await adapter.get_related_items(WorkItemId(item1.id))
        assert len(related) == 1
        assert related[0].id == item2.id

    async def test_register_webhook(self, adapter):
        """Test registering webhooks."""
        webhook_id = await adapter.register_webhook(
            "https://example.com/webhook",
            ["work_item.created", "work_item.updated"],
            project_id=ProjectId("project-1"),
        )

        assert webhook_id is not None
        assert adapter.get_webhook_count() == 1

    async def test_register_invalid_webhook(self, adapter):
        """Test registering webhook with invalid URL raises error."""
        with pytest.raises(ValidationError):
            await adapter.register_webhook(
                "not-a-url",
                ["work_item.created"],
            )

    async def test_unregister_webhook(self, adapter):
        """Test unregistering webhooks."""
        webhook_id = await adapter.register_webhook(
            "https://example.com/webhook",
            ["work_item.created"],
        )

        await adapter.unregister_webhook(webhook_id)
        assert adapter.get_webhook_count() == 0

    async def test_clear(self, adapter):
        """Test clearing all data."""
        await adapter.create_work_item(
            title="Test",
            description="Desc",
            project_id=ProjectId("project-1"),
        )

        adapter.clear()

        all_items = await adapter.list_work_items()
        assert len(all_items) == 0
