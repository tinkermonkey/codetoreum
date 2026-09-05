"""Event emitter port interface for vendor-agnostic adapters.

This interface defines the contract for emitting standardized events
from adapters to the orchestrator.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codetoreum.domain.events.adapter_events import CodetoreumEvent


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

    @abstractmethod
    def off(self, event_type: str, handler: Callable) -> None:
        """Unsubscribe from events.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove

        Raises:
            ValueError: If handler was not previously subscribed
        """

    @abstractmethod
    def emit(self, event: "CodetoreumEvent") -> None:
        """Emit an event to all subscribers.

        Events are dispatched to all handlers subscribed to the event type,
        plus any wildcard handlers. Handlers are called synchronously in
        registration order.

        Args:
            event: CodetoreumEvent instance to emit

        Raises:
            ValueError: If event is invalid or not a CodetoreumEvent
        """

    def once(self, event_type: str, handler: Callable) -> None:
        """Subscribe to receive a single event, then unsubscribe.

        Default implementation wraps on/off. Can be overridden
        for more efficient single-event subscription.

        Args:
            event_type: Type of event to subscribe to
            handler: Callback function
        """

        def one_time_handler(event: "CodetoreumEvent") -> None:
            try:
                handler(event)
            finally:
                self.off(event_type, one_time_handler)

        self.on(event_type, one_time_handler)


class NullEventEmitter(IEventEmitter):
    """Null-object pattern for optional event emission.

    Implements IEventEmitter with no-op methods for use when event emission is not required.
    All methods are silent, allowing adapters to run without event infrastructure.
    """

    def __init__(self) -> None:
        """Initialize the null event emitter."""
        self._warned = False

    def emit(self, event: "CodetoreumEvent") -> None:
        """No-op emit - silently discards all events.

        Logs a warning on first invocation to alert developers that DI wiring
        may have failed and events are not reaching the audit trail.
        """
        if not self._warned:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                "NullEventEmitter.emit() called - event DI wiring may have failed. "
                "Events are being discarded and will not reach the audit trail."
            )
            self._warned = True

    def on(self, event_type: str, handler: Callable) -> None:
        """No-op subscription - no handlers are registered."""

    def off(self, event_type: str, handler: Callable) -> None:
        """No-op unsubscription - no handlers to unregister."""

    def once(self, event_type: str, handler: Callable) -> None:
        """No-op single subscription - no handlers are registered."""
