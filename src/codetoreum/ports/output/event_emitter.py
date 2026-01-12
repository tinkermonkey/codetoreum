"""Event emitter port interface for vendor-agnostic adapters.

This interface defines the contract for emitting standardized events
from adapters to the orchestrator.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional


class IEventEmitter(ABC):
    """Event emission capability for adapters.

    Adapters implement this interface to emit standardized events
    to subscribers. Events use vendor-agnostic terminology and
    include source identification for routing and tracing.

    Attributes:
        Implementations should maintain internal state for:
        - Registered event handlers by event type
        - Subscription callbacks
        - Event emission capabilities
    """

    @abstractmethod
    def on(self, event_type: str, handler: Callable) -> None:
        """Subscribe to events of a specific type.

        Args:
            event_type: Type of event to subscribe to (e.g., "workitem.column_changed")
            handler: Callback function that accepts a CodetoreumEvent parameter

        Raises:
            ValueError: If event_type is invalid or handler is not callable
        """
        pass

    @abstractmethod
    def off(self, event_type: str, handler: Callable) -> None:
        """Unsubscribe from events.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove

        Raises:
            ValueError: If handler was not previously subscribed
        """
        pass

    @abstractmethod
    def emit(self, event: "CodetoreumEvent") -> None:  # type: ignore
        """Emit an event to all subscribers.

        Events are dispatched to all handlers subscribed to the event type,
        plus any wildcard handlers. Handlers are called synchronously in
        registration order.

        Args:
            event: CodetoreumEvent instance to emit

        Raises:
            ValueError: If event is invalid or not a CodetoreumEvent
        """
        pass

    def once(self, event_type: str, handler: Callable) -> None:
        """Subscribe to receive a single event, then unsubscribe.

        Default implementation wraps on/off. Can be overridden
        for more efficient single-event subscription.

        Args:
            event_type: Type of event to subscribe to
            handler: Callback function
        """
        def one_time_handler(event: "CodetoreumEvent") -> None:  # type: ignore
            try:
                handler(event)
            finally:
                self.off(event_type, one_time_handler)

        self.on(event_type, one_time_handler)
