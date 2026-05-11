"""Execution domain events.

Events track agent execution lifecycle, including initialization, start,
completion, failure, and timeouts detected by watchdogs.

All events are immutable (frozen dataclasses) to maintain event sourcing
audit trail integrity and enable observability integration.
"""

from dataclasses import dataclass
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class ExecutionInitializedEvent(CodetoreumEvent):
    """Emitted when an agent execution is initialized.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "execution.initialized"
        execution_id (str): Unique ID for the execution
        work_item_id (str): Work item being processed
        agent_id (str): Agent assigned to the execution
        source (str): Always "agent_execution_service"
    """

    execution_id: str = ""
    work_item_id: str = ""
    agent_id: str = ""
    stage_name: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.agent_id:
            msg = "agent_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "stage_name": self.stage_name,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionInitializedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "execution.initialized"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "agent_execution_service"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            work_item_id=data["work_item_id"],
            agent_id=data["agent_id"],
            stage_name=data.get("stage_name", ""),
        )


@dataclass(frozen=True)
class ExecutionStartedEvent(CodetoreumEvent):
    """Emitted when an agent execution starts running.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "execution.started"
        execution_id (str): Unique ID for the execution
        work_item_id (str): Work item being processed
        agent_id (str): Agent assigned to the execution
        container_name (str | None): Name of container where execution runs
        source (str): Always "agent_execution_service"
    """

    execution_id: str = ""
    work_item_id: str = ""
    agent_id: str = ""
    container_name: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.agent_id:
            msg = "agent_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "container_name": self.container_name,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "execution.started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "agent_execution_service"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            work_item_id=data["work_item_id"],
            agent_id=data["agent_id"],
            container_name=data.get("container_name"),
        )


@dataclass(frozen=True)
class ExecutionCompletedEvent(CodetoreumEvent):
    """Emitted when an agent execution completes successfully.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "execution.completed"
        execution_id (str): Unique ID for the execution
        work_item_id (str): Work item being processed
        agent_id (str): Agent that completed the execution
        output (str): Execution result/output
        source (str): Always "agent_execution_service"
    """

    execution_id: str = ""
    work_item_id: str = ""
    agent_id: str = ""
    output: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.agent_id:
            msg = "agent_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "output": self.output,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionCompletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "execution.completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "agent_execution_service"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            work_item_id=data["work_item_id"],
            agent_id=data["agent_id"],
            output=data.get("output", ""),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
        )


@dataclass(frozen=True)
class ExecutionFailedEvent(CodetoreumEvent):
    """Emitted when an agent execution fails.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "execution.failed"
        execution_id (str): Unique ID for the execution
        work_item_id (str): Work item being processed
        agent_id (str): Agent that failed
        error (str): Error message describing the failure
        source (str): Always "agent_execution_service"
    """

    execution_id: str = ""
    work_item_id: str = ""
    agent_id: str = ""
    error: str = ""
    error_message: str = ""
    exit_code: int | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.agent_id:
            msg = "agent_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "error": self.error,
                "error_message": self.error_message,
                "exit_code": self.exit_code,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionFailedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "execution.failed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "agent_execution_service"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            work_item_id=data["work_item_id"],
            agent_id=data["agent_id"],
            error=data.get("error", ""),
            error_message=data.get("error_message", ""),
            exit_code=data.get("exit_code"),
        )


@dataclass(frozen=True)
class ExecutionTimedOutEvent(CodetoreumEvent):
    """Emitted when an agent execution exceeds its timeout threshold.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    This event is emitted by ExecutionTimeoutWatchdog when an active execution
    has been running longer than its configured timeout_seconds threshold.
    It signals that the execution is stuck and should be cancelled.

    Attributes:
        type (str): Fixed to "execution.timed_out"
        execution_id (str): Unique ID for the execution that timed out
        work_item_id (str): Work item being processed
        timeout_seconds (int): Timeout threshold that was exceeded
        started_at (str): ISO 8601 timestamp when execution started
        timestamp (str): ISO 8601 timestamp when timeout was detected
        source (str): Always "execution_timeout_watchdog"

    Example:
        >>> event = ExecutionTimedOutEvent(
        ...     type="execution.timed_out",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="execution_timeout_watchdog",
        ...     execution_id="exec-123",
        ...     work_item_id="issue-456",
        ...     timeout_seconds=3600,
        ...     started_at="2025-01-14T09:15:00+00:00",
        ... )
        >>> event.execution_id = "exec-789"  # Raises FrozenInstanceError
    """

    execution_id: str = ""
    work_item_id: str = ""
    timeout_seconds: int = 0
    started_at: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if self.timeout_seconds <= 0:
            msg = "timeout_seconds must be > 0"
            raise ValueError(msg)
        if not self.started_at:
            msg = "started_at is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "work_item_id": self.work_item_id,
                "timeout_seconds": self.timeout_seconds,
                "started_at": self.started_at,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionTimedOutEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (execution_id, work_item_id,
                     timeout_seconds, started_at) are missing.
        """
        return cls(
            type=data.get("type", "execution.timed_out"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "execution_timeout_watchdog"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            work_item_id=data["work_item_id"],
            timeout_seconds=data["timeout_seconds"],
            started_at=data["started_at"],
        )


@dataclass(frozen=True)
class ExecutionCancelledEvent(CodetoreumEvent):
    """Emitted when an agent execution is cancelled.

    Fields:
        execution_id: Unique execution identifier
        work_item_id: Work item being processed
        agent_id: Agent that was executing
        cancelled_at: ISO timestamp when cancelled
    """

    execution_id: str = ""
    work_item_id: str = ""
    agent_id: str = ""
    cancelled_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.execution_id:
            raise ValueError("execution_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "execution_id": self.execution_id,
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "cancelled_at": self.cancelled_at,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionCancelledEvent":
        return cls(
            type=data.get("type", "execution.cancelled"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            execution_id=data["execution_id"],
            work_item_id=data["work_item_id"],
            agent_id=data.get("agent_id", ""),
            cancelled_at=data.get("cancelled_at", ""),
        )


@dataclass(frozen=True)
class ExecutionPausedEvent(CodetoreumEvent):
    """Emitted when an agent execution is paused.

    Fields:
        execution_id: Unique execution identifier
        work_item_id: Work item being processed
        agent_id: Agent that was executing
        paused_at: ISO timestamp when paused
    """

    execution_id: str = ""
    work_item_id: str = ""
    agent_id: str = ""
    paused_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.execution_id:
            raise ValueError("execution_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "execution_id": self.execution_id,
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "paused_at": self.paused_at,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionPausedEvent":
        return cls(
            type=data.get("type", "execution.paused"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            execution_id=data["execution_id"],
            work_item_id=data["work_item_id"],
            agent_id=data.get("agent_id", ""),
            paused_at=data.get("paused_at", ""),
        )


@dataclass(frozen=True)
class ExecutionResumedEvent(CodetoreumEvent):
    """Emitted when an agent execution is resumed after being paused.

    Fields:
        execution_id: Unique execution identifier
        work_item_id: Work item being processed
        agent_id: Agent that was executing
        resumed_at: ISO timestamp when resumed
    """

    execution_id: str = ""
    work_item_id: str = ""
    agent_id: str = ""
    resumed_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.execution_id:
            raise ValueError("execution_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "execution_id": self.execution_id,
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "resumed_at": self.resumed_at,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionResumedEvent":
        return cls(
            type=data.get("type", "execution.resumed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            execution_id=data["execution_id"],
            work_item_id=data["work_item_id"],
            agent_id=data.get("agent_id", ""),
            resumed_at=data.get("resumed_at", ""),
        )


@dataclass(frozen=True)
class ExecutionRetryScheduledEvent(CodetoreumEvent):
    """Emitted when an agent execution retry is scheduled.

    Fields:
        execution_id: Unique execution identifier
        work_item_id: Work item being processed
        agent_id: Agent that will retry
        retry_count: Current retry attempt number
        retry_at: ISO timestamp when retry is scheduled
    """

    execution_id: str = ""
    work_item_id: str = ""
    agent_id: str = ""
    retry_count: int = 0
    retry_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.execution_id:
            raise ValueError("execution_id is required")
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "execution_id": self.execution_id,
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "retry_count": self.retry_count,
                "retry_at": self.retry_at,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionRetryScheduledEvent":
        return cls(
            type=data.get("type", "execution.retry_scheduled"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id", ""),
            event_id=data.get("event_id", ""),
            execution_id=data["execution_id"],
            work_item_id=data["work_item_id"],
            agent_id=data.get("agent_id", ""),
            retry_count=data.get("retry_count", 0),
            retry_at=data.get("retry_at", ""),
        )
