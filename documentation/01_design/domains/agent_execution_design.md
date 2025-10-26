# Agent Execution Domain Design

## Overview

Agent Execution is an entity representing a single instance of an agent performing work. It tracks the execution lifecycle, context, results, and metrics.

## Domain Model

```python
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

class ExecutionStatus(Enum):
    """Status enumeration for agent executions."""
    INITIALIZED = "initialized"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

@dataclass
class AgentExecution:
    """
    Agent Execution entity.

    Represents a single execution instance of an agent.
    Part of the Workflow aggregate but has its own identity.
    """

    # Identity
    id: str
    agent_id: str
    work_item_id: str
    workflow_id: str
    stage_name: str

    # Status
    status: ExecutionStatus

    # Execution context
    prompt: str
    model: str
    session_id: Optional[str]

    # Container tracking
    container_name: Optional[str]
    container_id: Optional[str]

    # Results
    output: Optional[str]
    error_message: Optional[str]
    exit_code: Optional[int]

    # Metrics
    input_tokens: int
    output_tokens: int
    duration_seconds: Optional[float]

    # Timestamps
    initialized_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    # Metadata
    metadata: Dict[str, Any]

    # Event tracking
    _events: List[DomainEvent] = field(default_factory=list, init=False, repr=False)

    @classmethod
    def create(cls,
               agent_id: str,
               work_item_id: str,
               workflow_id: str,
               stage_name: str,
               prompt: str,
               model: str,
               session_id: Optional[str] = None) -> 'AgentExecution':
        """
        Create new agent execution.

        Emits: ExecutionInitialized event
        """
        execution = cls(
            id=str(uuid4()),
            agent_id=agent_id,
            work_item_id=work_item_id,
            workflow_id=workflow_id,
            stage_name=stage_name,
            status=ExecutionStatus.INITIALIZED,
            prompt=prompt,
            model=model,
            session_id=session_id,
            container_name=None,
            container_id=None,
            output=None,
            error_message=None,
            exit_code=None,
            input_tokens=0,
            output_tokens=0,
            duration_seconds=None,
            initialized_at=datetime.utcnow(),
            started_at=None,
            completed_at=None,
            metadata={}
        )

        event = ExecutionInitialized(
            aggregate_id=execution.id,
            aggregate_type="AgentExecution",
            payload={
                "agent_id": agent_id,
                "work_item_id": work_item_id,
                "workflow_id": workflow_id,
                "stage_name": stage_name,
                "model": model
            }
        )
        execution._add_event(event)

        return execution

    def start(self, container_name: Optional[str] = None) -> None:
        """
        Start execution.

        Emits: ExecutionStarted event
        """
        if self.status != ExecutionStatus.INITIALIZED:
            raise DomainError(f"Cannot start execution in status {self.status.value}")

        self.status = ExecutionStatus.RUNNING
        self.started_at = datetime.utcnow()
        self.container_name = container_name

        event = ExecutionStarted(
            aggregate_id=self.id,
            aggregate_type="AgentExecution",
            payload={
                "started_at": self.started_at.isoformat(),
                "container_name": container_name
            }
        )
        self._add_event(event)

    def complete(self,
                 output: str,
                 input_tokens: int,
                 output_tokens: int,
                 session_id: Optional[str] = None) -> None:
        """
        Mark execution as completed successfully.

        Emits: ExecutionCompleted event
        """
        if self.status != ExecutionStatus.RUNNING:
            raise DomainError(f"Cannot complete execution in status {self.status.value}")

        self.status = ExecutionStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.output = output
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.exit_code = 0

        if session_id:
            self.session_id = session_id

        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

        event = ExecutionCompleted(
            aggregate_id=self.id,
            aggregate_type="AgentExecution",
            payload={
                "completed_at": self.completed_at.isoformat(),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "duration_seconds": self.duration_seconds,
                "session_id": session_id
            }
        )
        self._add_event(event)

    def fail(self, error_message: str, exit_code: Optional[int] = None) -> None:
        """
        Mark execution as failed.

        Emits: ExecutionFailed event
        """
        if self.status not in [ExecutionStatus.INITIALIZED, ExecutionStatus.RUNNING]:
            raise DomainError(f"Cannot fail execution in status {self.status.value}")

        self.status = ExecutionStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
        self.exit_code = exit_code

        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

        event = ExecutionFailed(
            aggregate_id=self.id,
            aggregate_type="AgentExecution",
            payload={
                "failed_at": self.completed_at.isoformat(),
                "error_message": error_message,
                "exit_code": exit_code,
                "duration_seconds": self.duration_seconds
            }
        )
        self._add_event(event)

    def timeout(self) -> None:
        """
        Mark execution as timed out.

        Emits: ExecutionTimeout event
        """
        if self.status != ExecutionStatus.RUNNING:
            raise DomainError(f"Cannot timeout execution in status {self.status.value}")

        self.status = ExecutionStatus.TIMEOUT
        self.completed_at = datetime.utcnow()
        self.error_message = "Execution exceeded timeout"
        self.exit_code = -1

        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

        event = ExecutionTimeout(
            aggregate_id=self.id,
            aggregate_type="AgentExecution",
            payload={
                "timeout_at": self.completed_at.isoformat(),
                "duration_seconds": self.duration_seconds
            }
        )
        self._add_event(event)

    # Query methods
    def is_completed(self) -> bool:
        """Check if execution completed successfully."""
        return self.status == ExecutionStatus.COMPLETED

    def is_failed(self) -> bool:
        """Check if execution failed."""
        return self.status in [ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT]

    def is_terminal(self) -> bool:
        """Check if execution is in terminal state."""
        return self.status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.CANCELLED
        ]

    def get_total_tokens(self) -> int:
        """Get total tokens used."""
        return self.input_tokens + self.output_tokens

    def _add_event(self, event: DomainEvent) -> None:
        """Add event to pending events."""
        self._events.append(event)

    def get_pending_events(self) -> List[DomainEvent]:
        """Get pending events."""
        return self._events.copy()

    def clear_events(self) -> None:
        """Clear pending events."""
        self._events.clear()
```

## Domain Events

- **ExecutionInitialized**: Execution created
- **ExecutionStarted**: Execution began
- **ExecutionCompleted**: Execution finished successfully
- **ExecutionFailed**: Execution failed
- **ExecutionTimeout**: Execution timed out

## Business Rules

1. Must be initialized before starting
2. Can only complete/fail/timeout from RUNNING state
3. Duration calculated automatically from timestamps
4. Exit code 0 for success, non-zero for failure
5. Session ID preserved for conversation continuity

## CQRS Read Model

```python
@dataclass
class ExecutionReadModel:
    id: str
    agent_id: str
    agent_name: str  # Denormalized
    work_item_id: str
    workflow_id: str
    stage_name: str
    status: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration_seconds: Optional[float]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
```

## Testing

```python
def test_execution_lifecycle():
    execution = AgentExecution.create(
        agent_id="agent-1",
        work_item_id="work-1",
        workflow_id="wf-1",
        stage_name="coding",
        prompt="Test prompt",
        model="claude-sonnet-4-5"
    )

    execution.start(container_name="agent-container")
    assert execution.status == ExecutionStatus.RUNNING

    execution.complete(
        output="Result",
        input_tokens=100,
        output_tokens=200
    )
    assert execution.is_completed()
    assert execution.get_total_tokens() == 300
```

## Migration from Legacy

| Legacy | Domain |
|--------|--------|
| agent execution tracking | AgentExecution entity |
| execution_id | id |
| tokens_used | input_tokens + output_tokens |
| duration | duration_seconds |

## References

- **Agent**: `agent_design.md`
- **Workflow**: `workflow_design.md`
- **Domain Events**: `domain_events_design.md`
