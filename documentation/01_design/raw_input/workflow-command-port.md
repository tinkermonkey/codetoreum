# WorkflowCommandPort

## Overview

The `WorkflowCommandPort` is the primary interface for managing workflow lifecycles within Codetroeum. It handles all commands related to starting, controlling, and monitoring workflow executions.

## Interface Definition

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID

from codetroeum.domain.types import (
    WorkflowId, WorkItemId, TemplateId, AgentId, ProjectId
)
from codetroeum.domain.models import WorkflowStatus, WorkflowPriority

class WorkflowCommandPort(ABC):
    """
    Port for workflow management commands.
    
    This port handles all operations that modify workflow state,
    including creation, execution control, and termination.
    """
    
    @abstractmethod
    async def start_workflow(self, 
                           command: StartWorkflowCommand) -> WorkflowId:
        """
        Start a new workflow execution.
        
        Args:
            command: Command containing workflow parameters
            
        Returns:
            WorkflowId: Unique identifier for the started workflow
            
        Raises:
            ValidationError: Invalid command parameters
            WorkflowAlreadyExistsError: Workflow already running for work item
            ResourceNotFoundError: Work item or template not found
            AuthorizationError: User not authorized to start workflow
        """
        pass
    
    @abstractmethod
    async def pause_workflow(self, 
                           workflow_id: WorkflowId,
                           reason: Optional[str] = None) -> None:
        """
        Pause a running workflow.
        
        Args:
            workflow_id: Workflow to pause
            reason: Optional reason for pausing
            
        Raises:
            WorkflowNotFoundError: Workflow doesn't exist
            InvalidStateError: Workflow not in pauseable state
            AuthorizationError: User not authorized to pause workflow
        """
        pass
    
    @abstractmethod
    async def resume_workflow(self, 
                            workflow_id: WorkflowId,
                            parameters: Optional[Dict[str, Any]] = None) -> None:
        """
        Resume a paused workflow.
        
        Args:
            workflow_id: Workflow to resume
            parameters: Optional parameters for resumption
            
        Raises:
            WorkflowNotFoundError: Workflow doesn't exist
            InvalidStateError: Workflow not in paused state
            AuthorizationError: User not authorized to resume workflow
        """
        pass
    
    @abstractmethod
    async def cancel_workflow(self, 
                            workflow_id: WorkflowId,
                            reason: str) -> None:
        """
        Cancel a workflow execution.
        
        Args:
            workflow_id: Workflow to cancel
            reason: Reason for cancellation (required)
            
        Raises:
            WorkflowNotFoundError: Workflow doesn't exist
            InvalidStateError: Workflow already completed
            AuthorizationError: User not authorized to cancel workflow
        """
        pass
    
    @abstractmethod
    async def retry_workflow_stage(self,
                                  workflow_id: WorkflowId,
                                  stage_name: str,
                                  parameters: Optional[Dict[str, Any]] = None) -> None:
        """
        Retry a specific workflow stage.
        
        Args:
            workflow_id: Workflow containing the stage
            stage_name: Name of stage to retry
            parameters: Optional override parameters
            
        Raises:
            WorkflowNotFoundError: Workflow doesn't exist
            StageNotFoundError: Stage doesn't exist in workflow
            InvalidStateError: Stage not in retryable state
            AuthorizationError: User not authorized to retry stage
        """
        pass
    
    @abstractmethod
    async def update_workflow_priority(self,
                                      workflow_id: WorkflowId,
                                      priority: WorkflowPriority) -> None:
        """
        Update workflow execution priority.
        
        Args:
            workflow_id: Workflow to update
            priority: New priority level
            
        Raises:
            WorkflowNotFoundError: Workflow doesn't exist
            InvalidStateError: Workflow already completed
            AuthorizationError: User not authorized to update priority
        """
        pass
    
    @abstractmethod
    async def assign_workflow_agent(self,
                                   workflow_id: WorkflowId,
                                   stage_name: str,
                                   agent_id: AgentId) -> None:
        """
        Manually assign an agent to a workflow stage.
        
        Args:
            workflow_id: Workflow to update
            stage_name: Stage to assign agent to
            agent_id: Agent to assign
            
        Raises:
            WorkflowNotFoundError: Workflow doesn't exist
            StageNotFoundError: Stage doesn't exist
            AgentNotFoundError: Agent doesn't exist
            InvalidStateError: Stage already executed
            AuthorizationError: User not authorized to assign agents
        """
        pass
    
    @abstractmethod
    async def add_workflow_checkpoint(self,
                                     workflow_id: WorkflowId,
                                     checkpoint: WorkflowCheckpoint) -> None:
        """
        Add a checkpoint to save workflow state.
        
        Args:
            workflow_id: Workflow to checkpoint
            checkpoint: Checkpoint data
            
        Raises:
            WorkflowNotFoundError: Workflow doesn't exist
            InvalidStateError: Workflow not running
            AuthorizationError: User not authorized to add checkpoints
        """
        pass
    
    @abstractmethod
    async def rollback_to_checkpoint(self,
                                    workflow_id: WorkflowId,
                                    checkpoint_id: str) -> None:
        """
        Rollback workflow to a previous checkpoint.
        
        Args:
            workflow_id: Workflow to rollback
            checkpoint_id: Checkpoint to rollback to
            
        Raises:
            WorkflowNotFoundError: Workflow doesn't exist
            CheckpointNotFoundError: Checkpoint doesn't exist
            InvalidStateError: Cannot rollback from current state
            AuthorizationError: User not authorized to rollback
        """
        pass
```

## Command Objects

### StartWorkflowCommand

```python
@dataclass
class StartWorkflowCommand(Command):
    """
    Command to start a new workflow.
    
    Attributes:
        work_item_id: Work item to process
        template_id: Workflow template to use
        project_id: Project context
        priority: Execution priority
        parameters: Template-specific parameters
        auto_retry: Enable automatic retry on failure
        max_retries: Maximum retry attempts
        timeout_seconds: Overall workflow timeout
        metadata: Additional metadata
    """
    work_item_id: WorkItemId
    template_id: TemplateId
    project_id: ProjectId
    priority: WorkflowPriority = WorkflowPriority.NORMAL
    parameters: Dict[str, Any] = field(default_factory=dict)
    auto_retry: bool = True
    max_retries: int = 3
    timeout_seconds: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> None:
        """Validate command parameters."""
        if not self.work_item_id:
            raise ValidationError("work_item_id is required")
        if not self.template_id:
            raise ValidationError("template_id is required")
        if not self.project_id:
            raise ValidationError("project_id is required")
        if self.max_retries < 0:
            raise ValidationError("max_retries must be non-negative")
        if self.timeout_seconds and self.timeout_seconds < 0:
            raise ValidationError("timeout_seconds must be positive")
```

### WorkflowCheckpoint

```python
@dataclass
class WorkflowCheckpoint:
    """
    Checkpoint for workflow state.
    
    Attributes:
        checkpoint_id: Unique checkpoint identifier
        workflow_id: Associated workflow
        stage_name: Current stage
        state_data: Serialized state
        created_at: Checkpoint timestamp
        description: Human-readable description
    """
    checkpoint_id: str = field(default_factory=lambda: str(uuid4()))
    workflow_id: WorkflowId = None
    stage_name: str = None
    state_data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    description: Optional[str] = None
```

## Error Types

```python
class WorkflowCommandError(PortError):
    """Base error for workflow commands."""
    pass

class WorkflowAlreadyExistsError(WorkflowCommandError):
    """Workflow already exists for work item."""
    def __init__(self, work_item_id: str):
        super().__init__(f"Workflow already running for work item: {work_item_id}")
        self.work_item_id = work_item_id

class WorkflowNotFoundError(WorkflowCommandError):
    """Workflow not found."""
    def __init__(self, workflow_id: str):
        super().__init__(f"Workflow not found: {workflow_id}")
        self.workflow_id = workflow_id

class InvalidStateError(WorkflowCommandError):
    """Operation invalid for current workflow state."""
    def __init__(self, workflow_id: str, current_state: str, operation: str):
        super().__init__(
            f"Cannot {operation} workflow {workflow_id} in state {current_state}"
        )
        self.workflow_id = workflow_id
        self.current_state = current_state
        self.operation = operation

class StageNotFoundError(WorkflowCommandError):
    """Workflow stage not found."""
    def __init__(self, workflow_id: str, stage_name: str):
        super().__init__(f"Stage {stage_name} not found in workflow {workflow_id}")
        self.workflow_id = workflow_id
        self.stage_name = stage_name
```

## Implementation Example

```python
class WorkflowCommandAdapter(WorkflowCommandPort):
    """
    Concrete implementation of WorkflowCommandPort.
    """
    
    def __init__(self,
                 workflow_service: WorkflowService,
                 auth_service: AuthorizationService,
                 event_bus: EventBus):
        self.workflow_service = workflow_service
        self.auth_service = auth_service
        self.event_bus = event_bus
    
    async def start_workflow(self, command: StartWorkflowCommand) -> WorkflowId:
        # Validate command
        command.validate()
        
        # Check authorization
        await self.auth_service.check_permission(
            command.user_id,
            "workflow:start",
            resource=command.project_id
        )
        
        # Check for existing workflow
        existing = await self.workflow_service.find_by_work_item(
            command.work_item_id
        )
        if existing and existing.is_active():
            raise WorkflowAlreadyExistsError(command.work_item_id)
        
        # Create and start workflow
        workflow = await self.workflow_service.create_workflow(
            work_item_id=command.work_item_id,
            template_id=command.template_id,
            project_id=command.project_id,
            priority=command.priority,
            parameters=command.parameters
        )
        
        # Emit event
        await self.event_bus.publish(
            WorkflowStartedEvent(
                workflow_id=workflow.id,
                work_item_id=command.work_item_id,
                template_id=command.template_id,
                user_id=command.user_id
            )
        )
        
        return workflow.id
    
    async def pause_workflow(self, 
                           workflow_id: WorkflowId,
                           reason: Optional[str] = None) -> None:
        # Load workflow
        workflow = await self.workflow_service.get_workflow(workflow_id)
        if not workflow:
            raise WorkflowNotFoundError(workflow_id)
        
        # Check state
        if not workflow.can_pause():
            raise InvalidStateError(
                workflow_id,
                workflow.status.value,
                "pause"
            )
        
        # Pause workflow
        await self.workflow_service.pause_workflow(workflow_id, reason)
        
        # Emit event
        await self.event_bus.publish(
            WorkflowPausedEvent(
                workflow_id=workflow_id,
                reason=reason
            )
        )
```

## Testing

### Unit Tests

```python
class TestWorkflowCommandPort:
    """Test WorkflowCommandPort implementations."""
    
    @pytest.fixture
    def port(self) -> WorkflowCommandPort:
        """Create port with mock dependencies."""
        return WorkflowCommandAdapter(
            workflow_service=MockWorkflowService(),
            auth_service=MockAuthService(),
            event_bus=MockEventBus()
        )
    
    async def test_start_workflow_success(self, port):
        """Test successful workflow start."""
        command = StartWorkflowCommand(
            work_item_id="item-123",
            template_id="template-1",
            project_id="proj-1"
        )
        
        workflow_id = await port.start_workflow(command)
        
        assert workflow_id is not None
        assert isinstance(workflow_id, WorkflowId)
    
    async def test_start_workflow_validation_error(self, port):
        """Test validation error on invalid command."""
        command = StartWorkflowCommand(
            work_item_id="",  # Invalid
            template_id="template-1",
            project_id="proj-1"
        )
        
        with pytest.raises(ValidationError) as exc:
            await port.start_workflow(command)
        
        assert "work_item_id is required" in str(exc.value)
    
    async def test_start_workflow_already_exists(self, port):
        """Test error when workflow already exists."""
        command = StartWorkflowCommand(
            work_item_id="item-with-workflow",
            template_id="template-1",
            project_id="proj-1"
        )
        
        # Configure mock to return existing workflow
        port.workflow_service.existing_workflow = True
        
        with pytest.raises(WorkflowAlreadyExistsError) as exc:
            await port.start_workflow(command)
        
        assert exc.value.work_item_id == "item-with-workflow"
```

### Contract Tests

```python
class WorkflowCommandPortContract:
    """Contract tests for WorkflowCommandPort implementations."""
    
    @abstractmethod
    def create_port(self) -> WorkflowCommandPort:
        """Create port instance to test."""
        pass
    
    async def test_pause_and_resume(self):
        """Test pause and resume operations."""
        port = self.create_port()
        
        # Start workflow
        command = StartWorkflowCommand(
            work_item_id="test-item",
            template_id="test-template",
            project_id="test-project"
        )
        workflow_id = await port.start_workflow(command)
        
        # Pause workflow
        await port.pause_workflow(workflow_id, "Testing pause")
        
        # Resume workflow
        await port.resume_workflow(workflow_id)
        
        # Verify workflow is running again
        # (Implementation specific verification)
```

## Usage Examples

### Starting a Workflow

```python
# In an application service
class WorkflowApplicationService:
    def __init__(self, workflow_port: WorkflowCommandPort):
        self.workflow_port = workflow_port
    
    async def process_new_issue(self, issue_id: str) -> WorkflowId:
        """Process a new GitHub issue."""
        command = StartWorkflowCommand(
            work_item_id=issue_id,
            template_id="standard-development",
            project_id="my-project",
            priority=WorkflowPriority.NORMAL,
            parameters={
                "auto_assign": True,
                "require_review": True,
                "deploy_on_success": False
            }
        )
        
        return await self.workflow_port.start_workflow(command)
```

### Handling Failures with Retry

```python
async def execute_with_retry(workflow_port: WorkflowCommandPort,
                            workflow_id: WorkflowId,
                            stage_name: str) -> None:
    """Execute stage with automatic retry."""
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            # Try to execute stage
            await workflow_port.retry_workflow_stage(
                workflow_id,
                stage_name,
                parameters={"attempt": attempt + 1}
            )
            break  # Success
        except Exception as e:
            if attempt == max_attempts - 1:
                # Final attempt failed, cancel workflow
                await workflow_port.cancel_workflow(
                    workflow_id,
                    reason=f"Stage {stage_name} failed after {max_attempts} attempts"
                )
                raise
            # Wait before retry
            await asyncio.sleep(2 ** attempt)
```

## Best Practices

1. **Always validate commands** before processing
2. **Check authorization** for all operations
3. **Emit events** for all state changes
4. **Handle idempotency** - repeated commands should be safe
5. **Use meaningful error messages** with context
6. **Log all operations** for audit trail
7. **Implement timeouts** for long-running operations

## Related Components

- [TaskQueryPort](task-query-port.md) - Query workflow task status
- [EventStreamPort](event-stream-port.md) - Subscribe to workflow events
- [WorkflowService](../services/workflow-service.md) - Workflow business logic
- [WorkflowAggregate](../domain/workflow-aggregate.md) - Workflow domain model

## Next Steps

- Review [AgentCommandPort](agent-command-port.md)
- Explore [Domain Models](../domain/00-overview.md)
- See [Application Services](../services/00-overview.md)
