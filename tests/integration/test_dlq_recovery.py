"""Integration tests for DLQ event recovery and retry processing."""

import pytest

from codetoreum.adapters.testing import InMemoryFailedEventStore
from codetoreum.infrastructure.dead_letter_queue import DeadLetterQueue
from codetoreum.adapters.secondary.failed_event_store_adapter import DeadLetterQueueFailedEventStoreAdapter
from codetoreum.ports.output.failed_event_store import FailureReason


@pytest.mark.asyncio
async def test_dlq_adapter_stores_failed_events():
    """Test that DeadLetterQueueFailedEventStoreAdapter stores failed events."""
    dlq = DeadLetterQueue()
    adapter = DeadLetterQueueFailedEventStoreAdapter(dlq)

    event_id = await adapter.add_failed_event(
        event_type="test_event",
        event_data={"key": "value"},
        failure_reason=FailureReason.TRANSIENT_ERROR,
        error_message="Test error",
    )

    assert event_id is not None
    stats = adapter.get_stats()
    assert stats.total_failed_events == 1
    assert stats.pending_retries == 1


@pytest.mark.asyncio
async def test_dlq_adapter_lists_failed_events():
    """Test that DeadLetterQueueFailedEventStoreAdapter lists failed events."""
    dlq = DeadLetterQueue()
    adapter = DeadLetterQueueFailedEventStoreAdapter(dlq)

    await adapter.add_failed_event(
        event_type="event1",
        event_data={"data": 1},
        failure_reason=FailureReason.PROCESSING_ERROR,
        error_message="Error 1",
    )

    await adapter.add_failed_event(
        event_type="event2",
        event_data={"data": 2},
        failure_reason=FailureReason.TRANSIENT_ERROR,
        error_message="Error 2",
    )

    events = adapter.list_events()
    assert len(events) == 2
    assert events[0].event_type == "event1"
    assert events[1].event_type == "event2"


@pytest.mark.asyncio
async def test_dlq_adapter_filters_by_failure_reason():
    """Test that DeadLetterQueueFailedEventStoreAdapter filters by failure reason."""
    dlq = DeadLetterQueue()
    adapter = DeadLetterQueueFailedEventStoreAdapter(dlq)

    await adapter.add_failed_event(
        event_type="event1",
        event_data={},
        failure_reason=FailureReason.PROCESSING_ERROR,
        error_message="Error 1",
    )

    await adapter.add_failed_event(
        event_type="event2",
        event_data={},
        failure_reason=FailureReason.TRANSIENT_ERROR,
        error_message="Error 2",
    )

    processing_errors = adapter.list_events(failure_reason=FailureReason.PROCESSING_ERROR)
    assert len(processing_errors) == 1
    assert processing_errors[0].event_type == "event1"


@pytest.mark.asyncio
async def test_dlq_adapter_filters_by_retry_capability():
    """Test that DeadLetterQueueFailedEventStoreAdapter filters by retry capability."""
    dlq = DeadLetterQueue()
    adapter = DeadLetterQueueFailedEventStoreAdapter(dlq)

    # Validation errors cannot be retried
    await adapter.add_failed_event(
        event_type="event1",
        event_data={},
        failure_reason=FailureReason.VALIDATION_ERROR,
        error_message="Validation failed",
    )

    # Transient errors can be retried
    await adapter.add_failed_event(
        event_type="event2",
        event_data={},
        failure_reason=FailureReason.TRANSIENT_ERROR,
        error_message="Transient error",
    )

    retriable = adapter.list_events(can_retry=True)
    assert len(retriable) == 1
    assert retriable[0].event_type == "event2"

    non_retriable = adapter.list_events(can_retry=False)
    assert len(non_retriable) == 1
    assert non_retriable[0].event_type == "event1"


@pytest.mark.asyncio
async def test_in_memory_failed_event_store():
    """Test InMemoryFailedEventStore for testing purposes."""
    store = InMemoryFailedEventStore()

    event_id = await store.add_failed_event(
        event_type="test_event",
        event_data={"test": "data"},
        failure_reason=FailureReason.TRANSIENT_ERROR,
        error_message="Test error",
    )

    assert event_id is not None
    event = store.get_event(event_id)
    assert event is not None
    assert event.event_type == "test_event"
    assert event.failure_reason == FailureReason.TRANSIENT_ERROR

    stats = store.get_stats()
    assert stats.total_failed_events == 1

    # Test removal
    removed = store.remove_event(event_id)
    assert removed is True
    assert store.get_event(event_id) is None
    assert store.get_stats().total_failed_events == 0


@pytest.mark.asyncio
async def test_dlq_retry_processor_recovery():
    """Test that DLQ retry processor successfully recovers failed events.

    This test verifies the complete failure recovery path:
    1. A failed event is stored in the DLQ
    2. The retry processor picks it up
    3. The event is successfully retried and removed from the queue
    """
    import asyncio
    from datetime import datetime, UTC

    # Create DLQ with short backoff for testing
    dlq = DeadLetterQueue(base_delay_seconds=0.1)
    adapter = DeadLetterQueueFailedEventStoreAdapter(dlq)

    # Track which events were successfully retried
    retried_events = []

    async def test_retry_handler(event_type: str, event_data: dict) -> None:
        """Test handler that tracks retried events."""
        retried_events.append((event_type, event_data))

    # Add a failed event that can be retried
    event_id = await adapter.add_failed_event(
        event_type="test_recovery_event",
        event_data={"id": "test-123", "attempt": 1},
        failure_reason=FailureReason.TRANSIENT_ERROR,
        error_message="Transient error - should recover",
    )

    # Verify event is in DLQ before retry
    stats_before = adapter.get_stats()
    assert stats_before.total_failed_events == 1
    assert stats_before.pending_retries == 1

    # Manually set next_retry_at to now so it's immediately ready
    # This simulates the event being ready for its first retry
    event = dlq._storage[event_id]
    event.next_retry_at = datetime.now(UTC)

    # Start retry processor
    await adapter.start_retry_processor(test_retry_handler)

    # Wait for retry processor to pick up the event
    # The retry processor polls every 1 second by default
    await asyncio.sleep(1.5)

    # Stop retry processor
    await adapter.stop_retry_processor()

    # Verify event was retried and removed from DLQ
    assert len(retried_events) == 1
    assert retried_events[0][0] == "test_recovery_event"
    assert retried_events[0][1]["id"] == "test-123"

    stats_after = adapter.get_stats()
    assert stats_after.total_failed_events == 0  # Event should be removed after successful retry
    assert stats_after.total_retries_succeeded == 1
