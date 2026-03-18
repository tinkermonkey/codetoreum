"""Execution timeout domain events.

Events track agent execution lifecycle, including timeouts detected by watchdogs.

All events are immutable (frozen dataclasses) to maintain event sourcing
audit trail integrity and enable observability integration.
"""

from dataclasses import dataclass
from uuid import uuid4

from .adapter_events import CodetoreumEvent


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
        >>> event.execution_id = "exec-789"  # ❌ Raises FrozenInstanceError
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
