"""Event handler for workflow-related events."""

import logging

from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.domain.events import (
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
    ReviewCycleApprovedEvent,
    ReviewCycleEscalatedToHumanEvent,
    ReviewCycleRejectedEvent,
    WorkItemCreatedEvent,
)
from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventHandler, event_handler

logger = logging.getLogger(__name__)


@event_handler(
    "WorkItemCreatedEvent",
    "ExecutionCompletedEvent",
    "ExecutionFailedEvent",
    "ReviewCycleApprovedEvent",
    "ReviewCycleRejectedEvent",
    "ReviewCycleEscalatedToHumanEvent",
)
class WorkflowEventHandler(EventHandler):
    """
    Event handler for workflow orchestration events.

    Handles events that trigger workflow actions:
    - WorkItemCreatedEvent: Start new workflow
    - ExecutionCompletedEvent: Advance workflow stage
    - ExecutionFailedEvent: Handle execution failure
    - ReviewCycleApprovedEvent: Progress after review approval
    - ReviewCycleRejectedEvent: Handle review rejection
    - ReviewCycleEscalatedToHumanEvent: Handle human escalation
    """

    def __init__(self, orchestrator: WorkflowOrchestrator):
        """
        Initialize handler.

        Args: orchestrator: Workflow orchestrator service
        """
        self.orchestrator = orchestrator

    async def handle(self, event: CodetoreumEvent) -> None:
        """
        Handle workflow-related events.

        Args: event: Domain event to handle

        Raises: Exception: If handling fails
        """
        if isinstance(event, WorkItemCreatedEvent):
            await self._handle_work_item_created(event)
        elif isinstance(event, ExecutionCompletedEvent):
            await self._handle_execution_completed(event)
        elif isinstance(event, ExecutionFailedEvent):
            await self._handle_execution_failed(event)
        elif isinstance(event, ReviewCycleApprovedEvent):
            await self._handle_review_approved(event)
        elif isinstance(event, ReviewCycleRejectedEvent):
            await self._handle_review_rejected(event)
        elif isinstance(event, ReviewCycleEscalatedToHumanEvent):
            await self._handle_review_escalated(event)
        else:
            logger.warning(f"WorkflowEventHandler received unexpected event type: {event.event_type}")

    async def _handle_work_item_created(self, event: WorkItemCreatedEvent) -> None:
        """
        Handle work item creation - start workflow.

        Args: event: WorkItemCreatedEvent event
        """
        logger.info(f"Starting workflow for new work item: {event.work_item_id} (title: {event.title})")

        # Note: In a full implementation, this would:
        # 1. Load workflow configuration for the project
        # 2. Create initial CardMovedEvent from work item data
        # 3. Call orchestrator.handle_card_movement()
        #
        # For now, we log the event and rely on external triggers
        # (GitHub webhook) to move cards to initial column
        logger.debug(f"Work item {event.work_item_id} created, waiting for initial column assignment")

    async def _handle_execution_completed(self, event: ExecutionCompletedEvent) -> None:
        """
        Handle execution completion - advance workflow or queue review.

        Args: event: ExecutionCompletedEvent event
        """
        logger.info(f"Execution completed for work item: {event.work_item_id}, " f"triggering workflow progression")

        # Note: In a full implementation, this would:
        # 1. Reconstruct StageCompletedEvent from execution data
        # 2. Call orchestrator.handle_stage_completion()
        # 3. Either queue review or auto-advance to next stage

        logger.debug(f"Execution {event.execution_id} completed, workflow progression deferred to integration phase")

    async def _handle_execution_failed(self, event: ExecutionFailedEvent) -> None:
        """
        Handle execution failure - escalate or retry.

        Args: event: ExecutionFailedEvent event
        """
        logger.warning(f"Execution failed for work item: {event.work_item_id}, " f"error: {event.error}")

        # Note: In a full implementation, this would:
        # 1. Check retry policy
        # 2. Either retry execution or escalate to human
        # 3. Update work item status
        # 4. Notify stakeholders

        logger.error(
            f"Execution {event.execution_id} failed, escalation logic deferred to integration phase",
            extra={"error_id": ErrorRegistry.ERR_EXECUTION_ERROR},
        )

    async def _handle_review_approved(self, event: ReviewCycleApprovedEvent) -> None:
        """
        Handle review approval - advance workflow.

        Args: event: ReviewCycleApprovedEvent event
        """
        logger.info(f"Review cycle approved: {event.review_cycle_id}, " f"after {event.total_iterations} iteration(s)")

        # Note: In a full implementation, this would:
        # 1. Reconstruct ReviewCycleCompletedEvent
        # 2. Call orchestrator.handle_review_cycle_completion()
        # 3. Auto-advance to next stage if configured

        logger.debug(
            f"Review cycle {event.review_cycle_id} approved, workflow advancement deferred to integration phase"
        )

    async def _handle_review_rejected(self, event: ReviewCycleRejectedEvent) -> None:
        """
        Handle review rejection - queue maker revision or escalate.

        Args: event: ReviewCycleRejectedEvent event
        """
        logger.info(
            f"Review cycle rejected: {event.review_cycle_id}, "
            f"final iteration: {event.final_iteration}, reason: {event.rejection_reason}"
        )

        # Note: In a full implementation, this would:
        # 1. Check if max iterations reached
        # 2. If yes, escalate to human
        # 3. If no, queue revision task for maker
        # 4. Update work item status

        logger.info(
            f"Review cycle {event.review_cycle_id} needs maker revision, task queuing deferred to integration phase"
        )

    async def _handle_review_escalated(self, event: ReviewCycleEscalatedToHumanEvent) -> None:
        """
        Handle review escalation - notify human reviewers.

        Args: event: ReviewCycleEscalatedToHumanEvent event
        """
        logger.warning(f"Review cycle escalated to human: {event.review_cycle_id}, reason: {event.escalation_reason}")

        # Note: In a full implementation, this would:
        # 1. Add "needs-human-review" label to work item
        # 2. Create GitHub discussion or issue comment
        # 3. Send notifications to project maintainers
        # 4. Update work item status

        logger.info(f"Review cycle {event.review_cycle_id} escalated, notification logic deferred to integration phase")
