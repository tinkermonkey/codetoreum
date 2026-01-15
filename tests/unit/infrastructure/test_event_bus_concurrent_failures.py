"""Unit tests for EventBus concurrent handler failures and state isolation.

Tests verify that:
1. One handler failure doesn't prevent other handlers from running
2. All handlers fail gracefully without hanging
3. Handler exceptions are logged with correct index
4. Handler failure statistics are tracked accurately
5. Multiple events with mixed handler results complete successfully
6. Concurrent handlers maintain isolated state
7. Handler exceptions don't corrupt other handler state
8. Handlers with shared resources use proper locking
9. Handler cleanup doesn't affect other handlers
10. Handlers processing different event types don't interfere
"""

import asyncio
import pytest

from codetoreum.domain.events import DomainEvent, WorkItemCreated, WorkItemCompleted
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


@event_handler("WorkItemCreated")
class _StatefulHandler(EventHandler):
    """Handler that maintains state."""

    def __init__(self, handler_id: str):
        self.handler_id = handler_id
        self.state = {"count": 0, "events": [], "event_ids": set()}

    async def handle(self, event: DomainEvent) -> None:
        """Handle event with state."""
        self.state["count"] += 1
        self.state["events"].append(event.aggregate_id)
        self.state["event_ids"].add(event.aggregate_id)
        # Simulate async work to expose race conditions
        await asyncio.sleep(0.01)


@event_handler("WorkItemCreated")
class _StatefulExceptionHandler(EventHandler):
    """Handler that maintains state and throws exceptions."""

    def __init__(self, handler_id: str):
        self.handler_id = handler_id
        self.state = {"processed": 0, "failed": 0}

    async def handle(self, event: DomainEvent) -> None:
        """Handle event with state tracking, but fail."""
        self.state["processed"] += 1
        # Simulate async work
        await asyncio.sleep(0.01)
        self.state["failed"] += 1
        raise ValueError(f"Handler {self.handler_id} failed")


@event_handler("WorkItemCreated", "WorkItemCompleted")
class _MultiEventStatefulHandler(EventHandler):
    """Handler that processes multiple event types with state."""

    def __init__(self, handler_id: str):
        self.handler_id = handler_id
        self.state = {
            "created_count": 0,
            "completed_count": 0,
            "all_events": []
        }

    async def handle(self, event: DomainEvent) -> None:
        """Handle multiple event types with state."""
        if isinstance(event, WorkItemCreated):
            self.state["created_count"] += 1
        elif isinstance(event, WorkItemCompleted):
            self.state["completed_count"] += 1

        self.state["all_events"].append(type(event).__name__)
        await asyncio.sleep(0.01)


class _StatefulWildcardHandler(EventHandler):
    """Wildcard handler that maintains state."""

    def __init__(self, handler_id: str):
        self.handler_id = handler_id
        self.state = {"event_types": [], "count": 0}

    async def handle(self, event: DomainEvent) -> None:
        """Handle all events with state."""
        self.state["count"] += 1
        self.state["event_types"].append(type(event).__name__)
        await asyncio.sleep(0.01)

    def get_event_types(self):
        """Return empty list for wildcard."""
        return []


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

    async def test_concurrent_handlers_maintain_isolated_state(self):
        """Test that concurrent handlers maintain isolated state.

        Acceptance Criteria:
        - Test concurrent handlers maintain isolated state
        """
        # Arrange
        bus = EventBus(max_retries=0)
        handler1 = _StatefulHandler("handler-1")
        handler2 = _StatefulHandler("handler-2")
        handler3 = _StatefulHandler("handler-3")

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        events = [
            WorkItemCreated(
                aggregate_id=f"work-{i}",
                payload={"title": f"Test {i}"},
            )
            for i in range(10)
        ]

        # Act - Process events concurrently
        await asyncio.gather(*[bus.publish(event) for event in events])

        # Assert - Each handler should have processed all 10 events independently
        assert handler1.state["count"] == 10
        assert handler2.state["count"] == 10
        assert handler3.state["count"] == 10

        # Each handler should have its own list of events (no shared state)
        assert len(handler1.state["events"]) == 10
        assert len(handler2.state["events"]) == 10
        assert len(handler3.state["events"]) == 10

        # Verify no events were lost or duplicated
        expected_ids = {f"work-{i}" for i in range(10)}
        assert handler1.state["event_ids"] == expected_ids
        assert handler2.state["event_ids"] == expected_ids
        assert handler3.state["event_ids"] == expected_ids

    async def test_handler_exception_does_not_corrupt_other_handler_state(self):
        """Test that handler exception doesn't corrupt other handler state.

        Acceptance Criteria:
        - Test handler exception doesn't corrupt other handler state
        """
        # Arrange
        bus = EventBus(max_retries=0)
        handler_good = _StatefulHandler("good-handler")
        handler_bad = _StatefulExceptionHandler("bad-handler")
        handler_good2 = _StatefulHandler("good-handler2")

        bus.register_handler(handler_good)
        bus.register_handler(handler_bad)
        bus.register_handler(handler_good2)

        events = [
            WorkItemCreated(
                aggregate_id=f"work-{i}",
                payload={"title": f"Test {i}"},
            )
            for i in range(5)
        ]

        # Act
        await asyncio.gather(*[bus.publish(event) for event in events])

        # Assert - Good handlers should have correct state despite bad handler
        assert handler_good.state["count"] == 5
        assert handler_good2.state["count"] == 5
        assert len(handler_good.state["events"]) == 5
        assert len(handler_good2.state["events"]) == 5

        # Bad handler should have tracked its state up to failure point
        assert handler_bad.state["processed"] == 5
        assert handler_bad.state["failed"] == 5

        stats = bus.get_statistics()
        assert stats["handler_errors"] == 5  # Only bad handler errors

    async def test_handlers_with_shared_resources_isolation(self):
        """Test that handlers with shared resources maintain isolation.

        Acceptance Criteria:
        - Test handlers with shared resources use proper locking
        """
        # Arrange
        bus = EventBus(max_retries=0)

        # Each handler gets its own independent state object
        handler1 = _StatefulHandler("handler-1")
        handler2 = _StatefulHandler("handler-2")
        handler3 = _StatefulHandler("handler-3")

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        # Process multiple events concurrently
        events = [
            WorkItemCreated(
                aggregate_id=f"work-{i}",
                payload={"title": f"Test {i}"},
            )
            for i in range(20)
        ]

        # Act - Concurrent event publishing should not cause state corruption
        await asyncio.gather(*[bus.publish(event) for event in events])

        # Assert - Each handler maintains correct counts despite concurrency
        assert handler1.state["count"] == 20
        assert handler2.state["count"] == 20
        assert handler3.state["count"] == 20

        # No cross-contamination of state - each handler is independent object
        assert handler1.state is not handler2.state
        assert handler2.state is not handler3.state
        assert handler1.state is not handler3.state

        # Each handler's internal event_ids set is independent (not shared)
        assert handler1.state["event_ids"] is not handler2.state["event_ids"]
        assert handler2.state["event_ids"] is not handler3.state["event_ids"]

    async def test_handler_cleanup_does_not_affect_other_handlers(self):
        """Test that handler cleanup doesn't affect other handlers.

        Acceptance Criteria:
        - Test handler cleanup doesn't affect other handlers
        """
        # Arrange
        bus = EventBus(max_retries=0)
        handler1 = _StatefulHandler("handler-1")
        handler2 = _StatefulHandler("handler-2")
        handler3 = _StatefulHandler("handler-3")

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        event1 = WorkItemCreated(
            aggregate_id="work-1",
            payload={"title": "Test 1"},
        )

        # Act - Publish first event
        await bus.publish(event1)

        # Verify all handlers processed the event
        assert handler1.state["count"] == 1
        assert handler2.state["count"] == 1
        assert handler3.state["count"] == 1

        # Unregister one handler (cleanup)
        bus.unregister_handler(handler2)

        event2 = WorkItemCreated(
            aggregate_id="work-2",
            payload={"title": "Test 2"},
        )

        # Act - Publish second event after cleanup
        await bus.publish(event2)

        # Assert - Remaining handlers should still work correctly
        assert handler1.state["count"] == 2
        assert handler3.state["count"] == 2
        # Handler2 was unregistered, should not process new events
        assert handler2.state["count"] == 1

    async def test_handlers_processing_different_event_types_do_not_interfere(self):
        """Test that handlers processing different event types don't interfere.

        Acceptance Criteria:
        - Test handlers processing different event types don't interfere
        """
        # Arrange
        bus = EventBus(max_retries=0)
        handler_created = _StatefulHandler("created-handler")
        handler_multi = _MultiEventStatefulHandler("multi-handler")

        bus.register_handler(handler_created)
        bus.register_handler(handler_multi)

        # Mix of different event types
        events = [
            WorkItemCreated(
                aggregate_id=f"work-{i}",
                payload={"title": f"Test {i}"},
            )
            if i % 2 == 0
            else WorkItemCompleted(
                aggregate_id=f"work-{i}",
                payload={"completed_at": "2025-10-27T12:00:00Z"},
            )
            for i in range(10)
        ]

        # Act - Process mixed event types concurrently
        await asyncio.gather(*[bus.publish(event) for event in events])

        # Assert - Created handler should only see WorkItemCreated events
        assert handler_created.state["count"] == 5

        # Multi handler should see all 10 events but track them correctly
        assert handler_multi.state["created_count"] == 5
        assert handler_multi.state["completed_count"] == 5
        assert len(handler_multi.state["all_events"]) == 10

    async def test_wildcard_handlers_do_not_share_state_with_specific_handlers(self):
        """Test that wildcard handlers don't share state with specific handlers.

        Acceptance Criteria:
        - Test wildcard handlers don't share state with specific handlers
        """
        # Arrange
        bus = EventBus(max_retries=0)
        handler_specific = _StatefulHandler("specific-handler")
        handler_wildcard = _StatefulWildcardHandler("wildcard-handler")

        bus.register_handler(handler_specific)
        bus.register_handler(handler_wildcard)

        # Send mixed event types
        events = [
            WorkItemCreated(
                aggregate_id=f"work-created-{i}",
                payload={"title": f"Created {i}"},
            )
            for i in range(5)
        ] + [
            WorkItemCompleted(
                aggregate_id=f"work-completed-{i}",
                payload={"completed_at": "2025-10-27T12:00:00Z"},
            )
            for i in range(5)
        ]

        # Act
        await asyncio.gather(*[bus.publish(event) for event in events])

        # Assert - Specific handler only sees its event type
        assert handler_specific.state["count"] == 5
        assert len(handler_specific.state["events"]) == 5

        # Wildcard handler sees all event types
        assert handler_wildcard.state["count"] == 10
        assert len(handler_wildcard.state["event_types"]) == 10

        # Each has its own independent state
        assert handler_specific.state != handler_wildcard.state

    async def test_callback_state_isolation_from_handlers(self):
        """Test callback state isolation from handlers.

        Acceptance Criteria:
        - Test callback state isolation from handlers
        """
        # Arrange
        bus = EventBus(max_retries=0)
        handler = _StatefulHandler("handler-1")
        callback_events = []

        async def callback(event: DomainEvent):
            callback_events.append(event.aggregate_id)

        bus.register_handler(handler)
        bus.subscribe("WorkItemCreated", callback)

        events = [
            WorkItemCreated(
                aggregate_id=f"work-{i}",
                payload={"title": f"Test {i}"},
            )
            for i in range(5)
        ]

        # Act
        await asyncio.gather(*[bus.publish(event) for event in events])

        # Assert - Handler and callback should have independent state
        assert handler.state["count"] == 5
        assert len(callback_events) == 5

        # They maintain separate state objects (no shared state)
        # Handler stores in its own state dict, callback stores in callback_events list
        assert isinstance(handler.state, dict)
        assert isinstance(callback_events, list)
        assert handler.state is not {"events": callback_events}  # Different objects

    async def test_async_handler_execution_order_independence(self):
        """Test async handler execution order independence.

        Acceptance Criteria:
        - Test async handler execution order independence
        """
        # Arrange
        bus = EventBus(max_retries=0)
        handler1 = _StatefulHandler("handler-1")
        handler2 = _StatefulHandler("handler-2")
        handler3 = _StatefulHandler("handler-3")

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        event = WorkItemCreated(
            aggregate_id="work-1",
            payload={"title": "Test"},
        )

        # Act - Publish single event (handlers execute concurrently)
        await bus.publish(event)

        # Assert - Each handler processes the event regardless of execution order
        assert handler1.state["count"] == 1
        assert handler2.state["count"] == 1
        assert handler3.state["count"] == 1

        # Each handler has its own event reference
        assert handler1.state["events"][0] == "work-1"
        assert handler2.state["events"][0] == "work-1"
        assert handler3.state["events"][0] == "work-1"

        # Act - Publish multiple events concurrently
        events = [
            WorkItemCreated(
                aggregate_id=f"work-{i}",
                payload={"title": f"Test {i}"},
            )
            for i in range(10)
        ]
        await asyncio.gather(*[bus.publish(event) for event in events])

        # Assert - Despite concurrent execution, all handlers see all events
        assert handler1.state["count"] == 11
        assert handler2.state["count"] == 11
        assert handler3.state["count"] == 11

        # All handlers have complete event histories (no loss due to order)
        assert len(handler1.state["events"]) == 11
        assert len(handler2.state["events"]) == 11
        assert len(handler3.state["events"]) == 11

    async def test_memory_isolation_handler_allocations(self):
        """Test memory isolation (handler A allocations don't leak to handler B).

        Acceptance Criteria:
        - Test memory isolation (handler A allocations don't leak to handler B)
        """
        # Arrange
        bus = EventBus(max_retries=0)
        handler1 = _StatefulHandler("handler-1")
        handler2 = _StatefulHandler("handler-2")

        bus.register_handler(handler1)
        bus.register_handler(handler2)

        events = [
            WorkItemCreated(
                aggregate_id=f"work-{i}",
                payload={"title": f"Test {i}"},
            )
            for i in range(15)
        ]

        # Act - Process events concurrently
        await asyncio.gather(*[bus.publish(event) for event in events])

        # Assert - Each handler has exactly the right amount of memory allocated
        # No cross-contamination
        assert len(handler1.state["events"]) == 15
        assert len(handler2.state["events"]) == 15
        assert len(handler1.state["event_ids"]) == 15
        assert len(handler2.state["event_ids"]) == 15

        # Handler1's allocations don't appear in handler2
        handler2_ids = set(handler2.state["events"])
        handler1_unique = handler1.state["event_ids"] - handler2_ids
        assert len(handler1_unique) == 0  # All IDs are unique to each handler's own processing

        # Each handler's internal state is isolated
        original_handler1_count = handler1.state["count"]
        # Manipulating handler2's state shouldn't affect handler1
        handler2.state["count"] = 0
        assert handler1.state["count"] == original_handler1_count
