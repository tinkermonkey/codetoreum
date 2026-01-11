"""Workflow Orchestrator application service."""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from codetoreum.domain.events import (
    WorkflowStageAdvanced,
    WorkItemStageUpdated,
    DomainEvent,
)
from codetoreum.domain.workflow import Workflow, WorkflowStatus
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_types import EventTypes
from codetoreum.ports.output import IEventStore, ITicketSystem

logger = logging.getLogger(__name__)


class WorkflowAction(Enum):
    """Possible workflow actions."""

    TASK_QUEUED = "task_queued"
    AUTO_ADVANCE = "auto_advance"
    ESCALATE = "escalate"
    COMPLETE = "complete"
    NO_ACTION = "no_action"


@dataclass
class WorkflowResult:
    """Result of workflow orchestration action."""

    success: bool
    task_id: Optional[str]
    agent_name: Optional[str]
    action: WorkflowAction
    next_column: Optional[str]
    reason: str
    error: Optional[str] = None


@dataclass
class CardMovedEvent:
    """Event emitted when a card moves on GitHub Projects board."""

    project: str
    board: str
    issue_number: int
    from_column: Optional[str]
    to_column: str
    issue_data: "IssueData"
    timestamp: datetime


@dataclass
class IssueData:
    """Issue information from GitHub."""

    number: int
    title: str
    body: str
    labels: List[str]
    state: str
    created_at: datetime
    updated_at: datetime


@dataclass
class StageCompletedEvent:
    """Event emitted when a pipeline stage completes."""

    project: str
    issue_number: int
    stage_name: str
    agent_name: str
    success: bool
    output: str
    context: Dict[str, Any]
    timestamp: datetime


@dataclass
class ReviewCycleCompletedEvent:
    """Event emitted when review cycle completes."""

    project: str
    issue_number: int
    approved: bool
    iteration: int
    maker_agent: str
    reviewer_agent: str
    feedback: Optional[str]
    timestamp: datetime
    context: Dict[str, Any]


@dataclass
class FeedbackEvent:
    """Event for human feedback on agent output."""

    project: str
    issue_number: int
    feedback_type: str
    author: str
    content: str
    reply_to_comment_id: Optional[str]
    timestamp: datetime


@dataclass
class Task:
    """Task for agent execution."""

    id: str
    agent: str
    project: str
    priority: WorkItemPriority
    context: Dict[str, Any]
    created_at: datetime


@dataclass
class WorkflowConfig:
    """Workflow configuration from config system."""

    name: str
    columns: List["ColumnConfig"]
    workspace_type: str


@dataclass
class ColumnConfig:
    """Configuration for a workflow column."""

    name: str
    position: int
    agent: str
    auto_advance_on_approval: bool
    discussion_category: Optional[str]
    stage_type: str
    review_required: bool
    reviewer_agent: Optional[str]


@dataclass
class AgentConfig:
    """Agent configuration."""

    id: str
    name: str
    prompt_template: str
    capabilities: List[str]
    requires_dev_container: bool


@dataclass
class RoutingDecision:
    """Decision about agent routing."""

    project: str
    issue_number: int
    board: str
    column: str
    selected_agent: str
    reason: str
    alternatives: List[str]
    workspace_type: str
    timestamp: datetime


@dataclass
class ProgressionDecision:
    """Decision about workflow progression."""

    project: str
    issue_number: int
    from_stage: str
    to_stage: Optional[str]
    action: WorkflowAction
    reason: str
    timestamp: datetime


@dataclass
class ValidationResult:
    """Result of agent validation."""

    can_run: bool
    needs_dev_setup: bool
    reason: str


@dataclass
class WorkflowState:
    """State of workflow execution."""

    in_progress_tasks: Dict[str, Dict[str, bool]]  # {column: {agent: bool}}
    current_column: Optional[str]
    current_agent: Optional[str]

    def is_in_progress(self, column: str, agent: str) -> bool:
        """Check if work is in progress for column and agent."""
        if column not in self.in_progress_tasks:
            return False
        return self.in_progress_tasks[column].get(agent, False)

    def mark_in_progress(self, column: str, agent: str) -> None:
        """Mark work as in progress."""
        if column not in self.in_progress_tasks:
            self.in_progress_tasks[column] = {}
        self.in_progress_tasks[column][agent] = True
        self.current_column = column
        self.current_agent = agent


# Port interfaces for dependencies
class ITaskQueue:
    """Interface to task queue for enqueueing work."""

    async def enqueue(self, task: Task) -> str:
        """Enqueue a task and return task_id."""
        raise NotImplementedError


class IProjectConfiguration:
    """Interface to configuration system."""

    async def get_workflow_config(self, project: str, board: str) -> WorkflowConfig:
        """Get workflow configuration for a project board."""
        raise NotImplementedError

    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get agent configuration."""
        raise NotImplementedError


class IWorkflowStateManager:
    """Interface to workflow state management."""

    async def get_workflow_state(self, issue_id: str) -> WorkflowState:
        """Get current workflow state for an issue."""
        raise NotImplementedError

    async def update_workflow_state(self, issue_id: str, state: WorkflowState) -> None:
        """Update workflow state."""
        raise NotImplementedError


class IDecisionEvents:
    """Interface to decision event emission."""

    async def emit_routing_decision(self, decision: RoutingDecision) -> None:
        """Emit agent routing decision."""
        raise NotImplementedError

    async def emit_progression_decision(self, decision: ProgressionDecision) -> None:
        """Emit workflow progression decision."""
        raise NotImplementedError


class IProjectsAPI:
    """Interface to GitHub Projects API for card movement."""

    async def move_card_to_column(
        self, project: str, issue_number: int, column_name: str
    ) -> None:
        """Move card to specified column."""
        raise NotImplementedError

    async def add_label(self, project: str, issue_number: int, label: str) -> None:
        """Add label to issue."""
        raise NotImplementedError


class WorkflowOrchestrator:
    """
    Workflow Orchestrator application service.

    Coordinates workflow execution from card movement to agent completion.
    Handles agent routing, stage progression, and decision making.

    Also acts as an event handler subscribing to adapter events:
    - workitem.column_changed: Triggers agents for automated columns
    - comment.needs_response: Triggers conversational agents
    - lock.released: Acquires lock for next queued item
    - review.status_changed: Progresses work through maker-checker cycles
    """

    def __init__(
        self,
        task_queue: ITaskQueue,
        config: IProjectConfiguration,
        workflow_state: IWorkflowStateManager,
        decision_events: IDecisionEvents,
        event_store: IEventStore,
        ticket_system: ITicketSystem,
        event_bus: Optional[EventBus] = None,
        projects_api: Optional[IProjectsAPI] = None,
    ):
        """
        Initialize workflow orchestrator.

        Args:
            task_queue: Task queue for enqueueing agent work
            config: Configuration service for workflows and agents
            workflow_state: Workflow state management
            decision_events: Decision event emission
            event_store: Event store for domain events
            ticket_system: Ticket system for issue operations
            event_bus: Event bus for subscribing to adapter events (optional)
            projects_api: Projects API for card movement (optional)
        """
        self.task_queue = task_queue
        self.config = config
        self.workflow_state = workflow_state
        self.decision_events = decision_events
        self.event_store = event_store
        self.ticket_system = ticket_system
        self.event_bus = event_bus
        self.projects_api = projects_api

        # Subscribe to adapter events if event bus is available
        if self.event_bus:
            self._subscribe_to_events()

    async def handle_card_movement(self, event: CardMovedEvent) -> WorkflowResult:
        """
        Handle card movement from GitHub Projects.

        Decision Flow:
        1. Load workflow configuration for board
        2. Find column configuration for target column
        3. Check if work already in progress
        4. Determine agent from column config
        5. Validate agent can run
        6. Create task context
        7. Enqueue task
        8. Emit routing decision
        9. Update workflow state

        Args:
            event: Card movement event

        Returns:
            WorkflowResult indicating success and next action
        """
        logger.info(
            f"Handling card movement: issue #{event.issue_number} "
            f"from {event.from_column} to {event.to_column}"
        )

        # Load configuration
        try:
            workflow_config = await self.config.get_workflow_config(
                event.project, event.board
            )
        except Exception as e:
            logger.error(f"Failed to load workflow config: {e}")
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason=f"Failed to load workflow config: {e}",
                task_id=None,
                agent_name=None,
                next_column=None,
                error=str(e),
            )

        # Find target column config
        column_config = self._find_column_config(workflow_config, event.to_column)
        if not column_config:
            logger.warning(f"Column {event.to_column} not found in workflow config")
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason=f"Column {event.to_column} not found in workflow config",
                task_id=None,
                agent_name=None,
                next_column=None,
            )

        # Check if work already in progress
        workflow_state = await self.workflow_state.get_workflow_state(
            f"{event.project}:{event.issue_number}"
        )
        if workflow_state.is_in_progress(column_config.name, column_config.agent):
            logger.info(
                f"Work already in progress for column {column_config.name} "
                f"and agent {column_config.agent}"
            )
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason="Work already in progress for this column and agent",
                task_id=None,
                agent_name=None,
                next_column=None,
            )

        # Get agent configuration
        try:
            agent_config = await self.config.get_agent_config(column_config.agent)
        except Exception as e:
            logger.error(f"Failed to load agent config: {e}")
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason=f"Failed to load agent config: {e}",
                task_id=None,
                agent_name=None,
                next_column=None,
                error=str(e),
            )

        # Validate agent can run
        validation_result = await self._validate_agent_can_run(
            event.project, column_config.agent, agent_config
        )
        if not validation_result.can_run:
            logger.warning(
                f"Agent {column_config.agent} cannot run: {validation_result.reason}"
            )
            if validation_result.needs_dev_setup:
                await self._queue_dev_setup(event.project)
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason=validation_result.reason,
                task_id=None,
                agent_name=None,
                next_column=None,
            )

        # Build task context
        task_context = self._build_task_context(
            event, column_config, workflow_config
        )

        # Create task
        task = Task(
            id=f"card_moved_{event.project}_{event.issue_number}_{int(time.time())}",
            agent=column_config.agent,
            project=event.project,
            priority=WorkItemPriority.MEDIUM,
            context=task_context,
            created_at=datetime.now(timezone.utc),
        )

        # Enqueue task
        try:
            task_id = await self.task_queue.enqueue(task)
            logger.info(f"Enqueued task {task_id} for agent {column_config.agent}")
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}")
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason=f"Failed to enqueue task: {e}",
                task_id=None,
                agent_name=None,
                next_column=None,
                error=str(e),
            )

        # Emit routing decision
        await self.decision_events.emit_routing_decision(
            RoutingDecision(
                project=event.project,
                issue_number=event.issue_number,
                board=event.board,
                column=event.to_column,
                selected_agent=column_config.agent,
                reason=f"Agent {column_config.agent} configured for column {event.to_column}",
                alternatives=[],
                workspace_type=workflow_config.workspace_type,
                timestamp=datetime.now(timezone.utc),
            )
        )

        # Update workflow state
        workflow_state.mark_in_progress(column_config.name, column_config.agent)
        await self.workflow_state.update_workflow_state(
            f"{event.project}:{event.issue_number}", workflow_state
        )

        logger.info(
            f"Successfully handled card movement for issue #{event.issue_number}"
        )
        return WorkflowResult(
            success=True,
            task_id=task_id,
            agent_name=column_config.agent,
            action=WorkflowAction.TASK_QUEUED,
            reason="Task queued for agent execution",
            next_column=None,
        )

    async def handle_stage_completion(
        self, event: StageCompletedEvent
    ) -> WorkflowResult:
        """
        Handle completion of a pipeline stage.

        Decision Flow:
        1. Load workflow and column config
        2. Check if review required
        3. If review required: Queue reviewer task
        4. If review not required and auto-advance: Move to next column
        5. Else: No action (wait for human to move card)

        Args:
            event: Stage completion event

        Returns:
            WorkflowResult indicating next action
        """
        logger.info(
            f"Handling stage completion: {event.stage_name} for issue #{event.issue_number}"
        )

        workflow_config = await self.config.get_workflow_config(
            event.project, event.context.get("board", "default")
        )

        # Find current column
        current_column_config = self._find_column_by_agent(
            workflow_config, event.agent_name
        )

        if not event.success:
            # Stage failed, emit error decision
            await self.decision_events.emit_progression_decision(
                ProgressionDecision(
                    project=event.project,
                    issue_number=event.issue_number,
                    from_stage=event.stage_name,
                    to_stage=None,
                    action=WorkflowAction.ESCALATE,
                    reason=f"Stage {event.stage_name} failed",
                    timestamp=datetime.now(timezone.utc),
                )
            )
            return WorkflowResult(
                success=False,
                action=WorkflowAction.ESCALATE,
                reason="Stage execution failed",
                task_id=None,
                agent_name=None,
                next_column=None,
            )

        # Check if review required
        if current_column_config and current_column_config.review_required:
            # Queue reviewer task
            return await self._queue_review_task(event, current_column_config)

        # Check auto-advance
        if current_column_config and current_column_config.auto_advance_on_approval:
            # Determine next column
            next_column = self._get_next_column(workflow_config, current_column_config)
            if next_column and self.projects_api:
                # Move card to next column
                await self.projects_api.move_card_to_column(
                    event.project, event.issue_number, next_column.name
                )

                await self.decision_events.emit_progression_decision(
                    ProgressionDecision(
                        project=event.project,
                        issue_number=event.issue_number,
                        from_stage=current_column_config.name,
                        to_stage=next_column.name,
                        action=WorkflowAction.AUTO_ADVANCE,
                        reason="Auto-advance on stage completion",
                        timestamp=datetime.now(timezone.utc),
                    )
                )

                return WorkflowResult(
                    success=True,
                    action=WorkflowAction.AUTO_ADVANCE,
                    task_id=None,
                    agent_name=None,
                    next_column=next_column.name,
                    reason="Auto-advanced to next column",
                )

        # No auto-advance, wait for human
        return WorkflowResult(
            success=True,
            action=WorkflowAction.COMPLETE,
            task_id=None,
            agent_name=None,
            next_column=None,
            reason="Stage complete, waiting for manual progression",
        )

    async def handle_review_cycle_completion(
        self, event: ReviewCycleCompletedEvent
    ) -> WorkflowResult:
        """
        Handle review cycle completion.

        Decision Flow:
        1. If approved: Check auto-advance and progress workflow
        2. If not approved and max iterations: Escalate to human
        3. If not approved: Queue revision task for maker

        Args:
            event: Review cycle completion event

        Returns:
            WorkflowResult indicating next action
        """
        logger.info(
            f"Handling review cycle completion for issue #{event.issue_number}, "
            f"approved={event.approved}, iteration={event.iteration}"
        )

        if event.approved:
            # Review approved, check auto-advance
            workflow_config = await self.config.get_workflow_config(
                event.project, event.context.get("board", "default")
            )

            current_column = self._find_column_by_agent(
                workflow_config, event.maker_agent
            )

            if current_column and current_column.auto_advance_on_approval:
                next_column = self._get_next_column(workflow_config, current_column)
                if next_column and self.projects_api:
                    await self.projects_api.move_card_to_column(
                        event.project, event.issue_number, next_column.name
                    )

                    return WorkflowResult(
                        success=True,
                        action=WorkflowAction.AUTO_ADVANCE,
                        task_id=None,
                        agent_name=None,
                        next_column=next_column.name,
                        reason="Review approved, auto-advanced",
                    )

            return WorkflowResult(
                success=True,
                action=WorkflowAction.COMPLETE,
                task_id=None,
                agent_name=None,
                next_column=None,
                reason="Review approved, waiting for manual progression",
            )
        else:
            # Check if max iterations reached
            max_iterations = event.context.get("max_iterations", 3)
            if event.iteration >= max_iterations:
                # Escalate to human
                if self.projects_api:
                    await self.projects_api.add_label(
                        event.project, event.issue_number, "needs-human-review"
                    )

                return WorkflowResult(
                    success=True,
                    action=WorkflowAction.ESCALATE,
                    task_id=None,
                    agent_name=None,
                    next_column=None,
                    reason=f"Max review iterations ({event.iteration}) reached, escalated",
                )

            # Queue revision task
            task_id = await self._queue_revision_task(event)

            return WorkflowResult(
                success=True,
                action=WorkflowAction.TASK_QUEUED,
                task_id=task_id,
                agent_name=event.maker_agent,
                next_column=None,
                reason=f"Changes requested, queued revision (iteration {event.iteration + 1})",
            )

    async def handle_feedback(self, event: FeedbackEvent) -> WorkflowResult:
        """
        Process human feedback and route to appropriate agent.

        Args:
            event: Feedback event

        Returns:
            WorkflowResult for feedback handling task
        """
        logger.info(
            f"Handling feedback for issue #{event.issue_number} from {event.author}"
        )

        # Create feedback handling task
        task = Task(
            id=f"feedback_{event.project}_{event.issue_number}_{int(time.time())}",
            agent="feedback_handler",  # Special agent for feedback
            project=event.project,
            priority=WorkItemPriority.HIGH,
            context={
                "issue_number": event.issue_number,
                "feedback_type": event.feedback_type,
                "feedback_content": event.content,
                "author": event.author,
                "reply_to": event.reply_to_comment_id,
            },
            created_at=datetime.now(timezone.utc),
        )

        task_id = await self.task_queue.enqueue(task)

        return WorkflowResult(
            success=True,
            action=WorkflowAction.TASK_QUEUED,
            task_id=task_id,
            agent_name="feedback_handler",
            next_column=None,
            reason="Feedback handling task queued",
        )

    # Helper methods

    def _find_column_config(
        self, workflow: WorkflowConfig, column_name: str
    ) -> Optional[ColumnConfig]:
        """Find column configuration by name."""
        for col in workflow.columns:
            if col.name == column_name:
                return col
        return None

    def _find_column_by_agent(
        self, workflow: WorkflowConfig, agent_name: str
    ) -> Optional[ColumnConfig]:
        """Find column configuration by agent name."""
        for col in workflow.columns:
            if col.agent == agent_name:
                return col
        return None

    def _get_next_column(
        self, workflow: WorkflowConfig, current: ColumnConfig
    ) -> Optional[ColumnConfig]:
        """Get next column in workflow sequence."""
        sorted_columns = sorted(workflow.columns, key=lambda c: c.position)
        for i, col in enumerate(sorted_columns):
            if col.name == current.name and i + 1 < len(sorted_columns):
                return sorted_columns[i + 1]
        return None

    async def _validate_agent_can_run(
        self, project: str, agent_name: str, agent_config: AgentConfig
    ) -> ValidationResult:
        """Validate agent can execute."""
        # Simplified validation - would check dev container state in full implementation
        if agent_config.requires_dev_container:
            # In full implementation, check if dev container image exists
            # For now, assume it can run
            pass

        return ValidationResult(can_run=True, needs_dev_setup=False, reason="")

    async def _queue_dev_setup(self, project: str) -> None:
        """Queue dev environment setup task."""
        logger.info(f"Queuing dev setup for project {project}")
        # Implementation would queue a dev setup task

    def _build_task_context(
        self,
        event: CardMovedEvent,
        column_config: ColumnConfig,
        workflow_config: WorkflowConfig,
    ) -> Dict[str, Any]:
        """Build task context from card movement event."""
        return {
            "issue_number": event.issue_number,
            "issue_title": event.issue_data.title,
            "issue_body": event.issue_data.body,
            "issue_labels": event.issue_data.labels,
            "board": event.board,
            "column": column_config.name,
            "workspace_type": workflow_config.workspace_type,
            "stage_type": column_config.stage_type,
            "review_required": column_config.review_required,
        }

    async def _queue_review_task(
        self, event: StageCompletedEvent, column_config: ColumnConfig
    ) -> WorkflowResult:
        """Queue a review task."""
        if not column_config.reviewer_agent:
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason="Review required but no reviewer configured",
                task_id=None,
                agent_name=None,
                next_column=None,
            )

        task = Task(
            id=f"review_{event.project}_{event.issue_number}_{int(time.time())}",
            agent=column_config.reviewer_agent,
            project=event.project,
            priority=WorkItemPriority.MEDIUM,
            context={
                "issue_number": event.issue_number,
                "stage_name": event.stage_name,
                "maker_agent": event.agent_name,
                "maker_output": event.output,
                **event.context,
            },
            created_at=datetime.now(timezone.utc),
        )

        task_id = await self.task_queue.enqueue(task)

        return WorkflowResult(
            success=True,
            action=WorkflowAction.TASK_QUEUED,
            task_id=task_id,
            agent_name=column_config.reviewer_agent,
            next_column=None,
            reason="Review task queued",
        )

    async def _queue_revision_task(
        self, event: ReviewCycleCompletedEvent
    ) -> str:
        """Queue a revision task for the maker."""
        task = Task(
            id=f"revision_{event.project}_{event.issue_number}_{int(time.time())}",
            agent=event.maker_agent,
            project=event.project,
            priority=WorkItemPriority.HIGH,
            context={
                "issue_number": event.issue_number,
                "iteration": event.iteration + 1,
                "feedback": event.feedback,
                "reviewer_agent": event.reviewer_agent,
                **event.context,
            },
            created_at=datetime.now(timezone.utc),
        )

        return await self.task_queue.enqueue(task)

    # Event Bus Integration (Phase 7)

    def _subscribe_to_events(self) -> None:
        """
        Subscribe workflow engine to adapter events.

        Subscribes to:
        - workitem.column_changed: Handle column transitions
        - comment.needs_response: Handle discussion responses
        - lock.released: Handle lock release and queue progression
        - review.status_changed: Handle review cycle completion
        """
        if not self.event_bus:
            return

        # Subscribe to board events
        self.event_bus.subscribe(
            EventTypes.WORKITEM_COLUMN_CHANGED,
            self._handle_column_change
        )

        # Subscribe to discussion events
        self.event_bus.subscribe(
            EventTypes.COMMENT_NEEDS_RESPONSE,
            self._handle_comment_needs_response
        )

        # Subscribe to lock events
        self.event_bus.subscribe(
            EventTypes.LOCK_RELEASED,
            self._handle_lock_released
        )

        # Subscribe to review events
        self.event_bus.subscribe(
            EventTypes.REVIEW_STATUS_CHANGED,
            self._handle_review_status_changed
        )

        logger.info("WorkflowOrchestrator subscribed to adapter events")

    async def _handle_column_change(self, event: DomainEvent) -> None:
        """
        Handle work item column change event.

        Decision Flow:
        1. Get column configuration
        2. If automated column: Try to acquire lock and trigger agent
        3. If exit column: Release lock (triggers next item in queue)
        4. If conversational column: Start discussion monitoring
        5. If leaving conversational column: Stop discussion monitoring

        Args:
            event: workitem.column_changed event
        """
        try:
            # Extract event data
            work_item_id = event.payload.get("work_item_id")
            project_id = event.payload.get("project_id")
            board_id = event.payload.get("board_id")
            to_column = event.payload.get("to_column")
            from_column = event.payload.get("from_column")
            moved_by = event.payload.get("moved_by", "unknown")

            if not all([work_item_id, project_id, board_id, to_column]):
                logger.warning(
                    f"Column change event missing required fields: {event.payload}"
                )
                return

            logger.info(
                f"Handling column change: item {work_item_id} "
                f"from '{from_column}' to '{to_column}'"
            )

            # Get workflow configuration
            try:
                workflow_config = await self.config.get_workflow_config(
                    project_id, board_id
                )
            except Exception as e:
                logger.error(f"Failed to get workflow config: {e}")
                return

            # Find target column configuration
            target_column_config = self._find_column_config(workflow_config, to_column)
            if not target_column_config:
                logger.warning(f"Column '{to_column}' not found in workflow config")
                return

            # Case 1: Automated column - trigger agent
            if target_column_config.agent:
                # Create task context
                task_context = {
                    "work_item_id": work_item_id,
                    "column": to_column,
                    "project_id": project_id,
                    "board_id": board_id,
                    "moved_by": moved_by,
                }

                # Create and enqueue task
                task = Task(
                    id=f"auto_{project_id}_{work_item_id}_{int(time.time())}",
                    agent=target_column_config.agent,
                    project=project_id,
                    priority=WorkItemPriority.MEDIUM,
                    context=task_context,
                    created_at=datetime.now(timezone.utc),
                )

                try:
                    task_id = await self.task_queue.enqueue(task)
                    logger.info(
                        f"Enqueued agent task {task_id} for column '{to_column}'"
                    )
                except Exception as e:
                    logger.error(f"Failed to enqueue task: {e}")

            # Case 2: Exit column - release lock
            if getattr(target_column_config, 'exit_column', False):
                logger.debug(f"Column '{to_column}' is exit column, releasing lock")
                # Lock release is handled by lock service on item completion
                # This is informational

            # Case 3: Conversational column - start monitoring (if implemented)
            if getattr(target_column_config, 'discussion_category', None):
                logger.debug(
                    f"Column '{to_column}' has discussion, "
                    f"would start monitoring (implementation pending)"
                )

            # Case 4: Leaving conversational column - stop monitoring
            if from_column:
                from_column_config = self._find_column_config(workflow_config, from_column)
                if from_column_config and getattr(from_column_config, 'discussion_category', None):
                    logger.debug(
                        f"Leaving discussion column '{from_column}', "
                        f"would stop monitoring (implementation pending)"
                    )

        except Exception as e:
            logger.error(f"Error handling column change event: {e}", exc_info=e)

    async def _handle_comment_needs_response(self, event: DomainEvent) -> None:
        """
        Handle comment requiring response event.

        Triggers conversational agent to respond to comment.

        Args:
            event: comment.needs_response event
        """
        try:
            work_item_id = event.payload.get("work_item_id")
            project_id = event.payload.get("project_id")
            agent_name = event.payload.get("agent_assignment")
            comment_text = event.payload.get("comment")

            if not all([work_item_id, project_id, agent_name]):
                logger.warning(
                    f"Comment event missing required fields: {event.payload}"
                )
                return

            logger.info(
                f"Handling comment response for item {work_item_id} "
                f"with agent {agent_name}"
            )

            # Create task for conversational agent
            task = Task(
                id=f"comment_{project_id}_{work_item_id}_{int(time.time())}",
                agent=agent_name,
                project=project_id,
                priority=WorkItemPriority.MEDIUM,
                context={
                    "work_item_id": work_item_id,
                    "comment": comment_text,
                    "project_id": project_id,
                },
                created_at=datetime.now(timezone.utc),
            )

            try:
                task_id = await self.task_queue.enqueue(task)
                logger.info(f"Enqueued comment response task {task_id}")
            except Exception as e:
                logger.error(f"Failed to enqueue comment response task: {e}")

        except Exception as e:
            logger.error(f"Error handling comment event: {e}", exc_info=e)

    async def _handle_lock_released(self, event: DomainEvent) -> None:
        """
        Handle pipeline lock released event.

        When a lock is released, check if there's a next item in queue
        and try to acquire lock for it.

        Args:
            event: lock.released event
        """
        try:
            project_id = event.payload.get("project_id")
            board_id = event.payload.get("board_id")
            next_in_queue = event.payload.get("next_in_queue")

            if not all([project_id, board_id]):
                logger.warning(f"Lock event missing required fields: {event.payload}")
                return

            logger.info(
                f"Lock released for {project_id}/{board_id}, "
                f"next in queue: {next_in_queue}"
            )

            if not next_in_queue:
                logger.debug("No item queued after lock release")
                return

            # Get workflow configuration
            workflow_config = await self.config.get_workflow_config(project_id, board_id)
            if not workflow_config:
                logger.warning(f"No workflow config found for project {project_id}, board {board_id}")
                return

            # Load workflow state to get item position
            try:
                # Get the column where the next item is currently located
                item_position = await self.workflow_state.get_item_position(next_in_queue)
                if not item_position:
                    logger.warning(f"Could not find position for item {next_in_queue}")
                    return

                current_column_name = item_position.get("column")
                column_config = self._find_column_config(workflow_config, current_column_name)

                if not column_config:
                    logger.warning(f"No config found for column {current_column_name}")
                    return

                # If this is an automated column, trigger the agent
                if column_config.agent:
                    logger.info(
                        f"Triggering agent {column_config.agent} for queued item {next_in_queue}"
                    )
                    await self.task_queue.enqueue({
                        "work_item_id": next_in_queue,
                        "project_id": project_id,
                        "board_id": board_id,
                        "column": current_column_name,
                        "agent": column_config.agent,
                        "priority": WorkItemPriority.NORMAL,
                    })
                else:
                    logger.debug(f"Column {current_column_name} is not automated, no agent to trigger")

            except Exception as e:
                logger.error(f"Error processing next item {next_in_queue}: {e}", exc_info=e)

        except Exception as e:
            logger.error(f"Error handling lock released event: {e}", exc_info=e)

    async def _handle_review_status_changed(self, event: DomainEvent) -> None:
        """
        Handle code review status change event.

        Progresses work item based on review status:
        - Approved: Move to next column
        - Changes requested: Move back to development column

        Args:
            event: review.status_changed event
        """
        try:
            work_item_id = event.payload.get("work_item_id")
            project_id = event.payload.get("project_id")
            new_status = event.payload.get("new_status")
            previous_status = event.payload.get("previous_status")

            if not all([work_item_id, project_id, new_status]):
                logger.warning(
                    f"Review event missing required fields: {event.payload}"
                )
                return

            logger.info(
                f"Review status changed for item {work_item_id}: "
                f"{previous_status} -> {new_status}"
            )

            if new_status == "approved":
                # Move to next column
                if self.projects_api:
                    try:
                        # Get workflow to find next column
                        board_id = event.payload.get("board_id", "default")
                        workflow_config = await self.config.get_workflow_config(
                            project_id, board_id
                        )

                        # Find current column
                        item_position = await self.workflow_state.get_item_position(work_item_id)
                        if not item_position:
                            logger.warning(f"Could not find position for item {work_item_id}")
                            return

                        current_column_name = item_position.get("column")
                        current_column = self._find_column_config(workflow_config, current_column_name)
                        if not current_column:
                            logger.warning(f"No config for column {current_column_name}")
                            return

                        # Find next column
                        next_column = self._get_next_column(workflow_config, current_column)
                        if next_column:
                            logger.info(
                                f"Moving approved item {work_item_id} from {current_column.name} to {next_column.name}"
                            )
                            await self.projects_api.move_card_to_column(
                                project_id, board_id, work_item_id, next_column.name
                            )
                        else:
                            logger.info(
                                f"No next column found for item {work_item_id} in workflow"
                            )
                    except Exception as e:
                        logger.error(f"Failed to move approved item: {e}", exc_info=e)

            elif new_status == "changes_requested":
                # Move back to development column
                if self.projects_api:
                    try:
                        board_id = event.payload.get("board_id", "default")
                        workflow_config = await self.config.get_workflow_config(
                            project_id, board_id
                        )

                        # Find development column (typically first column or has "dev" in name)
                        dev_column = None
                        for col in workflow_config.columns:
                            if col.position == 0 or "dev" in col.name.lower():
                                dev_column = col
                                break

                        if dev_column:
                            logger.info(
                                f"Moving item {work_item_id} back to development column {dev_column.name}"
                            )
                            await self.projects_api.move_card_to_column(
                                project_id, board_id, work_item_id, dev_column.name
                            )
                        else:
                            logger.warning(f"No development column found for item {work_item_id}")
                    except Exception as e:
                        logger.error(f"Failed to move item back to development: {e}", exc_info=e)

        except Exception as e:
            logger.error(f"Error handling review status event: {e}", exc_info=e)
