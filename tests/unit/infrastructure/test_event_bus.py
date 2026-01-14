"""Unit tests for EventBus."""

import asyncio
import logging

import pytest

from codetoreum.domain.events import DomainEvent, WorkItemCreated, WorkItemCompleted
from codetoreum.infrastructure.event_bus import EventBus, EventBusError, EventHandler, event_handler


@event_handler("WorkItemCreated")
class _TestWorkItemCreatedHandler(EventHandler):
    """Test handler for WorkItemCreated events."""

    def __init__(self):
        self.handled_events = []

    async def handle(self, event: DomainEvent) -> None:
        """Handle event."""
        self.handled_events.append(event)


@event_handler("WorkItemCreated", "WorkItemCompleted")
class _TestMultiEventHandler(EventHandler):
    """Test handler for multiple event types."""

    def __init__(self):
        self.handled_events = []

    async def handle(self, event: DomainEvent) -> None:
        """Handle event."""
        self.handled_events.append(event)


class _TestWildcardHandler(EventHandler):
    """Test handler that receives all events."""

    def __init__(self):
        self.handled_events = []

    async def handle(self, event: DomainEvent) -> None:
        """Handle event."""
        self.handled_events.append(event)

    def get_event_types(self):
        """Return empty list for wildcard."""
        return []


@pytest.mark.asyncio
class TestEventBus:
    """Test suite for EventBus."""

    async def test_register_and_publish_to_single_handler(self):
        """Test registering handler and publishing events."""
        # Arrange
        bus = EventBus()
        handler = _TestWorkItemCreatedHandler()
        bus.register_handler(handler)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)

        # Assert
        assert len(handler.handled_events) == 1
        assert handler.handled_events[0] == event

    async def test_multiple_handlers_receive_same_event(self):
        """Test that multiple handlers receive the same event."""
        # Arrange
        bus = EventBus()
        handler1 = _TestWorkItemCreatedHandler()
        handler2 = _TestWorkItemCreatedHandler()

        bus.register_handler(handler1)
        bus.register_handler(handler2)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)

        # Assert
        assert len(handler1.handled_events) == 1
        assert len(handler2.handled_events) == 1
        assert handler1.handled_events[0] == event
        assert handler2.handled_events[0] == event

    async def test_multi_event_handler_receives_multiple_types(self):
        """Test handler registered for multiple event types."""
        # Arrange
        bus = EventBus()
        handler = _TestMultiEventHandler()
        bus.register_handler(handler)

        event1 = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        event2 = WorkItemCompleted(
            aggregate_id="work-item-123",
            payload={"completed_at": "2025-10-27T12:00:00Z"},
        )

        # Act
        await bus.publish(event1)
        await bus.publish(event2)

        # Assert
        assert len(handler.handled_events) == 2
        assert handler.handled_events[0] == event1
        assert handler.handled_events[1] == event2

    async def test_wildcard_handler_receives_all_events(self):
        """Test wildcard handler receives all event types."""
        # Arrange
        bus = EventBus()
        handler = _TestWildcardHandler()
        bus.register_handler(handler)

        event1 = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        event2 = WorkItemCompleted(
            aggregate_id="work-item-123",
            payload={"completed_at": "2025-10-27T12:00:00Z"},
        )

        # Act
        await bus.publish(event1)
        await bus.publish(event2)

        # Assert
        assert len(handler.handled_events) == 2
        assert handler.handled_events[0] == event1
        assert handler.handled_events[1] == event2

    async def test_subscribe_with_callback(self):
        """Test subscribing with callback function."""
        # Arrange
        bus = EventBus()
        received_events = []

        async def callback(event: DomainEvent):
            received_events.append(event)

        bus.subscribe("WorkItemCreated", callback)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)

        # Assert
        assert len(received_events) == 1
        assert received_events[0] == event

    async def test_wildcard_callback_subscription(self):
        """Test subscribing to all events with callback."""
        # Arrange
        bus = EventBus()
        received_events = []

        async def callback(event: DomainEvent):
            received_events.append(event)

        bus.subscribe(None, callback)  # None = wildcard

        event1 = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        event2 = WorkItemCompleted(
            aggregate_id="work-item-123",
            payload={"completed_at": "2025-10-27T12:00:00Z"},
        )

        # Act
        await bus.publish(event1)
        await bus.publish(event2)

        # Assert
        assert len(received_events) == 2

    async def test_unregister_handler(self):
        """Test unregistering a handler."""
        # Arrange
        bus = EventBus()
        handler = _TestWorkItemCreatedHandler()
        bus.register_handler(handler)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)
        assert len(handler.handled_events) == 1

        bus.unregister_handler(handler)
        await bus.publish(event)

        # Assert
        assert len(handler.handled_events) == 1  # No new events

    async def test_unsubscribe_callback(self):
        """Test unsubscribing a callback."""
        # Arrange
        bus = EventBus()
        received_events = []

        async def callback(event: DomainEvent):
            received_events.append(event)

        bus.subscribe("WorkItemCreated", callback)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)
        assert len(received_events) == 1

        bus.unsubscribe("WorkItemCreated", callback)
        await bus.publish(event)

        # Assert
        assert len(received_events) == 1  # No new events

    async def test_publish_batch(self):
        """Test publishing multiple events."""
        # Arrange
        bus = EventBus()
        handler = _TestWorkItemCreatedHandler()
        bus.register_handler(handler)

        events = [
            WorkItemCreated(
                aggregate_id=f"work-item-{i}",
                payload={"title": f"Test {i}"},
            )
            for i in range(5)
        ]

        # Act
        await bus.publish_batch(events)

        # Assert
        assert len(handler.handled_events) == 5

    async def test_handler_error_is_logged_but_not_raised(self):
        """Test that handler errors are caught and logged."""
        # Arrange
        class FailingHandler(EventHandler):
            async def handle(self, event: DomainEvent):
                raise Exception("Handler failed!")

            def get_event_types(self):
                return ["WorkItemCreated"]

        bus = EventBus(max_retries=0)  # No retries
        handler = FailingHandler()
        bus.register_handler(handler)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)  # Should not raise

        # Assert
        stats = bus.get_statistics()
        assert stats["handler_errors"] > 0

    async def test_handler_retry_on_failure(self):
        """Test that handlers are retried on failure."""
        # Arrange
        class RetryHandler(EventHandler):
            def __init__(self):
                self.attempt_count = 0

            async def handle(self, event: DomainEvent):
                self.attempt_count += 1
                if self.attempt_count < 3:
                    raise Exception("Temporary failure")
                # Success on 3rd attempt

            def get_event_types(self):
                return ["WorkItemCreated"]

        bus = EventBus(max_retries=3, retry_delay_seconds=0.01)
        handler = RetryHandler()
        bus.register_handler(handler)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)

        # Assert
        assert handler.attempt_count == 3  # Succeeded on 3rd attempt

    async def test_synchronous_callback_works(self):
        """Test that synchronous callbacks work."""
        # Arrange
        bus = EventBus()
        received_events = []

        def sync_callback(event: DomainEvent):
            received_events.append(event)

        bus.subscribe("WorkItemCreated", sync_callback)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)

        # Assert
        assert len(received_events) == 1

    async def test_get_statistics(self):
        """Test getting event bus statistics."""
        # Arrange
        bus = EventBus()
        handler = _TestWorkItemCreatedHandler()
        bus.register_handler(handler)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)
        stats = bus.get_statistics()

        # Assert
        assert stats["events_published"] == 1
        assert stats["events_handled"] == 1
        assert stats["total_handlers"] >= 1

    async def test_reset_statistics(self):
        """Test resetting statistics."""
        # Arrange
        bus = EventBus()
        handler = _TestWorkItemCreatedHandler()
        bus.register_handler(handler)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        await bus.publish(event)

        # Act
        bus.reset_statistics()
        stats = bus.get_statistics()

        # Assert
        assert stats["events_published"] == 0
        assert stats["events_handled"] == 0

    async def test_event_handler_decorator(self):
        """Test @event_handler decorator."""
        # Arrange - handler was already decorated in class definition

        handler = _TestWorkItemCreatedHandler()

        # Act
        event_types = handler.get_event_types()

        # Assert
        assert event_types == ["WorkItemCreated"]

    async def test_no_handlers_registered_does_not_error(self):
        """Test that publishing with no handlers doesn't error."""
        # Arrange
        bus = EventBus()

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)  # Should not raise

        # Assert
        stats = bus.get_statistics()
        assert stats["events_published"] == 1
        assert stats["events_handled"] == 0

    async def test_cancelled_error_propagates(self, caplog):
        """Test that asyncio.CancelledError is always propagated from publish()."""
        # Arrange
        class MockRedisClient:
            async def xadd(self, *args, **kwargs):
                # Simulate a cancelled operation
                raise asyncio.CancelledError()

        bus = EventBus(redis_client=MockRedisClient())

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act & Assert
        caplog.set_level(logging.INFO)
        with pytest.raises(asyncio.CancelledError):
            await bus.publish(event)

        # Verify cancellation was logged
        assert "cancelled" in caplog.text.lower()

    async def test_connection_error_propagates_from_get_handlers(self, caplog):
        """Test that ConnectionError during handler lookup raises EventBusError with retry hint."""
        # Arrange
        bus = EventBus()

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Monkey-patch _get_handlers_for_event to raise ConnectionError
        def failing_get_handlers(evt):
            raise ConnectionError("Handler lookup failed")

        bus._get_handlers_for_event = failing_get_handlers

        # Act & Assert
        caplog.set_level(logging.ERROR)
        with pytest.raises(EventBusError) as exc_info:
            await bus.publish(event)

        # Verify error message includes retry hint
        assert "transient" in str(exc_info.value).lower()
        assert "retry" in str(exc_info.value).lower()

        # Verify error was logged with exc_info=True
        assert "Connection error" in caplog.text
        assert "Traceback" in caplog.text

    async def test_timeout_error_propagates_from_handler_dispatch(self, caplog):
        """Test that TimeoutError during handler dispatch raises EventBusError with retry hint."""
        # Arrange
        bus = EventBus()

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Monkey-patch _get_callbacks_for_event to raise TimeoutError
        def failing_get_callbacks(evt):
            raise TimeoutError("Callback lookup timed out")

        bus._get_callbacks_for_event = failing_get_callbacks

        # Act & Assert
        caplog.set_level(logging.ERROR)
        with pytest.raises(EventBusError) as exc_info:
            await bus.publish(event)

        # Verify error message includes retry hint
        assert "transient" in str(exc_info.value).lower()
        assert "retry" in str(exc_info.value).lower()

        # Verify error was logged with exc_info=True
        assert "Connection error" in caplog.text
        assert "Traceback" in caplog.text

    async def test_value_error_propagates_from_validation(self, caplog):
        """Test that ValueError during publish() is caught and re-raised as EventBusError with validation hint."""
        # Arrange
        bus = EventBus()

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Monkey-patch _get_handlers_for_event to raise ValueError
        def failing_validation(evt):
            raise ValueError("Invalid event field: 'title' cannot be empty")

        bus._get_handlers_for_event = failing_validation

        # Act & Assert
        caplog.set_level(logging.ERROR)
        with pytest.raises(EventBusError) as exc_info:
            await bus.publish(event)

        # Verify error message includes validation hint
        assert "invalid" in str(exc_info.value).lower()
        assert "check event structure" in str(exc_info.value).lower()

        # Verify error was logged with exc_info=True
        assert "Validation error" in caplog.text
        assert "Traceback" in caplog.text

    async def test_unexpected_exception_propagates_from_dispatch(self, caplog):
        """Test that unexpected exceptions from dispatch are caught and re-raised as EventBusError."""
        # Arrange
        bus = EventBus()

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Monkey-patch _get_handlers_for_event to raise RuntimeError
        def failing_dispatch(evt):
            raise RuntimeError("Something unexpected happened")

        bus._get_handlers_for_event = failing_dispatch

        # Act & Assert
        caplog.set_level(logging.CRITICAL)
        with pytest.raises(EventBusError) as exc_info:
            await bus.publish(event)

        # Verify generic error message
        assert "Unexpected error" in str(exc_info.value)

        # Verify error was logged as critical with exc_info=True
        assert "Unexpected error" in caplog.text
        assert "Traceback" in caplog.text

    async def test_all_exception_logs_have_exc_info(self, caplog):
        """Test that all error logs include exc_info=True for debugging."""
        # Arrange
        class FailingRedisClient:
            async def xadd(self, *args, **kwargs):
                raise ValueError("Test error during persistence")

        bus = EventBus(redis_client=FailingRedisClient())

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        caplog.set_level(logging.ERROR)
        try:
            await bus.publish(event)
        except EventBusError:
            pass

        # Assert - traceback should be in logs (evidence of exc_info=True)
        assert "ValueError" in caplog.text
        assert "Traceback" in caplog.text
