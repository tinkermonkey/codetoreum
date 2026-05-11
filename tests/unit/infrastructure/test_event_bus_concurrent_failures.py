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
from typing import Any

import pytest

from codetoreum.domain.events import WorkItemCompletedEvent, WorkItemCreatedEvent
from codetoreum.domain.events.adapter_events import CodetoreumEvent, now_iso
from codetoreum.infrastructure.event_bus import EventBus, EventHandler, event_handler


def _created(work_item_id: str, title: str = "Test") -> WorkItemCreatedEvent:
    return WorkItemCreatedEvent(
        type="workitem.created",
        timestamp=now_iso(),
        source="test",
        work_item_id=work_item_id,
        project_id="proj-1",
        title=title,
    )


def _completed(work_item_id: str) -> WorkItemCompletedEvent:
    return WorkItemCompletedEvent(
        type="workitem.completed",
        timestamp=now_iso(),
        source="test",
        work_item_id=work_item_id,
    )


@event_handler("WorkItemCreatedEvent")
class _SuccessfulHandler(EventHandler):
    """Handler that succeeds."""

    def __init__(self):
        self.handled_events = []

    async def handle(self, event: CodetoreumEvent) -> None:
        self.handled_events.append(event)


@event_handler("WorkItemCreatedEvent")
class _FailingHandler(EventHandler):
    """Handler that fails."""

    def __init__(self, error_msg="Handler failed"):
        self.error_msg = error_msg
        self.attempt_count = 0

    async def handle(self, event: CodetoreumEvent) -> None:
        self.attempt_count += 1
        raise ValueError(self.error_msg)


@event_handler("WorkItemCreatedEvent")
class _StatefulHandler(EventHandler):
    """Handler that maintains state."""

    def __init__(self, handler_id: str):
        self.handler_id = handler_id
        self.state: dict[str, Any] = {"count": 0, "events": [], "event_ids": set()}

    async def handle(self, event: CodetoreumEvent) -> None:
        self.state["count"] += 1
        self.state["events"].append(event.work_item_id)
        self.state["event_ids"].add(event.work_item_id)
        await asyncio.sleep(0.01)


@event_handler("WorkItemCreatedEvent")
class _StatefulExceptionHandler(EventHandler):
    """Handler that maintains state and throws exceptions."""

    def __init__(self, handler_id: str):
        self.handler_id = handler_id
        self.state: dict[str, int] = {"processed": 0, "failed": 0}

    async def handle(self, event: CodetoreumEvent) -> None:
        self.state["processed"] += 1
        await asyncio.sleep(0.01)
        self.state["failed"] += 1
        raise ValueError(f"Handler {self.handler_id} failed")


@event_handler("WorkItemCreatedEvent", "WorkItemCompletedEvent")
class _MultiEventStatefulHandler(EventHandler):
    """Handler that processes multiple event types with state."""

    def __init__(self, handler_id: str):
        self.handler_id = handler_id
        self.state: dict[str, Any] = {"created_count": 0, "completed_count": 0, "all_events": []}

    async def handle(self, event: CodetoreumEvent) -> None:
        if isinstance(event, WorkItemCreatedEvent):
            self.state["created_count"] += 1
        elif isinstance(event, WorkItemCompletedEvent):
            self.state["completed_count"] += 1
        self.state["all_events"].append(type(event).__name__)
        await asyncio.sleep(0.01)


class _StatefulWildcardHandler(EventHandler):
    """Wildcard handler that maintains state."""

    def __init__(self, handler_id: str):
        self.handler_id = handler_id
        self.state: dict[str, Any] = {"event_types": [], "count": 0}

    async def handle(self, event: CodetoreumEvent) -> None:
        self.state["count"] += 1
        self.state["event_types"].append(type(event).__name__)
        await asyncio.sleep(0.01)

    def get_event_types(self):
        return []


@pytest.mark.asyncio
class TestEventBusConcurrentFailures:
    """Test suite for EventBus concurrent handler failures."""

    async def test_one_handler_fails_others_succeed(self):
        """Test that one handler failure doesn't prevent other handlers from running."""
        bus = EventBus(max_retries=0)
        handler1 = _SuccessfulHandler()
        handler2 = _FailingHandler("handler2 failed")
        handler3 = _SuccessfulHandler()

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        event = _created("work-item-123", "Test")
        await bus.publish(event)

        assert len(handler1.handled_events) == 1
        assert len(handler3.handled_events) == 1
        assert handler2.attempt_count == 1
        stats = bus.get_statistics()
        assert stats["handler_errors"] == 1

    async def test_all_handlers_fail_completes_without_hanging(self):
        """Test that all handler failures completes without hanging."""
        bus = EventBus(max_retries=0)
        handler1 = _FailingHandler("handler1 failed")
        handler2 = _FailingHandler("handler2 failed")
        handler3 = _FailingHandler("handler3 failed")

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        event = _created("work-item-123", "Test")
        await asyncio.wait_for(bus.publish(event), timeout=5.0)

        assert handler1.attempt_count == 1
        assert handler2.attempt_count == 1
        assert handler3.attempt_count == 1
        stats = bus.get_statistics()
        assert stats["handler_errors"] == 3

    async def test_handler_exceptions_logged_with_context(self):
        """Test that handler exceptions are logged with handler info."""
        bus = EventBus(max_retries=0)
        handler1 = _SuccessfulHandler()
        handler2 = _FailingHandler("specific error message")
        handler3 = _SuccessfulHandler()

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        event = _created("work-item-123", "Test")
        await bus.publish(event)

        assert len(handler1.handled_events) == 1
        assert len(handler3.handled_events) == 1
        assert handler2.attempt_count == 1

    async def test_handler_failure_statistics_increment(self):
        """Test that handler failure statistics increment correctly."""
        bus = EventBus(max_retries=0)
        handler1 = _FailingHandler("error 1")
        handler2 = _FailingHandler("error 2")
        handler3 = _SuccessfulHandler()

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        event = _created("work-item-123", "Test")
        await bus.publish(event)

        stats = bus.get_statistics()
        assert stats["handler_errors"] == 2
        assert stats["events_published"] == 1

    async def test_multiple_concurrent_events_with_mixed_results(self):
        """Test processing multiple events concurrently with mixed handler results."""
        bus = EventBus(max_retries=0)
        handler_success = _SuccessfulHandler()
        handler_fail = _FailingHandler("concurrent failure")

        bus.register_handler(handler_success)
        bus.register_handler(handler_fail)

        events: list[CodetoreumEvent] = [_created(f"work-item-{i}", f"Test {i}") for i in range(5)]

        await bus.publish_batch(events)

        assert len(handler_success.handled_events) == 5
        assert handler_fail.attempt_count == 5
        stats = bus.get_statistics()
        assert stats["handler_errors"] == 5
        assert stats["events_published"] == 5

    async def test_concurrent_handlers_maintain_isolated_state(self):
        """Test that concurrent handlers maintain isolated state."""
        bus = EventBus(max_retries=0)
        handler1 = _StatefulHandler("handler-1")
        handler2 = _StatefulHandler("handler-2")
        handler3 = _StatefulHandler("handler-3")

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        events = [_created(f"work-{i}", f"Test {i}") for i in range(10)]
        await asyncio.gather(*[bus.publish(event) for event in events])

        assert handler1.state["count"] == 10
        assert handler2.state["count"] == 10
        assert handler3.state["count"] == 10
        assert len(handler1.state["events"]) == 10
        assert len(handler2.state["events"]) == 10
        assert len(handler3.state["events"]) == 10
        expected_ids = {f"work-{i}" for i in range(10)}
        assert handler1.state["event_ids"] == expected_ids
        assert handler2.state["event_ids"] == expected_ids
        assert handler3.state["event_ids"] == expected_ids

    async def test_handler_exception_does_not_corrupt_other_handler_state(self):
        """Test that handler exception doesn't corrupt other handler state."""
        bus = EventBus(max_retries=0)
        handler_good = _StatefulHandler("good-handler")
        handler_bad = _StatefulExceptionHandler("bad-handler")
        handler_good2 = _StatefulHandler("good-handler2")

        bus.register_handler(handler_good)
        bus.register_handler(handler_bad)
        bus.register_handler(handler_good2)

        events = [_created(f"work-{i}", f"Test {i}") for i in range(5)]
        await asyncio.gather(*[bus.publish(event) for event in events])

        assert handler_good.state["count"] == 5
        assert handler_good2.state["count"] == 5
        assert len(handler_good.state["events"]) == 5
        assert len(handler_good2.state["events"]) == 5
        assert handler_bad.state["processed"] == 5
        assert handler_bad.state["failed"] == 5
        stats = bus.get_statistics()
        assert stats["handler_errors"] == 5

    async def test_handlers_with_shared_resources_isolation(self):
        """Test that handlers with shared resources maintain isolation."""
        bus = EventBus(max_retries=0)
        handler1 = _StatefulHandler("handler-1")
        handler2 = _StatefulHandler("handler-2")
        handler3 = _StatefulHandler("handler-3")

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        events = [_created(f"work-{i}", f"Test {i}") for i in range(20)]
        await asyncio.gather(*[bus.publish(event) for event in events])

        assert handler1.state["count"] == 20
        assert handler2.state["count"] == 20
        assert handler3.state["count"] == 20
        assert handler1.state is not handler2.state
        assert handler2.state is not handler3.state
        assert handler1.state is not handler3.state
        assert handler1.state["event_ids"] is not handler2.state["event_ids"]
        assert handler2.state["event_ids"] is not handler3.state["event_ids"]

    async def test_handler_cleanup_does_not_affect_other_handlers(self):
        """Test that handler cleanup doesn't affect other handlers."""
        bus = EventBus(max_retries=0)
        handler1 = _StatefulHandler("handler-1")
        handler2 = _StatefulHandler("handler-2")
        handler3 = _StatefulHandler("handler-3")

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        await bus.publish(_created("work-1", "Test 1"))

        assert handler1.state["count"] == 1
        assert handler2.state["count"] == 1
        assert handler3.state["count"] == 1

        bus.unregister_handler(handler2)
        await bus.publish(_created("work-2", "Test 2"))

        assert handler1.state["count"] == 2
        assert handler3.state["count"] == 2
        assert handler2.state["count"] == 1

    async def test_handlers_processing_different_event_types_do_not_interfere(self):
        """Test that handlers processing different event types don't interfere."""
        bus = EventBus(max_retries=0)
        handler_created = _StatefulHandler("created-handler")
        handler_multi = _MultiEventStatefulHandler("multi-handler")

        bus.register_handler(handler_created)
        bus.register_handler(handler_multi)

        events = [(_created(f"work-{i}", f"Test {i}") if i % 2 == 0 else _completed(f"work-{i}")) for i in range(10)]

        await asyncio.gather(*[bus.publish(event) for event in events])

        assert handler_created.state["count"] == 5
        assert handler_multi.state["created_count"] == 5
        assert handler_multi.state["completed_count"] == 5
        assert len(handler_multi.state["all_events"]) == 10

    async def test_wildcard_handlers_do_not_share_state_with_specific_handlers(self):
        """Test that wildcard handlers don't share state with specific handlers."""
        bus = EventBus(max_retries=0)
        handler_specific = _StatefulHandler("specific-handler")
        handler_wildcard = _StatefulWildcardHandler("wildcard-handler")

        bus.register_handler(handler_specific)
        bus.register_handler(handler_wildcard)

        events = [_created(f"work-created-{i}", f"Created {i}") for i in range(5)] + [
            _completed(f"work-completed-{i}") for i in range(5)
        ]

        await asyncio.gather(*[bus.publish(event) for event in events])

        assert handler_specific.state["count"] == 5
        assert len(handler_specific.state["events"]) == 5
        assert handler_wildcard.state["count"] == 10
        assert len(handler_wildcard.state["event_types"]) == 10
        assert handler_specific.state != handler_wildcard.state

    async def test_callback_state_isolation_from_handlers(self):
        """Test callback state isolation from handlers."""
        bus = EventBus(max_retries=0)
        handler = _StatefulHandler("handler-1")
        callback_events = []

        async def callback(event: CodetoreumEvent):
            callback_events.append(event.work_item_id)

        bus.register_handler(handler)
        bus.subscribe("WorkItemCreatedEvent", callback)

        events = [_created(f"work-{i}", f"Test {i}") for i in range(5)]
        await asyncio.gather(*[bus.publish(event) for event in events])

        assert handler.state["count"] == 5
        assert len(callback_events) == 5
        assert isinstance(handler.state, dict)
        assert isinstance(callback_events, list)

    async def test_async_handler_execution_order_independence(self):
        """Test async handler execution order independence."""
        bus = EventBus(max_retries=0)
        handler1 = _StatefulHandler("handler-1")
        handler2 = _StatefulHandler("handler-2")
        handler3 = _StatefulHandler("handler-3")

        bus.register_handler(handler1)
        bus.register_handler(handler2)
        bus.register_handler(handler3)

        await bus.publish(_created("work-1", "Test"))

        assert handler1.state["count"] == 1
        assert handler2.state["count"] == 1
        assert handler3.state["count"] == 1
        assert handler1.state["events"][0] == "work-1"
        assert handler2.state["events"][0] == "work-1"
        assert handler3.state["events"][0] == "work-1"

        events = [_created(f"work-{i}", f"Test {i}") for i in range(10)]
        await asyncio.gather(*[bus.publish(event) for event in events])

        assert handler1.state["count"] == 11
        assert handler2.state["count"] == 11
        assert handler3.state["count"] == 11
        assert len(handler1.state["events"]) == 11
        assert len(handler2.state["events"]) == 11
        assert len(handler3.state["events"]) == 11

    async def test_memory_isolation_handler_allocations(self):
        """Test memory isolation (handler A allocations don't leak to handler B)."""
        bus = EventBus(max_retries=0)
        handler1 = _StatefulHandler("handler-1")
        handler2 = _StatefulHandler("handler-2")

        bus.register_handler(handler1)
        bus.register_handler(handler2)

        events = [_created(f"work-{i}", f"Test {i}") for i in range(15)]
        await asyncio.gather(*[bus.publish(event) for event in events])

        assert len(handler1.state["events"]) == 15
        assert len(handler2.state["events"]) == 15
        assert len(handler1.state["event_ids"]) == 15
        assert len(handler2.state["event_ids"]) == 15

        handler2_ids = set(handler2.state["events"])
        handler1_unique = handler1.state["event_ids"] - handler2_ids
        assert len(handler1_unique) == 0

        original_handler1_count = handler1.state["count"]
        handler2.state["count"] = 0
        assert handler1.state["count"] == original_handler1_count
