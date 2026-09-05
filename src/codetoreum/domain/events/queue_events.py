"""Queue-related events for pipeline queue service.

Events track changes to pipeline queue items including addition, removal,
and position changes based on board state updates.
"""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class QueueItemAddedEvent(CodetoreumEvent):
    """Emitted when a work item is added to the queue.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "queue.item_added"
        queue_name (str): Name of the queue (typically "project_id:board_id")
        item_id (str): ID of the work item added to queue
        position (int): Position in the queue (0-based)
        project_id (str): ID of the project containing the queue

    Example:
        >>> event = QueueItemAddedEvent(
        ...     type="queue.item_added",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock",
        ...     queue_name="proj-1:board-1",
        ...     item_id="item-1",
        ...     position=0,
        ...     project_id="proj-1"
        ... )
        >>> event.position = 1  # ❌ Raises FrozenInstanceError
    """

    queue_name: str = ""
    item_id: str = ""
    position: int = 0
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.queue_name:
            msg = "queue_name is required"
            raise ValueError(msg)
        if not self.item_id:
            msg = "item_id is required"
            raise ValueError(msg)
        if self.position < 0:
            msg = "position cannot be negative"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "queue_name": self.queue_name,
                "item_id": self.item_id,
                "position": self.position,
                "project_id": self.project_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueItemAddedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "queue.item_added"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            queue_name=data.get("queue_name", ""),
            item_id=data.get("item_id", ""),
            position=data.get("position", 0),
            project_id=data.get("project_id"),
        )


@dataclass(frozen=True)
class QueueItemRemovedEvent(CodetoreumEvent):
    """Emitted when a work item is removed from the queue.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "queue.item_removed"
        queue_name (str): Name of the queue (typically "project_id:board_id")
        item_id (str): ID of the work item removed from queue
        project_id (str): ID of the project containing the queue

    Example:
        >>> event = QueueItemRemovedEvent(
        ...     type="queue.item_removed",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock",
        ...     queue_name="proj-1:board-1",
        ...     item_id="item-1",
        ...     project_id="proj-1"
        ... )
        >>> event.item_id = "item-2"  # ❌ Raises FrozenInstanceError
    """

    queue_name: str = ""
    item_id: str = ""
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.queue_name:
            msg = "queue_name is required"
            raise ValueError(msg)
        if not self.item_id:
            msg = "item_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "queue_name": self.queue_name,
                "item_id": self.item_id,
                "project_id": self.project_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueItemRemovedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "queue.item_removed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            queue_name=data.get("queue_name", ""),
            item_id=data.get("item_id", ""),
            project_id=data.get("project_id"),
        )


@dataclass(frozen=True)
class QueuePositionChangedEvent(CodetoreumEvent):
    """Emitted when a work item's position in the queue changes.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "queue.position_changed"
        queue_name (str): Name of the queue (typically "project_id:board_id")
        item_id (str): ID of the work item
        old_position (int): Previous position in queue
        new_position (int): New position in queue
        project_id (str): ID of the project containing the queue

    Example:
        >>> event = QueuePositionChangedEvent(
        ...     type="queue.position_changed",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock",
        ...     queue_name="proj-1:board-1",
        ...     item_id="item-1",
        ...     old_position=2,
        ...     new_position=0,
        ...     project_id="proj-1"
        ... )
        >>> event.new_position = 5  # ❌ Raises FrozenInstanceError
    """

    queue_name: str = ""
    item_id: str = ""
    old_position: int = 0
    new_position: int = 0
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.queue_name:
            msg = "queue_name is required"
            raise ValueError(msg)
        if not self.item_id:
            msg = "item_id is required"
            raise ValueError(msg)
        if self.old_position < 0:
            msg = "old_position cannot be negative"
            raise ValueError(msg)
        if self.new_position < 0:
            msg = "new_position cannot be negative"
            raise ValueError(msg)
        if self.old_position == self.new_position:
            msg = "old_position must differ from new_position (position did not actually change)"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "queue_name": self.queue_name,
                "item_id": self.item_id,
                "old_position": self.old_position,
                "new_position": self.new_position,
                "project_id": self.project_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueuePositionChangedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (queue_name, item_id, old_position,
                     new_position) are missing.
        """
        return cls(
            type=data.get("type", "queue.position_changed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            queue_name=data["queue_name"],
            item_id=data["item_id"],
            old_position=data["old_position"],
            new_position=data["new_position"],
            project_id=data.get("project_id"),
        )


@dataclass(frozen=True)
class TaskDispatchFailedEvent(CodetoreumEvent):
    """Emitted when a scheduled task fails to dispatch to execution.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Represents a failure in the AgentScheduler's consumer loop when attempting
    to dispatch a dequeued task to execution. Unlike ExecutionFailedEvent
    (which represents an agent execution failure), this event indicates that
    the task never reached the execution service due to dispatcher failure.

    Attributes:
        type (str): Fixed to "scheduling.task_dispatch_failed"
        task_id (str): ID of the scheduled task that failed to dispatch
        work_item_id (str): ID of the work item associated with the task
        agent_id (str): ID of the agent that should have executed
        error (str): Error description from the dispatch failure
        source (str): Always "agent_scheduler"

    Example:
        >>> event = TaskDispatchFailedEvent(
        ...     type="scheduling.task_dispatch_failed",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="agent_scheduler",
        ...     task_id="task-1",
        ...     work_item_id="item-1",
        ...     agent_id="agent-1",
        ...     error="Connection timeout to container service"
        ... )
        >>> event.error = "other"  # ❌ Raises FrozenInstanceError
    """

    task_id: str = ""
    work_item_id: str = ""
    agent_id: str = ""
    error: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.task_id:
            msg = "task_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.agent_id:
            msg = "agent_id is required"
            raise ValueError(msg)
        if not self.error:
            msg = "error is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "task_id": self.task_id,
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "error": self.error,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskDispatchFailedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "scheduling.task_dispatch_failed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "agent_scheduler"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            task_id=data.get("task_id", ""),
            work_item_id=data.get("work_item_id", ""),
            agent_id=data.get("agent_id", ""),
            error=data.get("error", ""),
        )


@dataclass(frozen=True)
class QueueMetadataCorruptionEvent(CodetoreumEvent):
    """Emitted when queue metadata is missing or corrupted.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Alerts about corrupted queue entries that remain in storage but have missing
    or unparseable metadata. This indicates a data integrity issue that requires
    investigation and potential manual remediation.

    Attributes:
        type (str): Fixed to "queue.metadata_corruption"
        queue_name (str): Name of the queue (typically "project_id:board_id")
        work_item_id (str): ID of the work item with corrupted metadata
        error_details (str): Description of what went wrong (missing, JSON parse error, etc.)
        project_id (str): ID of the project containing the queue

    Example:
        >>> event = QueueMetadataCorruptionEvent(
        ...     type="queue.metadata_corruption",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="redis_pipeline_queue",
        ...     queue_name="proj-1:board-1",
        ...     work_item_id="item-1",
        ...     error_details="JSON decode error: Expecting value",
        ...     project_id="proj-1"
        ... )
        >>> event.error_details = "other"  # ❌ Raises FrozenInstanceError
    """

    queue_name: str = ""
    work_item_id: str = ""
    error_details: str = ""
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.queue_name:
            msg = "queue_name is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.error_details:
            msg = "error_details is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "queue_name": self.queue_name,
                "work_item_id": self.work_item_id,
                "error_details": self.error_details,
                "project_id": self.project_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueMetadataCorruptionEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "queue.metadata_corruption"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            queue_name=data.get("queue_name", ""),
            work_item_id=data.get("work_item_id", ""),
            error_details=data.get("error_details", ""),
            project_id=data.get("project_id"),
        )


@dataclass(frozen=True)
class WorkItemDeadLetterQueuedEvent(CodetoreumEvent):
    """Emitted when a work item is queued to the dead letter queue.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    The dead letter queue (DLQ) is where work items are placed when they cannot
    be automatically progressed through the workflow due to failures. Manual
    intervention or async recovery is required.

    Attributes:
        type (str): Fixed to "dlq.work_item_queued"
        work_item_id (str): ID of the work item queued to DLQ
        board_id (str): ID of the board containing the work item
        from_column (str): Current column/state of the work item
        to_column (str): Intended next column/state (UNKNOWN if not determinable)
        reason (str): Reason for DLQ queueing (e.g., auto-progression callback failure)
        failure_details (str): Additional error details

    Example:
        >>> event = WorkItemDeadLetterQueuedEvent(
        ...     type="dlq.work_item_queued",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="recovery_service",
        ...     work_item_id="123",
        ...     board_id="board-1",
        ...     from_column="in_progress",
        ...     to_column="review",
        ...     reason="Auto-progression callback failed",
        ...     failure_details="ConnectionError: unable to reach board service"
        ... )
        >>> event.reason = "other"  # ❌ Raises FrozenInstanceError
    """

    work_item_id: str = ""
    board_id: str = ""
    from_column: str = ""
    to_column: str = ""
    reason: str = ""
    failure_details: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if not self.from_column:
            msg = "from_column is required"
            raise ValueError(msg)
        if not self.to_column:
            msg = "to_column is required"
            raise ValueError(msg)
        if not self.reason:
            msg = "reason is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "board_id": self.board_id,
                "from_column": self.from_column,
                "to_column": self.to_column,
                "reason": self.reason,
                "failure_details": self.failure_details,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkItemDeadLetterQueuedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "dlq.work_item_queued"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            board_id=data.get("board_id", ""),
            from_column=data.get("from_column", ""),
            to_column=data.get("to_column", ""),
            reason=data.get("reason", ""),
            failure_details=data.get("failure_details", ""),
        )
