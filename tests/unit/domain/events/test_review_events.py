"""Unit tests for code review events."""

from typing import cast

import pytest

from codetoreum.domain.events import (
    Comment,
    ReviewCommentAddedEvent,
    ReviewStatusChangedEvent,
    now_iso,
)
from codetoreum.domain.events.review_events import CodeReviewStatus

# For immutability tests (when events become frozen dataclasses)
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    # Fallback for older Python versions or non-frozen dataclasses
    FrozenInstanceError = AttributeError  # type: ignore


class TestReviewStatusChangedEvent:
    """Test ReviewStatusChangedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid review status changed event."""
        event = ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp=now_iso(),
            source="github",
            review_cycle_id="pr-123",
            project_id="proj-1",
            previous_status="open",
            new_status="approved",
            reviewer="alice",
        )

        assert event.review_id == "pr-123"
        assert event.previous_status == "open"
        assert event.new_status == "approved"
        assert event.reviewer == "alice"

    def test_review_status_to_merged(self):
        """Test review status changing to merged."""
        event = ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp=now_iso(),
            source="github",
            review_cycle_id="pr-123",
            project_id="proj-1",
            previous_status="approved",
            new_status="merged",
            reviewer="alice",
        )

        assert event.new_status == "merged"

    def test_review_status_changes_requested(self):
        """Test review status changing to changes requested."""
        event = ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp=now_iso(),
            source="github",
            review_cycle_id="pr-123",
            project_id="proj-1",
            previous_status="open",
            new_status="changes_requested",
            reviewer="alice",
        )

        assert event.new_status == "changes_requested"

    def test_review_without_reviewer(self):
        """Test review status change without reviewer."""
        event = ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp=now_iso(),
            source="github",
            review_cycle_id="pr-123",
            project_id="proj-1",
            previous_status="open",
            new_status="closed",
        )

        assert event.reviewer is None

    def test_review_with_work_item_id(self):
        """Test review status change with work item reference."""
        event = ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp=now_iso(),
            source="github",
            review_cycle_id="pr-123",
            work_item_id="issue-456",
            project_id="proj-1",
            previous_status="open",
            new_status="approved",
        )

        assert event.work_item_id == "issue-456"

    def test_invalid_previous_status(self):
        """Test that previous_status must be valid."""
        with pytest.raises(ValueError, match="Invalid previous_status"):
            ReviewStatusChangedEvent(
                type="review.status_changed",
                timestamp=now_iso(),
                source="github",
                review_cycle_id="pr-123",
                project_id="proj-1",
                previous_status=cast("CodeReviewStatus", "invalid"),  # Invalid status
                new_status="approved",
            )

    def test_invalid_new_status(self):
        """Test that new_status must be valid."""
        with pytest.raises(ValueError, match="Invalid new_status"):
            ReviewStatusChangedEvent(
                type="review.status_changed",
                timestamp=now_iso(),
                source="github",
                review_cycle_id="pr-123",
                project_id="proj-1",
                previous_status="open",
                new_status=cast("CodeReviewStatus", "pending"),  # Invalid status - testing validation
            )

    def test_missing_review_id(self):
        """Test that review_id is required."""
        with pytest.raises(ValueError, match="review_id"):
            ReviewStatusChangedEvent(
                type="review.status_changed",
                timestamp=now_iso(),
                source="github",
                review_cycle_id="",  # Empty
                project_id="proj-1",
                previous_status="open",
                new_status="approved",
            )

    def test_review_status_serialization(self):
        """Test review status changed event serialization."""
        event = ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp=now_iso(),
            source="github",
            correlation_id="corr-1",
            review_cycle_id="pr-123",
            work_item_id="issue-456",
            project_id="proj-1",
            previous_status="open",
            new_status="approved",
            reviewer="alice",
        )

        d = event.to_dict()

        assert d["review_id"] == "pr-123"
        assert d["previous_status"] == "open"
        assert d["new_status"] == "approved"
        assert d["reviewer"] == "alice"

    def test_review_status_roundtrip(self):
        """Test review status changed event roundtrip."""
        timestamp = now_iso()
        original = ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp=timestamp,
            source="jira",
            review_cycle_id="mr-789",
            project_id="proj-2",
            previous_status="open",
            new_status="merged",
            reviewer="bob",
        )

        d = original.to_dict()
        restored = ReviewStatusChangedEvent.from_dict(d)

        assert restored.review_id == original.review_id
        assert restored.previous_status == original.previous_status
        assert restored.new_status == original.new_status


class TestReviewCommentAddedEvent:
    """Test ReviewCommentAddedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid review comment added event."""
        comment = Comment(
            id="rc-1",
            author="alice",
            body="Line 42: This could be optimized",
            created_at=now_iso(),
        )

        event = ReviewCommentAddedEvent(
            type="review.comment_added",
            timestamp=now_iso(),
            source="github",
            review_cycle_id="pr-123",
            project_id="proj-1",
            comment=comment,
        )

        assert event.review_id == "pr-123"
        event_comment = event.comment
        assert event_comment is not None
        assert event_comment.author == "alice"

    def test_review_comment_with_work_item(self):
        """Test review comment with work item reference."""
        comment = Comment(
            id="rc-1",
            author="alice",
            body="Good changes",
            created_at=now_iso(),
        )

        event = ReviewCommentAddedEvent(
            type="review.comment_added",
            timestamp=now_iso(),
            source="github",
            review_cycle_id="pr-123",
            work_item_id="issue-456",
            project_id="proj-1",
            comment=comment,
        )

        assert event.work_item_id == "issue-456"

    def test_missing_review_id(self):
        """Test that review_id is required."""
        comment = Comment(
            id="rc-1",
            author="alice",
            body="test",
            created_at=now_iso(),
        )

        with pytest.raises(ValueError, match="review_id"):
            ReviewCommentAddedEvent(
                type="review.comment_added",
                timestamp=now_iso(),
                source="github",
                review_cycle_id="",  # Empty
                project_id="proj-1",
                comment=comment,
            )

    def test_review_comment_serialization(self):
        """Test review comment added event serialization."""
        timestamp = now_iso()
        comment = Comment(
            id="rc-1",
            author="alice",
            body="Looks good",
            created_at=timestamp,
        )

        event = ReviewCommentAddedEvent(
            type="review.comment_added",
            timestamp=timestamp,
            source="github",
            correlation_id="corr-2",
            review_cycle_id="pr-123",
            project_id="proj-1",
            comment=comment,
        )

        d = event.to_dict()

        assert d["review_id"] == "pr-123"
        comment_dict = d["comment"]
        assert comment_dict is not None
        assert comment_dict["author"] == "alice"
        assert comment_dict["body"] == "Looks good"

    def test_review_comment_roundtrip(self):
        """Test review comment added event roundtrip."""
        timestamp = now_iso()
        comment = Comment(
            id="rc-1",
            author="bob",
            body="Needs testing",
            created_at=timestamp,
        )

        original = ReviewCommentAddedEvent(
            type="review.comment_added",
            timestamp=timestamp,
            source="jira",
            review_cycle_id="mr-789",
            work_item_id="epic-1",
            project_id="proj-2",
            comment=comment,
        )

        d = original.to_dict()
        restored = ReviewCommentAddedEvent.from_dict(d)

        assert restored.review_id == original.review_id
        restored_comment = restored.comment
        original_comment = original.comment
        assert restored_comment is not None
        assert original_comment is not None
        assert restored_comment.author == original_comment.author
        assert restored.work_item_id == original.work_item_id


class TestReviewStatusChangedEventImmutability:
    """Test immutability of ReviewStatusChangedEvent (frozen dataclass)."""

    def test_review_status_changed_event_is_frozen(self):
        """Test that ReviewStatusChangedEvent is immutable (frozen dataclass)."""
        event = ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp=now_iso(),
            source="github",
            review_cycle_id="pr-123",
            project_id="proj-1",
            previous_status="open",
            new_status="approved",
            reviewer="alice",
        )

        # Verify the event is properly created
        assert event.review_id == "pr-123"
        assert event.previous_status == "open"
        assert event.new_status == "approved"

        # ReviewStatusChangedEvent is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.review_id = "pr-456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.previous_status = "closed"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.new_status = "rejected"  # type: ignore


class TestReviewCommentAddedEventImmutability:
    """Test immutability of ReviewCommentAddedEvent (frozen dataclass)."""

    def test_review_comment_added_event_is_frozen(self):
        """Test that ReviewCommentAddedEvent is immutable (frozen dataclass)."""
        comment = Comment(
            id="rc-1",
            author="alice",
            body="Line 42: This could be optimized",
            created_at=now_iso(),
        )

        event = ReviewCommentAddedEvent(
            type="review.comment_added",
            timestamp=now_iso(),
            source="github",
            review_cycle_id="pr-123",
            project_id="proj-1",
            comment=comment,
        )

        # Verify the event is properly created
        assert event.review_id == "pr-123"
        event_comment = event.comment
        assert event_comment is not None
        assert event_comment.author == "alice"

        # ReviewCommentAddedEvent is a frozen dataclass, so attempting to modify
        # any attribute should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.review_id = "pr-456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.comment = Comment("rc-2", "bob", "Different comment", now_iso())  # type: ignore

    def test_review_comment_added_nested_comment_immutability(self):
        """Test that nested Comment object in ReviewCommentAddedEvent is immutable."""
        comment = Comment(
            id="rc-1",
            author="alice",
            body="Great work!",
            created_at=now_iso(),
            is_bot=False,
        )

        event = ReviewCommentAddedEvent(
            type="review.comment_added",
            timestamp=now_iso(),
            source="github",
            review_cycle_id="pr-123",
            project_id="proj-1",
            comment=comment,
        )

        # Verify comment attributes are preserved
        event_comment = event.comment
        assert event_comment is not None
        assert event_comment.id == "rc-1"
        assert event_comment.body == "Great work!"
        assert event_comment.is_bot is False

        # Comment is a frozen dataclass, so attempting to modify
        # its attributes should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event_comment.author = "bob"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event_comment.body = "Different feedback"  # type: ignore
