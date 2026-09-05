"""Adapter implementing IFailedEventStore port using DeadLetterQueue.

This adapter bridges the gap between the port interface (IFailedEventStore)
and the infrastructure implementation (DeadLetterQueue), allowing the
application layer to depend on the port abstraction rather than concrete
infrastructure classes.

Note: This adapter also exposes infrastructure-specific lifecycle methods
(start_retry_processor, stop_retry_processor) for bootstrap coordination,
as these are not part of the core port interface but are needed for
infrastructure management.
"""

from collections.abc import Callable
from typing import Any

from codetoreum.infrastructure.dead_letter_queue import (
    DeadLetterQueue,
)
from codetoreum.infrastructure.dead_letter_queue import (
    FailureReason as DLQFailureReason,
)
from codetoreum.ports.output.failed_event_store import (
    FailedEventRecord,
    FailedEventStoreStats,
    FailureReason,
    IFailedEventStore,
)


class DeadLetterQueueFailedEventStoreAdapter(IFailedEventStore):
    """Adapter implementing IFailedEventStore using DeadLetterQueue infrastructure.

    Provides a clean separation between the application layer (which uses the
    IFailedEventStore port interface) and the infrastructure layer (which
    uses DeadLetterQueue), following hexagonal architecture principles.
    """

    def __init__(self, dead_letter_queue: DeadLetterQueue) -> None:
        """Initialize the adapter.

        Args: dead_letter_queue: The DeadLetterQueue instance to wrap.

        Raises: ValueError: If dead_letter_queue is None.
        """
        if dead_letter_queue is None:
            raise ValueError("dead_letter_queue cannot be None; the caller must instantiate DeadLetterQueue")
        self._dead_letter_queue = dead_letter_queue

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
        # Convert port FailureReason to infrastructure FailureReason
        dlq_failure_reason = DLQFailureReason(failure_reason.value)

        return await self._dead_letter_queue.add_failed_event(
            event_type=event_type,
            event_data=event_data,
            failure_reason=dlq_failure_reason,
            error_message=error_message,
            metadata=metadata,
        )

    def get_stats(self) -> FailedEventStoreStats:
        """Get statistics about stored failed events.

        Returns: Statistics including counts by reason, retry status, etc.
        """
        dlq_stats = self._dead_letter_queue.get_stats()

        return FailedEventStoreStats(
            total_failed_events=dlq_stats.total_failed_events,
            pending_retries=dlq_stats.pending_retries,
            exhausted_retries=dlq_stats.exhausted_retries,
            total_retries_attempted=dlq_stats.total_retries_attempted,
            total_retries_succeeded=dlq_stats.total_retries_succeeded,
            total_retries_failed=dlq_stats.total_retries_failed,
            oldest_event=dlq_stats.oldest_event,
            newest_event=dlq_stats.newest_event,
            failure_reasons=dlq_stats.failure_reasons,
        )

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
        # Convert port FailureReason to infrastructure FailureReason if provided
        dlq_failure_reason = None
        if failure_reason is not None:
            dlq_failure_reason = DLQFailureReason(failure_reason.value)

        # Get events from the underlying DeadLetterQueue
        dlq_events = self._dead_letter_queue.list_events(
            failure_reason=dlq_failure_reason,
            can_retry=can_retry,
            limit=limit,
        )

        # Convert to port-level FailedEventRecord objects
        return [
            FailedEventRecord(
                id=event.id,
                event_type=event.event_type,
                event_data=event.event_data,
                failure_reason=FailureReason(event.failure_reason.value),
                error_message=event.error_message,
                failed_at=event.failed_at,
                retry_count=event.retry_count,
                max_retries=event.max_retries,
                next_retry_at=event.next_retry_at,
                last_retry_at=event.last_retry_at,
                metadata=event.metadata,
            )
            for event in dlq_events
        ]

    def get_event(self, event_id: str) -> FailedEventRecord | None:
        """Get a specific failed event by ID.

        Args: event_id: ID of the event to retrieve

        Returns: The failed event record, or None if not found
        """
        dlq_event = self._dead_letter_queue.get_event(event_id)
        if dlq_event is None:
            return None

        return FailedEventRecord(
            id=dlq_event.id,
            event_type=dlq_event.event_type,
            event_data=dlq_event.event_data,
            failure_reason=FailureReason(dlq_event.failure_reason.value),
            error_message=dlq_event.error_message,
            failed_at=dlq_event.failed_at,
            retry_count=dlq_event.retry_count,
            max_retries=dlq_event.max_retries,
            next_retry_at=dlq_event.next_retry_at,
            last_retry_at=dlq_event.last_retry_at,
            metadata=dlq_event.metadata,
        )

    def remove_event(self, event_id: str) -> bool:
        """Remove an event from the store.

        Args: event_id: ID of the event to remove

        Returns: True if removed, False if not found
        """
        return self._dead_letter_queue.remove_event(event_id)

    def clear(self) -> None:
        """Clear all events from the store."""
        self._dead_letter_queue.clear()

    async def start_retry_processor(self, retry_handler: Callable) -> None:
        """Start background retry processor (infrastructure-specific lifecycle).

        This method is not part of the core IFailedEventStore interface but is
        exposed here for bootstrap coordination and management.

        Args: retry_handler: Async function to call for retrying events
                         Should accept (event_type, event_data) and raise on failure
        """
        await self._dead_letter_queue.start_retry_processor(retry_handler)

    async def stop_retry_processor(self) -> None:
        """Stop background retry processor (infrastructure-specific lifecycle).

        This method is not part of the core IFailedEventStore interface but is
        exposed here for bootstrap coordination and management.
        """
        await self._dead_letter_queue.stop_retry_processor()
