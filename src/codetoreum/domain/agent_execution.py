"""Agent Execution entity."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from codetoreum.domain.events import (
    DomainEvent,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionInitialized,
    ExecutionStarted,
    ExecutionTimeout,
)
from codetoreum.domain.exceptions import DomainError


class ExecutionStatus(Enum):
    """Status enumeration for agent executions."""

    PENDING = "pending"  # Waiting to be started
    INITIALIZED = "initialized"  # Created but not yet running
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
    def create(
        cls,
        agent_id: str,
        work_item_id: str,
        workflow_id: str,
        stage_name: str,
        prompt: str,
        model: str,
        session_id: Optional[str] = None,
    ) -> "AgentExecution":
        """
        Create new agent execution.

        Args:
            agent_id: ID of the agent to execute
            work_item_id: ID of the work item being processed
            workflow_id: ID of the workflow this execution belongs to
            stage_name: Name of the workflow stage
            prompt: Prompt to send to the agent
            model: LLM model to use
            session_id: Optional session ID for continuity

        Returns:
            Newly created AgentExecution instance

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
            initialized_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            metadata={},
        )

        event = ExecutionInitialized(
            aggregate_id=execution.id,
            payload={
                "agent_id": agent_id,
                "work_item_id": work_item_id,
                "workflow_id": workflow_id,
                "stage_name": stage_name,
                "model": model,
            },
        )
        execution._add_event(event)

        return execution

    def start(self, container_name: Optional[str] = None) -> None:
        """
        Start execution.

        Args:
            container_name: Optional name of container where execution runs

        Raises:
            DomainError: If execution is not in INITIALIZED status

        Emits: ExecutionStarted event
        """
        if self.status != ExecutionStatus.INITIALIZED:
            raise DomainError(f"Cannot start execution in status {self.status.value}")

        self.status = ExecutionStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        self.container_name = container_name

        event = ExecutionStarted(
            aggregate_id=self.id,
            payload={
                "started_at": self.started_at.isoformat(),
                "container_name": container_name,
            },
        )
        self._add_event(event)

    def complete(
        self,
        output: str,
        input_tokens: int,
        output_tokens: int,
        session_id: Optional[str] = None,
    ) -> None:
        """
        Mark execution as completed successfully.

        Args:
            output: Execution output/result
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            session_id: Optional session ID for continuity

        Raises:
            DomainError: If execution is not in RUNNING status

        Emits: ExecutionCompleted event
        """
        if self.status != ExecutionStatus.RUNNING:
            raise DomainError(
                f"Cannot complete execution in status {self.status.value}"
            )

        self.status = ExecutionStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.output = output
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.exit_code = 0

        if session_id:
            self.session_id = session_id

        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

        event = ExecutionCompleted(
            aggregate_id=self.id,
            payload={
                "completed_at": self.completed_at.isoformat(),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "duration_seconds": self.duration_seconds,
                "session_id": session_id,
            },
        )
        self._add_event(event)

    def fail(self, error_message: str, exit_code: Optional[int] = None) -> None:
        """
        Mark execution as failed.

        Args:
            error_message: Description of the failure
            exit_code: Optional exit code from execution

        Raises:
            DomainError: If execution is not in INITIALIZED or RUNNING status

        Emits: ExecutionFailed event
        """
        if self.status not in [ExecutionStatus.INITIALIZED, ExecutionStatus.RUNNING]:
            raise DomainError(f"Cannot fail execution in status {self.status.value}")

        self.status = ExecutionStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = error_message
        self.exit_code = exit_code

        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

        event = ExecutionFailed(
            aggregate_id=self.id,
            payload={
                "failed_at": self.completed_at.isoformat(),
                "error_message": error_message,
                "exit_code": exit_code,
                "duration_seconds": self.duration_seconds,
            },
        )
        self._add_event(event)

    def timeout(self) -> None:
        """
        Mark execution as timed out.

        Raises:
            DomainError: If execution is not in RUNNING status

        Emits: ExecutionTimeout event
        """
        if self.status != ExecutionStatus.RUNNING:
            raise DomainError(f"Cannot timeout execution in status {self.status.value}")

        self.status = ExecutionStatus.TIMEOUT
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = "Execution exceeded timeout"
        self.exit_code = -1

        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

        event = ExecutionTimeout(
            aggregate_id=self.id,
            payload={
                "timeout_at": self.completed_at.isoformat(),
                "duration_seconds": self.duration_seconds,
            },
        )
        self._add_event(event)

    # Query methods
    def is_completed(self) -> bool:
        """
        Check if execution completed successfully.

        Returns:
            True if execution completed successfully
        """
        return self.status == ExecutionStatus.COMPLETED

    def is_failed(self) -> bool:
        """
        Check if execution failed.

        Returns:
            True if execution failed or timed out
        """
        return self.status in [ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT]

    def is_terminal(self) -> bool:
        """
        Check if execution is in terminal state.

        Returns:
            True if execution is in a terminal state
        """
        return self.status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.CANCELLED,
        ]

    def get_total_tokens(self) -> int:
        """
        Get total tokens used.

        Returns:
            Sum of input and output tokens
        """
        return self.input_tokens + self.output_tokens

    def _add_event(self, event: DomainEvent) -> None:
        """
        Add event to pending events.

        Args:
            event: Domain event to add
        """
        self._events.append(event)

    def get_pending_events(self) -> List[DomainEvent]:
        """
        Get pending events.

        Returns:
            Shallow copy of the pending events list. Creates a new list
            containing references to the same event objects.
        """
        return list(self._events)

    def clear_events(self) -> None:
        """Clear pending events."""
        self._events.clear()
