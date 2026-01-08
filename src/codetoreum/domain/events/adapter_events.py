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
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4


@dataclass
class CodetoreumEvent:
    """Base event interface for vendor-agnostic adapters.

    All events emitted from adapters conform to this interface,
    ensuring consistent routing, tracing, and handling by the
    orchestrator regardless of the source vendor.

    Attributes:
        type: Event type in dot notation (e.g., "workitem.column_changed",
               "comment.needs_response"). Used for handler routing.
        timestamp: ISO 8601 timestamp when event occurred.
        source: Adapter that emitted the event (e.g., "github", "jira", "trello").
               Used to identify adapter-specific fields in the event.
        correlation_id: Optional ID to trace related events across the system.
                       Useful for correlating events from multiple adapters
                       handling the same work item.
        event_id: Unique identifier for this event (UUID). Generated if not provided.
    """

    type: str
    timestamp: str
    source: str
    correlation_id: Optional[str] = None
    event_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        if not self.type or "." not in self.type:
            raise ValueError(
                f"Event type must be in dot notation (e.g., 'workitem.created'), "
                f"got: {self.type}"
            )

        if not self.source:
            raise ValueError("Event source (adapter name) is required")

        # Validate timestamp is ISO format
        try:
            datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise ValueError(
                f"Timestamp must be ISO 8601 format, got: {self.timestamp}"
            )

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
            raise ValueError(f"Missing required field: {e}")


@staticmethod
def now_iso() -> str:
    """Get current time in ISO 8601 format.

    Returns:
        ISO 8601 formatted timestamp (UTC).
    """
    return datetime.now(timezone.utc).isoformat()
