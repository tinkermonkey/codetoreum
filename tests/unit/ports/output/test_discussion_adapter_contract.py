"""Contract tests for IDiscussionAdapter interface."""

from abc import ABC, abstractmethod

import pytest

from codetoreum.domain.events import Comment
from codetoreum.ports.exceptions import ResourceNotFoundError, ValidationError
from codetoreum.ports.output.discussion_adapter import (
    DiscussionMonitoringConfig,
    IDiscussionAdapter,
)


class TestDiscussionAdapterContract(ABC):
    """Abstract contract tests for IDiscussionAdapter implementations.

    Subclasses must implement create_adapter() to provide a concrete
    IDiscussionAdapter implementation to test.
    """

    @abstractmethod
    async def create_adapter(self) -> IDiscussionAdapter:
        """Create and return an IDiscussionAdapter instance for testing."""
        pass

    @pytest.mark.asyncio
    async def test_add_comment_returns_comment_with_id(self):
        """Adding comment should return comment with server-assigned ID."""
        adapter = await self.create_adapter()

        comment = await adapter.add_comment(
            work_item_id="issue-123",
            content="This is a test comment",
        )

        assert isinstance(comment, Comment)
        assert comment.id  # Should have ID assigned
        assert comment.body == "This is a test comment"
        assert comment.created_at  # Should have timestamp

    @pytest.mark.asyncio
    async def test_add_comment_with_parent_id(self):
        """Adding comment with parent_id should create reply."""
        adapter = await self.create_adapter()

        # Add initial comment
        comment1 = await adapter.add_comment(
            work_item_id="issue-123",
            content="Initial comment",
        )

        # Add reply
        comment2 = await adapter.add_comment(
            work_item_id="issue-123",
            content="Reply comment",
            parent_id=comment1.id,
        )

        assert comment2.parent_id == comment1.id

    @pytest.mark.asyncio
    async def test_get_thread_returns_all_comments(self):
        """Get thread should return all comments on work item."""
        adapter = await self.create_adapter()

        # Add comments
        await adapter.add_comment("issue-123", "Comment 1")
        await adapter.add_comment("issue-123", "Comment 2")

        thread = await adapter.get_thread("issue-123")

        assert thread.work_item_id == "issue-123"
        assert len(thread.comments) >= 2

    @pytest.mark.asyncio
    async def test_start_monitoring_enables_detection(self):
        """Starting monitoring should prepare for change detection."""
        adapter = await self.create_adapter()
        config = DiscussionMonitoringConfig(
            project_id="proj-123",
        )

        # Should not raise
        adapter.start_monitoring("issue-123", config)

    @pytest.mark.asyncio
    async def test_stop_monitoring_disables_detection(self):
        """Stopping monitoring should disable change detection."""
        adapter = await self.create_adapter()
        config = DiscussionMonitoringConfig(
            project_id="proj-123",
        )

        adapter.start_monitoring("issue-123", config)
        # Should not raise
        adapter.stop_monitoring("issue-123")

    @pytest.mark.asyncio
    async def test_add_comment_empty_content_raises_error(self):
        """Adding empty comment should raise ValidationError."""
        adapter = await self.create_adapter()

        with pytest.raises(ValidationError):
            await adapter.add_comment(
                work_item_id="issue-123",
                content="",  # Empty content
            )

    @pytest.mark.asyncio
    async def test_get_thread_nonexistent_work_item(self):
        """Getting thread for nonexistent item should raise ResourceNotFoundError."""
        adapter = await self.create_adapter()

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.get_thread("nonexistent-issue")
        assert exc_info.value.resource_type == "work_item"
        assert exc_info.value.resource_id == "nonexistent-issue"

    @pytest.mark.asyncio
    async def test_monitoring_config_with_last_processed_comment(self):
        """Monitoring config can specify last processed comment."""
        adapter = await self.create_adapter()
        config = DiscussionMonitoringConfig(
            project_id="proj-123",
            last_processed_comment_id="comment-789",
        )

        adapter.start_monitoring("issue-123", config)
        adapter.stop_monitoring("issue-123")

    @pytest.mark.asyncio
    async def test_multiple_work_items_independent(self):
        """Comments on different work items should be independent."""
        adapter = await self.create_adapter()

        # Add to item 1
        comment1 = await adapter.add_comment("issue-1", "Comment on issue 1")

        # Add to item 2
        comment2 = await adapter.add_comment("issue-2", "Comment on issue 2")

        # Verify separate
        thread1 = await adapter.get_thread("issue-1")
        thread2 = await adapter.get_thread("issue-2")

        assert comment1 in thread1.comments
        assert comment2 in thread2.comments
        assert comment1 not in thread2.comments
        assert comment2 not in thread1.comments
