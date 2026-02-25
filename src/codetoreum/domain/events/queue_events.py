"""Queue-related events for pipeline queue service.

Events track changes to pipeline queue items including addition, removal,
and position changes based on board state updates.
"""

from dataclasses import dataclass
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

    def to_dict(self) -> dict:
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
    def from_dict(cls, data: dict) -> "QueueItemAddedEvent":
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

    def to_dict(self) -> dict:
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
    def from_dict(cls, data: dict) -> "QueueItemRemovedEvent":
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

    def to_dict(self) -> dict:
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
    def from_dict(cls, data: dict) -> "QueuePositionChangedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "queue.position_changed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            queue_name=data.get("queue_name", ""),
            item_id=data.get("item_id", ""),
            old_position=data.get("old_position", 0),
            new_position=data.get("new_position", 0),
            project_id=data.get("project_id"),
        )
