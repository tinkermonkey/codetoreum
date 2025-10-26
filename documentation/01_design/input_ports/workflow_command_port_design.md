# Workflow Command Input Port Design

## Purpose

The Workflow Command Port accepts commands to control workflow execution lifecycle, including starting, pausing, resuming, and canceling workflows.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class TriggerType(Enum):
    """Type of workflow trigger"""
    CARD_MOVEMENT = "card_movement"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    API = "api"
    AGENT_FEEDBACK = "agent_feedback"

@dataclass
class StartWorkflowCommand:
    """Command to start a new workflow execution"""
    project_name: str
    work_item_id: str  # Issue number, discussion ID, etc.
    pipeline_name: str
    stage_name: Optional[str] = None  # If None, start from first stage
    trigger: TriggerType = TriggerType.MANUAL
    context: Optional[Dict[str, Any]] = None
    priority: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL

@dataclass
class PauseWorkflowCommand:
    """Command to pause an active workflow"""
    workflow_run_id: str
    reason: str
    pause_point: str  # Current stage to pause at

@dataclass
class ResumeWorkflowCommand:
    """Command to resume a paused workflow"""
    workflow_run_id: str
    from_stage: Optional[str] = None  # If None, resume from paused point

@dataclass
class CancelWorkflowCommand:
    """Command to cancel a workflow"""
    workflow_run_id: str
    reason: str
    force: bool = False  # If True, immediate cancellation

@dataclass
class RetryStageCommand:
    """Command to retry a failed stage"""
    workflow_run_id: str
    stage_name: str
    reset_state: bool = True  # If True, clear previous attempts

@dataclass
class WorkflowCommandResult:
    """Result of executing a workflow command"""
    success: bool
    workflow_run_id: str
    message: str
    state: str  # STARTED, PAUSED, RESUMED, CANCELLED, COMPLETED
    errors: Optional[List[str]] = None

class IWorkflowCommandPort(ABC):
    """Input port for workflow commands"""

    @abstractmethod
    async def start_workflow(
        self,
        command: StartWorkflowCommand
    ) -> WorkflowCommandResult:
        """
        Starts a new workflow execution.

        Args:
            command: Command with workflow execution parameters

        Returns:
            Result containing workflow run ID and status

        Raises:
            ProjectNotFoundError: If project doesn't exist
            PipelineNotFoundError: If pipeline doesn't exist
            WorkItemNotFoundError: If work item doesn't exist
            ValidationError: If command parameters invalid
        """
        pass

    @abstractmethod
    async def pause_workflow(
        self,
        command: PauseWorkflowCommand
    ) -> WorkflowCommandResult:
        """
        Pauses an active workflow execution.

        Args:
            command: Command with pause parameters

        Returns:
            Result containing updated workflow status

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            WorkflowNotActiveError: If workflow not in active state
        """
        pass

    @abstractmethod
    async def resume_workflow(
        self,
        command: ResumeWorkflowCommand
    ) -> WorkflowCommandResult:
        """
        Resumes a paused workflow execution.

        Args:
            command: Command with resume parameters

        Returns:
            Result containing updated workflow status

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            WorkflowNotPausedError: If workflow not in paused state
        """
        pass

    @abstractmethod
    async def cancel_workflow(
        self,
        command: CancelWorkflowCommand
    ) -> WorkflowCommandResult:
        """
        Cancels a workflow execution.

        Args:
            command: Command with cancellation parameters

        Returns:
            Result containing final workflow status

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
        """
        pass

    @abstractmethod
    async def retry_stage(
        self,
        command: RetryStageCommand
    ) -> WorkflowCommandResult:
        """
        Retries a failed workflow stage.

        Args:
            command: Command with retry parameters

        Returns:
            Result containing updated workflow status

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            StageNotFoundError: If stage doesn't exist
        """
        pass
```

## Command Validation

### StartWorkflowCommand Validation
```python
class StartWorkflowCommandValidator:
    """Validates StartWorkflowCommand"""

    def __init__(self, config_service: IConfigurationService):
        self.config_service = config_service

    async def validate(self, command: StartWorkflowCommand) -> ValidationResult:
        """
        Validates start workflow command.

        Checks:
        - Project exists in configuration
        - Pipeline exists for project
        - Stage exists in pipeline (if specified)
        - Work item exists (optional, can be created)
        - Context is valid JSON
        - Priority is valid enum value
        """
        errors = []

        # Validate project
        project = await self.config_service.get_project(command.project_name)
        if not project:
            errors.append(f"Project '{command.project_name}' not found")
            return ValidationResult(valid=False, errors=errors)

        # Validate pipeline
        pipeline = project.get_pipeline(command.pipeline_name)
        if not pipeline:
            errors.append(
                f"Pipeline '{command.pipeline_name}' not found in project '{command.project_name}'"
            )

        # Validate stage if specified
        if command.stage_name:
            stage = pipeline.get_stage(command.stage_name)
            if not stage:
                errors.append(
                    f"Stage '{command.stage_name}' not found in pipeline '{command.pipeline_name}'"
                )

        # Validate priority
        valid_priorities = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
        if command.priority not in valid_priorities:
            errors.append(
                f"Invalid priority '{command.priority}'. Must be one of {valid_priorities}"
            )

        # Validate context
        if command.context:
            try:
                json.dumps(command.context)  # Ensure serializable
            except (TypeError, ValueError) as e:
                errors.append(f"Invalid context: {str(e)}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None
        )
```

## Command Processing Flow

### Start Workflow Flow
```
1. Receive StartWorkflowCommand
   ↓
2. Validate command parameters
   ↓
3. Load project configuration
   ↓
4. Load pipeline template
   ↓
5. Create WorkItem aggregate (if doesn't exist)
   ↓
6. Create WorkflowExecution aggregate
   ↓
7. Initialize execution context
   ↓
8. Schedule first stage for execution
   ↓
9. Emit WorkflowStartedEvent
   ↓
10. Return WorkflowCommandResult
```

### Pause Workflow Flow
```
1. Receive PauseWorkflowCommand
   ↓
2. Load WorkflowExecution aggregate
   ↓
3. Verify workflow is in RUNNING state
   ↓
4. Check if current stage can be paused
   ↓
5. Call workflow.pause(reason, pause_point)
   ↓
6. Save workflow state
   ↓
7. Emit WorkflowPausedEvent
   ↓
8. Return WorkflowCommandResult
```

## Context Building

### Context for Agent Execution
```python
def build_execution_context(
    command: StartWorkflowCommand,
    work_item: WorkItem,
    stage: PipelineStage
) -> Dict[str, Any]:
    """
    Builds execution context for agent from workflow command.

    Includes:
    - Work item details (issue, description, labels)
    - Project context (tech stack, configuration)
    - Stage context (previous outputs, review feedback)
    - Environment variables
    - Mounted commands/sub-agents
    - Context file references (NOT inline context)
    """
    return {
        # Work item
        'work_item': {
            'id': work_item.id,
            'type': work_item.type,  # issue, discussion, pr
            'title': work_item.title,
            'description': work_item.description,
            'labels': work_item.labels,
            'state': work_item.state
        },

        # Project
        'project': {
            'name': command.project_name,
            'repository': project_config.github.repo,
            'tech_stack': project_config.tech_stack,
        },

        # Pipeline
        'pipeline': {
            'name': command.pipeline_name,
            'stage': stage.name,
            'workflow': pipeline.workflow_name
        },

        # Trigger
        'trigger': {
            'type': command.trigger.value,
            'timestamp': datetime.utcnow().isoformat()
        },

        # Context files (NEW in redesign)
        'context_files': build_context_file_references(
            work_item, stage, command.context
        ),

        # Environment (NEW in redesign)
        'environment_variables': project_config.environment_variables,

        # Mounted commands (NEW in redesign)
        'mounted_commands': project_config.mounted_commands,
        'mounted_subagents': project_config.mounted_subagents,

        # Custom context from command
        **(command.context or {})
    }
```

### Context File References (Design Change)
```python
def build_context_file_references(
    work_item: WorkItem,
    stage: PipelineStage,
    custom_context: Optional[Dict]
) -> Dict[str, str]:
    """
    Creates file references for context instead of inline data.

    This supports:
    - Much larger context without token limits
    - Complex context (multiple files, directories)
    - Binary context (images, PDFs)

    Returns: Dictionary mapping context keys to file paths
    """
    context_dir = Path(f"/context/{work_item.id}")
    context_dir.mkdir(parents=True, exist_ok=True)

    references = {}

    # Write work item description to file
    issue_file = context_dir / "work_item.md"
    issue_file.write_text(
        f"# {work_item.title}\n\n{work_item.description}"
    )
    references['work_item'] = "/context/{work_item.id}/work_item.md"

    # Write previous stage output if exists
    if stage.depends_on:
        for dep_stage in stage.depends_on:
            output = get_stage_output(work_item.id, dep_stage)
            if output:
                output_file = context_dir / f"{dep_stage}_output.md"
                output_file.write_text(output)
                references[f'previous_{dep_stage}'] = str(output_file)

    # Write custom context files
    if custom_context:
        for key, value in custom_context.items():
            if isinstance(value, str) and len(value) > 1000:
                # Large text, write to file
                ctx_file = context_dir / f"{key}.txt"
                ctx_file.write_text(value)
                references[key] = str(ctx_file)

    return references
```

## Adapter Implementations

### REST API Adapter
```python
class WorkflowCommandRESTAdapter(IWorkflowCommandPort):
    """REST API adapter for workflow commands"""

    def __init__(
        self,
        workflow_service: IWorkflowOrchestratorService,
        config_service: IConfigurationService,
        event_bus: IEventBus
    ):
        self.workflow_service = workflow_service
        self.config_service = config_service
        self.event_bus = event_bus

    async def start_workflow(
        self,
        command: StartWorkflowCommand
    ) -> WorkflowCommandResult:
        """Start workflow via REST API"""

        # Validate command
        validator = StartWorkflowCommandValidator(self.config_service)
        validation = await validator.validate(command)
        if not validation.valid:
            raise ValidationError(validation.errors)

        # Execute via workflow orchestrator service
        workflow_run = await self.workflow_service.start_workflow(
            project=command.project_name,
            work_item_id=command.work_item_id,
            pipeline=command.pipeline_name,
            stage=command.stage_name,
            trigger=command.trigger,
            context=command.context,
            priority=command.priority
        )

        # Emit event
        await self.event_bus.publish(
            WorkflowStartedEvent(
                workflow_run_id=workflow_run.id,
                project=command.project_name,
                pipeline=command.pipeline_name,
                work_item_id=command.work_item_id,
                trigger=command.trigger.value
            )
        )

        return WorkflowCommandResult(
            success=True,
            workflow_run_id=workflow_run.id,
            message=f"Workflow started for {command.work_item_id}",
            state="STARTED"
        )
```

### CLI Adapter
```python
class WorkflowCommandCLIAdapter(IWorkflowCommandPort):
    """CLI adapter for workflow commands"""

    def __init__(
        self,
        workflow_service: IWorkflowOrchestratorService,
        config_service: IConfigurationService
    ):
        self.workflow_service = workflow_service
        self.config_service = config_service

    async def start_workflow(
        self,
        command: StartWorkflowCommand
    ) -> WorkflowCommandResult:
        """Start workflow via CLI"""

        # Validate
        validator = StartWorkflowCommandValidator(self.config_service)
        validation = await validator.validate(command)
        if not validation.valid:
            # CLI-specific error formatting
            print(f"❌ Command validation failed:")
            for error in validation.errors:
                print(f"  - {error}")
            raise ValidationError(validation.errors)

        # Execute
        workflow_run = await self.workflow_service.start_workflow(...)

        # CLI-specific output
        print(f"✅ Workflow started")
        print(f"   Run ID: {workflow_run.id}")
        print(f"   Project: {command.project_name}")
        print(f"   Pipeline: {command.pipeline_name}")
        print(f"   Work Item: {command.work_item_id}")

        return WorkflowCommandResult(
            success=True,
            workflow_run_id=workflow_run.id,
            message="Workflow started",
            state="STARTED"
        )
```

## Mock Implementation for Testing

```python
class MockWorkflowCommandPort(IWorkflowCommandPort):
    """Mock implementation for testing"""

    def __init__(self):
        self.started_workflows: List[StartWorkflowCommand] = []
        self.paused_workflows: List[PauseWorkflowCommand] = []
        self.resumed_workflows: List[ResumeWorkflowCommand] = []
        self.cancelled_workflows: List[CancelWorkflowCommand] = []

    async def start_workflow(
        self,
        command: StartWorkflowCommand
    ) -> WorkflowCommandResult:
        """Record command and return success"""
        self.started_workflows.append(command)

        return WorkflowCommandResult(
            success=True,
            workflow_run_id=f"mock-wf-{len(self.started_workflows)}",
            message="Mock workflow started",
            state="STARTED"
        )

    # Similar for other commands...
```

## Error Handling

### Command Errors
```python
class WorkflowCommandError(Exception):
    """Base class for workflow command errors"""
    pass

class ProjectNotFoundError(WorkflowCommandError):
    """Project doesn't exist"""
    pass

class PipelineNotFoundError(WorkflowCommandError):
    """Pipeline doesn't exist"""
    pass

class WorkflowNotFoundError(WorkflowCommandError):
    """Workflow run doesn't exist"""
    pass

class WorkflowStateError(WorkflowCommandError):
    """Workflow in wrong state for command"""
    pass

class ValidationError(WorkflowCommandError):
    """Command validation failed"""
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"Validation failed: {', '.join(errors)}")
```

## Observability

### Events Emitted
```python
@dataclass
class WorkflowCommandReceivedEvent(DomainEvent):
    """Emitted when workflow command received"""
    command_type: str  # start, pause, resume, cancel, retry
    workflow_run_id: Optional[str]
    project: str
    work_item_id: Optional[str]

@dataclass
class WorkflowStartedEvent(DomainEvent):
    """Emitted when workflow started"""
    workflow_run_id: str
    project: str
    pipeline: str
    work_item_id: str
    trigger: str

@dataclass
class WorkflowPausedEvent(DomainEvent):
    """Emitted when workflow paused"""
    workflow_run_id: str
    reason: str
    pause_point: str

# Similar for other lifecycle events...
```

### Metrics
- Commands received (count, by type)
- Commands successful (count, duration)
- Commands failed (count, by error type)
- Workflows started (count, by project, by trigger)
- Workflows paused/resumed/cancelled (count)

## Security

### Authorization
```python
class WorkflowCommandAuthorizer:
    """Authorizes workflow commands"""

    def can_start_workflow(
        self,
        user: User,
        project: str
    ) -> bool:
        """Check if user can start workflows for project"""
        return user.has_permission(f"workflow:start:{project}")

    def can_pause_workflow(
        self,
        user: User,
        workflow_run_id: str
    ) -> bool:
        """Check if user can pause workflow"""
        # Only owner or admin can pause
        workflow = get_workflow(workflow_run_id)
        return (
            user.id == workflow.started_by
            or user.has_permission("workflow:admin")
        )

    def can_cancel_workflow(
        self,
        user: User,
        workflow_run_id: str,
        force: bool
    ) -> bool:
        """Check if user can cancel workflow"""
        # Force cancel requires admin
        if force:
            return user.has_permission("workflow:admin")
        # Regular cancel requires ownership
        workflow = get_workflow(workflow_run_id)
        return user.id == workflow.started_by
```

## Testing Strategy

### Unit Tests
- Command validation logic
- Context building
- Error handling
- Authorization checks

### Integration Tests
- End-to-end command execution
- Event emission
- State transitions

### Simulation Tests
- Mock port with simulated workflows
- Test all command types
- Verify correct service interactions

## Dependencies

- `IWorkflowOrchestratorService`: Execute workflow operations
- `IConfigurationService`: Load configuration
- `IEventBus`: Publish domain events
- `IAuthorizationService`: Check permissions
