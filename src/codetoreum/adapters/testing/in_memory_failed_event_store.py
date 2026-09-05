"""In-memory failed event store adapter for simulation and testing.

This adapter provides a fully in-memory implementation of IFailedEventStore without
any production infrastructure dependencies. It's designed for simulation mode where
we need deterministic behavior without contacting external systems like Redis or
databases.

The adapter:
1. Stores failed events in an in-memory dictionary
2. Provides all IFailedEventStore interface methods
3. Thread-safe for single event loop execution (no external locks needed)
4. Supports event filtering and statistics generation
5. Tracks retry success/failure metrics for testing
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from codetoreum.ports.output.failed_event_store import (
    FailedEventRecord,
    FailedEventStoreStats,
    FailureReason,
    IFailedEventStore,
)


class InMemoryFailedEventStore(IFailedEventStore):
    """In-memory implementation of IFailedEventStore for simulation mode.

    Stores failed events in memory without any external infrastructure dependencies.
    All operations are safe within a single event loop due to Python's single-threaded
    async execution model - no explicit locking needed.

    The adapter tracks both attempted and successful/failed retries to support
    comprehensive testing of event recovery scenarios.

    Example:
        failed_store = InMemoryFailedEventStore()
        event_id = await failed_store.add_failed_event(
            event_type="WorkItemColumnChanged",
            event_data={"work_item_id": "123"},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Connection timeout",
        )
        stats = failed_store.get_stats()
    """

    def __init__(self) -> None:
        """Initialize the in-memory failed event store."""
        self._events: dict[str, FailedEventRecord] = {}
        # Track retry outcomes for statistics
        self._retries_succeeded: dict[str, int] = {}  # event_id -> count
        self._retries_failed: dict[str, int] = {}  # event_id -> count

    async def add_failed_event(
        self,
        event_type: str,
        event_data: dict[str, Any],
        failure_reason: FailureReason,
        error_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a failed event to the store.

        Args:
            event_type: Type of the event that failed
            event_data: Event payload data
            failure_reason: Reason for the failure
            error_message: Human-readable error message
            metadata: Optional additional metadata about the failure

        Returns:
            ID of the stored failed event
        """
        event_id = str(uuid.uuid4())
        record = FailedEventRecord(
            id=event_id,
            event_type=event_type,
            event_data=event_data,
            failure_reason=failure_reason,
            error_message=error_message,
            failed_at=datetime.now(UTC),
            retry_count=0,
            max_retries=3,
            next_retry_at=None,
            last_retry_at=None,
            metadata=metadata,
        )
        self._events[event_id] = record
        # Initialize retry tracking for this event
        self._retries_succeeded[event_id] = 0
        self._retries_failed[event_id] = 0

        return event_id

    def get_stats(self) -> FailedEventStoreStats:
        """Get statistics about stored failed events.

        Returns:
            Statistics including counts by reason, retry status, etc.
        """
        # Safe to read without explicit lock since operations are single-threaded
        # within the event loop.
        events = list(self._events.values())

        if not events:
            return FailedEventStoreStats(
                total_failed_events=0,
                pending_retries=0,
                exhausted_retries=0,
                total_retries_attempted=0,
                total_retries_succeeded=0,
                total_retries_failed=0,
                oldest_event=None,
                newest_event=None,
                failure_reasons=None,
            )

        # Calculate statistics
        pending_retries = sum(1 for e in events if e.can_retry())
        exhausted_retries = sum(1 for e in events if not e.can_retry())

        # Count by failure reason
        failure_reasons: dict[str, int] = {}
        for event in events:
            reason = event.failure_reason.value
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

        # Find oldest and newest
        oldest = min(events, key=lambda e: e.failed_at).failed_at if events else None
        newest = max(events, key=lambda e: e.failed_at).failed_at if events else None

        # Calculate total retries
        total_retries_attempted = sum(e.retry_count for e in events)
        total_retries_succeeded = sum(self._retries_succeeded.get(e.id, 0) for e in events)
        total_retries_failed = sum(self._retries_failed.get(e.id, 0) for e in events)

        return FailedEventStoreStats(
            total_failed_events=len(events),
            pending_retries=pending_retries,
            exhausted_retries=exhausted_retries,
            total_retries_attempted=total_retries_attempted,
            total_retries_succeeded=total_retries_succeeded,
            total_retries_failed=total_retries_failed,
            oldest_event=oldest,
            newest_event=newest,
            failure_reasons=failure_reasons,
        )

    def list_events(
        self,
        failure_reason: FailureReason | None = None,
        can_retry: bool | None = None,
        limit: int | None = None,
    ) -> list[FailedEventRecord]:
        """List failed events with optional filtering.

        Args:
            failure_reason: Filter by specific failure reason
            can_retry: Filter by retry capability (True/False)
            limit: Maximum number of events to return

        Returns:
            List of failed event records matching the filters
        """
        # Safe to read without explicit lock since the event loop is single-threaded
        events = list(self._events.values())

        # Apply filters
        if failure_reason is not None:
            events = [e for e in events if e.failure_reason == failure_reason]

        if can_retry is not None:
            events = [e for e in events if e.can_retry() == can_retry]

        # Apply limit
        if limit is not None:
            events = events[:limit]

        return events

    def get_event(self, event_id: str) -> FailedEventRecord | None:
        """Get a specific failed event by ID.

        Args:
            event_id: ID of the event to retrieve

        Returns:
            The failed event record, or None if not found
        """
        # Safe to read without explicit lock since the event loop is single-threaded
        return self._events.get(event_id)

    def remove_event(self, event_id: str) -> bool:
        """Remove an event from the store.

        Args:
            event_id: ID of the event to remove

        Returns:
            True if removed, False if not found
        """
        # Safe to modify in single-threaded event loop context
        if event_id in self._events:
            del self._events[event_id]
            # Clean up retry tracking
            self._retries_succeeded.pop(event_id, None)
            self._retries_failed.pop(event_id, None)
            return True
        return False

    def clear(self) -> None:
        """Clear all events from the store."""
        self._events.clear()
        self._retries_succeeded.clear()
        self._retries_failed.clear()

    # Test-only methods for tracking retry outcomes
    def mark_retry_succeeded(self, event_id: str) -> None:
        """Mark a retry attempt as succeeded (test utility method).

        Args:
            event_id: ID of the event that was successfully retried
        """
        if event_id in self._events:
            self._retries_succeeded[event_id] = self._retries_succeeded.get(event_id, 0) + 1

    def mark_retry_failed(self, event_id: str) -> None:
        """Mark a retry attempt as failed (test utility method).

        Args:
            event_id: ID of the event whose retry failed
        """
        if event_id in self._events:
            self._retries_failed[event_id] = self._retries_failed.get(event_id, 0) + 1
