"""Review Service application service."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from codetoreum.domain.agent import Agent
from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.review_cycle import (
    ReviewCycle,
    ReviewDecision,
    ReviewFeedback,
    ReviewStatus,
)
from codetoreum.ports.exceptions import EventStoreError
from codetoreum.ports.output import IEventStore

logger = logging.getLogger(__name__)


@dataclass
class ReviewCycleResult:
    """Result from review cycle operations."""

    success: bool
    review_cycle: ReviewCycle
    reason: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ReviewIterationResult:
    """Result from review iteration execution."""

    success: bool
    should_continue: bool  # True if needs another iteration
    review_cycle: ReviewCycle
    maker_execution: Optional[AgentExecution] = None
    reviewer_execution: Optional[AgentExecution] = None
    reason: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ReviewCompletionResult:
    """Result from review cycle completion."""

    success: bool
    review_cycle: ReviewCycle
    approved: bool
    escalated: bool
    reason: Optional[str] = None


class ReviewService:
    """
    Application service for orchestrating maker-checker review cycles.

    Responsibilities:
    - Create and manage review cycles
    - Assign reviewers to work items
    - Process review feedback
    - Determine if re-execution is needed
    - Handle approval workflow
    - Escalate to human when necessary
    """

    def __init__(
        self,
        event_store: IEventStore,
    ):
        """
        Initialize ReviewService.

        Args:
            event_store: Event store for domain events
        """
        self.event_store = event_store

    async def create_review_cycle(
        self,
        workflow_id: str,
        stage_name: str,
        maker_agent: Agent,
        reviewer_agent: Agent,
        max_iterations: int = 3,
    ) -> ReviewCycleResult:
        """
        Create a new review cycle.

        Args:
            workflow_id: ID of the workflow this cycle belongs to
            stage_name: Name of the workflow stage
            maker_agent: Maker agent
            reviewer_agent: Reviewer agent
            max_iterations: Maximum number of iterations (default: 3)

        Returns:
            ReviewCycleResult with created review cycle

        Raises:
            DomainError: If validation fails
            EventStoreError: If event persistence fails
        """
        review_cycle = None
        try:
            review_cycle = ReviewCycle.create(
                workflow_id=workflow_id,
                stage_name=stage_name,
                maker_agent_id=maker_agent.id,
                reviewer_agent_id=reviewer_agent.id,
                max_iterations=max_iterations,
            )

            # Persist events
            events = review_cycle.get_pending_events()
            for event in events:
                await self.event_store.append(event)
            review_cycle.clear_events()

            logger.info(
                f"Created review cycle {review_cycle.id} for workflow {workflow_id}, "
                f"stage {stage_name} (maker: {maker_agent.name}, "
                f"reviewer: {reviewer_agent.name})"
            )

            return ReviewCycleResult(
                success=True,
                review_cycle=review_cycle,
                reason="Review cycle created successfully",
            )

        except EventStoreError as e:
            logger.error(f"Failed to persist review cycle creation events: {e}")
            # Clear any pending events to maintain consistency
            if review_cycle:
                review_cycle.clear_events()
            raise
        except DomainError as e:
            logger.error(f"Failed to create review cycle (validation error): {e}")
            raise

    async def start_iteration(
        self,
        review_cycle: ReviewCycle,
        maker_output: str,
        maker_execution: AgentExecution,
    ) -> ReviewCycleResult:
        """
        Start a new review iteration with maker's output.

        Args:
            review_cycle: Review cycle to update
            maker_output: Output from maker agent
            maker_execution: Maker's execution entity

        Returns:
            ReviewCycleResult with updated review cycle

        Raises:
            DomainError: If max iterations exceeded
            EventStoreError: If event persistence fails
        """
        try:
            review_cycle.start_iteration(
                maker_output=maker_output,
                maker_execution_id=maker_execution.id,
            )

            # Persist events
            events = review_cycle.get_pending_events()
            for event in events:
                await self.event_store.append(event)
            review_cycle.clear_events()

            logger.info(
                f"Started iteration {review_cycle.current_iteration} for "
                f"review cycle {review_cycle.id}"
            )

            return ReviewCycleResult(
                success=True,
                review_cycle=review_cycle,
                reason="Iteration started successfully",
            )

        except EventStoreError as e:
            logger.error(
                f"Failed to persist iteration start events for cycle {review_cycle.id}: {e}"
            )
            # Clear any pending events to maintain consistency
            review_cycle.clear_events()
            raise
        except DomainError as e:
            logger.error(
                f"Failed to start iteration for cycle {review_cycle.id} "
                f"(validation error): {e}"
            )
            raise

    async def submit_review(
        self,
        review_cycle: ReviewCycle,
        decision: ReviewDecision,
        comment: str,
        reviewer_execution: AgentExecution,
        issues: Optional[List[str]] = None,
        suggestions: Optional[List[str]] = None,
    ) -> ReviewCycleResult:
        """
        Submit reviewer's feedback for current iteration.

        Args:
            review_cycle: Review cycle to update
            decision: Reviewer's decision (approve, request changes, escalate)
            comment: Reviewer's comment
            reviewer_execution: Reviewer's execution entity
            issues: List of issues found (optional)
            suggestions: List of suggestions (optional)

        Returns:
            ReviewCycleResult with updated review cycle

        Raises:
            DomainError: If no iteration to review or already reviewed
        """
        try:
            review_cycle.submit_review(
                decision=decision,
                comment=comment,
                reviewer_execution_id=reviewer_execution.id,
                issues=issues,
                suggestions=suggestions,
            )

            # Persist events
            events = review_cycle.get_pending_events()
            for event in events:
                await self.event_store.append(event)
            review_cycle.clear_events()

            logger.info(
                f"Submitted review for cycle {review_cycle.id}, "
                f"iteration {review_cycle.current_iteration}: {decision.value}"
            )

            return ReviewCycleResult(
                success=True,
                review_cycle=review_cycle,
                reason=f"Review submitted with decision: {decision.value}",
            )

        except EventStoreError as e:
            logger.error(
                f"Failed to persist review submission events for cycle "
                f"{review_cycle.id}: {e}"
            )
            # Clear any pending events to maintain consistency
            review_cycle.clear_events()
            raise
        except DomainError as e:
            logger.error(
                f"Failed to submit review for cycle {review_cycle.id} "
                f"(validation error): {e}"
            )
            raise

    async def should_escalate(self, review_cycle: ReviewCycle) -> bool:
        """
        Check if review cycle should be escalated to human review.

        Escalation criteria:
        - Explicit escalation decision from reviewer (any iteration)
        - Already marked as escalated
        - Max iterations reached with changes still requested

        Args:
            review_cycle: Review cycle to check

        Returns:
            True if should escalate to human
        """
        # Already escalated
        if review_cycle.status == ReviewStatus.ESCALATED:
            return True

        # Explicit escalation decision (check first, applies to any iteration)
        latest_feedback = review_cycle.get_latest_feedback()
        if latest_feedback and latest_feedback.decision == ReviewDecision.ESCALATE:
            logger.info(
                f"Review cycle {review_cycle.id} explicitly escalated by reviewer "
                f"at iteration {review_cycle.current_iteration}"
            )
            return True

        # Max iterations reached
        if review_cycle.current_iteration >= review_cycle.max_iterations:
            if latest_feedback and latest_feedback.decision == ReviewDecision.REQUEST_CHANGES:
                logger.warning(
                    f"Review cycle {review_cycle.id} reached max iterations "
                    f"({review_cycle.max_iterations}), escalating to human"
                )
                return True

        return False

    async def complete_cycle(
        self, review_cycle: ReviewCycle, approved: bool
    ) -> ReviewCompletionResult:
        """
        Complete a review cycle.

        Args:
            review_cycle: Review cycle to complete
            approved: Whether the review is approved

        Returns:
            ReviewCompletionResult with completion details
        """
        try:
            if approved:
                if not review_cycle.is_complete():
                    # Approve if not already complete
                    review_cycle.approve()

                    # Persist events
                    events = review_cycle.get_pending_events()
                    for event in events:
                        await self.event_store.append(event)
                    review_cycle.clear_events()

                logger.info(
                    f"Review cycle {review_cycle.id} completed with approval "
                    f"after {review_cycle.current_iteration} iteration(s)"
                )

                return ReviewCompletionResult(
                    success=True,
                    review_cycle=review_cycle,
                    approved=True,
                    escalated=False,
                    reason="Review approved",
                )
            else:
                # Check if should escalate
                should_escalate = await self.should_escalate(review_cycle)

                if should_escalate:
                    # Either already escalated or needs escalation
                    if not review_cycle.is_complete():
                        reason = (
                            f"Max iterations reached ({review_cycle.max_iterations})"
                            if review_cycle.current_iteration >= review_cycle.max_iterations
                            else "Reviewer requested escalation"
                        )
                        review_cycle.escalate(reason)

                        # Persist events
                        events = review_cycle.get_pending_events()
                        for event in events:
                            await self.event_store.append(event)
                        review_cycle.clear_events()

                        logger.warning(
                            f"Review cycle {review_cycle.id} escalated to human: {reason}"
                        )

                    # Return escalation result (either just escalated or already was)
                    return ReviewCompletionResult(
                        success=True,
                        review_cycle=review_cycle,
                        approved=False,
                        escalated=True,
                        reason=review_cycle.escalation_reason or "Escalated to human",
                    )
                else:
                    # Not complete, needs another iteration
                    logger.info(
                        f"Review cycle {review_cycle.id} needs maker revision "
                        f"(iteration {review_cycle.current_iteration})"
                    )

                    return ReviewCompletionResult(
                        success=True,
                        review_cycle=review_cycle,
                        approved=False,
                        escalated=False,
                        reason="Changes requested, needs maker revision",
                    )

        except EventStoreError as e:
            logger.error(
                f"Failed to persist review completion events for cycle "
                f"{review_cycle.id}: {e}"
            )
            # Clear any pending events to maintain consistency
            review_cycle.clear_events()
            raise
        except DomainError as e:
            logger.error(
                f"Failed to complete review cycle {review_cycle.id} "
                f"(validation error): {e}"
            )
            raise

    def get_review_status(self, review_cycle: ReviewCycle) -> Dict[str, Any]:
        """
        Get current status of review cycle.

        Args:
            review_cycle: Review cycle to check

        Returns:
            Dictionary with status information
        """
        latest_feedback = review_cycle.get_latest_feedback()

        return {
            "id": review_cycle.id,
            "status": review_cycle.status.value,
            "current_iteration": review_cycle.current_iteration,
            "max_iterations": review_cycle.max_iterations,
            "is_complete": review_cycle.is_complete(),
            "needs_revision": review_cycle.needs_maker_revision(),
            "latest_feedback": {
                "decision": latest_feedback.decision.value,
                "comment": latest_feedback.comment,
                "issues_count": len(latest_feedback.issues),
                "suggestions_count": len(latest_feedback.suggestions),
            }
            if latest_feedback
            else None,
            "final_decision": review_cycle.final_decision.value
            if review_cycle.final_decision
            else None,
            "escalation_reason": review_cycle.escalation_reason,
        }
