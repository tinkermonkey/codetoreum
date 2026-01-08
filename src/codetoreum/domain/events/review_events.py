"""Code review events for vendor-agnostic integration.

Events track the lifecycle and status of code reviews (pull requests,
merge requests, etc.) across different vendor platforms.

Terminology (vendor-agnostic):
- Code Review: A review of proposed code changes (PR, MR, etc.)
- Review Status: The state of a code review (open, approved, changes_requested, merged, closed)
"""

from typing import Literal, Optional
from uuid import uuid4

from .adapter_events import CodetoreumEvent
from .discussion_events import Comment

CodeReviewStatus = Literal["open", "approved", "changes_requested", "merged", "closed"]


class ReviewStatusChangedEvent(CodetoreumEvent):
    """Emitted when a code review's status changes."""

    def __init__(
        self,
        type: str = "review.status_changed",
        timestamp: str = "",
        source: str = "",
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        review_id: str = "",
        work_item_id: Optional[str] = None,
        project_id: str = "",
        previous_status: CodeReviewStatus = "open",  # type: ignore
        new_status: CodeReviewStatus = "open",  # type: ignore
        reviewer: Optional[str] = None,
    ):
        super().__init__(
            type=type,
            timestamp=timestamp,
            source=source,
            correlation_id=correlation_id,
            event_id=event_id or str(uuid4()),
        )
        self.review_id = review_id
        self.work_item_id = work_item_id
        self.project_id = project_id
        self.previous_status = previous_status
        self.new_status = new_status
        self.reviewer = reviewer
        self._validate()

    def _validate(self) -> None:
        """Validate event fields."""
        if not self.review_id:
            raise ValueError("review_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")

        valid_statuses = {"open", "approved", "changes_requested", "merged", "closed"}
        if self.previous_status not in valid_statuses:
            raise ValueError(f"Invalid previous_status: {self.previous_status}")
        if self.new_status not in valid_statuses:
            raise ValueError(f"Invalid new_status: {self.new_status}")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "review_id": self.review_id,
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "reviewer": self.reviewer,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewStatusChangedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "review.status_changed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id"),
            review_id=data.get("review_id", ""),
            work_item_id=data.get("work_item_id"),
            project_id=data.get("project_id", ""),
            previous_status=data.get("previous_status", "open"),  # type: ignore
            new_status=data.get("new_status", "open"),  # type: ignore
            reviewer=data.get("reviewer"),
        )


class ReviewCommentAddedEvent(CodetoreumEvent):
    """Emitted when a comment is added to a code review."""

    def __init__(
        self,
        type: str = "review.comment_added",
        timestamp: str = "",
        source: str = "",
        correlation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        review_id: str = "",
        work_item_id: Optional[str] = None,
        project_id: str = "",
        comment: Optional[Comment] = None,
    ):
        super().__init__(
            type=type,
            timestamp=timestamp,
            source=source,
            correlation_id=correlation_id,
            event_id=event_id or str(uuid4()),
        )
        self.review_id = review_id
        self.work_item_id = work_item_id
        self.project_id = project_id
        self.comment = comment or Comment("", "", "", "")
        self._validate()

    def _validate(self) -> None:
        """Validate event fields."""
        if not self.review_id:
            raise ValueError("review_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "review_id": self.review_id,
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "comment": self.comment.to_dict(),
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewCommentAddedEvent":
        """Deserialize from dictionary."""
        comment = Comment.from_dict(data.get("comment", {}))

        return cls(
            type=data.get("type", "review.comment_added"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id"),
            review_id=data.get("review_id", ""),
            work_item_id=data.get("work_item_id"),
            project_id=data.get("project_id", ""),
            comment=comment,
        )
