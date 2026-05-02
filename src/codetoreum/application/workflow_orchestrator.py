"""Workflow Orchestrator application service."""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from codetoreum.domain.board_workflow_template import ColumnTemplate
from codetoreum.domain.events import (
    DomainEvent,
)
from codetoreum.domain.events.repair_cycle_events import RepairCycleCompletedEvent
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.domain.work_item import WorkItemPriority
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_types import EventTypes
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function,
)
from codetoreum.ports.exceptions import TimeoutError as PortTimeoutError
from codetoreum.ports.input.conversational_loop_service import IConversationalLoopService
from codetoreum.ports.output import IBoardService, IEventStore, ITicketSystem
from codetoreum.ports.output.board_service import MovedByType
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService
from codetoreum.ports.output.workflow_orchestrator import IWorkflowOrchestrator

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
    task_id: str | None
    agent_name: str | None
    action: WorkflowAction
    next_column: str | None
    reason: str
    error: str | None = None


@dataclass
class CardMovedEvent:
    """Event emitted when a card moves on GitHub Projects board."""

    project: str
    board: str
    issue_number: int
    from_column: str | None
    to_column: str
    issue_data: "IssueData"
    timestamp: datetime


@dataclass
class IssueData:
    """Issue information from GitHub."""

    number: int
    title: str
    body: str
    labels: list[str]
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
    context: dict[str, Any]
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
    feedback: str | None
    timestamp: datetime
    context: dict[str, Any]


@dataclass
class FeedbackEvent:
    """Event for human feedback on agent output."""

    project: str
    issue_number: int
    feedback_type: str
    author: str
    content: str
    reply_to_comment_id: str | None
    timestamp: datetime


@dataclass
class Task:
    """Task for agent execution."""

    id: str
    agent: str
    project: str
    priority: WorkItemPriority
    context: dict[str, Any]
    created_at: datetime


@dataclass
class WorkflowConfig:
    """Workflow configuration from config system."""

    name: str
    columns: list["ColumnConfig"]
    workspace_type: str


@dataclass
class ColumnConfig:
    """Configuration for a workflow column."""

    name: str
    position: int
    agent: str
    auto_advance_on_approval: bool
    discussion_category: str | None
    stage_type: str
    review_required: bool
    reviewer_agent: str | None


@dataclass
class AgentConfig:
    """Agent configuration."""

    id: str
    name: str
    prompt_template: str
    capabilities: list[str]
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
    alternatives: list[str]
    workspace_type: str
    timestamp: datetime


@dataclass
class ProgressionDecision:
    """Decision about workflow progression."""

    project: str
    issue_number: int
    from_stage: str
    to_stage: str | None
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

    in_progress_tasks: dict[str, dict[str, bool]]  # {column: {agent: bool}}
    current_column: str | None
    current_agent: str | None

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
class ITaskQueue(ABC):
    """Interface to task queue for enqueueing work."""

    @abstractmethod
    async def enqueue(self, task: Task) -> str:
        """Enqueue a task and return task_id."""


class IProjectConfiguration(ABC):
    """Interface to configuration system."""

    @abstractmethod
    async def get_workflow_config(self, project: str, board: str) -> WorkflowConfig:
        """Get workflow configuration for a project board."""

    @abstractmethod
    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get agent configuration."""


class IWorkflowStateManager(ABC):
    """Interface to workflow state management."""

    @abstractmethod
    async def get_workflow_state(self, issue_id: str) -> WorkflowState:
        """Get current workflow state for an issue."""

    @abstractmethod
    async def update_workflow_state(self, issue_id: str, state: WorkflowState) -> None:
        """Update workflow state."""

    @abstractmethod
    async def get_item_position(self, work_item_id: str) -> dict[str, Any] | None:
        """Get current position information for a work item."""


class IDecisionEvents(ABC):
    """Interface to decision event emission."""

    @abstractmethod
    async def emit_routing_decision(self, decision: RoutingDecision) -> None:
        """Emit agent routing decision."""

    @abstractmethod
    async def emit_progression_decision(self, decision: ProgressionDecision) -> None:
        """Emit workflow progression decision."""


class IProjectsAPI(ABC):
    """Interface to GitHub Projects API for card movement."""

    @abstractmethod
    async def move_card_to_column(self, project: str, issue_number: int, column_name: str) -> None:
        """Move card to specified column."""

    @abstractmethod
    async def add_label(self, project: str, issue_number: int, label: str) -> None:
        """Add label to issue."""


class WorkflowOrchestrator(IWorkflowOrchestrator):
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
        event_bus: EventBus | None = None,
        projects_api: IProjectsAPI | None = None,
        board_service: IBoardService | None = None,
        workflow_config: IWorkflowConfigService | None = None,
        conversational_loop_orchestrator: IConversationalLoopService | None = None,
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
            board_service: Board service for querying item positions (optional)
            workflow_config: Workflow config service for column templates (optional)
            conversational_loop_orchestrator: CLO for conversational columns (optional)
        """
        self.task_queue = task_queue
        self.config = config
        self.workflow_state = workflow_state
        self.decision_events = decision_events
        self.event_store = event_store
        self.ticket_system = ticket_system
        self.event_bus = event_bus
        self.projects_api = projects_api
        self.board_service = board_service
        self._workflow_config = workflow_config
        self._conversational_loop_orchestrator = conversational_loop_orchestrator

        # Subscribe to adapter events if event bus is available
        if self.event_bus:
            self._subscribe_to_events()

    @instrument_async_function(
        name="workflow.handle_card_movement",
        attributes={"service": "workflow_orchestrator", "operation": "card_movement"},
    )
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
            f"Handling card movement: issue #{event.issue_number} from {event.from_column} to {event.to_column}"
        )

        # Load configuration
        try:
            workflow_config = await self.config.get_workflow_config(event.project, event.board)
        except Exception as e:
            logger.error(
                f"Failed to load workflow config: {e}",
                exc_info=True,
                extra={"error_id": "ERR_ORCHESTRATOR_CONFIG_LOAD_FAILURE"},
            )
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
            logger.warning(
                f"Column {event.to_column} not found in workflow config",
                extra={"error_id": "ERR_ORCHESTRATOR_COLUMN_CONFIG_NOT_FOUND"},
            )
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason=f"Column {event.to_column} not found in workflow config",
                task_id=None,
                agent_name=None,
                next_column=None,
            )

        # Check if work already in progress
        workflow_state = await self.workflow_state.get_workflow_state(f"{event.project}:{event.issue_number}")
        if workflow_state.is_in_progress(column_config.name, column_config.agent):
            logger.info(f"Work already in progress for column {column_config.name} and agent {column_config.agent}")
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
            logger.error(
                f"Failed to load agent config: {e}",
                exc_info=True,
                extra={"error_id": "ERR_ORCHESTRATOR_AGENT_CONFIG_LOAD_FAILURE"},
            )
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
        validation_result = await self._validate_agent_can_run(event.project, column_config.agent, agent_config)
        if not validation_result.can_run:
            logger.warning(
                f"Agent {column_config.agent} cannot run: {validation_result.reason}",
                extra={"error_id": "ERR_ORCHESTRATOR_AGENT_VALIDATION_FAILURE"},
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
        task_context = self._build_task_context(event, column_config, workflow_config)

        # Create task
        task = Task(
            id=f"card_moved_{event.project}_{event.issue_number}_{int(time.time())}",
            agent=column_config.agent,
            project=event.project,
            priority=WorkItemPriority.MEDIUM,
            context=task_context,
            created_at=datetime.now(UTC),
        )

        # Enqueue task
        try:
            task_id = await self.task_queue.enqueue(task)
            logger.info(f"Enqueued task {task_id} for agent {column_config.agent}")
        except Exception as e:
            logger.error(
                f"CRITICAL: Failed to enqueue agent task for work_item={event.issue_number}, "
                f"column='{event.to_column}', agent='{column_config.agent}'. "
                f"Work item has been moved to column but will not be processed automatically.",
                exc_info=True,
                extra={
                    "error_id": "ERR_ORCHESTRATOR_HANDLER_ENQUEUE_FAILURE",
                    "work_item_id": event.issue_number,
                    "project_id": event.project,
                    "board_id": event.board,
                    "column": event.to_column,
                    "agent": column_config.agent,
                    "error_type": type(e).__name__,
                },
            )
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
                timestamp=datetime.now(UTC),
            )
        )

        # Update workflow state
        workflow_state.mark_in_progress(column_config.name, column_config.agent)
        await self.workflow_state.update_workflow_state(f"{event.project}:{event.issue_number}", workflow_state)

        logger.info(f"Successfully handled card movement for issue #{event.issue_number}")
        return WorkflowResult(
            success=True,
            task_id=task_id,
            agent_name=column_config.agent,
            action=WorkflowAction.TASK_QUEUED,
            reason="Task queued for agent execution",
            next_column=None,
        )

    @instrument_async_function(
        name="workflow.handle_stage_completion",
        attributes={"service": "workflow_orchestrator", "operation": "stage_completion"},
    )
    async def handle_stage_completion(self, event: StageCompletedEvent) -> WorkflowResult:
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
        logger.info(f"Handling stage completion: {event.stage_name} for issue #{event.issue_number}")

        # StageCompletedEvent.context is guaranteed to be Dict[str, Any] by type contract
        board_name = event.context.get("board", "default")
        workflow_config = await self.config.get_workflow_config(event.project, board_name)

        # Find current column
        current_column_config = self._find_column_by_agent(workflow_config, event.agent_name)

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
                    timestamp=datetime.now(UTC),
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
                await self.projects_api.move_card_to_column(event.project, event.issue_number, next_column.name)

                await self.decision_events.emit_progression_decision(
                    ProgressionDecision(
                        project=event.project,
                        issue_number=event.issue_number,
                        from_stage=current_column_config.name,
                        to_stage=next_column.name,
                        action=WorkflowAction.AUTO_ADVANCE,
                        reason="Auto-advance on stage completion",
                        timestamp=datetime.now(UTC),
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

    @instrument_async_function(
        name="workflow.handle_review_cycle_completion",
        attributes={"service": "workflow_orchestrator", "operation": "review_completion"},
    )
    async def handle_review_cycle_completion(self, event: ReviewCycleCompletedEvent) -> WorkflowResult:
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

        # ReviewCycleCompletedEvent.context is guaranteed to be Dict[str, Any] by type contract
        board_name = event.context.get("board", "default")

        if event.approved:
            # Review approved, check auto-advance
            workflow_config = await self.config.get_workflow_config(event.project, board_name)

            current_column = self._find_column_by_agent(workflow_config, event.maker_agent)

            if current_column and current_column.auto_advance_on_approval:
                next_column = self._get_next_column(workflow_config, current_column)
                if next_column and self.projects_api:
                    await self.projects_api.move_card_to_column(event.project, event.issue_number, next_column.name)

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
        # Check if max iterations reached
        max_iterations = event.context.get("max_iterations", 3)
        if event.iteration >= max_iterations:
            # Escalate to human
            if self.projects_api:
                await self.projects_api.add_label(event.project, event.issue_number, "needs-human-review")

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

    @instrument_async_function(
        name="workflow.handle_feedback",
        attributes={"service": "workflow_orchestrator", "operation": "feedback"},
    )
    async def handle_feedback(self, event: FeedbackEvent) -> WorkflowResult:
        """
        Process human feedback and route to appropriate agent.

        Args:
            event: Feedback event

        Returns:
            WorkflowResult for feedback handling task
        """
        logger.info(f"Handling feedback for issue #{event.issue_number} from {event.author}")

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
            created_at=datetime.now(UTC),
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

    def _find_column_config(self, workflow: WorkflowConfig, column_name: str) -> ColumnConfig | None:
        """Find column configuration by name."""
        for col in workflow.columns:
            if col.name == column_name:
                return col
        return None

    def _find_column_by_agent(self, workflow: WorkflowConfig, agent_name: str) -> ColumnConfig | None:
        """Find column configuration by agent name."""
        for col in workflow.columns:
            if col.agent == agent_name:
                return col
        return None

    def _get_next_column(self, workflow: WorkflowConfig, current: ColumnConfig) -> ColumnConfig | None:
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
    ) -> dict[str, Any]:
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

    async def _queue_review_task(self, event: StageCompletedEvent, column_config: ColumnConfig) -> WorkflowResult:
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
            created_at=datetime.now(UTC),
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

    async def _queue_revision_task(self, event: ReviewCycleCompletedEvent) -> str:
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
            created_at=datetime.now(UTC),
        )

        return await self.task_queue.enqueue(task)

    # Event Bus Integration

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

        # Subscribe to board events.
        # NOTE: EventBus routes callbacks by event.event_type, which is the Python class name
        # ("WorkItemColumnChanged"), not the dot-notation constant in EventTypes.
        # Using the class name here ensures this callback actually receives the event.
        self.event_bus.subscribe("WorkItemColumnChanged", self._handle_column_change)

        # Subscribe to discussion events
        self.event_bus.subscribe(EventTypes.COMMENT_NEEDS_RESPONSE, self._handle_comment_needs_response)

        # Subscribe to lock events
        self.event_bus.subscribe(EventTypes.LOCK_RELEASED, self._handle_lock_released)

        # Subscribe to review events
        self.event_bus.subscribe(EventTypes.REVIEW_STATUS_CHANGED, self._handle_review_status_changed)

        # Subscribe to repair cycle events (keyed by class name — EventBus routes by event.event_type)
        self.event_bus.subscribe("RepairCycleCompletedEvent", self._handle_repair_cycle_completed)

        logger.info("WorkflowOrchestrator subscribed to adapter events")

    @instrument_async_function(
        name="workflow.handle_column_change",
        attributes={"service": "workflow_orchestrator", "event_handler": "true"},
    )
    async def _handle_column_change(self, event: DomainEvent) -> None:
        """
        Handle work item column change event.

        Decision Flow:
        1. Get column configuration
        2. If automated column: Trigger agent (lock acquisition is handled by BoardEventHandler)
        3. If exit column: Log for reference (lock release is handled by BoardEventHandler)
        4. If conversational column: Start discussion monitoring
        5. If leaving conversational column: Stop discussion monitoring

        Note: Lock acquisition and release are orchestrated by BoardEventHandler, not here.
        The WorkflowOrchestrator focuses on task queue management and agent triggering
        based on column configuration. When a lock is released, the orchestrator reacts
        via _handle_lock_released() to check for queued items and continue processing.

        Args:
            event: workitem.column_changed event
        """
        # Validate event structure upfront - extract required fields with safe defaults
        # (KeyError will not be raised due to .get() usage; validation occurs below)
        work_item_id: str = event.payload.get("work_item_id") or ""
        project_id: str = event.payload.get("project_id") or ""
        board_id: str = event.payload.get("board_id") or ""
        to_column: str = event.payload.get("to_column") or ""
        moved_by: str = event.payload.get("moved_by") or "unknown"

        if not all([work_item_id, project_id, board_id, to_column]):
            logger.warning(
                "Column change event has empty required fields",
                extra={
                    "error_id": "ERR_ORCHESTRATOR_COLUMN_CHANGE_VALIDATION_FAILURE",
                    "event_payload": event.payload,
                },
            )
            return

        try:
            # Find target column configuration.
            # Prefer IWorkflowConfigService (new Gen2 YAML-seeded config) because it
            # returns ColumnTemplate with execution_type and agent_id.  Fall back to the
            # old MockProjectConfiguration path for backwards compatibility.
            target_column_config: ColumnConfig | ColumnTemplate | None = None
            if self._workflow_config:
                try:
                    board_template = await self._workflow_config.get_board_workflow_template(board_id)
                    if board_template:
                        target_column_config = board_template.get_column_config(to_column)
                except Exception as e:
                    logger.warning(
                        f"Failed to get board workflow template from Gen2 config for board={board_id}, "
                        f"falling back to legacy path: {e}",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_ORCHESTRATOR_WORKFLOW_CONFIG_LOOKUP",
                            "board_id": board_id,
                            "error_type": type(e).__name__,
                        },
                    )

            if target_column_config is None:
                # Legacy path: old-style WorkflowConfig
                try:
                    workflow_config = await self.config.get_workflow_config(project_id, board_id)
                except PortTimeoutError as e:
                    logger.error(
                        f"Failed to get workflow config for project={project_id}, board={board_id}: {e}",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_ORCHESTRATOR_CONFIG_TIMEOUT",
                            "project_id": project_id,
                            "board_id": board_id,
                            "work_item_id": work_item_id,
                            "error_type": type(e).__name__,
                        },
                    )
                    return
                target_column_config = self._find_column_config(workflow_config, to_column)

            if not target_column_config:
                logger.warning(
                    f"Column '{to_column}' not found in workflow config",
                    extra={"error_id": "ERR_ORCHESTRATOR_HANDLER_COLUMN_NOT_FOUND"},
                )
                return

            # Resolve agent ID — ColumnTemplate uses agent_id; legacy ColumnConfig uses agent
            agent_id = getattr(target_column_config, "agent_id", None) or getattr(target_column_config, "agent", None)

            # Case 1: Automated column — dispatch based on execution_type
            if agent_id:
                execution_type = getattr(target_column_config, "execution_type", "task_queue")

                if execution_type == "conversational":
                    # Conversational column: initialize loop via ConversationalLoopOrchestrator
                    if self._conversational_loop_orchestrator:
                        try:
                            await self._conversational_loop_orchestrator.initialize_loop(
                                work_item_id=work_item_id,
                                project_id=project_id,
                                column_config={
                                    "agent_assignment": agent_id,
                                    "column_name": to_column,
                                },
                            )
                            logger.info(
                                f"Initialized conversational loop for work_item={work_item_id}, "
                                f"column='{to_column}', agent='{agent_id}'"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to initialize conversational loop for work_item={work_item_id}, "
                                f"column='{to_column}': {e}",
                                exc_info=True,
                                extra={"error_id": "ERR_ORCHESTRATOR_CONVERSATIONAL_LOOP_INIT_FAILURE"},
                            )
                    else:
                        logger.warning(
                            f"Column '{to_column}' is conversational but no ConversationalLoopOrchestrator is wired. "
                            f"Falling back to task queue.",
                            extra={"error_id": "ERR_ORCHESTRATOR_CLO_NOT_WIRED"},
                        )
                        # Fall back to task queue
                        await self._enqueue_agent_task(
                            work_item_id, project_id, board_id, to_column, moved_by, target_column_config
                        )
                else:
                    # Standard task_queue: enqueue agent task
                    await self._enqueue_agent_task(
                        work_item_id, project_id, board_id, to_column, moved_by, target_column_config
                    )

            # Case 2: Exit column - log for reference
            if getattr(target_column_config, "exit_column", False):
                logger.debug(f"Column '{to_column}' is exit column")
                # Lock release is handled by BoardEventHandler when item moves to exit column.
                # This ensures all lock cleanup and next-item queue processing happens
                # in one coordinated place. WorkflowOrchestrator reacts to lock.released
                # events via _handle_lock_released().

        except Exception as e:
            logger.error(
                f"Error handling column change event for work_item={work_item_id}, "
                f"project={project_id}, board={board_id}",
                exc_info=True,
                extra={
                    "error_id": "ERR_ORCHESTRATOR_COLUMN_CHANGE_HANDLER_FAILURE",
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "board_id": board_id,
                    "error_type": type(e).__name__,
                },
            )

    async def _enqueue_agent_task(
        self,
        work_item_id: str,
        project_id: str,
        board_id: str,
        to_column: str,
        moved_by: str,
        column_config: "ColumnConfig | ColumnTemplate",
    ) -> None:
        """Enqueue an agent task for standard task_queue execution.

        Args:
            work_item_id: The work item to process
            project_id: The project context
            board_id: The board context
            to_column: Target column name
            moved_by: Actor who triggered the move
            column_config: Column configuration with agent assignment (ColumnConfig
                uses .agent; ColumnTemplate uses .agent_id)
        """
        # Resolve agent name: ColumnConfig uses .agent, ColumnTemplate uses .agent_id
        agent_name = getattr(column_config, "agent", None) or getattr(column_config, "agent_id", None) or ""
        task_context = {
            "work_item_id": work_item_id,
            "column": to_column,
            "project_id": project_id,
            "board_id": board_id,
            "moved_by": moved_by,
        }

        task = Task(
            id=f"auto_{project_id}_{work_item_id}_{int(time.time())}",
            agent=agent_name,
            project=project_id,
            priority=WorkItemPriority.MEDIUM,
            context=task_context,
            created_at=datetime.now(UTC),
        )

        try:
            task_id = await self.task_queue.enqueue(task)
            logger.info(f"Enqueued agent task {task_id} for column '{to_column}'")
        except Exception as e:
            logger.error(
                f"CRITICAL: Failed to enqueue agent task for work_item={work_item_id}, "
                f"column='{to_column}', agent='{agent_name}'. "
                f"Work item has been moved to column but will not be processed automatically.",
                exc_info=True,
                extra={
                    "error_id": "ERR_ORCHESTRATOR_TASK_ENQUEUE_FAILURE",
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "board_id": board_id,
                    "column": to_column,
                    "agent": agent_name,
                    "error_type": type(e).__name__,
                },
            )

    @instrument_async_function(
        name="workflow.handle_comment_needs_response",
        attributes={"service": "workflow_orchestrator", "event_handler": "true"},
    )
    async def _handle_comment_needs_response(self, event: DomainEvent) -> None:
        """
        Handle comment requiring response event.

        Triggers conversational agent to respond to comment.

        Args:
            event: comment.needs_response event
        """
        # Validate event structure upfront - extract required fields with safe defaults
        # (KeyError will not be raised due to .get() usage; validation occurs below)
        work_item_id: str = event.payload.get("work_item_id") or ""
        project_id: str = event.payload.get("project_id") or ""
        agent_name: str = event.payload.get("agent_assignment") or ""
        comment_text: str = event.payload.get("comment") or ""

        if not all([work_item_id, project_id, agent_name]):
            logger.warning(
                "Comment event has empty required fields",
                extra={
                    "error_id": "ERR_ORCHESTRATOR_COMMENT_EVENT_VALIDATION_FAILURE",
                    "event_payload": event.payload,
                },
            )
            return

        logger.info(f"Handling comment response for item {work_item_id} with agent {agent_name}")

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
            created_at=datetime.now(UTC),
        )

        try:
            try:
                task_id = await self.task_queue.enqueue(task)
                logger.info(f"Enqueued comment response task {task_id}")
            except Exception as e:
                logger.error(
                    f"Failed to enqueue comment response task for work_item={work_item_id}, project={project_id}: {e}",
                    exc_info=True,
                    extra={
                        "error_id": "ERR_ORCHESTRATOR_COMMENT_RESPONSE_ENQUEUE_FAILURE",
                        "work_item_id": work_item_id,
                        "project_id": project_id,
                        "agent_name": agent_name,
                        "error_type": type(e).__name__,
                    },
                )
                raise

        except Exception as e:
            logger.error(
                f"Error handling comment event for work_item={work_item_id}, project={project_id}",
                exc_info=True,
                extra={
                    "error_id": "ERR_ORCHESTRATOR_COMMENT_HANDLER_FAILURE",
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "error_type": type(e).__name__,
                },
            )

    @instrument_async_function(
        name="workflow.handle_lock_released",
        attributes={"service": "workflow_orchestrator", "event_handler": "true"},
    )
    async def _handle_lock_released(self, event: DomainEvent) -> None:
        """
        Handle pipeline lock released event.

        When a lock is released, check if there's a next item in queue
        and trigger its agent if configured.

        Args:
            event: lock.released event with project_id, board_id, next_in_queue
        """
        # Validate event structure upfront - extract required fields with safe defaults
        # (KeyError will not be raised due to .get() usage; validation occurs below)
        project_id: str = event.payload.get("project_id") or ""
        board_id: str = event.payload.get("board_id") or ""
        next_in_queue: str = event.payload.get("next_in_queue") or ""

        if not all([project_id, board_id]):
            logger.warning(
                "Lock event has empty required fields",
                extra={
                    "error_id": "ERR_ORCHESTRATOR_LOCK_EVENT_VALIDATION_FAILURE",
                    "event_payload": event.payload,
                },
            )
            return

        logger.info(f"Lock released for {project_id}/{board_id}, next in queue: {next_in_queue}")

        try:
            if not next_in_queue:
                logger.debug("No item queued after lock release")
                return

            # Board service required for processing next item
            if not self.board_service:
                logger.warning(
                    "Board service not configured, cannot process next queued item",
                    extra={"error_id": "ERR_ORCHESTRATOR_BOARD_SERVICE_NOT_CONFIGURED"},
                )
                return

            # Get workflow configuration
            workflow_config = await self.config.get_workflow_config(project_id, board_id)
            if not workflow_config:
                logger.warning(f"No workflow config found for project {project_id}, board {board_id}")
                return

            # Get the column where the next item is currently located
            try:
                item_position = await self.board_service.get_item_position(next_in_queue)
                if not item_position:
                    logger.warning(
                        f"Could not find position for item {next_in_queue}",
                        extra={"error_id": "ERR_ORCHESTRATOR_ITEM_POSITION_NOT_FOUND"},
                    )
                    return

                current_column_name = item_position.column_name
                column_config = self._find_column_config(workflow_config, current_column_name)

                if not column_config:
                    logger.warning(
                        f"No config found for column {current_column_name}",
                        extra={"error_id": "ERR_ORCHESTRATOR_QUEUE_COLUMN_CONFIG_NOT_FOUND"},
                    )
                    return

                # If this is an automated column, trigger the agent
                if column_config.agent:
                    logger.info(f"Triggering agent {column_config.agent} for queued item {next_in_queue}")
                    task = Task(
                        id=next_in_queue,
                        agent=column_config.agent,
                        project=project_id,
                        priority=WorkItemPriority.MEDIUM,
                        context={
                            "board_id": board_id,
                            "column": current_column_name,
                            "queued_item": True,
                        },
                        created_at=datetime.now(UTC),
                    )
                    await self.task_queue.enqueue(task)
                else:
                    logger.debug(f"Column {current_column_name} is not automated, no agent to trigger")

            except Exception as e:
                logger.error(
                    f"Error processing next queued item={next_in_queue} after lock release "
                    f"for project={project_id}, board={board_id}: {e}",
                    exc_info=True,
                    extra={
                        "error_id": "ERR_ORCHESTRATOR_QUEUED_ITEM_PROCESS_FAILURE",
                        "work_item_id": next_in_queue,
                        "project_id": project_id,
                        "board_id": board_id,
                        "error_type": type(e).__name__,
                    },
                )
                raise

        except Exception as e:
            logger.error(
                f"Error handling lock released event for project={project_id}, board={board_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_ORCHESTRATOR_LOCK_RELEASED_HANDLER_FAILURE",
                    "project_id": project_id,
                    "board_id": board_id,
                    "next_in_queue": next_in_queue,
                    "error_type": type(e).__name__,
                },
            )

    @instrument_async_function(
        name="workflow.handle_review_status_changed",
        attributes={"service": "workflow_orchestrator", "event_handler": "true"},
    )
    async def _handle_review_status_changed(self, event: DomainEvent) -> None:
        """
        Handle code review status change event.

        Progresses work item based on review status:
        - Approved: Move to next column
        - Changes requested: Move back to development column

        Args:
            event: review.status_changed event
        """
        work_item_id: str = event.payload.get("work_item_id") or ""
        project_id: str = event.payload.get("project_id") or ""
        new_status: str = event.payload.get("new_status") or ""
        previous_status: str = event.payload.get("previous_status") or ""

        if not all([work_item_id, project_id, new_status]):
            logger.warning(
                f"Review event missing required fields: {event.payload}",
                extra={"error_id": "ERR_ORCHESTRATOR_REVIEW_EVENT_VALIDATION_FAILURE"},
            )
            return

        logger.info(f"Review status changed for item {work_item_id}: {previous_status} -> {new_status}")

        if new_status == "approved":
            # Move to next column
            if self.projects_api:
                try:
                    # Get workflow to find next column
                    board_id_local: str = event.payload.get("board_id") or "default"
                    workflow_config = await self.config.get_workflow_config(project_id, board_id_local)

                    # Find current column
                    item_position = await self.workflow_state.get_item_position(work_item_id)
                    if not item_position:
                        logger.warning(
                            f"Could not find position for item {work_item_id}",
                            extra={"error_id": "ERR_ORCHESTRATOR_REVIEW_ITEM_POSITION_NOT_FOUND"},
                        )
                        return

                    current_column_name: str = item_position.get("column") or ""
                    current_column = self._find_column_config(workflow_config, current_column_name)
                    if not current_column:
                        logger.warning(
                            f"No config for column {current_column_name}",
                            extra={"error_id": "ERR_ORCHESTRATOR_REVIEW_COLUMN_CONFIG_NOT_FOUND"},
                        )
                        return

                    # Find next column
                    next_column = self._get_next_column(workflow_config, current_column)
                    if next_column:
                        logger.info(
                            f"Moving approved item {work_item_id} from {current_column.name} to {next_column.name}"
                        )
                        await self.projects_api.move_card_to_column(project_id, int(work_item_id), next_column.name)
                    else:
                        logger.info(f"No next column found for item {work_item_id} in workflow")
                except Exception as e:
                    logger.error(
                        f"Failed to move approved item: {e}",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_ORCHESTRATOR_APPROVED_ITEM_MOVE_FAILURE",
                            "work_item_id": work_item_id,
                            "project_id": project_id,
                            "board_id": board_id_local,
                            "error_type": type(e).__name__,
                        },
                    )
                    raise

        elif new_status == "changes_requested":
            # Move back to development column
            if self.projects_api:
                try:
                    board_id_local2: str = event.payload.get("board_id") or "default"
                    workflow_config = await self.config.get_workflow_config(project_id, board_id_local2)

                    # Find development column (typically first column or has "dev" in name)
                    dev_column = None
                    for col in workflow_config.columns:
                        if col.position == 0 or "dev" in col.name.lower():
                            dev_column = col
                            break

                    if dev_column:
                        logger.info(f"Moving item {work_item_id} back to development column {dev_column.name}")
                        await self.projects_api.move_card_to_column(project_id, int(work_item_id), dev_column.name)
                    else:
                        logger.warning(
                            f"No development column found for item {work_item_id}",
                            extra={"error_id": "ERR_ORCHESTRATOR_DEV_COLUMN_NOT_FOUND"},
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to move item back to development: {e}",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_ORCHESTRATOR_CHANGES_REQUESTED_MOVE_FAILURE",
                            "work_item_id": work_item_id,
                            "project_id": project_id,
                            "board_id": board_id_local2,
                            "error_type": type(e).__name__,
                        },
                    )
                    raise

    @instrument_async_function(
        name="workflow.handle_repair_cycle_completed",
        attributes={"service": "workflow_orchestrator", "event_handler": "true"},
    )
    async def _handle_repair_cycle_completed(self, event: DomainEvent) -> None:
        """
        Handle repair cycle completed event.

        Progresses work item based on repair cycle outcome:
        - overall_success=True: Move to next column (auto-progress)
        - overall_success=False: Move to failure column if configured, else log warning

        Args:
            event: repair_cycle.completed DomainEvent whose payload is deserialized
                   into a RepairCycleCompletedEvent
        """
        # The event arrives as a RepairCycleCompletedEvent (CodetoreumEvent duck-typed via EventBus).
        # Access fields directly — no payload deserialization needed.
        if not isinstance(event, RepairCycleCompletedEvent):
            logger.error(
                f"_handle_repair_cycle_completed received unexpected event type: {type(event).__name__}",
                extra={"error_id": "ERR_ORCHESTRATOR_REPAIR_CYCLE_EVENT_DESERIALIZATION_FAILURE"},
            )
            return

        typed_event = event

        # Resolve work_item_id: prefer explicit field, fall back to workflow_run_id
        work_item_id: str = typed_event.work_item_id or typed_event.workflow_run_id
        board_id: str = typed_event.board_id

        if not work_item_id or not board_id:
            logger.warning(
                "RepairCycleCompletedEvent missing work_item_id or board_id — cannot advance workflow",
                extra={
                    "error_id": "ERR_ORCHESTRATOR_REPAIR_CYCLE_EVENT_MISSING_IDS",
                    "work_item_id": work_item_id,
                    "board_id": board_id,
                    "workflow_run_id": typed_event.workflow_run_id,
                },
            )
            return

        if not self.board_service:
            logger.warning(
                "Board service not configured, cannot process repair cycle completion",
                extra={"error_id": "ERR_ORCHESTRATOR_BOARD_SERVICE_NOT_CONFIGURED"},
            )
            return

        if not self.board_service or not self._workflow_config:
            logger.warning(
                "board_service or workflow_config not configured — cannot advance workflow after repair cycle",
                extra={"error_id": "ERR_ORCHESTRATOR_REPAIR_CYCLE_MISSING_DEPS"},
            )
            return

        try:
            item_position = await self.board_service.get_item_position(work_item_id)
            if not item_position:
                logger.warning(
                    f"Could not find position for item {work_item_id} after repair cycle",
                    extra={
                        "error_id": "ERR_ORCHESTRATOR_REPAIR_CYCLE_ITEM_POSITION_NOT_FOUND",
                        "work_item_id": work_item_id,
                        "board_id": board_id,
                    },
                )
                return

            current_column_name: str = item_position.column_name

            # Load column template for progression rules (on_failure_column, position ordering)
            template = await self._workflow_config.get_board_workflow_template(board_id)
            if not template:
                logger.warning(
                    f"No workflow template for board '{board_id}' — cannot advance after repair cycle",
                    extra={
                        "error_id": "ERR_ORCHESTRATOR_REPAIR_CYCLE_COLUMN_CONFIG_NOT_FOUND",
                        "work_item_id": work_item_id,
                        "board_id": board_id,
                    },
                )
                return

            if typed_event.overall_success:
                next_column_name = template.get_next_column(current_column_name)
                if next_column_name:
                    logger.info(
                        f"Repair cycle succeeded for {work_item_id}: "
                        f"advancing from '{current_column_name}' to '{next_column_name}'"
                    )
                    await self.board_service.move_item_to_column(
                        work_item_id, next_column_name, MovedByType.ORCHESTRATOR
                    )
                else:
                    logger.info(
                        f"Repair cycle succeeded for {work_item_id}: "
                        f"no next column after '{current_column_name}', workflow complete"
                    )
            else:
                current_column = template.get_column_config(current_column_name)
                failure_column: str | None = (
                    getattr(current_column, "on_failure_column", None) if current_column else None
                )

                if failure_column:
                    logger.warning(
                        f"Repair cycle failed for {work_item_id}: "
                        f"moving from '{current_column_name}' to failure column '{failure_column}'"
                    )
                    await self.board_service.move_item_to_column(work_item_id, failure_column, MovedByType.ORCHESTRATOR)
                else:
                    logger.warning(
                        f"Repair cycle failed for {work_item_id} in column '{current_column_name}': "
                        "no failure column configured, item remains in current column"
                    )

        except Exception as e:
            logger.error(
                f"Error handling repair cycle completed for work_item={work_item_id}, board={board_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_ORCHESTRATOR_REPAIR_CYCLE_HANDLER_FAILURE",
                    "work_item_id": work_item_id,
                    "board_id": board_id,
                    "overall_success": typed_event.overall_success,
                    "error_type": type(e).__name__,
                },
            )

    @instrument_async_function(
        name="workflow.orchestrate_project",
        attributes={"service": "workflow_orchestrator", "operation": "orchestrate_project"},
    )
    async def orchestrate_project(self, project_name: str, workspace_path: str, config: ProjectConfig) -> int:
        """Execute orchestration for a single project.

        Coordinates all workflow activities for the project:
        1. Polls project board for work items needing processing
        2. Routes items to appropriate agents
        3. Queues agent execution tasks

        Args:
            project_name: Name of the project
            workspace_path: Local workspace path for the project
            config: Project configuration (repo, branch, enabled status)

        Returns:
            int: Number of actions taken (tasks queued, etc.)

        Raises:
            ExternalServiceError: External service communication failure
        """
        actions_taken = 0
        error_count = 0

        # Check if project is enabled before proceeding
        if not config.enabled:
            logger.info(
                f"Project {project_name} is disabled in configuration, skipping orchestration",
                extra={"project_name": project_name},
            )
            return actions_taken

        if not self.board_service:
            logger.warning(
                f"Board service not available, skipping orchestration for {project_name}",
                extra={"error_id": "ERR_ORCHESTRATOR_NO_BOARD_SERVICE", "project_name": project_name},
            )
            return actions_taken

        try:
            # Get all boards for the project
            all_boards = await self.board_service.get_all_boards()
            logger.debug(f"Retrieved {len(all_boards)} boards for orchestration of {project_name}")

            # Process each board for the project
            for board in all_boards:
                if board.project_id != project_name:
                    continue

                logger.debug(f"Processing board {board.name} for project {project_name}")

                # Get all work items on this board
                board_items = await self.board_service.get_board_items(project_id=project_name, board_id=board.id)
                logger.debug(f"Found {len(board_items)} items on board {board.name}")

                # Get workflow configuration
                try:
                    workflow_config = await self.config.get_workflow_config(project_name, board.name)
                except Exception as e:
                    logger.error(
                        f"Failed to load workflow config for board {board.name}, skipping all items on board: {e}",
                        exc_info=True,
                        extra={"error_id": "ERR_ORCHESTRATOR_CONFIG_LOAD", "board": board.name},
                    )
                    continue

                # Process each work item
                for item in board_items:
                    try:
                        # Validate work_item_id is numeric before any operations
                        try:
                            issue_number = int(item.work_item_id)
                        except ValueError as e:
                            logger.warning(
                                f"Invalid work_item_id format (not numeric): {item.work_item_id}",
                                exc_info=True,
                                extra={
                                    "error_id": "ERR_ORCHESTRATOR_INVALID_WORK_ITEM_ID",
                                    "work_item_id": item.work_item_id,
                                    "project": project_name,
                                },
                            )
                            continue

                        # Find the column configuration for this item's current column
                        column_config = self._find_column_config(workflow_config, item.column_name)
                        if not column_config:
                            logger.debug(f"No column config for {item.column_name}, skipping {item.work_item_id}")
                            continue

                        # Check if work is already in progress for this agent
                        workflow_state = await self.workflow_state.get_workflow_state(
                            f"{project_name}:{item.work_item_id}"
                        )
                        if workflow_state.is_in_progress(column_config.name, column_config.agent):
                            logger.debug(
                                f"Work already in progress for {item.work_item_id}, agent {column_config.agent}"
                            )
                            continue

                        # Validate agent can run
                        try:
                            agent_config = await self.config.get_agent_config(column_config.agent)
                        except Exception as e:
                            logger.warning(
                                f"Failed to load agent config for {column_config.agent}: {e}",
                                exc_info=True,
                                extra={"error_id": "ERR_ORCHESTRATOR_AGENT_CONFIG_LOAD"},
                            )
                            continue

                        validation_result = await self._validate_agent_can_run(
                            project_name, column_config.agent, agent_config
                        )
                        if not validation_result.can_run:
                            logger.debug(
                                f"Agent {column_config.agent} cannot run: {validation_result.reason}",
                                extra={"error_id": "ERR_ORCHESTRATOR_AGENT_VALIDATION"},
                            )
                            if validation_result.needs_dev_setup:
                                await self._queue_dev_setup(project_name)
                            continue

                        # Build task context and enqueue
                        task_context = {
                            "project": project_name,
                            "work_item_id": item.work_item_id,
                            "workspace_path": workspace_path,
                            "column": item.column_name,
                            "board": board.name,
                        }

                        task = Task(
                            id=f"orchestrate_{project_name}_{item.work_item_id}_{int(time.time())}",
                            agent=column_config.agent,
                            project=project_name,
                            priority=WorkItemPriority.MEDIUM,
                            context=task_context,
                            created_at=datetime.now(UTC),
                        )

                        task_id = await self.task_queue.enqueue(task)
                        logger.info(f"Enqueued task {task_id} for {item.work_item_id} via orchestrate_project")

                        # Emit routing decision
                        await self.decision_events.emit_routing_decision(
                            RoutingDecision(
                                project=project_name,
                                issue_number=issue_number,
                                board=board.name,
                                column=item.column_name,
                                selected_agent=column_config.agent,
                                reason=f"Agent {column_config.agent} configured for column {item.column_name}",
                                alternatives=[],
                                workspace_type=workflow_config.workspace_type,
                                timestamp=datetime.now(UTC),
                            )
                        )

                        # Update workflow state
                        workflow_state.mark_in_progress(column_config.name, column_config.agent)
                        await self.workflow_state.update_workflow_state(
                            f"{project_name}:{item.work_item_id}", workflow_state
                        )

                        actions_taken += 1

                    except Exception as e:
                        logger.error(
                            f"Error processing work item {item.work_item_id} during orchestrate_project: {e}",
                            exc_info=True,
                            extra={
                                "error_id": "ERR_ORCHESTRATOR_ITEM_PROCESSING",
                                "work_item_id": item.work_item_id,
                                "project": project_name,
                                "error_type": type(e).__name__,
                            },
                        )
                        error_count += 1
                        continue

            logger.info(
                f"Orchestrated project {project_name}: {actions_taken} actions taken, {error_count} errors encountered",
                extra={"error_id": "ERR_ORCHESTRATOR_PROJECT_ORCHESTRATION_SUMMARY", "actions": actions_taken, "errors": error_count},
            )
            return actions_taken

        except Exception as e:
            logger.error(
                f"Error orchestrating project {project_name}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_ORCHESTRATOR_PROJECT_ORCHESTRATION_FAILURE",
                    "project_name": project_name,
                    "error_type": type(e).__name__,
                },
            )
            raise
