"""Vendor-agnostic events emitted by adapters to the orchestrator.

This module defines the base CodetoreumEvent class and categorized
event types for vendor-agnostic integration. All events use
standardized terminology independent of the underlying ticket system,
board system, or code review platform.

Terminology mapping:
- Issue/Work Item Type -> Work Item
- Issue Number/ID -> Work Item ID
- Projects v2/Board -> Project Board
- Status Field/Column -> Column / Workflow State
- Pull Request/Merge Request -> Code Review
- Issue Comment/PR Comment -> Comment
- Discussion Thread -> Discussion Thread
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class CodetoreumEvent:
    """Base event interface for vendor-agnostic adapters.

    **Immutability**: All events are immutable (frozen dataclasses). This
    is a foundational architectural principle ensuring event sourcing audit
    trail integrity. Events represent immutable facts about state changes—
    they cannot and must not be modified after creation. Attempting to modify
    any field will raise `FrozenInstanceError`. This immutability guarantee
    is critical for maintaining a reliable event sourcing system where events
    serve as the single source of truth for the system's history.

    All events emitted from adapters conform to this interface,
    ensuring consistent routing, tracing, and handling by the
    orchestrator regardless of the source vendor.

    **EventBus Routing**: This class provides two type identifiers with
    different purposes:
    - `type` (field): Dot-notation type for semantic categorization
      (e.g., "workitem.column_changed"). Human-readable, hierarchical,
      used for event store queries and documentation.
    - `event_type` (property): Class name for EventBus subscription routing
      (e.g., "WorkItemColumnChangedEvent"). Matches legacy CodetoreumEvent
      routing behavior. When subscribing to events, use the class name,
      not the dot-notation type.

    Attributes:
        type: Event type in dot notation (e.g., "workitem.column_changed",
               "comment.needs_response"). Used for semantic categorization
               and event store queries.
        timestamp: ISO 8601 timestamp when event occurred.
        source: Adapter that emitted the event (e.g., "github", "jira", "trello").
               Used to identify adapter-specific fields in the event.
        correlation_id: Optional ID to trace related events across the system.
                       Useful for correlating events from multiple adapters
                       handling the same work item.
        event_id: Unique identifier for this event (UUID). Generated if not provided.

    Example:
        >>> from datetime import datetime, timezone
        >>> event = CodetoreumEvent(
        ...     type="example.event",
        ...     timestamp=datetime.now(timezone.utc).isoformat(),
        ...     source="test_adapter"
        ... )
        >>> event.type = "modified.event"  # ❌ Raises FrozenInstanceError
        >>> # Events are read-only after construction—this is enforced by the frozen dataclass
        >>> event.event_type  # Returns "CodetoreumEvent" (class name)
    """

    type: str
    timestamp: str
    source: str
    correlation_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        if not self.type or "." not in self.type:
            msg = f"Event type must be in dot notation (e.g., 'workitem.created'), got: {self.type}"
            raise ValueError(msg)

        if not self.source:
            msg = "Event source (adapter name) is required"
            raise ValueError(msg)

        # Validate timestamp is ISO format
        try:
            datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            msg = f"Timestamp must be ISO 8601 format, got: {self.timestamp}"
            raise ValueError(msg)

    @property
    def occurred_at(self) -> datetime:
        """Compatibility property — parses self.timestamp into a datetime.

        Returns:
            UTC datetime parsed from the ISO 8601 timestamp string.
        """
        ts = self.timestamp.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)

    @property
    def event_type(self) -> str:
        """Get event type for EventBus routing.

        Returns the class name for compatibility with legacy CodetoreumEvent-based
        EventBus routing. Subscriptions should use the class name (e.g.,
        "WorkItemColumnChangedEvent") to match events, not the dot-notation type.

        Returns:
            Class name (e.g., "WorkItemColumnChangedEvent")
        """
        return self.__class__.__name__

    def to_dict(self) -> dict:
        """Serialize event to dictionary for storage/transmission.

        Returns:
            Dictionary representation of the event with all fields.
        """
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "event_id": self.event_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CodetoreumEvent":
        """Deserialize event from dictionary.

        Args:
            data: Dictionary with event fields

        Returns:
            CodetoreumEvent instance

        Raises:
            ValueError: If required fields are missing or invalid
            KeyError: If required field is missing
        """
        try:
            return cls(
                type=data["type"],
                timestamp=data["timestamp"],
                source=data["source"],
                correlation_id=data.get("correlation_id"),
                event_id=data.get("event_id", str(uuid4())),
            )
        except KeyError as e:
            msg = f"Missing required field: {e}"
            raise ValueError(msg)


def now_iso() -> str:
    """Get current time in ISO 8601 format.

    Returns:
        ISO 8601 formatted timestamp (UTC).
    """
    return datetime.now(UTC).isoformat()
