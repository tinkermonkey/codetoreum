"""In-memory message broker for testing and simulation.

This module provides a mock implementation of IMessageBroker that simulates
pub/sub messaging without external infrastructure like Redis. Useful for
testing distributed event distribution logic without external dependencies.
"""

import asyncio
import inspect
import logging
from collections import defaultdict
from typing import Any, Callable

from codetoreum.domain.events import DomainEvent
from codetoreum.ports.output.message_broker import IMessageBroker

_logger = logging.getLogger(__name__)


class InMemoryMessageBroker(IMessageBroker):
    """In-memory message broker for testing and simulation.

    Simulates pub/sub messaging by maintaining in-memory subscriptions and
    delivering messages to registered callbacks. Provides statistics tracking
    for testing and debugging.

    Example:
        broker = InMemoryMessageBroker()

        # Initialize
        await broker.initialize()

        # Subscribe to a channel
        messages = []
        async def handler(msg):
            messages.append(msg)

        await broker.subscribe("events.workflow", handler)

        # Publish event
        await broker.publish_event(domain_event)

        # Verify message was delivered
        assert len(messages) == 1

        # Check statistics
        stats = broker.get_stats()
        assert stats['events_published'] == 1
    """

    def __init__(self) -> None:
        """Initialize the in-memory message broker."""
        # Map of channel_name -> list of (callback, is_async) tuples
        self._subscriptions: dict[str, list[tuple[Callable, bool]]] = defaultdict(list)

        # Statistics tracking
        self._stats = {
            "events_published": 0,
            "control_messages_published": 0,
            "messages_delivered": 0,
            "delivery_failures": 0,
            "subscriptions": 0,
            "unsubscriptions": 0,
        }

        # Track published messages for testing/debugging
        self._published_messages: list[Any] = []

    async def initialize(self) -> None:
        """Initialize the message broker connection and subscriptions.

        In the in-memory implementation, this is a no-op.

        Raises:
            MessageBrokerError: If initialization fails
        """
        # Nothing to initialize for in-memory broker
        pass

    async def publish_event(self, event: DomainEvent) -> None:
        """Publish a domain event to all subscribers across all instances.

        Args:
            event: Domain event to publish

        Raises:
            MessageBrokerError: If publish fails
        """
        self._stats["events_published"] += 1
        self._published_messages.append(event)

        # Deliver to all subscribers
        # In a real implementation, this would publish to all instances
        # Here we just deliver to local subscribers
        await self._deliver_to_subscribers("events", event)

    async def publish_control_message(self, message_type: str, data: dict[str, Any]) -> None:
        """Publish a control message to all subscribers.

        Control messages are used for coordination between instances
        (e.g., disconnect client, update connection state).

        Args:
            message_type: Type of control message
            data: Control message data

        Raises:
            MessageBrokerError: If publish fails
        """
        message = {"type": message_type, "data": data}
        self._stats["control_messages_published"] += 1
        self._published_messages.append(message)

        # Deliver to control message subscribers
        await self._deliver_to_subscribers(f"control.{message_type}", message)

    async def subscribe(self, channel: str, callback: Callable) -> None:
        """Subscribe to a message channel with a callback.

        Args:
            channel: Channel name to subscribe to
            callback: Async or sync callback function to handle messages
                     Signature: callback(message: Dict[str, Any]) -> None

        Raises:
            MessageBrokerError: If subscription fails
        """
        # Determine if callback is async
        is_async = asyncio.iscoroutinefunction(callback) or inspect.iscoroutinefunction(callback)

        self._subscriptions[channel].append((callback, is_async))
        self._stats["subscriptions"] += 1

    async def unsubscribe(self, channel: str, callback: Callable) -> None:
        """Unsubscribe from a message channel.

        Args:
            channel: Channel name to unsubscribe from
            callback: Callback to remove

        Raises:
            MessageBrokerError: If unsubscription fails
        """
        if channel in self._subscriptions:
            # Remove the specific callback
            self._subscriptions[channel] = [
                (cb, is_async) for cb, is_async in self._subscriptions[channel] if cb != callback
            ]

            # Remove empty channel entries
            if not self._subscriptions[channel]:
                del self._subscriptions[channel]

            self._stats["unsubscriptions"] += 1

    def get_stats(self) -> dict[str, Any]:
        """Get message broker statistics.

        Returns:
            Dictionary with statistics (messages published/received, errors, etc.)
        """
        return {
            **self._stats,
            "active_subscriptions": sum(len(cbs) for cbs in self._subscriptions.values()),
            "channels": len(self._subscriptions),
        }

    def reset_stats(self) -> None:
        """Reset message broker statistics."""
        self._stats = {
            "events_published": 0,
            "control_messages_published": 0,
            "messages_delivered": 0,
            "delivery_failures": 0,
            "subscriptions": 0,
            "unsubscriptions": 0,
        }
        self._published_messages.clear()

    async def close(self) -> None:
        """Close message broker connection and cleanup resources."""
        self._subscriptions.clear()
        self._published_messages.clear()

    # =========================================================================
    # Test Helper Methods
    # =========================================================================

    async def _deliver_to_subscribers(self, channel: str, message: Any) -> None:
        """Deliver message to all subscribers on a channel.

        Args:
            channel: Channel name to deliver to
            message: Message to deliver
        """
        if channel not in self._subscriptions:
            return

        for callback, is_async in self._subscriptions[channel]:
            try:
                if is_async:
                    await callback(message)
                else:
                    callback(message)
                self._stats["messages_delivered"] += 1
            except Exception:
                self._stats["delivery_failures"] += 1
                _logger.error("Message delivery failed for channel %s", channel, exc_info=True)

    def get_published_messages(self) -> list[Any]:
        """Test helper: Get all published messages.

        Returns:
            List of all published messages and events
        """
        return self._published_messages.copy()

    def get_subscriptions_for_channel(self, channel: str) -> int:
        """Test helper: Get number of subscriptions on a channel.

        Args:
            channel: Channel name to query

        Returns:
            Number of active subscriptions on the channel
        """
        return len(self._subscriptions.get(channel, []))

    def clear_published_messages(self) -> None:
        """Test helper: Clear the published messages log."""
        self._published_messages.clear()
