"""Failed Event Store Port Interface.

Abstracts the storage and retrieval of failed events for recovery purposes.
This port enables decoupling the application layer from specific dead letter queue
implementations, supporting multiple backends (in-memory, database, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class FailureReason(Enum):
    """Reason for event failure."""

    TRANSIENT_ERROR = "transient_error"
    VALIDATION_ERROR = "validation_error"
    PROCESSING_ERROR = "processing_error"
    TIMEOUT = "timeout"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FailedEventRecord:
    """Represents a failed event stored in the failed event store.

    Frozen to prevent accidental mutation after retrieval from the port,
    ensuring audit-trail integrity. Port-layer dataclasses must be immutable
    to maintain contract guarantees across the port boundary.
    """

    id: str
    event_type: str
    event_data: dict[str, Any]
    failure_reason: FailureReason
    error_message: str
    failed_at: datetime
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: datetime | None = None
    last_retry_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    def can_retry(self) -> bool:
        """Check if event can be retried (has retries left)."""
        if self.retry_count >= self.max_retries:
            return False

        # Don't retry validation errors
        if self.failure_reason == FailureReason.VALIDATION_ERROR:
            return False

        return True


@dataclass(frozen=True)
class FailedEventStoreStats:
    """Statistics for failed event store.

    Frozen to prevent accidental mutation after retrieval from the port,
    ensuring statistics integrity. Port-layer dataclasses must be immutable
    to maintain contract guarantees across the port boundary.
    """

    total_failed_events: int
    pending_retries: int
    exhausted_retries: int
    total_retries_attempted: int
    total_retries_succeeded: int
    total_retries_failed: int
    oldest_event: datetime | None = None
    newest_event: datetime | None = None
    failure_reasons: dict[str, int] | None = None


class IFailedEventStore(ABC):
    """Port interface for storing and managing failed events.

    This interface abstracts the storage mechanism for failed events, allowing
    pluggable implementations (in-memory, database-backed, etc.). The application
    layer depends on this port instead of concrete implementations, preserving
    hexagonal architecture principles.
    """

    @abstractmethod
    async def add_failed_event(
        self,
        event_type: str,
        event_data: dict[str, Any],
        failure_reason: FailureReason,
        error_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a failed event to the store.

        Args: event_type: Type of the event that failed
            event_data: Event payload data
            failure_reason: Reason for the failure
            error_message: Human-readable error message
            metadata: Optional additional metadata about the failure

        Returns: ID of the stored failed event
        """

    @abstractmethod
    def get_stats(self) -> FailedEventStoreStats:
        """Get statistics about stored failed events.

        Returns: Statistics including counts by reason, retry status, etc.
        """

    @abstractmethod
    def list_events(
        self,
        failure_reason: FailureReason | None = None,
        can_retry: bool | None = None,
        limit: int | None = None,
    ) -> list[FailedEventRecord]:
        """List failed events with optional filtering.

        Args: failure_reason: Filter by specific failure reason
            can_retry: Filter by retry capability (True/False)
            limit: Maximum number of events to return

        Returns: List of failed event records matching the filters
        """

    @abstractmethod
    def get_event(self, event_id: str) -> FailedEventRecord | None:
        """Get a specific failed event by ID.

        Args: event_id: ID of the event to retrieve

        Returns: The failed event record, or None if not found
        """

    @abstractmethod
    def remove_event(self, event_id: str) -> bool:
        """Remove an event from the store.

        Args: event_id: ID of the event to remove

        Returns: True if removed, False if not found
        """

    @abstractmethod
    def clear(self) -> None:
        """Clear all events from the store."""
