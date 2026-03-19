"""Dead Letter Queue implementation.

Handles failed events with retry logic and persistent storage.
"""

import asyncio
import logging
import threading
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.resilience.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class DeadLetterQueueRegistry:
    """Thread-safe registry of active DeadLetterQueue instances.

    This replaces expensive gc.get_objects() scans with a lightweight
    registry that tracks instances as they're created and destroyed.
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._instances: set[weakref.ref] = set()
        self._lock = threading.Lock()

    def register(self, instance: "DeadLetterQueue") -> None:
        """Register a DeadLetterQueue instance.

        Args:
            instance: The DeadLetterQueue instance to register
        """
        with self._lock:
            # Use weakref so instances can be garbage collected
            self._instances.add(weakref.ref(instance, self._on_finalize))

    def _on_finalize(self, ref: weakref.ref) -> None:
        """Called when a weakref is finalized (instance deleted).

        Args:
            ref: The weakref that was finalized
        """
        with self._lock:
            self._instances.discard(ref)

    def get_all_running(self) -> list["DeadLetterQueue"]:
        """Get all active DeadLetterQueue instances that are currently running.

        Returns:
            List of running DeadLetterQueue instances (alive references only)
        """
        with self._lock:
            # Remove dead references and collect live instances
            live_refs = set()
            running_instances = []

            for ref in list(self._instances):
                instance = ref()
                if instance is not None:
                    live_refs.add(ref)
                    if instance._running:
                        running_instances.append(instance)

            # Clean up dead references
            self._instances = live_refs

            return running_instances


# Global registry instance
_dlq_registry = DeadLetterQueueRegistry()


class FailureReason(Enum):
    """Reason for event failure."""

    TRANSIENT_ERROR = "transient_error"
    VALIDATION_ERROR = "validation_error"
    PROCESSING_ERROR = "processing_error"
    TIMEOUT = "timeout"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    UNKNOWN = "unknown"


@dataclass
class FailedEvent:
    """
    Represents a failed event in the dead letter queue.
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
    metadata: dict[str, Any] = field(default_factory=dict)

    def can_retry(self) -> bool:
        """Check if event can be retried (has retries left)."""
        if self.retry_count >= self.max_retries:
            return False

        # Don't retry validation errors
        if self.failure_reason == FailureReason.VALIDATION_ERROR:
            return False

        return True

    def is_ready_for_retry(self) -> bool:
        """Check if event is ready to be retried now."""
        if not self.can_retry():
            return False

        if self.next_retry_at and datetime.now(UTC) < self.next_retry_at:
            return False

        return True

    def calculate_next_retry(self, base_delay: float = 60.0, exponential_base: float = 2.0) -> datetime:
        """
        Calculate next retry time using exponential backoff.

        Args:
            base_delay: Base delay in seconds
            exponential_base: Base for exponential calculation

        Returns:
            Next retry timestamp
        """
        delay_seconds = base_delay * (exponential_base**self.retry_count)
        # Cap at 1 hour
        delay_seconds = min(delay_seconds, 3600)

        return datetime.now(UTC) + timedelta(seconds=delay_seconds)


@dataclass
class DeadLetterQueueStats:
    """Statistics for dead letter queue."""

    total_failed_events: int
    pending_retries: int
    exhausted_retries: int
    total_retries_attempted: int
    total_retries_succeeded: int
    total_retries_failed: int
    oldest_event: datetime | None = None
    newest_event: datetime | None = None
    failure_reasons: dict[str, int] = field(default_factory=dict)


class DeadLetterQueue:
    """
    Dead Letter Queue for handling failed events.

    Features:
    - Persistent storage of failed events
    - Automatic retry with exponential backoff
    - Configurable max retries
    - Statistics and monitoring
    - Event filtering and querying

    IMPORTANT - Memory Management:
    This implementation uses in-memory storage by default. Failed events
    accumulate indefinitely unless purged manually or integrated with
    persistent storage. For production use:
    1. Pass a persistent storage backend (e.g., database dict-like wrapper)
    2. Configure periodic purging via purge_old_events() or purge_exhausted_events()
    3. Monitor memory usage via get_stats()
    """

    def __init__(
        self,
        storage: dict[str, FailedEvent] | None = None,
        max_retries: int = 3,
        base_delay_seconds: float = 60.0,
        exponential_base: float = 2.0,
        retry_interval_seconds: float = 30.0,
        retry_loop_failure_threshold: int = 5,
        retry_loop_timeout_seconds: float = 300.0,
    ):
        """
        Initialize dead letter queue.

        Args:
            storage: Optional external storage (for persistence)
            max_retries: Maximum retry attempts per event
            base_delay_seconds: Base delay for exponential backoff
            exponential_base: Base for exponential calculation
            retry_interval_seconds: How often to check for retryable events
            retry_loop_failure_threshold: Consecutive failures before circuit opens
            retry_loop_timeout_seconds: Time to wait before attempting recovery
        """
        self._storage: dict[str, FailedEvent] = storage if storage is not None else {}
        self._max_retries = max_retries
        self._base_delay_seconds = base_delay_seconds
        self._exponential_base = exponential_base
        self._retry_interval_seconds = retry_interval_seconds

        # Statistics
        self._total_retries_attempted = 0
        self._total_retries_succeeded = 0
        self._total_retries_failed = 0

        # Retry processing
        self._retry_task: asyncio.Task | None = None
        self._running = False
        self._retry_handler: Callable | None = None

        # Circuit breaker for retry loop to prevent unbounded error logs
        self._retry_loop_circuit_breaker = CircuitBreaker(
            failure_threshold=retry_loop_failure_threshold,
            timeout_seconds=retry_loop_timeout_seconds,
            success_threshold=1,
            expected_exceptions=(Exception,),
        )

        # Register this instance in the global registry
        _dlq_registry.register(self)

    async def add_failed_event(
        self,
        event_type: str,
        event_data: dict[str, Any],
        failure_reason: FailureReason,
        error_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Add a failed event to the queue.

        Args:
            event_type: Type of the event
            event_data: Event payload
            failure_reason: Reason for failure
            error_message: Error message
            metadata: Optional metadata

        Returns:
            ID of the failed event
        """
        event_id = str(uuid4())

        failed_event = FailedEvent(
            id=event_id,
            event_type=event_type,
            event_data=event_data,
            failure_reason=failure_reason,
            error_message=error_message,
            failed_at=datetime.now(UTC),
            max_retries=self._max_retries,
            metadata=metadata or {},
        )

        # Calculate initial retry time
        if failed_event.can_retry():
            failed_event.next_retry_at = failed_event.calculate_next_retry(
                self._base_delay_seconds, self._exponential_base
            )

        self._storage[event_id] = failed_event

        return event_id

    async def retry_event(self, event_id: str) -> bool:
        """
        Manually retry a specific event.

        Args:
            event_id: ID of the event to retry

        Returns:
            True if retry succeeded, False otherwise
        """
        if event_id not in self._storage:
            return False

        event = self._storage[event_id]

        if not event.can_retry():
            return False

        if not self._retry_handler:
            return False

        self._total_retries_attempted += 1
        event.retry_count += 1
        event.last_retry_at = datetime.now(UTC)

        try:
            # Call the retry handler
            await self._retry_handler(event.event_type, event.event_data)

            # Success - remove from queue
            del self._storage[event_id]
            self._total_retries_succeeded += 1
            return True

        except Exception as e:
            # Failed - update retry time
            self._total_retries_failed += 1

            logger.warning(
                "Failed to retry event %s (attempt %d/%d): %s",
                event_id,
                event.retry_count,
                event.max_retries,
                str(e),
                exc_info=True,
                extra={
                    "event_id": event_id,
                    "event_type": event.event_type,
                    "retry_count": event.retry_count,
                    "max_retries": event.max_retries,
                    "failure_reason": event.failure_reason.value,
                    "component": "dead_letter_queue",
                },
            )

            if event.can_retry():
                event.next_retry_at = event.calculate_next_retry(self._base_delay_seconds, self._exponential_base)
            else:
                # Exhausted retries
                event.next_retry_at = None
                logger.error(
                    "Event %s exhausted all retries (%d attempts)",
                    event_id,
                    event.retry_count,
                    exc_info=True,
                    extra={
                        "event_id": event_id,
                        "event_type": event.event_type,
                        "retry_count": event.retry_count,
                        "original_failure": event.failure_reason.value,
                        "component": "dead_letter_queue",
                        "error_id": ErrorRegistry.ERR_DEAD_LETTER_QUEUE_ERROR,
                    },
                )

            return False

    async def start_retry_processor(self, retry_handler: Callable) -> None:
        """
        Start background retry processor.

        Args:
            retry_handler: Async function to call for retrying events
                         Should accept (event_type, event_data) and raise on failure
        """
        if self._running:
            return

        self._retry_handler = retry_handler
        self._running = True
        self._retry_task = asyncio.create_task(self._retry_loop())

    async def stop_retry_processor(self) -> None:
        """Stop background retry processor."""
        self._running = False

        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass

    async def _retry_loop(self) -> None:
        """
        Background loop for processing retries with circuit breaker protection.

        Uses circuit breaker to prevent unbounded error logs on persistent failures.
        When circuit opens, retry loop backs off exponentially before attempting recovery.
        """
        consecutive_successes = 0

        while self._running:
            try:
                # Try to execute processing through circuit breaker
                await self._retry_loop_circuit_breaker.call(
                    self._process_retryable_events,
                    "process_retryable_events",
                )
                consecutive_successes += 1

                # Normal interval after success
                await asyncio.sleep(self._retry_interval_seconds)

            except Exception as e:
                consecutive_successes = 0

                # Check circuit breaker state
                if self._retry_loop_circuit_breaker.is_open():
                    # Circuit is open - use exponential backoff to prevent hammering
                    stats = self._retry_loop_circuit_breaker.get_stats()
                    time_until_retry = self._retry_loop_circuit_breaker._time_until_retry()

                    logger.error(
                        "Dead letter queue retry loop circuit breaker is OPEN. "
                        "Will pause processing and attempt recovery in %.1fs. "
                        "Error: %s",
                        time_until_retry,
                        str(e),
                        exc_info=True,
                        extra={
                            "component": "dead_letter_queue",
                            "operation": "retry_loop",
                            "error_id": ErrorRegistry.ERR_DEAD_LETTER_QUEUE_ERROR,
                            "circuit_state": "OPEN",
                            "total_failures": stats.total_failures,
                            "failure_count": stats.failure_count,
                        },
                    )

                    # Back off exponentially while circuit is open
                    # Use circuit breaker's timeout as minimum backoff
                    await asyncio.sleep(time_until_retry)
                else:
                    # Circuit is in HALF_OPEN state (recovering) - log but continue
                    logger.warning(
                        "Error in dead letter queue retry loop (recovery attempt): %s",
                        str(e),
                        exc_info=True,
                        extra={
                            "component": "dead_letter_queue",
                            "operation": "retry_loop",
                            "error_id": ErrorRegistry.ERR_DEAD_LETTER_QUEUE_ERROR,
                            "circuit_state": "HALF_OPEN",
                        },
                    )

                    # Use normal interval, let circuit breaker handle recovery
                    await asyncio.sleep(self._retry_interval_seconds)

    async def _process_retryable_events(self) -> None:
        """Process all retryable events."""
        # Find events ready for retry
        retryable_events = [event_id for event_id, event in self._storage.items() if event.is_ready_for_retry()]

        # Retry events
        for event_id in retryable_events:
            await self.retry_event(event_id)

    def get_stats(self) -> DeadLetterQueueStats:
        """Get dead letter queue statistics."""
        events = list(self._storage.values())

        pending_retries = sum(1 for e in events if e.can_retry())
        exhausted_retries = sum(1 for e in events if not e.can_retry())

        oldest_event = min((e.failed_at for e in events), default=None)
        newest_event = max((e.failed_at for e in events), default=None)

        # Count failure reasons
        failure_reasons: dict[str, int] = {}
        for event in events:
            reason = event.failure_reason.value
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

        return DeadLetterQueueStats(
            total_failed_events=len(events),
            pending_retries=pending_retries,
            exhausted_retries=exhausted_retries,
            total_retries_attempted=self._total_retries_attempted,
            total_retries_succeeded=self._total_retries_succeeded,
            total_retries_failed=self._total_retries_failed,
            oldest_event=oldest_event,
            newest_event=newest_event,
            failure_reasons=failure_reasons,
        )

    def get_event(self, event_id: str) -> FailedEvent | None:
        """Get a specific failed event."""
        return self._storage.get(event_id)

    def list_events(
        self,
        failure_reason: FailureReason | None = None,
        can_retry: bool | None = None,
        limit: int | None = None,
    ) -> list[FailedEvent]:
        """
        List failed events with optional filtering.

        Args:
            failure_reason: Filter by failure reason
            can_retry: Filter by retry capability
            limit: Maximum number of events to return

        Returns:
            List of failed events
        """
        events = list(self._storage.values())

        # Apply filters
        if failure_reason is not None:
            events = [e for e in events if e.failure_reason == failure_reason]

        if can_retry is not None:
            events = [e for e in events if e.can_retry() == can_retry]

        # Sort by failed_at (oldest first)
        events.sort(key=lambda e: e.failed_at)

        # Apply limit
        if limit:
            events = events[:limit]

        return events

    def remove_event(self, event_id: str) -> bool:
        """
        Remove an event from the queue.

        Args:
            event_id: ID of the event to remove

        Returns:
            True if removed, False if not found
        """
        if event_id in self._storage:
            del self._storage[event_id]
            return True
        return False

    def clear(self) -> None:
        """Clear all events from the queue."""
        self._storage.clear()

    def purge_exhausted_events(self) -> int:
        """
        Remove events that have exhausted retries.

        Returns:
            Number of events removed
        """
        exhausted = [event_id for event_id, event in self._storage.items() if not event.can_retry()]

        for event_id in exhausted:
            del self._storage[event_id]

        return len(exhausted)

    def purge_old_events(self, days: int = 7) -> int:
        """
        Remove events older than specified days.

        Args:
            days: Number of days

        Returns:
            Number of events removed
        """
        cutoff = datetime.now(UTC) - timedelta(days=days)

        old_events = [event_id for event_id, event in self._storage.items() if event.failed_at < cutoff]

        for event_id in old_events:
            del self._storage[event_id]

        return len(old_events)


def get_active_dead_letter_queues() -> list[DeadLetterQueue]:
    """Get all active DeadLetterQueue instances that are currently running.

    This is used by test fixtures to clean up running retry processors
    without expensive gc.get_objects() scans.

    Returns:
        List of running DeadLetterQueue instances
    """
    return _dlq_registry.get_all_running()
