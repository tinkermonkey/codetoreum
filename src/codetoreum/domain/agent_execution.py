"""Agent Execution entity."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from codetoreum.domain.events import (
    ExecutionCancelledEvent,
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
    ExecutionInitializedEvent,
    ExecutionPausedEvent,
    ExecutionResumedEvent,
    ExecutionStartedEvent,
    ExecutionTimedOutEvent,
)
from codetoreum.domain.exceptions import DomainError


class ExecutionStatus(Enum):
    """Status enumeration for agent executions."""

    PENDING = "pending"  # Waiting to be started
    INITIALIZED = "initialized"  # Created but not yet running
    RUNNING = "running"
    PAUSED = "paused"  # Execution paused by user/system
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
    session_id: str | None

    # Container tracking
    container_name: str | None
    container_id: str | None

    # Results
    output: str | None
    error_message: str | None
    exit_code: int | None

    # Metrics
    input_tokens: int
    output_tokens: int
    duration_seconds: float | None

    # Timestamps
    initialized_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    # Metadata
    metadata: dict[str, Any]

    # Event tracking
    _events: list = field(default_factory=list, init=False, repr=False)

    @classmethod
    def create(
        cls,
        agent_id: str,
        work_item_id: str,
        workflow_id: str,
        stage_name: str,
        prompt: str,
        model: str,
        session_id: str | None = None,
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
            initialized_at=datetime.now(UTC),
            started_at=None,
            completed_at=None,
            metadata={},
        )

        event = ExecutionInitializedEvent(
            type="execution.initialized",
            timestamp=datetime.now(UTC).isoformat(),
            source="agent_execution",
            execution_id=execution.id,
            work_item_id=work_item_id,
            agent_id=agent_id,
            stage_name=stage_name,
        )
        execution._add_event(event)

        return execution

    def start(self, container_name: str | None = None) -> None:
        """
        Start execution.

        Args:
            container_name: Optional name of container where execution runs

        Raises:
            DomainError: If execution is not in INITIALIZED status

        Emits: ExecutionStarted event
        """
        if self.status != ExecutionStatus.INITIALIZED:
            msg = f"Cannot start execution in status {self.status.value}"
            raise DomainError(msg)

        self.status = ExecutionStatus.RUNNING
        self.started_at = datetime.now(UTC)
        self.container_name = container_name

        event = ExecutionStartedEvent(
            type="execution.started",
            timestamp=self.started_at.isoformat(),
            source="agent_execution",
            execution_id=self.id,
            work_item_id=self.work_item_id,
            agent_id=self.agent_id,
            container_name=container_name,
        )
        self._add_event(event)

    def complete(
        self,
        output: str,
        input_tokens: int,
        output_tokens: int,
        session_id: str | None = None,
        commit_sha: str | None = None,
        branch: str | None = None,
    ) -> None:
        """
        Mark execution as completed successfully.

        Args:
            output: Execution output/result
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            session_id: Optional session ID for continuity
            commit_sha: Git commit SHA produced by this execution (None if no file changes)
            branch: Branch that was pushed (None if no commit was made)

        Raises:
            DomainError: If execution is not in RUNNING status

        Emits: ExecutionCompleted event
        """
        if self.status != ExecutionStatus.RUNNING:
            msg = f"Cannot complete execution in status {self.status.value}"
            raise DomainError(msg)

        self.status = ExecutionStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        self.output = output
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.exit_code = 0

        if session_id:
            self.session_id = session_id

        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

        event = ExecutionCompletedEvent(
            type="execution.completed",
            timestamp=self.completed_at.isoformat(),
            source="agent_execution",
            execution_id=self.id,
            work_item_id=self.work_item_id,
            agent_id=self.agent_id,
            output=output or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self._add_event(event)

    def fail(self, error_message: str, exit_code: int | None = None) -> None:
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
            msg = f"Cannot fail execution in status {self.status.value}"
            raise DomainError(msg)

        self.status = ExecutionStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.error_message = error_message
        self.exit_code = exit_code

        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

        event = ExecutionFailedEvent(
            type="execution.failed",
            timestamp=self.completed_at.isoformat(),
            source="agent_execution",
            execution_id=self.id,
            work_item_id=self.work_item_id,
            agent_id=self.agent_id,
            error=error_message,
            error_message=error_message,
            exit_code=exit_code,
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
            msg = f"Cannot timeout execution in status {self.status.value}"
            raise DomainError(msg)

        self.status = ExecutionStatus.TIMEOUT
        self.completed_at = datetime.now(UTC)
        self.error_message = "Execution exceeded timeout"
        self.exit_code = -1

        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

        elapsed = int((self.completed_at - self.started_at).total_seconds()) if self.started_at else 0
        event = ExecutionTimedOutEvent(
            type="execution.timed_out",
            timestamp=self.completed_at.isoformat(),
            source="agent_execution",
            execution_id=self.id,
            work_item_id=self.work_item_id,
            timeout_seconds=max(elapsed, 1),
            started_at=self.started_at.isoformat() if self.started_at else "",
        )
        self._add_event(event)

    def cancel(self, reason: str | None = None) -> None:
        """
        Cancel execution.

        Args:
            reason: Optional reason for cancellation

        Raises:
            DomainError: If execution is not in INITIALIZED, RUNNING, or PAUSED status

        Emits: ExecutionCancelled event
        """
        if self.status not in [
            ExecutionStatus.INITIALIZED,
            ExecutionStatus.RUNNING,
            ExecutionStatus.PAUSED,
        ]:
            msg = f"Cannot cancel execution in status {self.status.value}"
            raise DomainError(msg)

        self.status = ExecutionStatus.CANCELLED
        self.completed_at = datetime.now(UTC)
        self.error_message = reason or "Execution cancelled"
        self.exit_code = -2

        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

        event = ExecutionCancelledEvent(
            type="execution.cancelled",
            timestamp=self.completed_at.isoformat(),
            source="agent_execution",
            execution_id=self.id,
            work_item_id=self.work_item_id,
            agent_id=self.agent_id,
            cancelled_at=self.completed_at.isoformat(),
        )
        self._add_event(event)

    def pause(self, reason: str | None = None) -> None:
        """
        Pause execution.

        Args:
            reason: Optional reason for pausing

        Raises:
            DomainError: If execution is not in RUNNING status

        Emits: ExecutionPaused event
        """
        if self.status != ExecutionStatus.RUNNING:
            msg = f"Cannot pause execution in status {self.status.value}"
            raise DomainError(msg)

        self.status = ExecutionStatus.PAUSED

        event = ExecutionPausedEvent(
            type="execution.paused",
            timestamp=datetime.now(UTC).isoformat(),
            source="agent_execution",
            execution_id=self.id,
            work_item_id=self.work_item_id,
            agent_id=self.agent_id,
            paused_at=datetime.now(UTC).isoformat(),
        )
        self._add_event(event)

    def resume(self) -> None:
        """
        Resume paused execution.

        Raises:
            DomainError: If execution is not in PAUSED status

        Emits: ExecutionResumed event
        """
        if self.status != ExecutionStatus.PAUSED:
            msg = f"Cannot resume execution in status {self.status.value}"
            raise DomainError(msg)

        self.status = ExecutionStatus.RUNNING

        event = ExecutionResumedEvent(
            type="execution.resumed",
            timestamp=datetime.now(UTC).isoformat(),
            source="agent_execution",
            execution_id=self.id,
            work_item_id=self.work_item_id,
            agent_id=self.agent_id,
            resumed_at=datetime.now(UTC).isoformat(),
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

    def _add_event(self, event: object) -> None:
        """
        Add event to pending events.

        Args:
            event: Domain event to add
        """
        self._events.append(event)

    def get_pending_events(self) -> list:
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
