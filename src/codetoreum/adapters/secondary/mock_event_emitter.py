"""In-memory event emitter for testing and simulation.

This module provides a mock implementation of IEventEmitter that stores
event handlers in memory and emits events synchronously to all registered
subscribers. Used as a base class for mock adapters to support event
simulation testing without external service dependencies.
"""

from collections.abc import Callable

from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.ports.output.event_emitter import IEventEmitter


class MockEventEmitter(IEventEmitter):
    """In-memory event emitter for testing.

    Provides a simple implementation of IEventEmitter that maintains
    a registry of event handlers and emits events synchronously.
    Events are dispatched to all subscribers in registration order.

    This class serves as a base for mock adapters that need to emit
    events during testing without connecting to external systems.

    Example:
        emitter = MockEventEmitter()

        # Subscribe to events
        events = []
        emitter.on("workitem.column_changed", events.append)

        # Emit an event
        event = WorkItemColumnChangedEvent(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            from_column="Backlog",
            to_column="In Progress",
            timestamp="2025-01-08T00:00:00+00:00",
            source="mock"
        )
        emitter.emit(event)

        # Check results
        assert len(events) == 1
        assert events[0].to_column == "In Progress"
    """

    def __init__(self) -> None:
        """Initialize the event emitter with empty handler registry."""
        self._handlers: dict[str, list[Callable[[CodetoreumEvent], None]]] = {}

    def on(self, event_type: str, handler: Callable[[CodetoreumEvent], None]) -> None:
        """Subscribe to events of a specific type.

        Registers a handler function that will be called each time an event
        of the specified type is emitted.

        Args:
            event_type: Type of event to subscribe to (e.g., "workitem.column_changed")
            handler: Callback function that accepts a CodetoreumEvent parameter

        Raises:
            ValueError: If event_type is empty or handler is not callable
        """
        if not event_type:
            msg = "event_type cannot be empty"
            raise ValueError(msg)
        if not callable(handler):
            msg = "handler must be callable"
            raise ValueError(msg)

        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Callable[[CodetoreumEvent], None]) -> None:
        """Unsubscribe from events.

        Removes a previously registered handler function. If the handler
        is not registered, raises ValueError.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove

        Raises:
            ValueError: If handler was not previously subscribed to this event type
        """
        if event_type not in self._handlers or handler not in self._handlers[event_type]:
            msg = f"Handler not subscribed to event type: {event_type}"
            raise ValueError(msg)
        self._handlers[event_type].remove(handler)

    def emit(self, event: CodetoreumEvent) -> None:
        """Emit an event to all subscribers.

        Dispatches the event to all handlers subscribed to the event type.
        Handlers are called synchronously in registration order. If a handler
        raises an exception, subsequent handlers are still called.

        Args:
            event: CodetoreumEvent instance to emit

        Raises:
            ValueError: If event is not a CodetoreumEvent instance
        """
        if not isinstance(event, CodetoreumEvent):
            msg = "event must be a CodetoreumEvent instance"
            raise ValueError(msg)

        if event.type in self._handlers:
            for handler in self._handlers[event.type]:
                handler(event)
