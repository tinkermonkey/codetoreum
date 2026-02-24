"""Unit tests for dead letter queue."""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone

from codetoreum.infrastructure.dead_letter_queue import (
    DeadLetterQueue,
    FailedEvent,
    FailureReason,
)


class TestFailedEvent:
    """Test FailedEvent model."""

    def test_can_retry_when_under_max_retries(self):
        """Test that event can retry when under max retries."""
        event = FailedEvent(
            id="test",
            event_type="test_event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test error",
            failed_at=datetime.now(timezone.utc),
            retry_count=2,
            max_retries=3
        )

        assert event.can_retry() is True

    def test_cannot_retry_when_max_retries_reached(self):
        """Test that event cannot retry when max retries reached."""
        event = FailedEvent(
            id="test",
            event_type="test_event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test error",
            failed_at=datetime.now(timezone.utc),
            retry_count=3,
            max_retries=3
        )

        assert event.can_retry() is False

    def test_cannot_retry_validation_errors(self):
        """Test that validation errors are not retryable."""
        event = FailedEvent(
            id="test",
            event_type="test_event",
            event_data={},
            failure_reason=FailureReason.VALIDATION_ERROR,
            error_message="Validation failed",
            failed_at=datetime.now(timezone.utc),
            retry_count=0,
            max_retries=3
        )

        assert event.can_retry() is False

    def test_cannot_retry_when_next_retry_in_future(self):
        """Test that event is not ready for retry when next retry time is in future."""
        event = FailedEvent(
            id="test",
            event_type="test_event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test error",
            failed_at=datetime.now(timezone.utc),
            retry_count=0,
            max_retries=3,
            next_retry_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )

        assert event.can_retry() is True  # Has retries left
        assert event.is_ready_for_retry() is False  # But not ready yet

    def test_calculate_next_retry_exponential_backoff(self):
        """Test that next retry uses exponential backoff."""
        event = FailedEvent(
            id="test",
            event_type="test_event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test error",
            failed_at=datetime.now(timezone.utc),
            retry_count=0,
            max_retries=3
        )

        next_retry = event.calculate_next_retry(base_delay=10.0, exponential_base=2.0)

        # First retry: 10 * (2^0) = 10 seconds
        expected = datetime.now(timezone.utc) + timedelta(seconds=10)
        assert (next_retry - expected).total_seconds() < 1  # Within 1 second

        event.retry_count = 2
        next_retry = event.calculate_next_retry(base_delay=10.0, exponential_base=2.0)

        # Third retry: 10 * (2^2) = 40 seconds
        expected = datetime.now(timezone.utc) + timedelta(seconds=40)
        assert (next_retry - expected).total_seconds() < 1

    def test_calculate_next_retry_caps_at_max(self):
        """Test that retry delay is capped at 1 hour."""
        event = FailedEvent(
            id="test",
            event_type="test_event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test error",
            failed_at=datetime.now(timezone.utc),
            retry_count=10,  # Would be 10 * (2^10) = 10,240 seconds
            max_retries=20
        )

        next_retry = event.calculate_next_retry(base_delay=10.0, exponential_base=2.0)

        # Should be capped at 1 hour (3600 seconds)
        expected_max = datetime.now(timezone.utc) + timedelta(seconds=3600)
        assert (next_retry - expected_max).total_seconds() < 1


class TestDeadLetterQueue:
    """Test dead letter queue."""

    @pytest.mark.asyncio
    async def test_add_failed_event(self):
        """Test adding a failed event."""
        dlq = DeadLetterQueue()

        event_id = await dlq.add_failed_event(
            event_type="test_event",
            event_data={"key": "value"},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test error",
            metadata={"extra": "data"}
        )

        assert event_id is not None
        event = dlq.get_event(event_id)
        assert event is not None
        assert event.event_type == "test_event"
        assert event.event_data["key"] == "value"
        assert event.failure_reason == FailureReason.TRANSIENT_ERROR
        assert event.metadata["extra"] == "data"

    @pytest.mark.asyncio
    async def test_retry_event_success(self):
        """Test retrying an event that succeeds."""
        dlq = DeadLetterQueue(max_retries=3)

        retry_called = False

        async def retry_handler(event_type, event_data):
            nonlocal retry_called
            retry_called = True
            # Success

        await dlq.start_retry_processor(retry_handler)

        event_id = await dlq.add_failed_event(
            event_type="test_event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test error"
        )

        # Retry the event
        success = await dlq.retry_event(event_id)

        assert success is True
        assert retry_called is True
        # Event should be removed from queue on success
        assert dlq.get_event(event_id) is None

        await dlq.stop_retry_processor()

    @pytest.mark.asyncio
    async def test_retry_event_failure(self):
        """Test retrying an event that fails."""
        dlq = DeadLetterQueue(max_retries=3)

        async def retry_handler(event_type, event_data):
            raise Exception("Retry failed")

        await dlq.start_retry_processor(retry_handler)

        event_id = await dlq.add_failed_event(
            event_type="test_event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test error"
        )

        # Retry the event
        success = await dlq.retry_event(event_id)

        assert success is False
        # Event should still be in queue
        event = dlq.get_event(event_id)
        assert event is not None
        assert event.retry_count == 1

        await dlq.stop_retry_processor()

    @pytest.mark.asyncio
    async def test_retry_event_exhausted_retries(self):
        """Test that events with exhausted retries cannot be retried."""
        dlq = DeadLetterQueue(max_retries=2)

        event_id = await dlq.add_failed_event(
            event_type="test_event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test error"
        )

        # Manually exhaust retries
        event = dlq.get_event(event_id)
        assert event is not None
        event.retry_count = 2  # At max

        success = await dlq.retry_event(event_id)

        assert success is False

    @pytest.mark.asyncio
    async def test_retry_event_not_found(self):
        """Test retrying a non-existent event."""
        dlq = DeadLetterQueue()

        success = await dlq.retry_event("nonexistent")

        assert success is False

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting queue statistics."""
        dlq = DeadLetterQueue(max_retries=3)

        # Add some events
        await dlq.add_failed_event(
            event_type="test1",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error 1"
        )

        await dlq.add_failed_event(
            event_type="test2",
            event_data={},
            failure_reason=FailureReason.TIMEOUT,
            error_message="Error 2"
        )

        # Add an exhausted event
        event_id = await dlq.add_failed_event(
            event_type="test3",
            event_data={},
            failure_reason=FailureReason.PROCESSING_ERROR,
            error_message="Error 3"
        )
        event = dlq.get_event(event_id)
        assert event is not None
        event.retry_count = 3  # Exhausted

        stats = dlq.get_stats()

        assert stats.total_failed_events == 3
        assert stats.pending_retries == 2
        assert stats.exhausted_retries == 1
        assert stats.failure_reasons[FailureReason.TRANSIENT_ERROR.value] == 1
        assert stats.failure_reasons[FailureReason.TIMEOUT.value] == 1
        assert stats.oldest_event is not None
        assert stats.newest_event is not None

    @pytest.mark.asyncio
    async def test_list_events(self):
        """Test listing events."""
        dlq = DeadLetterQueue()

        # Add various events
        await dlq.add_failed_event(
            event_type="test1",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error 1"
        )

        await dlq.add_failed_event(
            event_type="test2",
            event_data={},
            failure_reason=FailureReason.TIMEOUT,
            error_message="Error 2"
        )

        # List all
        events = dlq.list_events()
        assert len(events) == 2

        # Filter by failure reason
        events = dlq.list_events(failure_reason=FailureReason.TRANSIENT_ERROR)
        assert len(events) == 1

        # Limit
        events = dlq.list_events(limit=1)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_list_events_can_retry_filter(self):
        """Test filtering events by retry capability."""
        dlq = DeadLetterQueue(max_retries=2)

        # Add retryable event
        await dlq.add_failed_event(
            event_type="retryable",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Retryable"
        )

        # Add non-retryable event
        event_id = await dlq.add_failed_event(
            event_type="exhausted",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Exhausted"
        )
        event = dlq.get_event(event_id)
        assert event is not None
        event.retry_count = 2  # Exhausted

        # Filter for retryable
        events = dlq.list_events(can_retry=True)
        assert len(events) == 1
        assert events[0].event_type == "retryable"

        # Filter for non-retryable
        events = dlq.list_events(can_retry=False)
        assert len(events) == 1
        assert events[0].event_type == "exhausted"

    @pytest.mark.asyncio
    async def test_remove_event(self):
        """Test removing an event."""
        dlq = DeadLetterQueue()

        event_id = await dlq.add_failed_event(
            event_type="test",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test"
        )

        assert dlq.remove_event(event_id) is True
        assert dlq.get_event(event_id) is None
        assert dlq.remove_event(event_id) is False  # Already removed

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing all events."""
        dlq = DeadLetterQueue()

        await dlq.add_failed_event(
            event_type="test1",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test"
        )

        await dlq.add_failed_event(
            event_type="test2",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test"
        )

        dlq.clear()

        stats = dlq.get_stats()
        assert stats.total_failed_events == 0

    @pytest.mark.asyncio
    async def test_purge_exhausted_events(self):
        """Test purging events with exhausted retries."""
        dlq = DeadLetterQueue(max_retries=2)

        # Add retryable event
        await dlq.add_failed_event(
            event_type="retryable",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Retryable"
        )

        # Add exhausted events
        for i in range(3):
            event_id = await dlq.add_failed_event(
                event_type=f"exhausted_{i}",
                event_data={},
                failure_reason=FailureReason.TRANSIENT_ERROR,
                error_message=f"Exhausted {i}"
            )
            event = dlq.get_event(event_id)
            assert event is not None
            event.retry_count = 2  # Exhausted

        count = dlq.purge_exhausted_events()

        assert count == 3
        stats = dlq.get_stats()
        assert stats.total_failed_events == 1
        assert stats.exhausted_retries == 0

    @pytest.mark.asyncio
    async def test_purge_old_events(self):
        """Test purging events older than specified days."""
        dlq = DeadLetterQueue()

        # Add old event
        old_event_id = await dlq.add_failed_event(
            event_type="old",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Old event"
        )
        old_event = dlq.get_event(old_event_id)
        assert old_event is not None
        old_event.failed_at = datetime.now(timezone.utc) - timedelta(days=10)

        # Add recent event
        await dlq.add_failed_event(
            event_type="recent",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Recent event"
        )

        count = dlq.purge_old_events(days=7)

        assert count == 1
        stats = dlq.get_stats()
        assert stats.total_failed_events == 1
        assert dlq.get_event(old_event_id) is None

    @pytest.mark.asyncio
    async def test_retry_processor_lifecycle(self):
        """Test starting and stopping retry processor."""
        dlq = DeadLetterQueue()

        async def retry_handler(event_type, event_data):
            pass

        # Start processor
        await dlq.start_retry_processor(retry_handler)
        assert dlq._running is True
        assert dlq._retry_task is not None

        # Stop processor
        await dlq.stop_retry_processor()
        assert dlq._running is False

    @pytest.mark.asyncio
    async def test_automatic_retry_processing(self):
        """Test that retry processor automatically processes retryable events."""
        dlq = DeadLetterQueue(retry_interval_seconds=0.1, base_delay_seconds=0.01)

        retry_count = 0

        async def retry_handler(event_type, event_data):
            nonlocal retry_count
            retry_count += 1

        await dlq.start_retry_processor(retry_handler)

        # Add event that's immediately retryable
        event_id = await dlq.add_failed_event(
            event_type="test",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Test"
        )

        # Set next retry to now (past)
        event = dlq.get_event(event_id)
        assert event is not None
        event.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Wait for retry processor to process it
        await asyncio.sleep(0.3)

        await dlq.stop_retry_processor()

        # Should have been retried at least once
        assert retry_count >= 1
