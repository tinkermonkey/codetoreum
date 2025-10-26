# Pipeline Stage Domain Design

## Overview

Pipeline Stage is an entity representing a discrete stage within a workflow pipeline. It defines the stage configuration, dependencies, and tracks execution status.

## Domain Model

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class StageStatus(Enum):
    """Status enumeration for pipeline stages."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class StageType(Enum):
    """Type of pipeline stage."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    REVIEW = "review"

@dataclass
class PipelineStage:
    """
    Pipeline Stage entity.

    Represents a stage in a workflow pipeline with dependencies and execution tracking.
    """

    # Identity
    name: str
    workflow_id: str

    # Configuration
    stage_type: StageType
    agent_id: str
    description: str

    # Dependencies
    dependencies: List[str]
    is_parallel: bool

    # Review configuration (if stage_type == REVIEW)
    requires_review: bool
    maker_agent_id: Optional[str]
    reviewer_agent_id: Optional[str]
    max_review_iterations: int

    # Status
    status: StageStatus

    # Execution tracking
    execution_id: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    # Results
    output: Optional[str]
    error_message: Optional[str]

    # Metadata
    metadata: Dict[str, Any]

    @classmethod
    def create(cls,
               name: str,
               workflow_id: str,
               agent_id: str,
               stage_type: StageType = StageType.SEQUENTIAL,
               description: str = "",
               dependencies: Optional[List[str]] = None,
               is_parallel: bool = False,
               requires_review: bool = False,
               maker_agent_id: Optional[str] = None,
               reviewer_agent_id: Optional[str] = None,
               max_review_iterations: int = 3) -> 'PipelineStage':
        """Create new pipeline stage."""
        return cls(
            name=name,
            workflow_id=workflow_id,
            stage_type=stage_type,
            agent_id=agent_id,
            description=description,
            dependencies=dependencies or [],
            is_parallel=is_parallel,
            requires_review=requires_review,
            maker_agent_id=maker_agent_id,
            reviewer_agent_id=reviewer_agent_id,
            max_review_iterations=max_review_iterations,
            status=StageStatus.PENDING,
            execution_id=None,
            started_at=None,
            completed_at=None,
            output=None,
            error_message=None,
            metadata={}
        )

    def can_start(self, completed_stages: List[str]) -> bool:
        """
        Check if stage can start based on dependencies.

        Business rules:
        - All dependencies must be completed
        - Stage must be in PENDING or READY status
        """
        if self.status not in [StageStatus.PENDING, StageStatus.READY]:
            return False

        return all(dep in completed_stages for dep in self.dependencies)

    def mark_ready(self) -> None:
        """Mark stage as ready to execute."""
        if self.status != StageStatus.PENDING:
            raise DomainError(f"Cannot mark ready: stage in status {self.status.value}")

        self.status = StageStatus.READY

    def start(self, execution_id: str) -> None:
        """Start stage execution."""
        if self.status != StageStatus.READY:
            raise DomainError(f"Cannot start: stage not ready (status: {self.status.value})")

        self.status = StageStatus.RUNNING
        self.execution_id = execution_id
        self.started_at = datetime.utcnow()

    def complete(self, output: str) -> None:
        """Complete stage successfully."""
        if self.status != StageStatus.RUNNING:
            raise DomainError(f"Cannot complete: stage not running")

        self.status = StageStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.output = output

    def fail(self, error_message: str) -> None:
        """Mark stage as failed."""
        if self.status not in [StageStatus.READY, StageStatus.RUNNING]:
            raise DomainError(f"Cannot fail: invalid status {self.status.value}")

        self.status = StageStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error_message

    def skip(self, reason: str) -> None:
        """Skip stage execution."""
        if self.status != StageStatus.PENDING:
            raise DomainError(f"Cannot skip: stage in status {self.status.value}")

        self.status = StageStatus.SKIPPED
        self.metadata["skip_reason"] = reason
        self.completed_at = datetime.utcnow()

    def is_completed(self) -> bool:
        """Check if stage completed successfully."""
        return self.status == StageStatus.COMPLETED

    def is_failed(self) -> bool:
        """Check if stage failed."""
        return self.status == StageStatus.FAILED

    def is_terminal(self) -> bool:
        """Check if stage is in terminal state."""
        return self.status in [StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.SKIPPED]

    def get_duration_seconds(self) -> Optional[float]:
        """Get stage duration."""
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def update_status(self, status: str) -> None:
        """Update stage status (for workflow use)."""
        self.status = StageStatus(status)
```

## Business Rules

### Dependency Rules
1. Stage cannot start until all dependencies completed
2. Dependencies must reference valid stages
3. No circular dependencies allowed (validated at workflow level)

### Review Stage Rules
1. Review stages must have both maker and reviewer agents
2. Maker and reviewer must be different agents
3. Maximum review iterations enforced (default: 3)

### Status Transitions
- PENDING → READY (dependencies satisfied)
- READY → RUNNING (execution started)
- RUNNING → COMPLETED (successful)
- RUNNING → FAILED (error)
- PENDING → SKIPPED (conditional skip)

## Integration with Workflow

Pipeline stages are part of the Workflow aggregate:

```python
class Workflow:
    stages: List[PipelineStage]

    def get_ready_stages(self) -> List[PipelineStage]:
        """Get all stages ready to execute."""
        return [
            stage for stage in self.stages
            if stage.can_start(self.completed_stages)
        ]
```

## Testing

```python
def test_stage_dependencies():
    stage1 = PipelineStage.create("stage1", "wf-1", "agent-1")
    stage2 = PipelineStage.create("stage2", "wf-1", "agent-2", dependencies=["stage1"])

    assert not stage2.can_start([])
    assert not stage2.can_start(["other-stage"])
    assert stage2.can_start(["stage1"])

def test_stage_lifecycle():
    stage = PipelineStage.create("test", "wf-1", "agent-1")

    stage.mark_ready()
    stage.start("exec-1")
    assert stage.status == StageStatus.RUNNING

    stage.complete("output")
    assert stage.is_completed()
```

## Migration from Legacy

| Legacy | Domain |
|--------|--------|
| pipeline_stage dict | PipelineStage entity |
| stage_config | PipelineStage fields |
| stage dependencies | dependencies list |

## References

- **Workflow**: `workflow_design.md`
- **Review Cycle**: `review_cycle_design.md`
