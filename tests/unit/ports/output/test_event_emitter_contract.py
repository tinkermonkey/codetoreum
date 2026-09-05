"""Contract tests for IEventEmitter interface.

These abstract tests verify that all IEventEmitter implementations
follow the contract correctly.
"""

from abc import ABC, abstractmethod

import pytest

from codetoreum.domain.events import CodetoreumEvent, now_iso
from codetoreum.ports.output.event_emitter import IEventEmitter


class TestEventEmitterContract(ABC):
    """Abstract contract tests for IEventEmitter implementations.

    Subclasses must implement create_emitter() to provide a concrete
    IEventEmitter implementation to test.
    """

    @abstractmethod
    def create_emitter(self) -> IEventEmitter:
        """Create and return an IEventEmitter instance for testing."""

    def test_on_registers_handler(self):
        """Handler should be called when event is emitted."""
        emitter = self.create_emitter()
        events: list[CodetoreumEvent] = []

        def handler(event: CodetoreumEvent) -> None:
            events.append(event)

        emitter.on("test.event", handler)

        # Create and emit test event
        event = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )
        emitter.emit(event)

        assert len(events) == 1
        assert events[0] == event

    def test_off_unregisters_handler(self):
        """Handler should not be called after unsubscribe."""
        emitter = self.create_emitter()
        events: list[CodetoreumEvent] = []

        def handler(event: CodetoreumEvent) -> None:
            events.append(event)

        emitter.on("test.event", handler)
        emitter.off("test.event", handler)

        event = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )
        emitter.emit(event)

        assert len(events) == 0

    def test_multiple_handlers_all_called(self):
        """All registered handlers should be called for an event."""
        emitter = self.create_emitter()
        events1: list[CodetoreumEvent] = []
        events2: list[CodetoreumEvent] = []

        def handler1(event: CodetoreumEvent) -> None:
            events1.append(event)

        def handler2(event: CodetoreumEvent) -> None:
            events2.append(event)

        emitter.on("test.event", handler1)
        emitter.on("test.event", handler2)

        event = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )
        emitter.emit(event)

        assert len(events1) == 1
        assert len(events2) == 1
        assert events1[0] == event
        assert events2[0] == event

    def test_once_calls_handler_once(self):
        """Handler registered with once() should only be called once."""
        emitter = self.create_emitter()
        events: list[CodetoreumEvent] = []

        def handler(event: CodetoreumEvent) -> None:
            events.append(event)

        emitter.once("test.event", handler)

        event1 = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )
        emitter.emit(event1)

        event2 = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )
        emitter.emit(event2)

        # Handler should only have been called once
        assert len(events) == 1
        assert events[0] == event1

    def test_different_event_types_separate_handlers(self):
        """Handlers for different event types should not interfere."""
        emitter = self.create_emitter()
        events1: list[CodetoreumEvent] = []
        events2: list[CodetoreumEvent] = []

        def handler1(event: CodetoreumEvent) -> None:
            events1.append(event)

        def handler2(event: CodetoreumEvent) -> None:
            events2.append(event)

        emitter.on("test.event1", handler1)
        emitter.on("test.event2", handler2)

        event1 = CodetoreumEvent(
            type="test.event1",
            timestamp=now_iso(),
            source="test",
        )
        emitter.emit(event1)

        event2 = CodetoreumEvent(
            type="test.event2",
            timestamp=now_iso(),
            source="test",
        )
        emitter.emit(event2)

        assert len(events1) == 1
        assert events1[0] == event1
        assert len(events2) == 1
        assert events2[0] == event2

    def test_emit_calls_handlers_synchronously_in_order(self):
        """Handlers should be called synchronously in registration order."""
        emitter = self.create_emitter()
        call_order: list[str] = []

        def handler1(event: CodetoreumEvent) -> None:
            call_order.append("handler1")

        def handler2(event: CodetoreumEvent) -> None:
            call_order.append("handler2")

        emitter.on("test.event", handler1)
        emitter.on("test.event", handler2)

        event = CodetoreumEvent(
            type="test.event",
            timestamp=now_iso(),
            source="test",
        )
        emitter.emit(event)

        assert call_order == ["handler1", "handler2"]

    def test_invalid_event_type_raises_error(self):
        """Event type must be in dot notation."""
        emitter = self.create_emitter()

        with pytest.raises(ValueError):
            CodetoreumEvent(
                type="invalid_no_dot",  # Missing dot
                timestamp=now_iso(),
                source="test",
            )

    def test_off_raises_on_unregistered_handler(self):
        """Unsubscribing a handler that wasn't registered should raise."""
        emitter = self.create_emitter()

        def handler(event: CodetoreumEvent) -> None:
            pass

        with pytest.raises(ValueError):
            emitter.off("test.event", handler)
