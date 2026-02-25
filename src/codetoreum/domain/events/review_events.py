"""Code review events for vendor-agnostic integration.

Events track the lifecycle and status of code reviews (pull requests,
merge requests, etc.) across different vendor platforms.

Terminology (vendor-agnostic):
- Code Review: A review of proposed code changes (PR, MR, etc.)
- Review Status: The state of a code review (open, approved, changes_requested, merged, closed)
"""

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from .adapter_events import CodetoreumEvent
from .discussion_events import Comment

CodeReviewStatus = Literal["open", "approved", "changes_requested", "merged", "closed"]


@dataclass(frozen=True)
class ReviewStatusChangedEvent(CodetoreumEvent):
    """Emitted when a code review's status changes.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "review.status_changed"
        review_id (str): ID of the code review (e.g., PR ID)
        work_item_id (Optional[str]): ID of associated work item, None if not linked
        project_id (str): ID of the project containing the review
        previous_status (Literal["open", "approved", "changes_requested", "merged", "closed"]): Previous review status
        new_status (Literal["open", "approved", "changes_requested", "merged", "closed"]): New review status
        reviewer (Optional[str]): Username of reviewer who changed status, None if automated

    Example:
        >>> event = ReviewStatusChangedEvent(
        ...     type="review.status_changed",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     review_id="pr-1",
        ...     project_id="proj-1",
        ...     previous_status="open",
        ...     new_status="approved",
        ...     reviewer="reviewer123"
        ... )
        >>> event.new_status = "changes_requested"  # ❌ Raises FrozenInstanceError
    """

    review_id: str = ""
    work_item_id: str | None = None
    project_id: str = ""
    previous_status: CodeReviewStatus = "open"
    new_status: CodeReviewStatus = "open"
    reviewer: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.review_id:
            msg = "review_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)

        valid_statuses = {"open", "approved", "changes_requested", "merged", "closed"}
        if self.previous_status not in valid_statuses:
            msg = f"Invalid previous_status: {self.previous_status}"
            raise ValueError(msg)
        if self.new_status not in valid_statuses:
            msg = f"Invalid new_status: {self.new_status}"
            raise ValueError(msg)

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
            event_id=data.get("event_id") or str(uuid4()),
            review_id=data.get("review_id", ""),
            work_item_id=data.get("work_item_id"),
            project_id=data.get("project_id", ""),
            previous_status=data.get("previous_status", "open"),
            new_status=data.get("new_status", "open"),
            reviewer=data.get("reviewer"),
        )


@dataclass(frozen=True)
class ReviewCommentAddedEvent(CodetoreumEvent):
    """Emitted when a comment is added to a code review.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "review.comment_added"
        review_id (str): ID of the code review (e.g., PR ID)
        work_item_id (Optional[str]): ID of associated work item, None if not linked
        project_id (str): ID of the project containing the review
        comment (Optional[Comment]): The comment object added to the review, None if not available

    Example:
        >>> event = ReviewCommentAddedEvent(
        ...     type="review.comment_added",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="github",
        ...     review_id="pr-1",
        ...     project_id="proj-1"
        ... )
        >>> event.review_id = "pr-2"  # ❌ Raises FrozenInstanceError
    """

    review_id: str = ""
    work_item_id: str | None = None
    project_id: str = ""
    comment: Comment | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.review_id:
            msg = "review_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        # Note: comment is optional and can be None
        # Do not auto-initialize it as this prevents tests from checking None handling

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "review_id": self.review_id,
            "work_item_id": self.work_item_id,
            "project_id": self.project_id,
            "comment": self.comment.to_dict() if self.comment else None,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewCommentAddedEvent":
        """Deserialize from dictionary."""
        comment = Comment.from_dict(data.get("comment", {})) if data.get("comment") else None

        return cls(
            type=data.get("type", "review.comment_added"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_id=data.get("review_id", ""),
            work_item_id=data.get("work_item_id"),
            project_id=data.get("project_id", ""),
            comment=comment,
        )
