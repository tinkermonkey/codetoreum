"""Scheduler-related events for agent task scheduling.

Events track changes to task scheduling including queueing, throttling,
and rejection due to rate limiting or resource constraints.
"""

from dataclasses import dataclass
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class TaskQueuedEvent(CodetoreumEvent):
    """Emitted when a task is successfully enqueued for agent execution.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "task.queued"
        task_id (str): Unique identifier for the task
        agent (str): Agent that will execute the task
        project (str): Project context for the task
        priority (str): Task priority level (from WorkItemPriority)
        reason (str): Reason for queueing the task

    Example:
        >>> event = TaskQueuedEvent(
        ...     type="task.queued",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="agent_scheduler",
        ...     task_id="task-123",
        ...     agent="code_review_agent",
        ...     project="proj-1",
        ...     priority="high",
        ...     reason="Workflow transition triggered"
        ... )
        >>> event.task_id = "task-456"  # ❌ Raises FrozenInstanceError
    """

    task_id: str = ""
    agent: str = ""
    project: str = ""
    priority: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.task_id:
            msg = "task_id is required"
            raise ValueError(msg)
        if not self.agent:
            msg = "agent is required"
            raise ValueError(msg)
        if not self.project:
            msg = "project is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "task_id": self.task_id,
                "agent": self.agent,
                "project": self.project,
                "priority": self.priority,
                "reason": self.reason,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TaskQueuedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "task.queued"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            task_id=data.get("task_id", ""),
            agent=data.get("agent", ""),
            project=data.get("project", ""),
            priority=data.get("priority", ""),
            reason=data.get("reason", ""),
        )


@dataclass(frozen=True)
class TaskThrottledEvent(CodetoreumEvent):
    """Emitted when a task is throttled due to rate limiting.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "task.throttled"
        agent (str): Agent that was throttled
        project (str): Project context
        reason (str): Reason for throttling
        retry_after (int): Seconds to wait before retry

    Example:
        >>> event = TaskThrottledEvent(
        ...     type="task.throttled",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="agent_scheduler",
        ...     agent="code_review_agent",
        ...     project="proj-1",
        ...     reason="Rate limit exceeded",
        ...     retry_after=30
        ... )
        >>> event.retry_after = 60  # ❌ Raises FrozenInstanceError
    """

    agent: str = ""
    project: str = ""
    reason: str = ""
    retry_after: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.agent:
            msg = "agent is required"
            raise ValueError(msg)
        if not self.project:
            msg = "project is required"
            raise ValueError(msg)
        if self.retry_after < 0:
            msg = "retry_after cannot be negative"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "agent": self.agent,
                "project": self.project,
                "reason": self.reason,
                "retry_after": self.retry_after,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TaskThrottledEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "task.throttled"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            agent=data.get("agent", ""),
            project=data.get("project", ""),
            reason=data.get("reason", ""),
            retry_after=data.get("retry_after", 0),
        )


@dataclass(frozen=True)
class TaskRejectedEvent(CodetoreumEvent):
    """Emitted when a task is rejected and cannot be executed.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "task.rejected"
        agent (str): Agent that rejected the task
        project (str): Project context
        reason (str): Reason for rejection

    Example:
        >>> event = TaskRejectedEvent(
        ...     type="task.rejected",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="agent_scheduler",
        ...     agent="code_review_agent",
        ...     project="proj-1",
        ...     reason="Docker unavailable"
        ... )
        >>> event.reason = "other reason"  # ❌ Raises FrozenInstanceError
    """

    agent: str = ""
    project: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.agent:
            msg = "agent is required"
            raise ValueError(msg)
        if not self.project:
            msg = "project is required"
            raise ValueError(msg)
        if not self.reason:
            msg = "reason is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "agent": self.agent,
                "project": self.project,
                "reason": self.reason,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TaskRejectedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "task.rejected"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            agent=data.get("agent", ""),
            project=data.get("project", ""),
            reason=data.get("reason", ""),
        )
