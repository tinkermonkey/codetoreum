"""In-memory code review adapter with event simulation for testing.

This module provides a first-class implementation of ICodeReviewService that stores
code reviews and comments in memory, emits events on status changes, and includes
test helper methods for simulation scenarios.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.domain.events.review_events import ReviewStatusChangedEvent
from codetoreum.ports.output.code_review_service import (
    Approval,
    CodeReview,
    CodeReviewStatus,
    ICodeReviewService,
    ReviewComment,
)
from codetoreum.ports.output.monitoring import (
    MonitoringConfig,
    MonitoringState,
    MonitoringStatus,
)


class InMemoryCodeReviewAdapter(MockEventEmitter, ICodeReviewService):
    """In-memory code review adapter with event simulation.

    Provides a first-class implementation of ICodeReviewService that:
    1. Stores code reviews and comments in memory
    2. Tracks work item to review associations
    3. Emits events when review status changes
    4. Is clock-aware for simulation time control
    5. Provides test helper methods for event simulation and verification

    Intended for testing and simulation without external code review systems
    (GitHub PRs, GitLab MRs, Bitbucket PRs, etc.).

    Test Helper Methods:
        - add_review() - Create a code review in the store
        - add_comment_to_review() - Pre-populate review comments for testing
        - simulate_approval() - Simulate reviewer approval (emits event)
        - simulate_changes_requested() - Simulate requesting changes (emits event)
        - simulate_review_comment() - Simulate a comment being posted (emits event)

    Example:
        # Setup
        adapter = InMemoryCodeReviewAdapter()
        adapter.current_project = "proj-1"
        adapter.add_review("pr-123", "item-1", status="open")

        # Pre-populate comments for get_review_comments() assertions
        comment = ReviewComment(id="c-1", review_id="pr-123", author="reviewer-1",
                                body="Please fix the null check", created_at="...")
        adapter.add_comment_to_review("pr-123", comment)

        # Simulate approval
        adapter.simulate_approval("pr-123", "reviewer-1")

        # Verify
        comments = await adapter.get_review_comments("pr-123")
        assert len(comments) == 1
    """

    def __init__(self, time_source: Callable[[], datetime] | None = None) -> None:
        """Initialize the code review adapter.

        Args:
            time_source: Optional callable returning current datetime for simulation clock control.
                        Defaults to datetime.now(UTC).
        """
        super().__init__()
        self._reviews: dict[str, CodeReview] = {}  # review_id -> CodeReview
        self._work_item_reviews: dict[str, str] = {}  # work_item_id -> review_id
        self._review_comments: dict[str, list[ReviewComment]] = {}  # review_id -> comments
        self._monitoring: dict[str, MonitoringStatus] = {}  # project_id -> status
        self.current_project: str | None = None
        self._time_source = time_source or (lambda: datetime.now(UTC))

    # Query Operations

    async def get_review_for_work_item(self, work_item_id: str) -> CodeReview | None:
        """Find code review associated with a work item.

        Args:
            work_item_id: Work item to find review for

        Returns:
            CodeReview if associated review exists, None otherwise
        """
        review_id = self._work_item_reviews.get(work_item_id)
        return self._reviews.get(review_id) if review_id else None

    async def get_review_status(self, review_id: str) -> CodeReviewStatus:
        """Query current review status.

        Args:
            review_id: Review to query

        Returns:
            CodeReviewStatus: Current status

        Raises:
            ValueError: Review doesn't exist
        """
        if review_id not in self._reviews:
            msg = f"Review not found: {review_id}"
            raise ValueError(msg)
        return self._reviews[review_id].status

    async def get_review_comments(self, review_id: str) -> list[ReviewComment]:
        """Retrieve all comments on a code review.

        Args:
            review_id: Review to get comments from

        Returns:
            List[ReviewComment]: All comments on the review

        Raises:
            ValueError: Review doesn't exist
        """
        if review_id not in self._reviews:
            msg = f"Review not found: {review_id}"
            raise ValueError(msg)
        return list(self._review_comments.get(review_id, []))

    # Command Operations

    async def request_changes(self, review_id: str, comments: str) -> None:
        """Request changes on a code review.

        Args:
            review_id: Review to request changes on
            comments: Feedback about what needs to change

        Raises:
            ValueError: Review doesn't exist
        """
        if review_id not in self._reviews:
            msg = f"Review not found: {review_id}"
            raise ValueError(msg)

        review = self._reviews[review_id]
        previous_status = review.status

        if previous_status != "changes_requested":
            new_review = CodeReview(
                id=review.id,
                title=review.title,
                source_branch=review.source_branch,
                target_branch=review.target_branch,
                status="changes_requested",
                reviewers=review.reviewers,
                approvals=review.approvals,
                work_item_id=review.work_item_id,
            )
            self._reviews[review_id] = new_review

            if self.current_project is not None:
                self.emit(
                    ReviewStatusChangedEvent(
                        type="review.status_changed",
                        review_id=review_id,
                        work_item_id=review.work_item_id,
                        project_id=self.current_project,
                        previous_status=previous_status,
                        new_status="changes_requested",
                        reviewer="reviewer-1",
                        timestamp=self._get_iso_timestamp(),
                        source="mock",
                    )
                )

    async def approve(self, review_id: str) -> None:
        """Approve a code review.

        Args:
            review_id: Review to approve

        Raises:
            ValueError: Review doesn't exist
        """
        if review_id not in self._reviews:
            msg = f"Review not found: {review_id}"
            raise ValueError(msg)

        review = self._reviews[review_id]
        previous_status = review.status

        if previous_status != "approved":
            new_approval = Approval(reviewer="reviewer-1", approved_at=self._get_iso_timestamp())
            new_approvals = tuple(list(review.approvals) + [new_approval])
            new_review = CodeReview(
                id=review.id,
                title=review.title,
                source_branch=review.source_branch,
                target_branch=review.target_branch,
                status="approved",
                reviewers=review.reviewers,
                approvals=new_approvals,
                work_item_id=review.work_item_id,
            )
            self._reviews[review_id] = new_review

            if self.current_project is not None:
                self.emit(
                    ReviewStatusChangedEvent(
                        type="review.status_changed",
                        review_id=review_id,
                        work_item_id=review.work_item_id,
                        project_id=self.current_project,
                        previous_status=previous_status,
                        new_status="approved",
                        reviewer="reviewer-1",
                        timestamp=self._get_iso_timestamp(),
                        source="mock",
                    )
                )

    # Monitoring Lifecycle

    async def start_monitoring(self, project_id: str, config: MonitoringConfig) -> None:
        """Begin monitoring for changes.

        Args:
            project_id: Project to monitor
            config: Monitoring configuration
        """
        self._monitoring[project_id] = MonitoringStatus(
            state=MonitoringState.ACTIVE,
            project_id=project_id,
            started_at=self._get_iso_timestamp(),
        )

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring for changes.

        Args:
            project_id: Project to stop monitoring
        """
        if project_id in self._monitoring:
            status = self._monitoring[project_id]
            stopped_status = MonitoringStatus(
                state=MonitoringState.STOPPED,
                project_id=status.project_id,
                started_at=status.started_at,
                error_message=status.error_message,
            )
            self._monitoring[project_id] = stopped_status

    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Query current monitoring state.

        Args:
            project_id: Project to query status for

        Returns:
            MonitoringStatus with current state
        """
        return self._monitoring.get(project_id, MonitoringStatus(state=MonitoringState.STOPPED, project_id=project_id))

    # Test Helper Methods

    def add_review(self, review_id: str, work_item_id: str, status: CodeReviewStatus = "open") -> None:
        """Test helper: Create a code review.

        Args:
            review_id: Review ID
            work_item_id: Associated work item
            status: Initial review status
        """
        self._reviews[review_id] = CodeReview(
            id=review_id,
            work_item_id=work_item_id,
            title=f"Review {review_id}",
            source_branch="feature-branch",
            target_branch="main",
            status=status,
            reviewers=("reviewer-1",),
            approvals=(),
        )
        self._work_item_reviews[work_item_id] = review_id

    def add_comment_to_review(self, review_id: str, comment: ReviewComment) -> None:
        """Test helper: Add a pre-existing comment to a review.

        Populates the comment store so get_review_comments() returns it.
        Useful for setting up preconditions in tests without triggering events.

        Args:
            review_id: Review to add comment to
            comment: ReviewComment to store
        """
        if review_id not in self._review_comments:
            self._review_comments[review_id] = []
        self._review_comments[review_id].append(comment)

    def simulate_approval(self, review_id: str, reviewer: str) -> None:
        """Test helper: Simulate review approval with event emission.

        Args:
            review_id: Review to approve
            reviewer: Username of the reviewer

        Raises:
            ValueError: Review doesn't exist
        """
        if review_id not in self._reviews:
            msg = f"Review not found: {review_id}"
            raise ValueError(msg)

        review = self._reviews[review_id]
        previous_status = review.status

        new_approval = Approval(reviewer=reviewer, approved_at=self._get_iso_timestamp())
        new_approvals = tuple(list(review.approvals) + [new_approval])
        new_review = CodeReview(
            id=review.id,
            title=review.title,
            source_branch=review.source_branch,
            target_branch=review.target_branch,
            status="approved",
            reviewers=review.reviewers,
            approvals=new_approvals,
            work_item_id=review.work_item_id,
        )
        self._reviews[review_id] = new_review

        if self.current_project is not None:
            self.emit(
                ReviewStatusChangedEvent(
                    type="review.status_changed",
                    review_id=review_id,
                    work_item_id=review.work_item_id,
                    project_id=self.current_project,
                    previous_status=previous_status,
                    new_status="approved",
                    reviewer=reviewer,
                    timestamp=self._get_iso_timestamp(),
                    source="mock",
                )
            )

    def simulate_changes_requested(self, review_id: str, reviewer: str) -> None:
        """Test helper: Simulate requesting changes with event emission.

        Args:
            review_id: Review to request changes on
            reviewer: Username of the reviewer

        Raises:
            ValueError: Review doesn't exist
        """
        if review_id not in self._reviews:
            msg = f"Review not found: {review_id}"
            raise ValueError(msg)

        review = self._reviews[review_id]
        previous_status = review.status

        new_review = CodeReview(
            id=review.id,
            title=review.title,
            source_branch=review.source_branch,
            target_branch=review.target_branch,
            status="changes_requested",
            reviewers=review.reviewers,
            approvals=review.approvals,
            work_item_id=review.work_item_id,
        )
        self._reviews[review_id] = new_review

        if self.current_project is not None:
            self.emit(
                ReviewStatusChangedEvent(
                    type="review.status_changed",
                    review_id=review_id,
                    work_item_id=review.work_item_id,
                    project_id=self.current_project,
                    previous_status=previous_status,
                    new_status="changes_requested",
                    reviewer=reviewer,
                    timestamp=self._get_iso_timestamp(),
                    source="mock",
                )
            )

    def simulate_review_comment(
        self,
        review_id: str,
        comment_id: str,
        author: str,
        body: str,
    ) -> ReviewComment:
        """Test helper: Simulate a review comment being posted.

        Stores the comment and returns it. Does not emit an event (comments
        don't have a dedicated domain event in the current model).

        Args:
            review_id: Review to add the comment to
            comment_id: ID for the new comment
            author: Author username
            body: Comment text

        Returns:
            The created ReviewComment

        Raises:
            ValueError: Review doesn't exist
        """
        if review_id not in self._reviews:
            msg = f"Review not found: {review_id}"
            raise ValueError(msg)

        comment = ReviewComment(
            id=comment_id,
            author=author,
            body=body,
            created_at=self._get_iso_timestamp(),
        )
        if review_id not in self._review_comments:
            self._review_comments[review_id] = []
        self._review_comments[review_id].append(comment)
        return comment

    # Helper Methods

    def _get_iso_timestamp(self) -> str:
        """Get current time as ISO 8601 timestamp."""
        return self._time_source().isoformat()
