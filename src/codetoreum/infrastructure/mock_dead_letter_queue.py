"""Mock Dead Letter Queue for testing and simulation.

Provides deterministic behavior for testing workflows that use DLQ.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from .dead_letter_queue import (
    DeadLetterQueue,
    FailedEvent,
    FailureReason,
)


class MockDeadLetterQueue(DeadLetterQueue):
    """
    Mock Dead Letter Queue for testing and simulation mode.

    Provides additional control and inspection capabilities for testing:
    - Synchronous retry processing (no background tasks)
    - Controllable time progression for testing time-based behavior
    - Event history tracking
    - Simulated retry success/failure
    """

    def __init__(
        self,
        storage: dict[str, FailedEvent] | None = None,
        max_retries: int = 3,
        base_delay_seconds: float = 60.0,
        exponential_base: float = 2.0,
        retry_interval_seconds: float = 30.0,
        auto_succeed_after: int | None = None,
    ):
        """
        Initialize mock dead letter queue.

        Args:
            storage: Optional external storage (for persistence)
            max_retries: Maximum retry attempts per event
            base_delay_seconds: Base delay for exponential backoff
            exponential_base: Base for exponential calculation
            retry_interval_seconds: How often to check for retryable events
            auto_succeed_after: Automatically succeed retries after N attempts (for testing)
        """
        super().__init__(
            storage=storage,
            max_retries=max_retries,
            base_delay_seconds=base_delay_seconds,
            exponential_base=exponential_base,
            retry_interval_seconds=retry_interval_seconds,
        )

        # Testing features
        self._auto_succeed_after = auto_succeed_after
        self._event_history: list[dict[str, Any]] = []
        self._current_time = datetime.now(UTC)
        self._retry_outcomes: dict[str, bool] = {}  # event_id -> should_succeed

    def set_current_time(self, time: datetime) -> None:
        """
        Set the current time for testing.

        Allows testing time-based retry logic without waiting.
        """
        self._current_time = time

    def advance_time(self, delta: timedelta) -> None:
        """Advance the current time by a delta."""
        self._current_time += delta

    def set_retry_outcome(self, event_id: str, should_succeed: bool) -> None:
        """
        Set the outcome for a specific event's next retry.

        Args:
            event_id: ID of the event
            should_succeed: Whether the next retry should succeed
        """
        self._retry_outcomes[event_id] = should_succeed

    def get_event_history(self) -> list[dict[str, Any]]:
        """Get complete history of all events."""
        return self._event_history.copy()

    async def add_failed_event(
        self,
        event_type: str,
        event_data: dict[str, Any],
        failure_reason: FailureReason,
        error_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add failed event and track in history."""
        event_id = await super().add_failed_event(event_type, event_data, failure_reason, error_message, metadata)

        self._event_history.append(
            {
                "action": "add",
                "event_id": event_id,
                "event_type": event_type,
                "failure_reason": failure_reason.value,
                "timestamp": self._current_time,
            }
        )

        return event_id

    async def retry_event(self, event_id: str) -> bool:
        """
        Retry event with controllable outcome.

        Uses set_retry_outcome() or auto_succeed_after to determine success.
        """
        if event_id not in self._storage:
            return False

        event = self._storage[event_id]

        if not event.can_retry():
            return False

        # Check if we should force an outcome
        should_succeed = self._retry_outcomes.pop(event_id, None)

        if should_succeed is None and self._auto_succeed_after is not None:
            # Auto-succeed after N attempts
            should_succeed = event.retry_count >= self._auto_succeed_after - 1

        if should_succeed is True:
            # Force success
            event.retry_count += 1
            event.last_retry_at = self._current_time
            del self._storage[event_id]
            self._total_retries_attempted += 1
            self._total_retries_succeeded += 1

            self._event_history.append(
                {
                    "action": "retry_success",
                    "event_id": event_id,
                    "retry_count": event.retry_count,
                    "timestamp": self._current_time,
                }
            )

            return True

        if should_succeed is False:
            # Force failure
            event.retry_count += 1
            event.last_retry_at = self._current_time
            self._total_retries_attempted += 1
            self._total_retries_failed += 1

            if event.can_retry():
                event.next_retry_at = event.calculate_next_retry(self._base_delay_seconds, self._exponential_base)
            else:
                event.next_retry_at = None

            self._event_history.append(
                {
                    "action": "retry_failure",
                    "event_id": event_id,
                    "retry_count": event.retry_count,
                    "timestamp": self._current_time,
                }
            )

            return False

        # Use default behavior from parent class
        result = await super().retry_event(event_id)

        self._event_history.append(
            {
                "action": "retry_success" if result else "retry_failure",
                "event_id": event_id,
                "retry_count": event.retry_count,
                "timestamp": self._current_time,
            }
        )

        return result

    async def process_retries_now(self) -> int:
        """
        Synchronously process all retryable events.

        Returns count of events processed. Useful for testing without
        background tasks.
        """
        if not self._retry_handler:
            return 0

        # Override time check using mock time
        retryable_events = [
            event_id
            for event_id, event in self._storage.items()
            if event.can_retry() and (event.next_retry_at is None or event.next_retry_at <= self._current_time)
        ]

        processed_count = 0
        for event_id in retryable_events:
            await self.retry_event(event_id)
            processed_count += 1

        return processed_count

    async def start_retry_processor(self, retry_handler: Callable) -> None:
        """
        Mock retry processor - does nothing.

        In mock mode, use process_retries_now() instead for synchronous testing.
        """
        self._retry_handler = retry_handler
        # Don't start background task in mock mode

    async def stop_retry_processor(self) -> None:
        """Mock stop - nothing to stop."""

    def reset(self) -> None:
        """Reset the mock DLQ to initial state."""
        self._storage.clear()
        self._event_history.clear()
        self._retry_outcomes.clear()
        self._total_retries_attempted = 0
        self._total_retries_succeeded = 0
        self._total_retries_failed = 0
        self._current_time = datetime.now(UTC)
