"""Comprehensive tests for InMemoryFailedEventStore adapter.

Tests cover all methods, edge cases, and failure scenarios to ensure
the adapter correctly implements IFailedEventStore for simulation mode.
"""

import pytest
from datetime import UTC, datetime, timedelta

from codetoreum.adapters.testing.in_memory_failed_event_store import (
    InMemoryFailedEventStore,
)
from codetoreum.ports.output.failed_event_store import (
    FailedEventRecord,
    FailureReason,
)


class TestInMemoryFailedEventStoreBasics:
    """Test basic operations of InMemoryFailedEventStore."""

    @pytest.fixture
    def store(self):
        """Create a fresh store for each test."""
        return InMemoryFailedEventStore()

    @pytest.mark.asyncio
    async def test_add_failed_event_creates_valid_record(self, store):
        """Test that add_failed_event creates a valid record with all fields set."""
        event_id = await store.add_failed_event(
            event_type="WorkItemColumnChanged",
            event_data={"work_item_id": "123"},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Connection timeout",
        )

        assert event_id is not None
        assert isinstance(event_id, str)
        assert len(event_id) > 0

        record = store.get_event(event_id)
        assert record is not None
        assert record.id == event_id
        assert record.event_type == "WorkItemColumnChanged"
        assert record.event_data == {"work_item_id": "123"}
        assert record.failure_reason == FailureReason.TRANSIENT_ERROR
        assert record.error_message == "Connection timeout"
        assert record.retry_count == 0
        assert record.max_retries == 3
        assert record.next_retry_at is None
        assert record.last_retry_at is None
        assert record.metadata == {}

    @pytest.mark.asyncio
    async def test_add_failed_event_with_metadata(self, store):
        """Test that metadata is correctly stored when provided."""
        metadata = {"custom_field": "value", "context": "test"}
        event_id = await store.add_failed_event(
            event_type="ReviewStatusChanged",
            event_data={"review_id": "456"},
            failure_reason=FailureReason.VALIDATION_ERROR,
            error_message="Invalid review state",
            metadata=metadata,
        )

        record = store.get_event(event_id)
        assert record is not None
        assert record.metadata == metadata

    @pytest.mark.asyncio
    async def test_add_failed_event_without_metadata_defaults_to_empty_dict(self, store):
        """Test that metadata defaults to empty dict when not provided."""
        event_id = await store.add_failed_event(
            event_type="Event",
            event_data={},
            failure_reason=FailureReason.TIMEOUT,
            error_message="Timeout",
        )

        record = store.get_event(event_id)
        assert record is not None
        assert record.metadata == {}

    @pytest.mark.asyncio
    async def test_get_event_returns_none_for_nonexistent_id(self, store):
        """Test that get_event returns None for non-existent IDs."""
        result = store.get_event("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_event_returns_frozen_record(self, store):
        """Test that retrieved records are frozen (immutable)."""
        event_id = await store.add_failed_event(
            event_type="Event",
            event_data={"key": "value"},
            failure_reason=FailureReason.PROCESSING_ERROR,
            error_message="Error",
        )

        record = store.get_event(event_id)
        assert record is not None

        # Frozen dataclass should prevent mutations
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            record.event_type = "Modified"  # type: ignore


class TestInMemoryFailedEventStoreStats:
    """Test statistics functionality."""

    @pytest.fixture
    def store(self):
        """Create a fresh store for each test."""
        return InMemoryFailedEventStore()

    @pytest.mark.asyncio
    async def test_get_stats_empty_store(self, store):
        """Test that stats for empty store match port contract."""
        stats = store.get_stats()

        assert stats.total_failed_events == 0
        assert stats.pending_retries == 0
        assert stats.exhausted_retries == 0
        assert stats.total_retries_attempted == 0
        assert stats.total_retries_succeeded == 0
        assert stats.total_retries_failed == 0
        assert stats.oldest_event is None
        assert stats.newest_event is None
        assert stats.failure_reasons is None  # Port contract: None when empty

    @pytest.mark.asyncio
    async def test_get_stats_with_single_event(self, store):
        """Test stats with a single failed event."""
        before_add = datetime.now(UTC)
        await store.add_failed_event(
            event_type="TestEvent",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )
        after_add = datetime.now(UTC)

        stats = store.get_stats()

        assert stats.total_failed_events == 1
        assert stats.pending_retries == 1  # Can retry transient errors
        assert stats.exhausted_retries == 0
        assert stats.total_retries_attempted == 0
        assert before_add <= stats.oldest_event <= after_add
        assert before_add <= stats.newest_event <= after_add
        assert stats.failure_reasons == {"transient_error": 1}

    @pytest.mark.asyncio
    async def test_get_stats_counts_by_failure_reason(self, store):
        """Test that stats correctly count events by failure reason."""
        await store.add_failed_event(
            event_type="Event1",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )
        await store.add_failed_event(
            event_type="Event2",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )
        await store.add_failed_event(
            event_type="Event3",
            event_data={},
            failure_reason=FailureReason.TIMEOUT,
            error_message="Error",
        )
        await store.add_failed_event(
            event_type="Event4",
            event_data={},
            failure_reason=FailureReason.VALIDATION_ERROR,
            error_message="Error",
        )

        stats = store.get_stats()

        assert stats.total_failed_events == 4
        assert stats.failure_reasons == {
            "transient_error": 2,
            "timeout": 1,
            "validation_error": 1,
        }

    @pytest.mark.asyncio
    async def test_get_stats_distinguishes_retry_capability(self, store):
        """Test that stats correctly identify events that can and cannot retry."""
        # Transient errors can retry
        await store.add_failed_event(
            event_type="Event1",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )
        # Validation errors cannot retry
        await store.add_failed_event(
            event_type="Event2",
            event_data={},
            failure_reason=FailureReason.VALIDATION_ERROR,
            error_message="Error",
        )

        stats = store.get_stats()

        assert stats.total_failed_events == 2
        assert stats.pending_retries == 1  # Only transient error
        assert stats.exhausted_retries == 1  # Only validation error

    @pytest.mark.asyncio
    async def test_get_stats_tracks_retry_metrics(self, store):
        """Test that stats accurately track successful and failed retries."""
        event_id = await store.add_failed_event(
            event_type="Event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )

        # Mark some retries
        store.mark_retry_succeeded(event_id)
        store.mark_retry_succeeded(event_id)
        store.mark_retry_failed(event_id)

        stats = store.get_stats()

        assert stats.total_retries_succeeded == 2
        assert stats.total_retries_failed == 1

    @pytest.mark.asyncio
    async def test_get_stats_aggregates_retry_metrics_across_events(self, store):
        """Test that retry metrics are aggregated across all events."""
        event_id1 = await store.add_failed_event(
            event_type="Event1",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )
        event_id2 = await store.add_failed_event(
            event_type="Event2",
            event_data={},
            failure_reason=FailureReason.TIMEOUT,
            error_message="Error",
        )

        store.mark_retry_succeeded(event_id1)
        store.mark_retry_succeeded(event_id1)
        store.mark_retry_failed(event_id1)
        store.mark_retry_succeeded(event_id2)
        store.mark_retry_failed(event_id2)
        store.mark_retry_failed(event_id2)

        stats = store.get_stats()

        assert stats.total_retries_succeeded == 3
        assert stats.total_retries_failed == 3

    @pytest.mark.asyncio
    async def test_get_stats_ignores_retries_for_nonexistent_events(self, store):
        """Test that marking retries for non-existent events doesn't affect stats."""
        stats_before = store.get_stats()

        store.mark_retry_succeeded("nonexistent-id")
        store.mark_retry_failed("nonexistent-id")

        stats_after = store.get_stats()

        assert stats_before.total_retries_succeeded == stats_after.total_retries_succeeded
        assert stats_before.total_retries_failed == stats_after.total_retries_failed


class TestInMemoryFailedEventStoreFiltering:
    """Test event listing and filtering functionality."""

    @pytest.fixture
    def store_with_events(self):
        """Create a store with various events for testing."""
        store = InMemoryFailedEventStore()

        async def setup():
            await store.add_failed_event(
                event_type="Event1",
                event_data={},
                failure_reason=FailureReason.TRANSIENT_ERROR,
                error_message="Transient",
            )
            await store.add_failed_event(
                event_type="Event2",
                event_data={},
                failure_reason=FailureReason.VALIDATION_ERROR,
                error_message="Validation",
            )
            await store.add_failed_event(
                event_type="Event3",
                event_data={},
                failure_reason=FailureReason.TIMEOUT,
                error_message="Timeout",
            )
            await store.add_failed_event(
                event_type="Event4",
                event_data={},
                failure_reason=FailureReason.TRANSIENT_ERROR,
                error_message="Transient2",
            )

        # Run setup in event loop
        import asyncio
        asyncio.run(setup())
        return store

    def test_list_events_returns_all_by_default(self, store_with_events):
        """Test that list_events returns all events when no filters applied."""
        events = store_with_events.list_events()
        assert len(events) == 4

    def test_list_events_filter_by_failure_reason(self, store_with_events):
        """Test filtering events by failure reason."""
        events = store_with_events.list_events(failure_reason=FailureReason.TRANSIENT_ERROR)
        assert len(events) == 2
        assert all(e.failure_reason == FailureReason.TRANSIENT_ERROR for e in events)

    def test_list_events_filter_by_can_retry_true(self, store_with_events):
        """Test filtering events that can retry."""
        events = store_with_events.list_events(can_retry=True)
        # Transient and Timeout can retry, Validation cannot
        assert len(events) == 3
        assert all(e.can_retry() for e in events)

    def test_list_events_filter_by_can_retry_false(self, store_with_events):
        """Test filtering events that cannot retry."""
        events = store_with_events.list_events(can_retry=False)
        # Only Validation error cannot retry
        assert len(events) == 1
        assert all(not e.can_retry() for e in events)

    def test_list_events_filter_combined(self, store_with_events):
        """Test combining multiple filters."""
        events = store_with_events.list_events(
            failure_reason=FailureReason.TRANSIENT_ERROR,
            can_retry=True,
        )
        assert len(events) == 2
        assert all(e.failure_reason == FailureReason.TRANSIENT_ERROR for e in events)
        assert all(e.can_retry() for e in events)

    def test_list_events_with_limit(self, store_with_events):
        """Test limiting the number of returned events."""
        events = store_with_events.list_events(limit=2)
        assert len(events) == 2

    def test_list_events_filter_and_limit(self, store_with_events):
        """Test combining filters with limit."""
        events = store_with_events.list_events(
            failure_reason=FailureReason.TRANSIENT_ERROR,
            limit=1,
        )
        assert len(events) == 1
        assert events[0].failure_reason == FailureReason.TRANSIENT_ERROR

    def test_list_events_no_matches(self, store_with_events):
        """Test list_events returns empty list when no events match."""
        events = store_with_events.list_events(
            failure_reason=FailureReason.CIRCUIT_BREAKER_OPEN,
        )
        assert len(events) == 0


class TestInMemoryFailedEventStoreRemoval:
    """Test event removal and clearing functionality."""

    @pytest.fixture
    def store(self):
        """Create a fresh store for each test."""
        return InMemoryFailedEventStore()

    @pytest.mark.asyncio
    async def test_remove_event_removes_from_store(self, store):
        """Test that remove_event removes an event from the store."""
        event_id = await store.add_failed_event(
            event_type="Event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )

        assert store.get_event(event_id) is not None
        result = store.remove_event(event_id)
        assert result is True
        assert store.get_event(event_id) is None

    @pytest.mark.asyncio
    async def test_remove_event_returns_false_for_nonexistent(self, store):
        """Test that remove_event returns False for non-existent event."""
        result = store.remove_event("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_event_cleans_up_retry_tracking(self, store):
        """Test that removing an event also cleans up its retry tracking."""
        event_id = await store.add_failed_event(
            event_type="Event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )

        store.mark_retry_succeeded(event_id)
        store.mark_retry_failed(event_id)

        store.remove_event(event_id)

        # After removal, retry tracking should not affect stats
        stats = store.get_stats()
        assert stats.total_retries_succeeded == 0
        assert stats.total_retries_failed == 0

    @pytest.mark.asyncio
    async def test_clear_removes_all_events(self, store):
        """Test that clear removes all events."""
        await store.add_failed_event(
            event_type="Event1",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )
        await store.add_failed_event(
            event_type="Event2",
            event_data={},
            failure_reason=FailureReason.TIMEOUT,
            error_message="Error",
        )

        assert len(store.list_events()) == 2

        store.clear()

        assert len(store.list_events()) == 0

    @pytest.mark.asyncio
    async def test_clear_resets_stats(self, store):
        """Test that clear resets all statistics."""
        await store.add_failed_event(
            event_type="Event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )
        event_id = store.list_events()[0].id
        store.mark_retry_succeeded(event_id)

        stats_before = store.get_stats()
        assert stats_before.total_failed_events == 1
        assert stats_before.total_retries_succeeded == 1

        store.clear()

        stats_after = store.get_stats()
        assert stats_after.total_failed_events == 0
        assert stats_after.total_retries_succeeded == 0
        assert stats_after.failure_reasons is None


class TestInMemoryFailedEventStoreConcurrency:
    """Test concurrent operations in the store."""

    @pytest.mark.asyncio
    async def test_concurrent_add_events(self):
        """Test that concurrent additions work correctly."""
        import asyncio

        store = InMemoryFailedEventStore()

        async def add_multiple():
            tasks = [
                store.add_failed_event(
                    event_type=f"Event{i}",
                    event_data={"index": i},
                    failure_reason=FailureReason.TRANSIENT_ERROR,
                    error_message=f"Error {i}",
                )
                for i in range(10)
            ]
            return await asyncio.gather(*tasks)

        event_ids = await add_multiple()

        assert len(event_ids) == 10
        assert len(set(event_ids)) == 10  # All IDs should be unique

        all_events = store.list_events()
        assert len(all_events) == 10

    @pytest.mark.asyncio
    async def test_concurrent_add_and_read(self):
        """Test concurrent additions and reads work correctly."""
        import asyncio

        store = InMemoryFailedEventStore()

        async def add_and_read():
            # Add 5 events
            event_ids = []
            for i in range(5):
                eid = await store.add_failed_event(
                    event_type=f"Event{i}",
                    event_data={"index": i},
                    failure_reason=FailureReason.TRANSIENT_ERROR,
                    error_message=f"Error {i}",
                )
                event_ids.append(eid)

            # Read them back
            retrieved = [store.get_event(eid) for eid in event_ids]
            assert all(r is not None for r in retrieved)

        await add_and_read()


class TestInMemoryFailedEventStoreEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def store(self):
        """Create a fresh store for each test."""
        return InMemoryFailedEventStore()

    @pytest.mark.asyncio
    async def test_add_event_with_empty_event_data(self, store):
        """Test adding an event with empty event data."""
        event_id = await store.add_failed_event(
            event_type="Event",
            event_data={},
            failure_reason=FailureReason.PROCESSING_ERROR,
            error_message="Error",
        )

        record = store.get_event(event_id)
        assert record is not None
        assert record.event_data == {}

    @pytest.mark.asyncio
    async def test_add_event_with_large_event_data(self, store):
        """Test adding an event with large event data."""
        large_data = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}
        event_id = await store.add_failed_event(
            event_type="Event",
            event_data=large_data,
            failure_reason=FailureReason.PROCESSING_ERROR,
            error_message="Error",
        )

        record = store.get_event(event_id)
        assert record is not None
        assert record.event_data == large_data

    @pytest.mark.asyncio
    async def test_mark_retry_succeeded_multiple_times(self, store):
        """Test marking multiple successful retries."""
        event_id = await store.add_failed_event(
            event_type="Event",
            event_data={},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Error",
        )

        for _ in range(5):
            store.mark_retry_succeeded(event_id)

        stats = store.get_stats()
        assert stats.total_retries_succeeded == 5

    @pytest.mark.asyncio
    async def test_all_failure_reasons_supported(self, store):
        """Test that all FailureReason enum values are handled correctly."""
        for reason in FailureReason:
            event_id = await store.add_failed_event(
                event_type=f"Event_{reason.value}",
                event_data={},
                failure_reason=reason,
                error_message=f"Error for {reason.value}",
            )

            record = store.get_event(event_id)
            assert record is not None
            assert record.failure_reason == reason

        stats = store.get_stats()
        assert stats.total_failed_events == len(FailureReason)
        assert len(stats.failure_reasons) == len(FailureReason)
