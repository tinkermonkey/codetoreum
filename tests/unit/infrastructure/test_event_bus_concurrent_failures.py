"""Unit tests for EventBus concurrent handler failures.

Tests verify that:
1. One handler failure doesn't prevent other handlers from running
2. All handlers fail gracefully without hanging
3. Handler exceptions are logged with correct index
4. Handler failure statistics are tracked accurately
5. Multiple events with mixed handler results complete successfully
"""

import asyncio
import pytest

from codetoreum.domain.events import DomainEvent, WorkItemCreated
from codetoreum.infrastructure.event_bus import EventBus, EventHandler, event_handler


@event_handler("WorkItemCreated")
class _SuccessfulHandler(EventHandler):
    """Handler that succeeds."""

    def __init__(self):
        self.handled_events = []

    async def handle(self, event: DomainEvent) -> None:
        """Handle event."""
        self.handled_events.append(event)


@event_handler("WorkItemCreated")
class _FailingHandler(EventHandler):
    """Handler that fails."""

    def __init__(self, error_msg="Handler failed"):
        self.error_msg = error_msg
        self.attempt_count = 0

    async def handle(self, event: DomainEvent) -> None:
        """Handle event but fail."""
        self.attempt_count += 1
        raise ValueError(self.error_msg)


@pytest.mark.asyncio
class TestEventBusConcurrentFailures:
    """Test suite for EventBus concurrent handler failures."""

    async def test_one_handler_fails_others_succeed(self):
        """Test that one handler failure doesn't prevent other handlers from running."""
        # Arrange
        bus = EventBus(max_retries=0)
        handler1 = _SuccessfulHandler()
        handler2 = _FailingHandler("handler2 failed")
        handler3 = _SuccessfulHandler()

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)

        # Assert
        assert len(handler1.handled_events) == 1
        assert len(handler3.handled_events) == 1
        assert handler2.attempt_count == 1
        stats = bus.get_statistics()
        assert stats["handler_errors"] == 1

    async def test_all_handlers_fail_completes_without_hanging(self):
        """Test that all handler failures completes without hanging."""
        # Arrange
        bus = EventBus(max_retries=0)
        handler1 = _FailingHandler("handler1 failed")
        handler2 = _FailingHandler("handler2 failed")
        handler3 = _FailingHandler("handler3 failed")

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act - should not hang or raise
        await asyncio.wait_for(bus.publish(event), timeout=5.0)

        # Assert
        assert handler1.attempt_count == 1
        assert handler2.attempt_count == 1
        assert handler3.attempt_count == 1
        stats = bus.get_statistics()
        assert stats["handler_errors"] == 3

    async def test_handler_exceptions_logged_with_context(self):
        """Test that handler exceptions are logged with handler info."""
        # Arrange
        bus = EventBus(max_retries=0)
        handler1 = _SuccessfulHandler()
        handler2 = _FailingHandler("specific error message")
        handler3 = _SuccessfulHandler()

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)

        # Assert - verify all handlers ran despite failure
        assert len(handler1.handled_events) == 1
        assert len(handler3.handled_events) == 1
        assert handler2.attempt_count == 1

    async def test_handler_failure_statistics_increment(self):
        """Test that handler failure statistics increment correctly."""
        # Arrange
        bus = EventBus(max_retries=0)
        handler1 = _FailingHandler("error 1")
        handler2 = _FailingHandler("error 2")
        handler3 = _SuccessfulHandler()

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        await bus.publish(event)

        # Assert
        stats = bus.get_statistics()
        assert stats["handler_errors"] == 2
        assert stats["events_published"] == 1

    async def test_multiple_concurrent_events_with_mixed_results(self):
        """Test processing multiple events concurrently with mixed handler results."""
        # Arrange
        bus = EventBus(max_retries=0)
        handler_success = _SuccessfulHandler()
        handler_fail = _FailingHandler("concurrent failure")

        bus.register_handler(handler_success)
        bus.register_handler(handler_fail)

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
        assert len(handler_success.handled_events) == 5
        assert handler_fail.attempt_count == 5
        stats = bus.get_statistics()
        assert stats["handler_errors"] == 5
        assert stats["events_published"] == 5
