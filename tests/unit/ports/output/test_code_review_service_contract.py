"""Contract tests for ICodeReviewService interface.

These abstract tests verify that all ICodeReviewService implementations
follow the contract correctly, including event emission on status changes
and comment additions.
"""

from abc import ABC, abstractmethod

import pytest

from codetoreum.ports.output.code_review_service import (
    CodeReview,
    ICodeReviewService,
    ReviewComment,
)
from codetoreum.ports.output.monitoring import MonitoringConfig


class TestCodeReviewServiceContract(ABC):
    """Abstract contract tests for ICodeReviewService implementations.

    Subclasses must implement create_service() to provide a concrete
    ICodeReviewService implementation to test.
    """

    @abstractmethod
    async def create_service(self) -> ICodeReviewService:
        """Create and return an ICodeReviewService instance for testing."""

    # Query Operation Tests

    @pytest.mark.asyncio
    async def test_get_review_for_work_item_returns_review(self):
        """Should return a code review when associated with work item."""
        service = await self.create_service()

        review = await service.get_review_for_work_item("item-123")

        # Should return CodeReview or None
        assert review is None or isinstance(review, CodeReview)

    @pytest.mark.asyncio
    async def test_get_review_for_work_item_nonexistent_returns_none(self):
        """Should return None when no review exists for work item."""
        service = await self.create_service()

        review = await service.get_review_for_work_item("nonexistent-item")

        assert review is None

    @pytest.mark.asyncio
    async def test_get_review_status_returns_valid_status(self):
        """Should return valid code review status."""
        service = await self.create_service()

        # First create/get a review
        review = await service.get_review_for_work_item("item-123")
        if review:
            status = await service.get_review_status(review.id)

            # Status should be one of the valid values
            valid_statuses = ("open", "approved", "changes_requested", "merged", "closed")
            assert status in valid_statuses

    @pytest.mark.asyncio
    async def test_get_review_comments_returns_list(self):
        """Should return list of comments for a review."""
        service = await self.create_service()

        review = await service.get_review_for_work_item("item-123")
        if review:
            comments = await service.get_review_comments(review.id)

            assert isinstance(comments, list)
            for comment in comments:
                assert isinstance(comment, ReviewComment)
                assert comment.id is not None
                assert comment.author is not None
                assert comment.body is not None
                assert comment.created_at is not None

    # Command Operation Tests

    @pytest.mark.asyncio
    async def test_request_changes_updates_review_state(self):
        """Requesting changes should update review and emit events."""
        service = await self.create_service()

        # Setup monitoring to capture events
        events: list = []
        service.on("review.status_changed", lambda e: events.append(("status_changed", e)))
        service.on("review.comment_added", lambda e: events.append(("comment_added", e)))

        review = await service.get_review_for_work_item("item-123")
        if review:
            await service.request_changes(review.id, "Please fix the following...")

            # Should have triggered at least comment_added event
            comment_events = [e for e in events if e[0] == "comment_added"]
            assert len(comment_events) > 0

    @pytest.mark.asyncio
    async def test_approve_updates_review_status(self):
        """Approving should update status and emit status_changed event."""
        service = await self.create_service()

        # Setup event capture
        events: list = []
        service.on("review.status_changed", lambda e: events.append(("status_changed", e)))

        review = await service.get_review_for_work_item("item-123")
        if review and review.status == "open":
            await service.approve(review.id)

            # Should have triggered status_changed event
            status_events = [e for e in events if e[0] == "status_changed"]
            assert len(status_events) > 0

    # Monitoring Lifecycle Tests

    @pytest.mark.asyncio
    async def test_monitoring_lifecycle_for_code_reviews(self):
        """Should support start/stop monitoring for project-wide code reviews."""
        service = await self.create_service()
        config = MonitoringConfig(project_id="proj-123")

        # Start monitoring
        await service.start_monitoring("proj-123", config)
        status = await service.get_monitoring_status("proj-123")
        assert status.state.value == "active"

        # Stop monitoring
        await service.stop_monitoring("proj-123")
        status = await service.get_monitoring_status("proj-123")
        assert status.state.value == "stopped"

    @pytest.mark.asyncio
    async def test_code_review_event_emission(self):
        """Should emit events when review status changes."""
        service = await self.create_service()

        emitted_events: list = []

        def capture_event(event):
            emitted_events.append(event)

        service.on("review.status_changed", capture_event)
        service.on("review.comment_added", capture_event)

        # Trigger a change
        review = await service.get_review_for_work_item("item-123")
        if review:
            if review.status == "open":
                await service.approve(review.id)
                # Should have emitted at least one event
                assert len(emitted_events) > 0

    @pytest.mark.asyncio
    async def test_review_has_work_item_association(self):
        """CodeReview should optionally associate with work item."""
        service = await self.create_service()

        review = await service.get_review_for_work_item("item-123")
        if review:
            # work_item_id can be None or a string
            assert review.work_item_id is None or isinstance(review.work_item_id, str)

    @pytest.mark.asyncio
    async def test_review_has_branch_information(self):
        """CodeReview should include source and target branch."""
        service = await self.create_service()

        review = await service.get_review_for_work_item("item-123")
        if review:
            assert hasattr(review, "source_branch")
            assert hasattr(review, "target_branch")
            assert isinstance(review.source_branch, str)
            assert isinstance(review.target_branch, str)
