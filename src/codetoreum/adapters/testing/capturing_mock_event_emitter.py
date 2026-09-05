"""Capturing mock event emitter for testing domain event emission.

Captures all emitted events in memory without external dependencies.
Used for verifying event emission behavior in unit tests.
Supports event type filtering and wildcard subscriptions.
"""

import logging
from collections.abc import Callable

from codetoreum.ports.output.event_emitter import IEventEmitter

logger = logging.getLogger(__name__)


class CapturingMockEventEmitter(IEventEmitter):
    """In-memory event emitter for testing.

    Captures all emitted events and allows subscribing to event types.
    Useful for verifying that domain events are emitted correctly.

    Example:
        emitter = CapturingMockEventEmitter()

        # Subscribe to specific events
        events = []
        emitter.on("project.cloned", events.append)

        # Emit an event
        event = ProjectClonedEvent(...)
        emitter.emit(event)

        # Verify event was captured
        assert len(events) == 1
        assert events[0].project_name == "api-service"

        # Get all emitted events
        all_events = emitter.get_events()
        assert len(all_events) == 1
    """

    def __init__(self) -> None:
        """Initialize the mock event emitter."""
        self._events: list = []  # All emitted events
        self._handlers: dict[str, list[Callable]] = {}  # Event type -> handlers
        self._wildcard_handlers: list[Callable] = []  # Handlers for all events

    def on(self, event_type: str, handler: Callable) -> None:
        """Subscribe to events of a specific type.

        Args:
            event_type: Type of event to subscribe to (e.g., "project.cloned")
            handler: Callback function that accepts a CodetoreumEvent parameter

        Raises:
            ValueError: If event_type is invalid or handler is not callable
        """
        if not event_type:
            msg = "event_type cannot be empty"
            raise ValueError(msg)
        if not callable(handler):
            msg = "handler must be callable"
            raise ValueError(msg)

        if event_type == "*":
            self._wildcard_handlers.append(handler)
        else:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Callable) -> None:
        """Unsubscribe from events.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove

        Raises:
            ValueError: If handler was not previously subscribed
        """
        if event_type == "*":
            if handler not in self._wildcard_handlers:
                msg = f"Handler not subscribed to {event_type}"
                raise ValueError(msg)
            self._wildcard_handlers.remove(handler)
        else:
            if event_type not in self._handlers or handler not in self._handlers[event_type]:
                msg = f"Handler not subscribed to {event_type}"
                raise ValueError(msg)
            self._handlers[event_type].remove(handler)

    def emit(self, event) -> None:
        """Emit an event to all subscribers.

        Args:
            event: CodetoreumEvent instance to emit

        Raises:
            ValueError: If event is invalid or not a CodetoreumEvent
        """
        if event is None:
            msg = "event cannot be None"
            raise ValueError(msg)

        # Store event for later inspection
        self._events.append(event)

        # Call wildcard handlers
        for handler in self._wildcard_handlers:
            try:
                handler(event)
            except Exception:
                logger.warning("Handler error in mock event emitter", exc_info=True)

        # Call type-specific handlers
        event_type = getattr(event, "type", None)
        if event_type and event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    handler(event)
                except Exception:
                    logger.warning("Handler error in mock event emitter", exc_info=True)

    # =========================================================================
    # Test Helper Methods
    # =========================================================================

    def get_events(self) -> list:
        """Get all emitted events.

        Returns:
            List of all CodetoreumEvent instances emitted
        """
        return self._events.copy()

    def get_events_by_type(self, event_type: str) -> list:
        """Get all emitted events of a specific type.

        Args:
            event_type: Type of event to filter by

        Returns:
            List of events matching the type
        """
        return [e for e in self._events if getattr(e, "type", None) == event_type]

    def clear(self) -> None:
        """Clear all recorded events and handlers."""
        self._events.clear()
        self._handlers.clear()
        self._wildcard_handlers.clear()

    def clear_events(self) -> None:
        """Clear all recorded events but keep handlers."""
        self._events.clear()

    def get_event_count(self) -> int:
        """Get total count of emitted events.

        Returns:
            Number of events emitted
        """
        return len(self._events)

    def has_event_type(self, event_type: str) -> bool:
        """Check if any event of a specific type was emitted.

        Args:
            event_type: Type of event to check

        Returns:
            True if at least one event of that type was emitted
        """
        return any(getattr(e, "type", None) == event_type for e in self._events)
