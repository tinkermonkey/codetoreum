"""Code review service port interface with event emission.

This interface defines contracts for code review management, including querying
review status, reading comments, and updating review state (approve/request changes).

Code reviews are vendor-agnostic abstractions over GitHub pull requests, GitLab
merge requests, Bitbucket PRs, etc. They represent proposed code changes that
flow through a review process before merging.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from .event_emitter import IEventEmitter
from .monitoring import IMonitoredService

CodeReviewStatus = Literal["open", "approved", "changes_requested", "merged", "closed"]


@dataclass(frozen=True)
class Approval:
    """Represents an approval from a reviewer.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        reviewer: User who approved
        approved_at: ISO 8601 timestamp of approval
    """

    reviewer: str
    approved_at: str

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.reviewer, str) or not self.reviewer:
            msg = "reviewer must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.approved_at, str) or not self.approved_at:
            msg = "approved_at must be a non-empty string"
            raise ValueError(msg)


@dataclass(frozen=True)
class CodeReview:
    """Represents a code review (PR/MR).

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Reviewers and approvals
    are converted to tuples for true immutability.

    Attributes:
        id: Unique identifier for the review
        work_item_id: Associated work item ID (if known), otherwise None
        title: Review title (branch name or PR title)
        source_branch: Branch with proposed changes
        target_branch: Branch changes will merge into
        status: Current review status (open, approved, changes_requested, etc.)
        reviewers: Tuple of user IDs assigned to review
        approvals: Tuple of approvals received
    """

    id: str
    title: str
    source_branch: str
    target_branch: str
    status: CodeReviewStatus
    reviewers: tuple[str, ...]
    approvals: tuple[Approval, ...]
    work_item_id: str | None = None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        # Coerce list to tuple for reviewers
        if isinstance(self.reviewers, list):
            object.__setattr__(self, 'reviewers', tuple(self.reviewers))

        # Coerce list to tuple for approvals
        if isinstance(self.approvals, list):
            object.__setattr__(self, 'approvals', tuple(self.approvals))

        if not isinstance(self.id, str) or not self.id:
            msg = "id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.title, str) or not self.title:
            msg = "title must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.source_branch, str) or not self.source_branch:
            msg = "source_branch must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.target_branch, str) or not self.target_branch:
            msg = "target_branch must be a non-empty string"
            raise ValueError(msg)

        if self.status not in ("open", "approved", "changes_requested", "merged", "closed"):
            msg = f"status must be one of: open, approved, changes_requested, merged, closed. Got: {self.status}"
            raise ValueError(msg)

        if not isinstance(self.reviewers, tuple):
            msg = "reviewers must be a list or tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(r, str) and r for r in self.reviewers):
            msg = "all reviewers must be non-empty strings"
            raise ValueError(msg)

        if not isinstance(self.approvals, tuple):
            msg = "approvals must be a list or tuple of Approval instances"
            raise ValueError(msg)

        if not all(isinstance(a, Approval) for a in self.approvals):
            msg = "all approvals must be Approval instances"
            raise ValueError(msg)

        if self.work_item_id is not None:
            if not isinstance(self.work_item_id, str) or not self.work_item_id:
                msg = "work_item_id must be a non-empty string or None"
                raise ValueError(msg)


@dataclass(frozen=True)
class ReviewComment:
    """Represents a comment on a code review.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        id: Unique identifier for the comment
        author: User who posted the comment
        body: Comment text (may include code review feedback)
        created_at: ISO 8601 timestamp
        file_path: Optional source file the comment references
        line_number: Optional line number in the file (0-indexed)
    """

    id: str
    author: str
    body: str
    created_at: str
    file_path: str | None = None
    line_number: int | None = None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.id, str) or not self.id:
            msg = "id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.author, str) or not self.author:
            msg = "author must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.body, str) or not self.body:
            msg = "body must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.created_at, str) or not self.created_at:
            msg = "created_at must be a non-empty string"
            raise ValueError(msg)

        if self.file_path is not None:
            if not isinstance(self.file_path, str) or not self.file_path:
                msg = "file_path must be a non-empty string or None"
                raise ValueError(msg)

        if self.line_number is not None:
            # Explicitly reject bool (subclass of int)
            if isinstance(self.line_number, bool):
                msg = "line_number must be an integer, got bool"
                raise ValueError(msg)

            if not isinstance(self.line_number, int) or self.line_number < 0:
                msg = "line_number must be a non-negative integer or None"
                raise ValueError(msg)


class ICodeReviewService(IEventEmitter, IMonitoredService, ABC):
    """Code review management with event emission and project-wide monitoring.

    Provides vendor-agnostic abstraction for code reviews (GitHub PRs, GitLab MRs,
    Bitbucket PRs, etc.). Enables:
    1. Querying code review status and associated work items
    2. Reading review comments and feedback
    3. Approving reviews or requesting changes
    4. Monitoring project for review status changes

    Events emitted:
        - 'review.status_changed' → ReviewStatusChangedEvent
                                   When review status changes (open→approved, etc.)
        - 'review.comment_added' → ReviewCommentAddedEvent
                                  When comments are posted on the review

    Example:
        async with service as svc:
            # Start monitoring for PR status changes
            await svc.start_monitoring(
                project_id="proj-123",
                config=MonitoringConfig(project_id="proj-123")
            )

            # Subscribe to review events
            svc.on("review.status_changed", handle_status_change)

            # Query review for a work item
            review = await svc.get_review_for_work_item("item-456")
            if review:
                status = await svc.get_review_status(review.id)
                comments = await svc.get_review_comments(review.id)

                # Request changes or approve
                if needs_changes:
                    await svc.request_changes(review.id, "Please fix X")
                else:
                    await svc.approve(review.id)

            # Stop monitoring
            await svc.stop_monitoring("proj-123")
    """

    # Query Operations

    @abstractmethod
    async def get_review_for_work_item(self, work_item_id: str) -> CodeReview | None:
        """Find code review associated with a work item.

        Returns the code review (PR/MR) linked to this work item,
        or None if no review exists yet.

        Args:
            work_item_id: Work item to find review for

        Returns:
            CodeReview if associated review exists, None otherwise

        Raises:
            ResourceNotFoundError: Work item doesn't exist
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    async def get_review_status(self, review_id: str) -> CodeReviewStatus:
        """Query current review status.

        Returns the current state of the review without fetching all details.

        Args:
            review_id: Review to query

        Returns:
            CodeReviewStatus: Current status (open, approved, changes_requested, etc.)

        Raises:
            ResourceNotFoundError: Review doesn't exist
            ExternalServiceError: Service communication failure
        """

    @abstractmethod
    async def get_review_comments(self, review_id: str) -> list[ReviewComment]:
        """Retrieve all comments on a code review.

        Returns all feedback comments posted during the review process.

        Args:
            review_id: Review to get comments from

        Returns:
            List[ReviewComment]: All comments on the review

        Raises:
            ResourceNotFoundError: Review doesn't exist
            ExternalServiceError: Service communication failure
        """

    # Command Operations

    @abstractmethod
    async def request_changes(self, review_id: str, comments: str) -> None:
        """Request changes on a code review.

        Posts a review comment requesting that changes be made before
        this review can be approved.

        Args:
            review_id: Review to request changes on
            comments: Feedback about what needs to change

        Raises:
            ResourceNotFoundError: Review doesn't exist
            ValidationError: Comments are empty or too long
            PermissionError: Current user cannot request changes
            ExternalServiceError: Service communication failure

        Events:
            Emits 'review.status_changed' event if review status changes
            Emits 'review.comment_added' event for the new comment
        """

    @abstractmethod
    async def approve(self, review_id: str) -> None:
        """Approve a code review.

        Approves the code review, indicating the proposed changes are
        acceptable and can proceed to merge.

        Args:
            review_id: Review to approve

        Raises:
            ResourceNotFoundError: Review doesn't exist
            InvalidStateError: Review status doesn't allow approval
            PermissionError: Current user cannot approve
            ExternalServiceError: Service communication failure

        Events:
            Emits 'review.status_changed' event with new_status='approved'
        """
