# Workflow Orchestrator Service - Detailed Design

## Overview

The Workflow Orchestrator is the central coordination service that manages complete workflows from GitHub card movement to agent completion. It orchestrates task creation, agent selection, and progression through pipeline stages based on workflow configuration.

## Responsibilities

### Primary Responsibilities
1. **Card Movement Handling**: Process GitHub Projects card movement events and initiate appropriate workflows
2. **Agent Routing**: Determine which agent should handle work based on column and workflow configuration
3. **Pipeline Stage Coordination**: Manage progression through pipeline stages with proper sequencing
4. **Workflow Lifecycle**: Track workflow execution from start to completion
5. **Decision Making**: Make and record routing, progression, and escalation decisions

### Secondary Responsibilities
1. **Event Emission**: Emit decision events for observability
2. **State Coordination**: Coordinate with state management services
3. **Error Handling**: Handle workflow failures and implement retry logic

## Port Interfaces (Hexagonal Architecture)

### Input Ports (Commands)
```python
class IWorkflowOrchestrator(ABC):
    """Primary interface for workflow orchestration"""

    @abstractmethod
    async def handle_card_movement(self, event: CardMovedEvent) -> WorkflowResult:
        """
        Process a card movement event from GitHub Projects

        Args:
            event: Card movement event containing issue, column, board info

        Returns:
            WorkflowResult with task_id, agent_name, and status
        """
        pass

    @abstractmethod
    async def handle_stage_completion(self, event: StageCompletedEvent) -> WorkflowResult:
        """
        Process completion of a pipeline stage and determine next action

        Args:
            event: Stage completion event with results and context

        Returns:
            WorkflowResult indicating next stage or completion
        """
        pass

    @abstractmethod
    async def handle_review_cycle_completion(
        self, event: ReviewCycleCompletedEvent
    ) -> WorkflowResult:
        """
        Process review cycle completion and determine progression

        Args:
            event: Review completion with approval status

        Returns:
            WorkflowResult for auto-advancement or escalation
        """
        pass

    @abstractmethod
    async def handle_feedback(self, event: FeedbackEvent) -> WorkflowResult:
        """
        Process human feedback and route to appropriate agent

        Args:
            event: Feedback event with comment and context

        Returns:
            WorkflowResult for feedback handling task
        """
        pass
```

### Output Ports (Infrastructure Dependencies)
```python
class ITaskQueue(ABC):
    """Interface to task queue for enqueueing work"""
    @abstractmethod
    async def enqueue(self, task: Task) -> str:
        """Enqueue a task and return task_id"""
        pass

class IProjectConfiguration(ABC):
    """Interface to configuration system"""
    @abstractmethod
    async def get_workflow_config(self, project: str, board: str) -> WorkflowConfig:
        """Get workflow configuration for a project board"""
        pass

    @abstractmethod
    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get agent configuration"""
        pass

class IWorkflowState(ABC):
    """Interface to workflow state management"""
    @abstractmethod
    async def get_workflow_state(self, issue_id: str) -> WorkflowState:
        """Get current workflow state for an issue"""
        pass

    @abstractmethod
    async def update_workflow_state(self, issue_id: str, state: WorkflowState) -> None:
        """Update workflow state"""
        pass

class IDecisionEvents(ABC):
    """Interface to decision event emission"""
    @abstractmethod
    async def emit_routing_decision(self, decision: RoutingDecision) -> None:
        """Emit agent routing decision"""
        pass

    @abstractmethod
    async def emit_progression_decision(self, decision: ProgressionDecision) -> None:
        """Emit workflow progression decision"""
        pass
```

## Domain Models

### Input Models
```python
@dataclass
class CardMovedEvent:
    """Event emitted when a card moves on GitHub Projects board"""
    project: str
    board: str
    issue_number: int
    from_column: Optional[str]
    to_column: str
    issue_data: IssueData
    timestamp: datetime

@dataclass
class IssueData:
    """Issue information from GitHub"""
    number: int
    title: str
    body: str
    labels: List[str]
    state: str
    created_at: datetime
    updated_at: datetime

@dataclass
class StageCompletedEvent:
    """Event emitted when a pipeline stage completes"""
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
    """Event emitted when review cycle completes"""
    project: str
    issue_number: int
    approved: bool
    iteration: int
    maker_agent: str
    reviewer_agent: str
    feedback: Optional[str]
    timestamp: datetime

@dataclass
class FeedbackEvent:
    """Event for human feedback on agent output"""
    project: str
    issue_number: int
    feedback_type: FeedbackType  # COMMENT, LABEL, REACTION
    author: str
    content: str
    reply_to_comment_id: Optional[str]
    timestamp: datetime
```

### Output Models
```python
@dataclass
class WorkflowResult:
    """Result of workflow orchestration action"""
    success: bool
    task_id: Optional[str]
    agent_name: Optional[str]
    action: WorkflowAction  # TASK_QUEUED, AUTO_ADVANCE, ESCALATE, COMPLETE
    next_column: Optional[str]
    reason: str
    error: Optional[str] = None

class WorkflowAction(Enum):
    """Possible workflow actions"""
    TASK_QUEUED = "task_queued"
    AUTO_ADVANCE = "auto_advance"
    ESCALATE = "escalate"
    COMPLETE = "complete"
    NO_ACTION = "no_action"

@dataclass
class Task:
    """Task for agent execution"""
    id: str
    agent: str
    project: str
    priority: TaskPriority
    context: Dict[str, Any]
    created_at: datetime
```

### Configuration Models
```python
@dataclass
class WorkflowConfig:
    """Workflow configuration from config system"""
    name: str
    columns: List[ColumnConfig]
    workspace_type: WorkspaceType  # ISSUES, DISCUSSIONS, HYBRID

@dataclass
class ColumnConfig:
    """Configuration for a workflow column"""
    name: str
    position: int
    agent: str
    auto_advance_on_approval: bool
    discussion_category: Optional[str]
    stage_type: StageType  # AGENT, REPAIR_CYCLE, REVIEW
    review_required: bool
    reviewer_agent: Optional[str]
```

## Core Orchestration Logic

### 1. Card Movement Handler
```python
class WorkflowOrchestrator:
    def __init__(
        self,
        task_queue: ITaskQueue,
        config: IProjectConfiguration,
        workflow_state: IWorkflowState,
        decision_events: IDecisionEvents
    ):
        self.task_queue = task_queue
        self.config = config
        self.workflow_state = workflow_state
        self.decision_events = decision_events

    async def handle_card_movement(self, event: CardMovedEvent) -> WorkflowResult:
        """
        Handle card movement from GitHub Projects

        Decision Flow:
        1. Load workflow configuration for board
        2. Find column configuration for target column
        3. Check if work already in progress
        4. Determine agent from column config
        5. Validate agent can run (dev container available, etc.)
        6. Create task context
        7. Enqueue task
        8. Emit routing decision
        9. Update workflow state
        """
        # Load configuration
        workflow_config = await self.config.get_workflow_config(
            event.project, event.board
        )

        # Find target column config
        column_config = self._find_column_config(workflow_config, event.to_column)
        if not column_config:
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason=f"Column {event.to_column} not found in workflow config",
                task_id=None,
                agent_name=None,
                next_column=None
            )

        # Check if work already in progress
        workflow_state = await self.workflow_state.get_workflow_state(
            f"{event.project}:{event.issue_number}"
        )
        if workflow_state.is_in_progress(column_config.name, column_config.agent):
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason="Work already in progress for this column and agent",
                task_id=None,
                agent_name=None,
                next_column=None
            )

        # Get agent configuration
        agent_config = await self.config.get_agent_config(column_config.agent)

        # Validate agent can run
        validation_result = await self._validate_agent_can_run(
            event.project, column_config.agent, agent_config
        )
        if not validation_result.can_run:
            # Queue dev environment setup if needed
            if validation_result.needs_dev_setup:
                await self._queue_dev_setup(event.project)
            return WorkflowResult(
                success=False,
                action=WorkflowAction.NO_ACTION,
                reason=validation_result.reason,
                task_id=None,
                agent_name=None,
                next_column=None
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
            priority=TaskPriority.MEDIUM,
            context=task_context,
            created_at=datetime.utcnow()
        )

        # Enqueue task
        task_id = await self.task_queue.enqueue(task)

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
                timestamp=datetime.utcnow()
            )
        )

        # Update workflow state
        workflow_state.mark_in_progress(column_config.name, column_config.agent)
        await self.workflow_state.update_workflow_state(
            f"{event.project}:{event.issue_number}",
            workflow_state
        )

        return WorkflowResult(
            success=True,
            task_id=task_id,
            agent_name=column_config.agent,
            action=WorkflowAction.TASK_QUEUED,
            reason="Task queued for agent execution",
            next_column=None
        )
```

### 2. Stage Completion Handler
```python
async def handle_stage_completion(
    self, event: StageCompletedEvent
) -> WorkflowResult:
    """
    Handle completion of a pipeline stage

    Decision Flow:
    1. Load workflow and column config
    2. Check if review required
    3. If review required: Queue reviewer task
    4. If review not required and auto-advance: Move to next column
    5. Else: No action (wait for human to move card)
    """
    workflow_config = await self.config.get_workflow_config(
        event.project, event.context.get('board')
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
                timestamp=datetime.utcnow()
            )
        )
        return WorkflowResult(
            success=False,
            action=WorkflowAction.ESCALATE,
            reason="Stage execution failed",
            task_id=None,
            agent_name=None,
            next_column=None
        )

    # Check if review required
    if current_column_config.review_required:
        # Queue reviewer task
        return await self._queue_review_task(
            event, current_column_config
        )

    # Check auto-advance
    if current_column_config.auto_advance_on_approval:
        # Determine next column
        next_column = self._get_next_column(
            workflow_config, current_column_config
        )
        if next_column:
            # Move card to next column (via GitHub integration)
            await self._advance_to_column(
                event.project,
                event.issue_number,
                next_column.name
            )

            await self.decision_events.emit_progression_decision(
                ProgressionDecision(
                    project=event.project,
                    issue_number=event.issue_number,
                    from_stage=current_column_config.name,
                    to_stage=next_column.name,
                    action=WorkflowAction.AUTO_ADVANCE,
                    reason="Auto-advance on stage completion",
                    timestamp=datetime.utcnow()
                )
            )

            return WorkflowResult(
                success=True,
                action=WorkflowAction.AUTO_ADVANCE,
                task_id=None,
                agent_name=None,
                next_column=next_column.name,
                reason="Auto-advanced to next column"
            )

    # No auto-advance, wait for human
    return WorkflowResult(
        success=True,
        action=WorkflowAction.COMPLETE,
        task_id=None,
        agent_name=None,
        next_column=None,
        reason="Stage complete, waiting for manual progression"
    )
```

### 3. Review Cycle Completion Handler
```python
async def handle_review_cycle_completion(
    self, event: ReviewCycleCompletedEvent
) -> WorkflowResult:
    """
    Handle review cycle completion

    Decision Flow:
    1. If approved: Check auto-advance and progress workflow
    2. If not approved and max iterations: Escalate to human
    3. If not approved: Queue revision task for maker
    """
    if event.approved:
        # Review approved, check auto-advance
        workflow_config = await self.config.get_workflow_config(
            event.project, event.context.get('board')
        )

        current_column = self._find_column_by_agent(
            workflow_config, event.maker_agent
        )

        if current_column.auto_advance_on_approval:
            next_column = self._get_next_column(workflow_config, current_column)
            if next_column:
                await self._advance_to_column(
                    event.project,
                    event.issue_number,
                    next_column.name
                )

                return WorkflowResult(
                    success=True,
                    action=WorkflowAction.AUTO_ADVANCE,
                    task_id=None,
                    agent_name=None,
                    next_column=next_column.name,
                    reason="Review approved, auto-advanced"
                )

        return WorkflowResult(
            success=True,
            action=WorkflowAction.COMPLETE,
            task_id=None,
            agent_name=None,
            next_column=None,
            reason="Review approved, waiting for manual progression"
        )
    else:
        # Check if max iterations reached
        if event.iteration >= event.context.get('max_iterations', 3):
            # Escalate to human
            await self._add_escalation_label(event.project, event.issue_number)

            return WorkflowResult(
                success=True,
                action=WorkflowAction.ESCALATE,
                task_id=None,
                agent_name=None,
                next_column=None,
                reason=f"Max review iterations ({event.iteration}) reached, escalated"
            )

        # Queue revision task
        task_id = await self._queue_revision_task(event)

        return WorkflowResult(
            success=True,
            action=WorkflowAction.TASK_QUEUED,
            task_id=task_id,
            agent_name=event.maker_agent,
            next_column=None,
            reason=f"Changes requested, queued revision (iteration {event.iteration + 1})"
        )
```

## Testing Strategy

### Unit Tests
```python
# Test with mock adapters
async def test_handle_card_movement_success():
    # Arrange
    mock_queue = InMemoryTaskQueue()
    mock_config = MockProjectConfiguration()
    mock_state = MockWorkflowState()
    mock_events = MockDecisionEvents()

    orchestrator = WorkflowOrchestrator(
        mock_queue, mock_config, mock_state, mock_events
    )

    event = CardMovedEvent(
        project="test-project",
        board="Development",
        issue_number=123,
        from_column="Backlog",
        to_column="In Progress",
        issue_data=IssueData(...),
        timestamp=datetime.utcnow()
    )

    # Act
    result = await orchestrator.handle_card_movement(event)

    # Assert
    assert result.success
    assert result.action == WorkflowAction.TASK_QUEUED
    assert result.task_id is not None
    assert mock_queue.size() == 1
    assert len(mock_events.emitted_decisions) == 1
```

### Integration Tests
```python
async def test_full_workflow_cycle():
    """Test complete workflow from card movement to completion"""
    # Uses real implementations with in-memory adapters
    pass

async def test_review_cycle_with_approval():
    """Test review cycle that approves and auto-advances"""
    pass

async def test_review_cycle_with_escalation():
    """Test review cycle that hits max iterations and escalates"""
    pass
```

## Simulation Mode Support

The Workflow Orchestrator fully supports simulation mode through:

1. **Mock Task Queue**: Uses in-memory task queue instead of Redis
2. **Mock Configuration**: Loads configuration from in-memory structures
3. **Mock State**: Uses in-memory workflow state
4. **Mock Events**: Captures decision events in memory for assertion
5. **Deterministic Time**: Uses injected clock for predictable timestamps

## Migration from Legacy

### Legacy Implementation
- Located in `main.py` and `agents/orchestrator_integration.py`
- Tightly coupled to Redis, Elasticsearch, GitHub
- Mixed concerns (orchestration + infrastructure)

### Migration Steps
1. Extract core orchestration logic into new service
2. Define port interfaces for dependencies
3. Implement adapters for production (Redis, GitHub, etc.)
4. Implement mock adapters for testing
5. Run both implementations in parallel
6. Validate outputs match
7. Cut over to new implementation

## Dependencies

### Required Ports
- ITaskQueue (Redis or in-memory)
- IProjectConfiguration (file-based or database)
- IWorkflowState (Redis or in-memory)
- IDecisionEvents (Elasticsearch or in-memory)
- IGitHubProjects (GitHub API or mock)

### Optional Ports
- IDevContainerState (for validation)
- IMetrics (for performance tracking)

## Performance Considerations

1. **Workflow State Caching**: Cache workflow states in memory with TTL
2. **Configuration Caching**: Cache workflow configs to avoid repeated loads
3. **Batch Decision Events**: Buffer decision events and emit in batches
4. **Async All The Way**: Use async/await throughout for non-blocking I/O

## Error Handling

1. **Configuration Errors**: Return WorkflowResult with error, don't throw
2. **State Errors**: Retry with exponential backoff, then escalate
3. **Queue Errors**: Retry, then emit alert and escalate
4. **Validation Errors**: Return clear error messages in WorkflowResult

## Observability

### Decision Events
- `routing_decision`: Agent selection for column
- `progression_decision`: Workflow advancement
- `escalation_decision`: Human intervention needed
- `validation_decision`: Agent validation results

### Metrics
- `workflow.card_movement.count`: Card movements processed
- `workflow.task_queued.count`: Tasks queued
- `workflow.auto_advance.count`: Auto-advancements
- `workflow.escalation.count`: Escalations

### Logs
- INFO: Card movements, task creations, progressions
- WARN: Validation failures, retry attempts
- ERROR: Unrecoverable errors, escalations
