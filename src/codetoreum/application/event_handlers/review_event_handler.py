"""Event handler for review cycle events."""

import logging

from codetoreum.application.review_service import ReviewService
from codetoreum.domain.events import (
    ReviewCycleApprovedEvent,
    ReviewCycleCreatedEvent,
    ReviewCycleEscalatedToHumanEvent,
    ReviewCycleFeedbackSubmittedEvent,
    ReviewCycleIterationStartedEvent,
    ReviewCycleRejectedEvent,
)
from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.infrastructure.event_bus import EventHandler, event_handler
from codetoreum.ports.output.ci_pipeline_service import ICIPipelineService

logger = logging.getLogger(__name__)


@event_handler(
    "ReviewCycleCreatedEvent",
    "ReviewCycleIterationStartedEvent",
    "ReviewCycleFeedbackSubmittedEvent",
    "ReviewCycleApprovedEvent",
    "ReviewCycleRejectedEvent",
    "ReviewCycleEscalatedToHumanEvent",
)
class ReviewEventHandler(EventHandler):
    """
    Event handler for review cycle events.

    Handles events for:
    - ReviewCycleCreatedEvent: Initialize review tracking
    - ReviewCycleIterationStartedEvent: Log iteration start
    - ReviewCycleFeedbackSubmittedEvent: Process feedback
    - ReviewCycleApprovedEvent: Handle approval
    - ReviewCycleRejectedEvent: Handle rejection and re-execution
    - ReviewCycleEscalatedToHumanEvent: Handle escalation to human
    """

    def __init__(self, review_service: ReviewService, ci_pipeline_service: ICIPipelineService | None = None):
        """
        Initialize handler.

        Args: review_service: Review service
            ci_pipeline_service: Optional CI pipeline service for executing CI checks during review
        """
        self.review_service = review_service
        self._ci_pipeline_service = ci_pipeline_service

        # Track review metrics
        self._metrics: dict[str, int] = {
            "total_reviews": 0,
            "active_reviews": 0,
            "approved_reviews": 0,
            "rejected_reviews": 0,
            "escalated_reviews": 0,
            "total_iterations": 0,
        }

        # Track active reviews by ID
        self._active_reviews: dict[str, str] = {}  # review_id -> workflow_id

    @property
    def ci_pipeline_service(self) -> ICIPipelineService | None:
        """Get the CI pipeline service if configured."""
        return self._ci_pipeline_service

    async def handle(self, event: CodetoreumEvent) -> None:
        """
        Handle review cycle events.

        Args: event: Domain event to handle

        Raises: Exception: If handling fails
        """
        if isinstance(event, ReviewCycleCreatedEvent):
            await self._handle_review_cycle_created(event)
        elif isinstance(event, ReviewCycleIterationStartedEvent):
            await self._handle_review_iteration_started(event)
        elif isinstance(event, ReviewCycleFeedbackSubmittedEvent):
            await self._handle_review_feedback_submitted(event)
        elif isinstance(event, ReviewCycleApprovedEvent):
            await self._handle_review_cycle_approved(event)
        elif isinstance(event, ReviewCycleRejectedEvent):
            await self._handle_review_cycle_rejected(event)
        elif isinstance(event, ReviewCycleEscalatedToHumanEvent):
            await self._handle_review_cycle_escalated(event)
        else:
            logger.warning(f"ReviewEventHandler received unexpected event type: {event.event_type}")

    async def _handle_review_cycle_created(self, event: ReviewCycleCreatedEvent) -> None:
        """
        Handle review cycle creation - initialize tracking.

        Args: event: ReviewCycleCreatedEvent event
        """
        self._metrics["total_reviews"] += 1
        self._metrics["active_reviews"] += 1
        self._active_reviews[event.review_cycle_id] = event.workflow_id

        logger.info(
            f"Review cycle created: {event.review_cycle_id} "
            f"(workflow: {event.workflow_id}, stage: {event.stage_name}, "
            f"maker: {event.maker_agent_id}, reviewer: {event.reviewer_agent_id}, "
            f"max_iterations: {event.max_iterations})"
        )

        logger.debug(f"Total reviews: {self._metrics['total_reviews']}, Active: {self._metrics['active_reviews']}")

        # Note: In a full implementation, this would:
        # 1. Initialize review dashboard entry
        # 2. Set up review notifications
        # 3. Track review cycle start time
        # 4. Create review audit log

    async def _handle_review_iteration_started(self, event: ReviewCycleIterationStartedEvent) -> None:
        """
        Handle review iteration start - log iteration.

        Args: event: ReviewCycleIterationStartedEvent event
        """
        self._metrics["total_iterations"] += 1

        logger.info(
            f"Review iteration started: {event.review_cycle_id}, "
            f"iteration {event.iteration_number} "
            f"(maker_execution: {event.maker_execution_id})"
        )

        logger.debug(
            f"Average iterations per review: "
            f"{self._metrics['total_iterations'] / max(self._metrics['total_reviews'], 1):.2f}"
        )

        # Note: In a full implementation, this would:
        # 1. Queue reviewer agent task
        # 2. Set iteration timeout
        # 3. Update review dashboard
        # 4. Stream maker output to reviewer

    async def _handle_review_feedback_submitted(self, event: ReviewCycleFeedbackSubmittedEvent) -> None:
        """
        Handle review feedback submission.

        Args: event: ReviewCycleFeedbackSubmittedEvent event
        """
        logger.info(
            f"Review feedback submitted: {event.review_cycle_id}, "
            f"iteration {event.iteration_number}, "
            f"decision: {event.decision}, "
            f"issues: {event.issues_count}"
        )

        # Note: In a full implementation, this would:
        # 1. Parse feedback for actionable items
        # 2. Create GitHub comments with feedback
        # 3. Update review dashboard
        # 4. Trigger next action based on decision:
        #    - APPROVE: Complete review cycle
        #    - REQUEST_CHANGES: Queue maker revision
        #    - ESCALATE: Escalate to human

    async def _handle_review_cycle_approved(self, event: ReviewCycleApprovedEvent) -> None:
        """
        Handle review cycle approval.

        Args: event: ReviewCycleApprovedEvent event
        """
        self._metrics["approved_reviews"] += 1
        self._metrics["active_reviews"] -= 1
        self._active_reviews.pop(event.review_cycle_id, None)

        logger.info(f"Review cycle approved: {event.review_cycle_id}, total iterations: {event.total_iterations}")

        logger.info(
            f"Approval rate: {self._metrics['approved_reviews']}/{self._metrics['total_reviews']} "
            f"({self._get_approval_rate():.1f}%)"
        )

        # Note: In a full implementation, this would:
        # 1. Update work item status
        # 2. Trigger workflow progression (handled by WorkflowEventHandler)
        # 3. Send approval notifications
        # 4. Update agent performance metrics
        # 5. Archive review artifacts
        # 6. Update review dashboard

    async def _handle_review_cycle_rejected(self, event: ReviewCycleRejectedEvent) -> None:
        """
        Handle review cycle rejection - trigger re-execution or escalation.

        Args: event: ReviewCycleRejectedEvent event
        """
        self._metrics["rejected_reviews"] += 1

        # Decrement active reviews since rejection means review is complete
        self._metrics["active_reviews"] -= 1
        self._active_reviews.pop(event.review_cycle_id, None)

        logger.warning(
            f"Review cycle rejected: {event.review_cycle_id}, "
            f"final iteration: {event.final_iteration}, "
            f"reason: {event.rejection_reason}"
        )

        logger.warning(
            f"Rejection rate: {self._metrics['rejected_reviews']}/{self._metrics['total_reviews']} "
            f"({self._get_rejection_rate():.1f}%)"
        )

        # Note: In a full implementation, this would:
        # 1. Check if max iterations reached
        # 2. If yes, trigger escalation
        # 3. If no, queue maker revision task
        # 4. Send rejection notifications
        # 5. Update review dashboard
        # 6. Track rejection reasons for analysis

    async def _handle_review_cycle_escalated(self, event: ReviewCycleEscalatedToHumanEvent) -> None:
        """
        Handle review cycle escalation to human.

        Args: event: ReviewCycleEscalatedToHumanEvent event
        """
        self._metrics["escalated_reviews"] += 1
        self._metrics["active_reviews"] -= 1
        self._active_reviews.pop(event.review_cycle_id, None)

        logger.warning(f"Review cycle escalated: {event.review_cycle_id}, reason: {event.escalation_reason}")

        logger.warning(
            f"Escalation rate: {self._metrics['escalated_reviews']}/{self._metrics['total_reviews']} "
            f"({self._get_escalation_rate():.1f}%)"
        )

        # Note: In a full implementation, this would:
        # 1. Add "needs-human-review" label to work item
        # 2. Create GitHub discussion or issue comment
        # 3. Send escalation notifications to maintainers
        # 4. Update work item status to "blocked"
        # 5. Create escalation dashboard entry
        # 6. Track escalation reasons for pattern analysis

    def _get_approval_rate(self) -> float:
        """Calculate approval rate percentage."""
        if self._metrics["total_reviews"] == 0:
            return 0.0
        return self._metrics["approved_reviews"] / self._metrics["total_reviews"] * 100

    def _get_rejection_rate(self) -> float:
        """Calculate rejection rate percentage."""
        if self._metrics["total_reviews"] == 0:
            return 0.0
        return self._metrics["rejected_reviews"] / self._metrics["total_reviews"] * 100

    def _get_escalation_rate(self) -> float:
        """Calculate escalation rate percentage."""
        if self._metrics["total_reviews"] == 0:
            return 0.0
        return self._metrics["escalated_reviews"] / self._metrics["total_reviews"] * 100

    def get_metrics(self) -> dict[str, object]:
        """
        Get review metrics.

        Returns: Dictionary of review metrics
        """
        avg_iterations = self._metrics["total_iterations"] / max(self._metrics["total_reviews"], 1)

        return {
            **self._metrics,
            "approval_rate": self._get_approval_rate(),
            "rejection_rate": self._get_rejection_rate(),
            "escalation_rate": self._get_escalation_rate(),
            "avg_iterations_per_review": round(avg_iterations, 2),
        }

    def get_active_reviews(self) -> dict[str, str]:
        """
        Get currently active reviews.

        Returns: Dictionary mapping review_id to workflow_id
        """
        return dict(self._active_reviews)
