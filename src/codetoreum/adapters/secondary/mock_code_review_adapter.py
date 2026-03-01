"""In-memory code review adapter with event simulation for testing.

This module provides a mock implementation of ICodeReviewService that stores
code reviews in memory and includes test helper methods for simulating
review status changes via event emission.
"""

from datetime import UTC, datetime

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

from .mock_event_emitter import MockEventEmitter


class MockCodeReviewAdapter(MockEventEmitter, ICodeReviewService):
    """In-memory code review adapter with event simulation.

    Provides a mock implementation of ICodeReviewService that:
    1. Stores code reviews in memory
    2. Tracks work item to review associations
    3. Emits events when review status changes
    4. Provides test helper methods for event simulation

    Intended for testing and simulation without external code review systems
    (GitHub PRs, GitLab MRs, Bitbucket PRs, etc.).

    Example:
        # Setup
        adapter = MockCodeReviewAdapter()
        adapter.current_project = "proj-1"
        adapter.add_review("pr-123", "item-1", status="open")

        # Subscribe to events
        events = []
        adapter.on("review.status_changed", events.append)

        # Simulate approval
        adapter.simulate_approval("pr-123", "reviewer-1")

        # Verify
        assert len(events) == 1
        assert events[0].new_status == "approved"
    """

    def __init__(self) -> None:
        """Initialize the code review adapter."""
        super().__init__()
        self._reviews: dict[str, CodeReview] = {}  # review_id -> CodeReview
        self._work_item_reviews: dict[str, str] = {}  # work_item_id -> review_id
        self._monitoring: dict[str, MonitoringStatus] = {}  # project_id -> status
        self.current_project: str | None = None

    # Query Operations

    async def get_review_for_work_item(self, work_item_id: str) -> CodeReview | None:
        """Find code review associated with a work item.

        Args:
            work_item_id: Work item to find review for

        Returns:
            CodeReview if associated review exists, None otherwise

        Raises:
            ValueError: Work item doesn't exist
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
        # Simplified for mock: return empty list
        return []

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
            reviewers=["reviewer-1"],
            approvals=[],
        )
        self._work_item_reviews[work_item_id] = review_id

    def simulate_approval(self, review_id: str, reviewer: str) -> None:
        """Test helper: Simulate review approval.

        Simulates a reviewer approving a code review, emitting a status
        change event.

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
        """Test helper: Simulate requesting changes on review.

        Simulates a reviewer requesting changes to a code review,
        emitting a status change event.

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

    # Helper Methods

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current time as ISO 8601 timestamp."""
        return datetime.now(UTC).isoformat()
