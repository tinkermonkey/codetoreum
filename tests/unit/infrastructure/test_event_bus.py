"""Unit tests for EventBus."""

import asyncio
import logging

import pytest

from codetoreum.domain.events import WorkItemCompletedEvent, WorkItemCreatedEvent
from codetoreum.domain.events.adapter_events import CodetoreumEvent, now_iso
from codetoreum.infrastructure.event_bus import (
    EventBus,
    EventHandler,
    event_handler,
)


def _make_created_event(work_item_id: str = "work-item-123") -> WorkItemCreatedEvent:
    return WorkItemCreatedEvent(
        type="workitem.created",
        timestamp=now_iso(),
        source="test",
        work_item_id=work_item_id,
        project_id="proj-1",
        title="Test",
    )


def _make_completed_event(work_item_id: str = "work-item-123") -> WorkItemCompletedEvent:
    return WorkItemCompletedEvent(
        type="workitem.completed",
        timestamp=now_iso(),
        source="test",
        work_item_id=work_item_id,
    )


@event_handler("WorkItemCreatedEvent")
class _TestWorkItemCreatedHandler(EventHandler):
    """Test handler for WorkItemCreatedEvent events."""

    def __init__(self):
        self.handled_events = []

    async def handle(self, event: CodetoreumEvent) -> None:
        """Handle event."""
        self.handled_events.append(event)


@event_handler("WorkItemCreatedEvent", "WorkItemCompletedEvent")
class _TestMultiEventHandler(EventHandler):
    """Test handler for multiple event types."""

    def __init__(self):
        self.handled_events = []

    async def handle(self, event: CodetoreumEvent) -> None:
        """Handle event."""
        self.handled_events.append(event)


class _TestWildcardHandler(EventHandler):
    """Test handler that receives all events."""

    def __init__(self):
        self.handled_events = []

    async def handle(self, event: CodetoreumEvent) -> None:
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
        bus = EventBus()
        handler = _TestWorkItemCreatedHandler()
        bus.register_handler(handler)

        event = _make_created_event()

        await bus.publish(event)

        assert len(handler.handled_events) == 1
        assert handler.handled_events[0] == event

    async def test_multiple_handlers_receive_same_event(self):
        """Test that multiple handlers receive the same event."""
        bus = EventBus()
        handler1 = _TestWorkItemCreatedHandler()
        handler2 = _TestWorkItemCreatedHandler()

        bus.register_handler(handler1)
        bus.register_handler(handler2)

        event = _make_created_event()

        await bus.publish(event)

        assert len(handler1.handled_events) == 1
        assert len(handler2.handled_events) == 1
        assert handler1.handled_events[0] == event
        assert handler2.handled_events[0] == event

    async def test_multi_event_handler_receives_multiple_types(self):
        """Test handler registered for multiple event types."""
        bus = EventBus()
        handler = _TestMultiEventHandler()
        bus.register_handler(handler)

        event1 = _make_created_event()
        event2 = _make_completed_event()

        await bus.publish(event1)
        await bus.publish(event2)

        assert len(handler.handled_events) == 2
        assert handler.handled_events[0] == event1
        assert handler.handled_events[1] == event2

    async def test_wildcard_handler_receives_all_events(self):
        """Test wildcard handler receives all event types."""
        bus = EventBus()
        handler = _TestWildcardHandler()
        bus.register_handler(handler)

        event1 = _make_created_event()
        event2 = _make_completed_event()

        await bus.publish(event1)
        await bus.publish(event2)

        assert len(handler.handled_events) == 2
        assert handler.handled_events[0] == event1
        assert handler.handled_events[1] == event2

    async def test_subscribe_with_callback(self):
        """Test subscribing with callback function."""
        bus = EventBus()
        received_events = []

        async def callback(event: CodetoreumEvent):
            received_events.append(event)

        bus.subscribe("WorkItemCreatedEvent", callback)

        event = _make_created_event()

        await bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0] == event

    async def test_wildcard_callback_subscription(self):
        """Test subscribing to all events with callback."""
        bus = EventBus()
        received_events = []

        async def callback(event: CodetoreumEvent):
            received_events.append(event)

        bus.subscribe(None, callback)  # None = wildcard

        event1 = _make_created_event()
        event2 = _make_completed_event()

        await bus.publish(event1)
        await bus.publish(event2)

        assert len(received_events) == 2

    async def test_unregister_handler(self):
        """Test unregistering a handler."""
        bus = EventBus()
        handler = _TestWorkItemCreatedHandler()
        bus.register_handler(handler)

        event = _make_created_event()

        await bus.publish(event)
        assert len(handler.handled_events) == 1

        bus.unregister_handler(handler)
        await bus.publish(event)

        assert len(handler.handled_events) == 1  # No new events

    async def test_unsubscribe_callback(self):
        """Test unsubscribing a callback."""
        bus = EventBus()
        received_events = []

        async def callback(event: CodetoreumEvent):
            received_events.append(event)

        bus.subscribe("WorkItemCreatedEvent", callback)

        event = _make_created_event()

        await bus.publish(event)
        assert len(received_events) == 1

        bus.unsubscribe("WorkItemCreatedEvent", callback)
        await bus.publish(event)

        assert len(received_events) == 1  # No new events

    async def test_publish_batch(self):
        """Test publishing multiple events."""
        bus = EventBus()
        handler = _TestWorkItemCreatedHandler()
        bus.register_handler(handler)

        events: list[CodetoreumEvent] = [_make_created_event(f"work-item-{i}") for i in range(5)]

        await bus.publish_batch(events)

        assert len(handler.handled_events) == 5

    async def test_handler_error_is_logged_but_not_raised(self):
        """Test that handler errors are caught and logged."""

        class FailingHandler(EventHandler):
            async def handle(self, event: CodetoreumEvent):
                raise Exception("Handler failed!")

            def get_event_types(self):
                return ["WorkItemCreatedEvent"]

        bus = EventBus(max_retries=0)  # No retries
        handler = FailingHandler()
        bus.register_handler(handler)

        event = _make_created_event()

        await bus.publish(event)  # Should not raise

        stats = bus.get_statistics()
        assert stats["handler_errors"] > 0

    async def test_handler_retry_on_failure(self):
        """Test that handlers are retried on failure."""

        class RetryHandler(EventHandler):
            def __init__(self):
                self.attempt_count = 0

            async def handle(self, event: CodetoreumEvent):
                self.attempt_count += 1
                if self.attempt_count < 3:
                    raise Exception("Temporary failure")
                # Success on 3rd attempt

            def get_event_types(self):
                return ["WorkItemCreatedEvent"]

        bus = EventBus(max_retries=3, retry_delay_seconds=0.01)
        handler = RetryHandler()
        bus.register_handler(handler)

        event = _make_created_event()

        await bus.publish(event)

        assert handler.attempt_count == 3  # Succeeded on 3rd attempt

    async def test_synchronous_callback_works(self):
        """Test that synchronous callbacks work."""
        bus = EventBus()
        received_events = []

        def sync_callback(event: CodetoreumEvent):
            received_events.append(event)

        bus.subscribe("WorkItemCreatedEvent", sync_callback)

        event = _make_created_event()

        await bus.publish(event)

        assert len(received_events) == 1

    async def test_get_statistics(self):
        """Test getting event bus statistics."""
        bus = EventBus()
        handler = _TestWorkItemCreatedHandler()
        bus.register_handler(handler)

        event = _make_created_event()

        await bus.publish(event)
        stats = bus.get_statistics()

        assert stats["events_published"] == 1
        assert stats["events_handled"] == 1
        assert stats["total_handlers"] >= 1

    async def test_reset_statistics(self):
        """Test resetting statistics."""
        bus = EventBus()
        handler = _TestWorkItemCreatedHandler()
        bus.register_handler(handler)

        event = _make_created_event()

        await bus.publish(event)

        bus.reset_statistics()
        stats = bus.get_statistics()

        assert stats["events_published"] == 0
        assert stats["events_handled"] == 0

    async def test_event_handler_decorator(self):
        """Test @event_handler decorator."""
        handler = _TestWorkItemCreatedHandler()

        event_types = handler.get_event_types()

        assert event_types == ["WorkItemCreatedEvent"]

    async def test_no_handlers_registered_does_not_error(self):
        """Test that publishing with no handlers doesn't error."""
        bus = EventBus()

        event = _make_created_event()

        await bus.publish(event)  # Should not raise

        stats = bus.get_statistics()
        assert stats["events_published"] == 1
        assert stats["events_handled"] == 0

    async def test_cancelled_error_propagates(self, caplog):
        """Test that asyncio.CancelledError is always propagated from publish()."""

        class MockRedisClient:
            async def xadd(self, *args, **kwargs):
                raise asyncio.CancelledError()

        bus = EventBus(redis_client=MockRedisClient())

        event = _make_created_event()

        caplog.set_level(logging.INFO)
        with pytest.raises(asyncio.CancelledError):
            await bus.publish(event)

        assert "cancelled" in caplog.text.lower()
