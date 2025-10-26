# Workflow Domain Design

## Overview

The Workflow is a core aggregate root that orchestrates the execution of work items through a series of pipeline stages. It manages the lifecycle of work execution, coordinates agent assignments, and tracks progress through defined stages.

## Domain Model

### Aggregate Root: Workflow

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

class WorkflowStatus(Enum):
    """Status enumeration for workflows."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Workflow:
    """
    Workflow aggregate root.

    Orchestrates execution of work items through pipeline stages.
    Maintains consistency boundary for workflow execution.
    """

    # Identity
    id: str
    work_item_id: str
    template_id: str
    project_id: str

    # Status
    status: WorkflowStatus

    # Stage tracking
    stages: List['PipelineStage']
    current_stage_index: int
    completed_stages: List[str]

    # Execution tracking
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    paused_at: Optional[datetime]

    # Metadata
    metadata: Dict[str, Any]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Event tracking
    _events: List[DomainEvent] = field(default_factory=list, init=False, repr=False)
    _version: int = field(default=0, init=False, repr=False)

    def __post_init__(self):
        """Validate invariants after initialization."""
        self._validate_invariants()

    def _validate_invariants(self) -> None:
        """
        Validate domain invariants.

        Invariants:
        - Must have at least one stage
        - Cannot exceed maximum parallel stages
        - Stage dependencies must not create cycles
        - All dependencies must be satisfied
        """
        if len(self.stages) < 1:
            raise DomainError("Workflow must have at least one stage")

        if self._count_parallel_stages() > 10:
            raise DomainError("Cannot exceed 10 parallel stages")

        if self._has_circular_dependencies():
            raise DomainError("Workflow has circular stage dependencies")

        if not self._all_dependencies_satisfied():
            raise DomainError("Not all stage dependencies are satisfied")

    @classmethod
    def create(cls,
               work_item_id: str,
               template: 'WorkflowTemplate',
               project_id: str) -> 'Workflow':
        """
        Factory method to create a new workflow from template.

        Emits: WorkflowCreated event
        """
        workflow = cls(
            id=str(uuid4()),
            work_item_id=work_item_id,
            template_id=template.id,
            project_id=project_id,
            status=WorkflowStatus.PENDING,
            stages=template.build_stages(),
            current_stage_index=0,
            completed_stages=[],
            started_at=None,
            completed_at=None,
            paused_at=None,
            metadata={},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        event = WorkflowCreated(
            aggregate_id=workflow.id,
            aggregate_type="Workflow",
            payload={
                "work_item_id": work_item_id,
                "template_id": template.id,
                "project_id": project_id,
                "stage_count": len(workflow.stages)
            }
        )
        workflow._add_event(event)

        return workflow

    # Lifecycle methods
    def start(self) -> None:
        """
        Start workflow execution.

        Business rules:
        - Must be in PENDING status
        - Must have at least one stage

        Emits: WorkflowStarted event
        """
        if self.status != WorkflowStatus.PENDING:
            raise DomainError(f"Cannot start workflow in status {self.status.value}")

        if not self.stages:
            raise DomainError("Cannot start workflow with no stages")

        self.status = WorkflowStatus.RUNNING
        self.started_at = datetime.utcnow()
        self.updated_at = self.started_at
        self._version += 1

        event = WorkflowStarted(
            aggregate_id=self.id,
            aggregate_type="Workflow",
            payload={
                "started_at": self.started_at.isoformat(),
                "work_item_id": self.work_item_id,
                "first_stage": self.stages[0].name
            }
        )
        self._add_event(event)

    def advance_to_next_stage(self) -> None:
        """
        Advance workflow to next stage.

        Business rules:
        - Current stage must be completed
        - Must have remaining stages

        Emits: WorkflowStageAdvanced event
        """
        if self.status != WorkflowStatus.RUNNING:
            raise DomainError("Cannot advance non-running workflow")

        current_stage = self.get_current_stage()
        if not current_stage.is_completed():
            raise DomainError("Cannot advance: current stage not completed")

        # Mark current stage as completed
        self.completed_stages.append(current_stage.name)

        # Check if workflow is complete
        if self.current_stage_index >= len(self.stages) - 1:
            self.complete()
            return

        # Move to next stage
        old_stage = current_stage.name
        self.current_stage_index += 1
        new_stage = self.get_current_stage().name
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = WorkflowStageAdvanced(
            aggregate_id=self.id,
            aggregate_type="Workflow",
            payload={
                "from_stage": old_stage,
                "to_stage": new_stage,
                "stage_index": self.current_stage_index,
                "advanced_at": self.updated_at.isoformat()
            }
        )
        self._add_event(event)

    def complete(self) -> None:
        """
        Mark workflow as completed.

        Business rules:
        - Must be running
        - All stages must be completed

        Emits: WorkflowCompleted event
        """
        if self.status != WorkflowStatus.RUNNING:
            raise DomainError(f"Cannot complete workflow in status {self.status.value}")

        # Verify all stages completed
        for stage in self.stages:
            if not stage.is_completed():
                raise DomainError(f"Cannot complete: stage {stage.name} not completed")

        self.status = WorkflowStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.updated_at = self.completed_at
        self._version += 1

        event = WorkflowCompleted(
            aggregate_id=self.id,
            aggregate_type="Workflow",
            payload={
                "completed_at": self.completed_at.isoformat(),
                "work_item_id": self.work_item_id,
                "duration_seconds": (self.completed_at - self.started_at).total_seconds()
            }
        )
        self._add_event(event)

    def fail(self, reason: str, failed_stage: Optional[str] = None) -> None:
        """
        Mark workflow as failed.

        Emits: WorkflowFailed event
        """
        if self.status in [WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED]:
            raise DomainError(f"Cannot fail workflow in terminal status {self.status.value}")

        self.status = WorkflowStatus.FAILED
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = WorkflowFailed(
            aggregate_id=self.id,
            aggregate_type="Workflow",
            payload={
                "failed_at": self.updated_at.isoformat(),
                "reason": reason,
                "failed_stage": failed_stage or self.get_current_stage().name,
                "completed_stages": self.completed_stages
            }
        )
        self._add_event(event)

    def pause(self, reason: str) -> None:
        """
        Pause workflow execution.

        Emits: WorkflowPaused event
        """
        if self.status != WorkflowStatus.RUNNING:
            raise DomainError("Can only pause running workflows")

        self.status = WorkflowStatus.PAUSED
        self.paused_at = datetime.utcnow()
        self.updated_at = self.paused_at
        self._version += 1

        event = WorkflowPaused(
            aggregate_id=self.id,
            aggregate_type="Workflow",
            payload={
                "paused_at": self.paused_at.isoformat(),
                "reason": reason,
                "current_stage": self.get_current_stage().name
            }
        )
        self._add_event(event)

    def resume(self) -> None:
        """
        Resume paused workflow.

        Emits: WorkflowResumed event
        """
        if self.status != WorkflowStatus.PAUSED:
            raise DomainError("Can only resume paused workflows")

        self.status = WorkflowStatus.RUNNING
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = WorkflowResumed(
            aggregate_id=self.id,
            aggregate_type="Workflow",
            payload={
                "resumed_at": self.updated_at.isoformat(),
                "current_stage": self.get_current_stage().name
            }
        )
        self._add_event(event)

    def cancel(self, reason: str) -> None:
        """
        Cancel workflow execution.

        Emits: WorkflowCancelled event
        """
        if self.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]:
            raise DomainError(f"Cannot cancel workflow in terminal status {self.status.value}")

        self.status = WorkflowStatus.CANCELLED
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = WorkflowCancelled(
            aggregate_id=self.id,
            aggregate_type="Workflow",
            payload={
                "cancelled_at": self.updated_at.isoformat(),
                "reason": reason,
                "completed_stages": self.completed_stages
            }
        )
        self._add_event(event)

    # Stage management
    def get_current_stage(self) -> 'PipelineStage':
        """Get the current pipeline stage."""
        if self.current_stage_index >= len(self.stages):
            raise DomainError("Invalid stage index")
        return self.stages[self.current_stage_index]

    def get_stage_by_name(self, name: str) -> Optional['PipelineStage']:
        """Get stage by name."""
        for stage in self.stages:
            if stage.name == name:
                return stage
        return None

    def update_stage_status(self, stage_name: str, status: str) -> None:
        """
        Update status of a specific stage.

        Emits: WorkflowStageStatusUpdated event
        """
        stage = self.get_stage_by_name(stage_name)
        if not stage:
            raise DomainError(f"Stage {stage_name} not found")

        old_status = stage.status
        stage.update_status(status)
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = WorkflowStageStatusUpdated(
            aggregate_id=self.id,
            aggregate_type="Workflow",
            payload={
                "stage_name": stage_name,
                "old_status": old_status,
                "new_status": status,
                "updated_at": self.updated_at.isoformat()
            }
        )
        self._add_event(event)

    # Query methods
    def is_completed(self) -> bool:
        """Check if workflow is completed."""
        return self.status == WorkflowStatus.COMPLETED

    def is_failed(self) -> bool:
        """Check if workflow has failed."""
        return self.status == WorkflowStatus.FAILED

    def is_running(self) -> bool:
        """Check if workflow is currently running."""
        return self.status == WorkflowStatus.RUNNING

    def get_progress_percentage(self) -> float:
        """Calculate workflow completion percentage."""
        if not self.stages:
            return 0.0
        return (len(self.completed_stages) / len(self.stages)) * 100

    def get_duration_seconds(self) -> Optional[int]:
        """Get workflow duration in seconds."""
        if not self.started_at:
            return None

        end_time = self.completed_at or datetime.utcnow()
        return int((end_time - self.started_at).total_seconds())

    # Validation helpers
    def _count_parallel_stages(self) -> int:
        """Count number of parallel stages."""
        return sum(1 for stage in self.stages if stage.is_parallel)

    def _has_circular_dependencies(self) -> bool:
        """Check if stage dependencies create a cycle."""
        visited = set()
        rec_stack = set()

        def has_cycle(stage_name: str) -> bool:
            visited.add(stage_name)
            rec_stack.add(stage_name)

            stage = self.get_stage_by_name(stage_name)
            if stage:
                for dep in stage.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(stage_name)
            return False

        for stage in self.stages:
            if stage.name not in visited:
                if has_cycle(stage.name):
                    return True

        return False

    def _all_dependencies_satisfied(self) -> bool:
        """Check if all stage dependencies reference valid stages."""
        stage_names = {stage.name for stage in self.stages}

        for stage in self.stages:
            for dep in stage.dependencies:
                if dep not in stage_names:
                    return False

        return True

    # Event management
    def _add_event(self, event: DomainEvent) -> None:
        """Add event to pending events list."""
        self._events.append(event)

    def get_pending_events(self) -> List[DomainEvent]:
        """Get all pending events."""
        return self._events.copy()

    def clear_events(self) -> None:
        """Clear pending events (after persistence)."""
        self._events.clear()

    # Event sourcing support
    @classmethod
    def from_events(cls, events: List[DomainEvent]) -> 'Workflow':
        """Reconstruct workflow from event stream."""
        if not events:
            raise DomainError("Cannot reconstruct workflow from empty event stream")

        first_event = events[0]
        if not isinstance(first_event, WorkflowCreated):
            raise DomainError("First event must be WorkflowCreated")

        # This is simplified - actual implementation would need to
        # reconstruct stages from template or events
        payload = first_event.payload
        workflow = cls(
            id=first_event.aggregate_id,
            work_item_id=payload["work_item_id"],
            template_id=payload["template_id"],
            project_id=payload["project_id"],
            status=WorkflowStatus.PENDING,
            stages=[],  # Would be reconstructed
            current_stage_index=0,
            completed_stages=[],
            started_at=None,
            completed_at=None,
            paused_at=None,
            metadata={},
            created_at=first_event.occurred_at,
            updated_at=first_event.occurred_at
        )

        # Apply subsequent events
        for event in events[1:]:
            workflow._apply_event(event)

        workflow._version = len(events)
        return workflow

    def _apply_event(self, event: DomainEvent) -> None:
        """Apply event to update state."""
        if isinstance(event, WorkflowStarted):
            self.status = WorkflowStatus.RUNNING
            self.started_at = event.occurred_at

        elif isinstance(event, WorkflowStageAdvanced):
            self.current_stage_index = event.payload["stage_index"]
            self.completed_stages = event.payload.get("completed_stages", [])

        elif isinstance(event, WorkflowCompleted):
            self.status = WorkflowStatus.COMPLETED
            self.completed_at = event.occurred_at

        elif isinstance(event, WorkflowFailed):
            self.status = WorkflowStatus.FAILED

        elif isinstance(event, WorkflowPaused):
            self.status = WorkflowStatus.PAUSED
            self.paused_at = event.occurred_at

        elif isinstance(event, WorkflowResumed):
            self.status = WorkflowStatus.RUNNING

        elif isinstance(event, WorkflowCancelled):
            self.status = WorkflowStatus.CANCELLED

        self.updated_at = event.occurred_at
```

## Domain Events

### WorkflowCreated
Emitted when a workflow is created from a template.

### WorkflowStarted
Emitted when workflow execution begins.

### WorkflowStageAdvanced
Emitted when workflow moves to the next stage.

### WorkflowStageStatusUpdated
Emitted when a stage's status changes.

### WorkflowCompleted
Emitted when workflow completes successfully.

### WorkflowFailed
Emitted when workflow fails.

### WorkflowPaused / WorkflowResumed
Emitted when workflow is paused or resumed.

### WorkflowCancelled
Emitted when workflow is cancelled.

## Business Rules

### Creation Rules
1. Must be created from a valid template
2. Must reference a valid work item
3. Must have at least one stage
4. Initial status is always PENDING

### Stage Dependency Rules
1. Maximum 10 parallel stages
2. No circular dependencies allowed
3. All dependencies must reference valid stages
4. Dependencies must be satisfied before stage execution

### Transition Rules
1. PENDING → RUNNING (via start)
2. RUNNING → PAUSED (via pause)
3. PAUSED → RUNNING (via resume)
4. RUNNING → COMPLETED (via complete, all stages done)
5. RUNNING → FAILED (via fail)
6. Any non-terminal → CANCELLED (via cancel)

### Invariants
1. Must have at least one stage
2. Current stage index must be valid
3. Cannot exceed max parallel stages
4. Stage dependencies must be acyclic
5. All completed stages must be valid stage names

## Integration Points

### Input Ports
- **WorkflowCommandPort**: Commands to create/manage workflows

### Output Ports
- **IEventStore**: Persist workflow events
- **INotifier**: Notify on workflow status changes

### Application Services
- **WorkflowOrchestrator**: Manages workflow lifecycle
- **PipelineManager**: Controls pipeline execution

## CQRS Read Model

```python
@dataclass
class WorkflowReadModel:
    """Optimized read model for workflow queries."""
    id: str
    work_item_id: str
    work_item_title: str  # Denormalized
    project_id: str
    status: str
    current_stage: str
    completed_stages: List[str]
    total_stages: int
    progress_percentage: float
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    created_at: datetime
    updated_at: datetime
```

## Testing Approach

```python
def test_create_workflow():
    """Test workflow creation from template."""
    template = WorkflowTemplate.create("test-template")
    template.add_stage("stage1", "agent1")

    workflow = Workflow.create("work-1", template, "proj-1")

    assert workflow.status == WorkflowStatus.PENDING
    assert len(workflow.stages) == 1

def test_workflow_lifecycle():
    """Test complete workflow lifecycle."""
    workflow = create_test_workflow()

    workflow.start()
    assert workflow.status == WorkflowStatus.RUNNING

    # Complete stage and advance
    current_stage = workflow.get_current_stage()
    current_stage.complete()
    workflow.advance_to_next_stage()

    assert workflow.status == WorkflowStatus.COMPLETED

def test_circular_dependency_detection():
    """Test that circular dependencies are rejected."""
    template = WorkflowTemplate.create("circular")
    stage1 = template.add_stage("stage1", "agent1", dependencies=["stage2"])
    stage2 = template.add_stage("stage2", "agent2", dependencies=["stage1"])

    with pytest.raises(DomainError):
        Workflow.create("work-1", template, "proj-1")
```

## Migration from Legacy

### Legacy Mapping
| Legacy | Domain | Notes |
|--------|--------|-------|
| Pipeline execution | Workflow | Explicit aggregate |
| Stage configs | Pipeline stages | First-class entities |
| pipeline_run_id | workflow.id | Type-safe ID |
| Pipeline state dict | Workflow status | Structured state machine |

### Key Improvements
1. **Explicit Lifecycle**: Clear workflow states with validation
2. **Dependency Management**: Built-in cycle detection
3. **Event Sourcing**: Complete execution audit trail
4. **Progress Tracking**: First-class progress calculation
5. **Pause/Resume**: Explicit workflow control

## References

- **Pipeline Stage**: `pipeline_stage_design.md`
- **Workflow Template**: `workflow_template_design.md`
- **Domain Events**: `domain_events_design.md`
