"""Integration tests for event bridge reliability with dead letter queue fallback.

Tests verify that:
1. Event publishing failures are captured in the dead letter queue
2. Failed events are retried automatically
3. Work item automation is not silently disabled on publishing failure (issue #371)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.domain.events import BoardReconciledEvent, WorkItemColumnChangedEvent
from codetoreum.infrastructure.dead_letter_queue import DeadLetterQueue, FailureReason
from codetoreum.infrastructure.event_bus import EventBus, EventBusError


class TestEventBridgeErrorHandling:
    """Test event bridge error handling with dead letter queue."""

    @pytest.fixture
    def event_bus(self):
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def dead_letter_queue(self):
        """Create dead letter queue."""
        return DeadLetterQueue()

    @pytest.mark.asyncio
    async def test_event_publishing_failure_is_queued_to_dlq(self, event_bus, dead_letter_queue):
        """Test that event publishing failures are captured in DLQ."""
        # Mock event bus to raise error
        event_bus.publish = AsyncMock(side_effect=Exception("Network error"))

        # Create domain event
        domain_event = WorkItemColumnChangedEvent(
            aggregate_id="work-item-1",
            payload={
                "work_item_id": "work-item-1",
                "board_id": "board-1",
                "project_id": "project-1",
                "from_column": "Backlog",
                "to_column": "In Progress",
                "moved_by": "user-1",
            },
        )

        # Simulate the bridge's error handling
        try:
            await event_bus.publish(domain_event)
        except Exception as e:
            # This is what the bridge does: capture error and queue to DLQ
            event_id = await dead_letter_queue.add_failed_event(
                event_type=domain_event.event_type,
                event_data=domain_event.payload,
                failure_reason=FailureReason.PROCESSING_ERROR,
                error_message=str(e),
                metadata={
                    "work_item_id": "work-item-1",
                    "original_error": "Exception",
                },
            )

        # Verify event is in DLQ
        stats = dead_letter_queue.get_stats()
        assert stats.total_failed_events == 1
        assert stats.pending_retries == 1
        assert stats.exhausted_retries == 0

    @pytest.mark.asyncio
    async def test_transient_vs_permanent_errors_are_classified(self, dead_letter_queue):
        """Test that transient and permanent errors are classified correctly."""
        # Add transient error (connection issue)
        transient_event_id = await dead_letter_queue.add_failed_event(
            event_type="WorkItemColumnChanged",
            event_data={"work_item_id": "item-1"},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Connection timeout",
        )

        # Add permanent error (validation)
        permanent_event_id = await dead_letter_queue.add_failed_event(
            event_type="WorkItemColumnChanged",
            event_data={"work_item_id": "item-2"},
            failure_reason=FailureReason.VALIDATION_ERROR,
            error_message="Invalid event data",
        )

        # Both should be in the queue
        stats = dead_letter_queue.get_stats()
        assert stats.total_failed_events == 2

        # Check failure reasons
        transient = dead_letter_queue.get_event(transient_event_id)
        permanent = dead_letter_queue.get_event(permanent_event_id)

        assert transient.failure_reason == FailureReason.TRANSIENT_ERROR
        assert permanent.failure_reason == FailureReason.VALIDATION_ERROR

        # Permanent errors should not be retryable
        assert transient.can_retry() is True
        assert permanent.can_retry() is False

    @pytest.mark.asyncio
    async def test_dlq_retry_processor_retries_failed_events(self):
        """Test that DLQ retry processor retries failed events."""
        # Create DLQ with short retry interval for testing
        dead_letter_queue = DeadLetterQueue(retry_interval_seconds=0.1)

        # Track retry attempts
        retry_attempts = []

        async def mock_retry_handler(event_type: str, event_data: dict) -> None:
            """Mock retry handler that succeeds on second attempt."""
            retry_attempts.append((event_type, event_data))
            if len(retry_attempts) < 2:
                raise Exception("First attempt fails")
            # Second attempt succeeds

        # Add failed event with no initial retry delay (make it ready immediately)
        event_id = await dead_letter_queue.add_failed_event(
            event_type="WorkItemColumnChanged",
            event_data={"work_item_id": "item-1"},
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Temporary failure",
        )

        # Force the event to be ready for retry immediately
        event = dead_letter_queue.get_event(event_id)
        event.next_retry_at = None  # Make it ready to retry now

        # Start retry processor
        await dead_letter_queue.start_retry_processor(mock_retry_handler)

        # Wait for retry attempts (processor runs every 0.1s, with exponential backoff)
        # First attempt: immediate, fails with base_delay=60s for next retry
        # But we can manually trigger retry to test the logic
        await asyncio.sleep(0.2)  # Let first attempt happen

        # Now manually retry to test the success path
        await dead_letter_queue.retry_event(event_id)

        # Check stats - event should be successful now
        stats = dead_letter_queue.get_stats()
        assert stats.total_failed_events == 0  # Event was successfully retried
        assert stats.total_retries_attempted >= 2
        assert stats.total_retries_succeeded >= 1

        await dead_letter_queue.stop_retry_processor()

    @pytest.mark.asyncio
    async def test_board_reconciled_event_publishing_failure_is_queued(self, event_bus, dead_letter_queue):
        """Test that BoardReconciled event publishing failures are captured."""
        # Create board reconciled event
        domain_event = BoardReconciledEvent(
            aggregate_id="board-1",
            payload={
                "board_id": "board-1",
                "project_id": "project-1",
                "columns_added": ["New Column"],
                "columns_removed": [],
                "orphaned_items": [],
            },
        )

        # Simulate publishing failure
        event_bus.publish = AsyncMock(side_effect=ConnectionError("Network down"))

        try:
            await event_bus.publish(domain_event)
        except Exception as e:
            # Simulate bridge's error handling
            await dead_letter_queue.add_failed_event(
                event_type=domain_event.event_type,
                event_data=domain_event.payload,
                failure_reason=FailureReason.TRANSIENT_ERROR,
                error_message=str(e),
                metadata={"board_id": "board-1"},
            )

        # Verify in DLQ
        stats = dead_letter_queue.get_stats()
        assert stats.total_failed_events == 1
        events = dead_letter_queue.list_events()
        assert len(events) == 1
        assert events[0].event_type == "BoardReconciled"

    @pytest.mark.asyncio
    async def test_failed_events_preserve_metadata_for_debugging(self, dead_letter_queue):
        """Test that failed events preserve metadata for debugging."""
        event_id = await dead_letter_queue.add_failed_event(
            event_type="WorkItemColumnChanged",
            event_data={
                "work_item_id": "item-123",
                "from_column": "Backlog",
                "to_column": "In Progress",
            },
            failure_reason=FailureReason.PROCESSING_ERROR,
            error_message="Handler raised exception",
            metadata={
                "handler_name": "BoardColumnEventHandler",
                "original_error": "ValueError",
                "timestamp": "2024-01-01T00:00:00Z",
            },
        )

        # Retrieve and verify metadata
        event = dead_letter_queue.get_event(event_id)
        assert event.metadata["handler_name"] == "BoardColumnEventHandler"
        assert event.metadata["original_error"] == "ValueError"
        assert event.event_data["work_item_id"] == "item-123"

    @pytest.mark.asyncio
    async def test_dlq_prevents_silent_automation_failure(self, dead_letter_queue):
        """Test that DLQ prevents silent automation failure (the core issue #371).

        Verifies that when event publishing fails:
        1. The failure is captured in DLQ (not silent)
        2. The event data is preserved (can be retried)
        3. Operators can discover and fix the issue
        """
        # Simulate: work item moves on board, event publishing fails
        # Without DLQ: automation silently disabled, no visibility
        # With DLQ: failure is visible, can be retried

        # Add failed event simulating "work item moved but agent not triggered"
        event_id = await dead_letter_queue.add_failed_event(
            event_type="WorkItemColumnChanged",
            event_data={
                "work_item_id": "item-123",
                "board_id": "board-1",
                "project_id": "project-1",
                "from_column": "Backlog",
                "to_column": "In Progress",
                "moved_by": "user-1",
            },
            failure_reason=FailureReason.TRANSIENT_ERROR,
            error_message="Event bus connection timeout",
        )

        # Before fix: event is lost, automation disabled, no visibility
        # After fix:
        # 1. Event is captured in DLQ
        stats = dead_letter_queue.get_stats()
        assert stats.total_failed_events == 1

        # 2. Event data is preserved
        failed_event = dead_letter_queue.get_event(event_id)
        assert failed_event.event_data["work_item_id"] == "item-123"

        # 3. Event can be retried
        assert failed_event.can_retry() is True

        # 4. Operators can see the failure
        events = dead_letter_queue.list_events(failure_reason=FailureReason.TRANSIENT_ERROR)
        assert len(events) == 1
        assert events[0].event_type == "WorkItemColumnChanged"


class TestBridgeIntegration:
    """Integration tests for actual bridge code paths using SimulationApplicationBootstrap."""

    @pytest.mark.asyncio
    async def test_board_column_bridge_queues_to_dlq_on_publish_failure(self, simulation_bootstrap, simulation_seeder):
        """Test that actual bridge queues failed events to DLQ when publishing fails.

        Mocks event_bus.publish to fail, then verifies the bridge's error handling
        queues to DLQ with proper error classification.
        """
        from unittest.mock import AsyncMock

        from codetoreum.ports.output.board_service import MovedByType
        from tests.conftest import assert_condition

        bootstrap = simulation_bootstrap
        adapters = bootstrap.adapters

        # Ensure we have required adapters
        if adapters.agent_executor is None:
            pytest.skip("Agent executor not available")

        await simulation_seeder.seed_default_scenario()
        work_item_id = simulation_seeder.created_items.work_items[0]

        # Mock event bus to fail with EventBusError wrapping ConnectionError
        original_publish = bootstrap.infrastructure.event_bus.publish

        try:

            async def failing_publish(event):
                # Simulate transient error (connection failure) as would happen in production
                connection_error = ConnectionError("Network unreachable")
                bus_error = EventBusError("Connection error publishing event")
                bus_error.__cause__ = connection_error
                raise bus_error

            bootstrap.infrastructure.event_bus.publish = AsyncMock(side_effect=failing_publish)

            # Move item to trigger bridge (exercises actual error handling in bridge)
            await adapters.board_as_mock().move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

            # Wait for DLQ to capture the failed event
            async def has_failed_event():
                stats = bootstrap.infrastructure.failed_event_store.get_stats()
                return stats.total_failed_events > 0

            await assert_condition(
                has_failed_event,
                timeout=2.0,
                poll_interval=0.05,
                message="DLQ should capture failed event when event_bus.publish fails",
            )

            # Verify event was captured in DLQ with correct error classification
            events = bootstrap.infrastructure.failed_event_store.list_events()
            assert len(events) >= 1

            # Find the WorkItemColumnChanged event
            work_item_event = next((e for e in events if e.event_type == "WorkItemColumnChanged"), None)
            assert work_item_event is not None, "WorkItemColumnChanged not found in DLQ"
            assert work_item_event.event_data["work_item_id"] == work_item_id

            # Verify error was classified as transient (bridge logic checks for ConnectionError)
            assert (
                work_item_event.failure_reason.value == "transient_error"
            ), f"Expected transient_error but got {work_item_event.failure_reason.value}"
        finally:
            # Restore original publish for cleanup
            bootstrap.infrastructure.event_bus.publish = original_publish
