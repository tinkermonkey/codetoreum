"""Event handler for review cycle events."""

import logging
from typing import Dict, List, Optional

from codetoreum.application.review_service import ReviewService
from codetoreum.domain.events import (
    DomainEvent,
    ReviewCycleApproved,
    ReviewCycleCreated,
    ReviewCycleEscalated,
    ReviewCycleRejected,
    ReviewFeedbackSubmitted,
    ReviewIterationStarted,
)
from codetoreum.infrastructure.event_bus import EventHandler, event_handler

logger = logging.getLogger(__name__)


@event_handler(
    "ReviewCycleCreated",
    "ReviewIterationStarted",
    "ReviewFeedbackSubmitted",
    "ReviewCycleApproved",
    "ReviewCycleRejected",
    "ReviewCycleEscalated",
)
class ReviewEventHandler(EventHandler):
    """
    Event handler for review cycle events.

    Handles events for:
    - ReviewCycleCreated: Initialize review tracking
    - ReviewIterationStarted: Log iteration start
    - ReviewFeedbackSubmitted: Process feedback
    - ReviewCycleApproved: Handle approval
    - ReviewCycleRejected: Handle rejection and re-execution
    - ReviewCycleEscalated: Handle escalation to human
    """

    def __init__(self, review_service: ReviewService):
        """
        Initialize handler.

        Args:
            review_service: Review service
        """
        self.review_service = review_service

        # Track review metrics
        self._metrics: Dict[str, int] = {
            "total_reviews": 0,
            "active_reviews": 0,
            "approved_reviews": 0,
            "rejected_reviews": 0,
            "escalated_reviews": 0,
            "total_iterations": 0,
        }

        # Track active reviews by ID
        self._active_reviews: Dict[str, str] = {}  # review_id -> workflow_id

    async def handle(self, event: DomainEvent) -> None:
        """
        Handle review cycle events.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails
        """
        if isinstance(event, ReviewCycleCreated):
            await self._handle_review_cycle_created(event)
        elif isinstance(event, ReviewIterationStarted):
            await self._handle_review_iteration_started(event)
        elif isinstance(event, ReviewFeedbackSubmitted):
            await self._handle_review_feedback_submitted(event)
        elif isinstance(event, ReviewCycleApproved):
            await self._handle_review_cycle_approved(event)
        elif isinstance(event, ReviewCycleRejected):
            await self._handle_review_cycle_rejected(event)
        elif isinstance(event, ReviewCycleEscalated):
            await self._handle_review_cycle_escalated(event)
        else:
            logger.warning(
                f"ReviewEventHandler received unexpected event type: {event.event_type}"
            )

    async def _handle_review_cycle_created(self, event: ReviewCycleCreated) -> None:
        """
        Handle review cycle creation - initialize tracking.

        Args:
            event: ReviewCycleCreated event
        """
        self._metrics["total_reviews"] += 1
        self._metrics["active_reviews"] += 1
        self._active_reviews[event.aggregate_id] = event.payload.get('workflow_id', '')

        logger.info(
            f"Review cycle created: {event.aggregate_id} "
            f"(workflow: {event.payload.get('workflow_id')}, stage: {event.payload.get('stage_name')}, "
            f"maker: {event.payload.get('maker_agent_id')}, reviewer: {event.payload.get('reviewer_agent_id')}, "
            f"max_iterations: {event.payload.get('max_iterations')})"
        )

        logger.debug(
            f"Total reviews: {self._metrics['total_reviews']}, "
            f"Active: {self._metrics['active_reviews']}"
        )

        # Note: In a full implementation, this would:
        # 1. Initialize review dashboard entry
        # 2. Set up review notifications
        # 3. Track review cycle start time
        # 4. Create review audit log

    async def _handle_review_iteration_started(
        self, event: ReviewIterationStarted
    ) -> None:
        """
        Handle review iteration start - log iteration.

        Args:
            event: ReviewIterationStarted event
        """
        self._metrics["total_iterations"] += 1

        logger.info(
            f"Review iteration started: {event.aggregate_id}, "
            f"iteration {event.payload.get('iteration_number')} "
            f"(maker_execution: {event.payload.get('maker_execution_id')})"
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

    async def _handle_review_feedback_submitted(
        self, event: ReviewFeedbackSubmitted
    ) -> None:
        """
        Handle review feedback submission.

        Args:
            event: ReviewFeedbackSubmitted event
        """
        issues_found = event.payload.get('issues_found', [])
        logger.info(
            f"Review feedback submitted: {event.aggregate_id}, "
            f"iteration {event.payload.get('iteration_number')}, "
            f"decision: {event.payload.get('decision')}, "
            f"issues: {len(issues_found)}"
        )

        feedback_text = event.payload.get('feedback')
        if feedback_text:
            logger.debug(f"Reviewer comment: {feedback_text}")

        # Note: In a full implementation, this would:
        # 1. Parse feedback for actionable items
        # 2. Create GitHub comments with feedback
        # 3. Update review dashboard
        # 4. Trigger next action based on decision:
        #    - APPROVE: Complete review cycle
        #    - REQUEST_CHANGES: Queue maker revision
        #    - ESCALATE: Escalate to human

    async def _handle_review_cycle_approved(self, event: ReviewCycleApproved) -> None:
        """
        Handle review cycle approval.

        Args:
            event: ReviewCycleApproved event
        """
        self._metrics["approved_reviews"] += 1
        self._metrics["active_reviews"] -= 1
        self._active_reviews.pop(event.aggregate_id, None)

        logger.info(
            f"Review cycle approved: {event.aggregate_id}, "
            f"total iterations: {event.payload.get('total_iterations')}"
        )

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

    async def _handle_review_cycle_rejected(self, event: ReviewCycleRejected) -> None:
        """
        Handle review cycle rejection - trigger re-execution or escalation.

        Args:
            event: ReviewCycleRejected event
        """
        self._metrics["rejected_reviews"] += 1

        # Decrement active reviews since rejection means review is complete
        self._metrics["active_reviews"] -= 1
        self._active_reviews.pop(event.aggregate_id, None)

        final_iteration = event.payload.get('final_iteration', 0)
        logger.warning(
            f"Review cycle rejected: {event.aggregate_id}, "
            f"final iteration: {final_iteration}, "
            f"reason: {event.payload.get('rejection_reason')}"
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

    async def _handle_review_cycle_escalated(
        self, event: ReviewCycleEscalated
    ) -> None:
        """
        Handle review cycle escalation to human.

        Args:
            event: ReviewCycleEscalated event
        """
        self._metrics["escalated_reviews"] += 1
        self._metrics["active_reviews"] -= 1
        self._active_reviews.pop(event.aggregate_id, None)

        logger.warning(
            f"Review cycle escalated: {event.aggregate_id}, "
            f"reason: {event.payload.get('reason')}"
        )

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
        return (
            self._metrics["approved_reviews"] / self._metrics["total_reviews"] * 100
        )

    def _get_rejection_rate(self) -> float:
        """Calculate rejection rate percentage."""
        if self._metrics["total_reviews"] == 0:
            return 0.0
        return (
            self._metrics["rejected_reviews"] / self._metrics["total_reviews"] * 100
        )

    def _get_escalation_rate(self) -> float:
        """Calculate escalation rate percentage."""
        if self._metrics["total_reviews"] == 0:
            return 0.0
        return (
            self._metrics["escalated_reviews"] / self._metrics["total_reviews"] * 100
        )

    def get_metrics(self) -> Dict[str, any]:
        """
        Get review metrics.

        Returns:
            Dictionary of review metrics
        """
        avg_iterations = (
            self._metrics["total_iterations"] / max(self._metrics["total_reviews"], 1)
        )

        return {
            **self._metrics,
            "approval_rate": self._get_approval_rate(),
            "rejection_rate": self._get_rejection_rate(),
            "escalation_rate": self._get_escalation_rate(),
            "avg_iterations_per_review": round(avg_iterations, 2),
        }

    def get_active_reviews(self) -> Dict[str, str]:
        """
        Get currently active reviews.

        Returns:
            Dictionary mapping review_id to workflow_id
        """
        return dict(self._active_reviews)
