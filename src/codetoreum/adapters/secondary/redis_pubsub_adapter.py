"""
Redis Pub/Sub Adapter for WebSocket Message Distribution

This adapter enables horizontal scalability for WebSocket connections by
using Redis pub/sub to distribute messages across multiple server instances.

Architecture:
    Instance 1 (WS Connections) ←→ Redis Pub/Sub ←→ Instance 2 (WS Connections)
                                          ↕
                                    Instance 3 (WS Connections)

When an event is published to Redis, all server instances receive it and
broadcast to their local WebSocket connections.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from redis import asyncio as aioredis

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.event_serialization import EventSerializer

logger = logging.getLogger(__name__)


class RedisPubSubError(Exception):
    """Raised when Redis pub/sub operations fail."""

    pass


class RedisPubSubAdapter:
    """
    Redis pub/sub adapter for WebSocket message distribution across instances.

    Features:
    - Multi-instance message distribution
    - Channel-based message routing
    - Automatic reconnection on failure
    - Subscription management
    - Message serialization/deserialization
    - Error handling and resilience

    Channels:
    - websocket:events - All domain events for WebSocket broadcast
    - websocket:control - Control messages (disconnect, etc.)
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        event_channel: str = "websocket:events",
        control_channel: str = "websocket:control",
    ):
        """
        Initialize Redis pub/sub adapter.

        Args:
            redis_client: Redis async client
            event_channel: Channel for event messages
            control_channel: Channel for control messages
        """
        self.redis = redis_client
        self.event_channel = event_channel
        self.control_channel = control_channel

        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

        # Callback registry: channel -> List[callback]
        self._callbacks: Dict[str, List[Callable]] = {}
        self._callbacks_lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "messages_published": 0,
            "messages_received": 0,
            "publish_errors": 0,
            "receive_errors": 0,
        }

    async def initialize(self) -> None:
        """
        Initialize pub/sub listener.

        This method is safe to call concurrently - only one initialization will occur.

        Raises:
            RedisPubSubError: If initialization fails
        """
        async with self._init_lock:
            if self._initialized:
                return

            try:
                # Create pub/sub instance
                self._pubsub = self.redis.pubsub()

                # Subscribe to channels
                await self._pubsub.subscribe(self.event_channel, self.control_channel)

                # Start listener task
                self._listener_task = asyncio.create_task(self._listen_for_messages())

                self._initialized = True
                logger.info(
                    f"Redis pub/sub initialized - subscribed to {self.event_channel}, {self.control_channel}"
                )

            except Exception as e:
                raise RedisPubSubError(f"Failed to initialize pub/sub: {e}") from e

    async def _listen_for_messages(self) -> None:
        """
        Listen for messages from Redis pub/sub channels.

        This runs in a background task and dispatches messages to registered callbacks.
        """
        try:
            while self._initialized and self._pubsub:
                try:
                    # Get message with timeout to allow checking _initialized flag
                    message = await self._pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )

                    if message and message["type"] == "message":
                        channel = message["channel"].decode("utf-8")
                        data = message["data"]

                        # Dispatch to callbacks
                        await self._dispatch_message(channel, data)

                        self._stats["messages_received"] += 1

                except asyncio.TimeoutError:
                    # No message received, continue
                    continue
                except Exception as e:
                    logger.error(f"Error receiving message: {e}")
                    self._stats["receive_errors"] += 1
                    # Continue listening despite errors
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Pub/sub listener cancelled")
        except Exception as e:
            logger.error(f"Fatal error in pub/sub listener: {e}")

    async def _dispatch_message(self, channel: str, data: bytes) -> None:
        """
        Dispatch message to registered callbacks.

        Args:
            channel: Channel the message was received on
            data: Message data
        """
        try:
            # Parse message
            message_dict = json.loads(data.decode("utf-8"))

            # Get callbacks for this channel
            async with self._callbacks_lock:
                callbacks = self._callbacks.get(channel, [])

            # Call all callbacks
            for callback in callbacks:
                try:
                    # Check if callback is async or sync
                    if asyncio.iscoroutinefunction(callback):
                        await callback(message_dict)
                    else:
                        callback(message_dict)
                except Exception as e:
                    logger.error(f"Error in pub/sub callback: {e}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode message: {e}")
        except Exception as e:
            logger.error(f"Error dispatching message: {e}")

    async def publish_event(self, event: DomainEvent) -> None:
        """
        Publish domain event to all server instances.

        Args:
            event: Domain event to publish

        Raises:
            RedisPubSubError: If publish fails
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Serialize event
            event_dict = event.to_dict() if hasattr(event, "to_dict") else event.__dict__

            # Create message envelope
            message = {
                "type": "event",
                "event_type": type(event).__name__,
                "event": event_dict,
            }

            # Publish to Redis
            await self.redis.publish(self.event_channel, json.dumps(message))

            self._stats["messages_published"] += 1

            logger.debug(
                f"Published event {type(event).__name__} to channel {self.event_channel}"
            )

        except Exception as e:
            self._stats["publish_errors"] += 1
            raise RedisPubSubError(f"Failed to publish event: {e}") from e

    async def publish_control_message(
        self, message_type: str, data: Dict[str, Any]
    ) -> None:
        """
        Publish control message to all server instances.

        Control messages are used for coordination between instances
        (e.g., disconnect client, update connection state).

        Args:
            message_type: Type of control message
            data: Control message data

        Raises:
            RedisPubSubError: If publish fails
        """
        if not self._initialized:
            await self.initialize()

        try:
            message = {"type": message_type, "data": data}

            # Publish to Redis
            await self.redis.publish(self.control_channel, json.dumps(message))

            self._stats["messages_published"] += 1

            logger.debug(
                f"Published control message {message_type} to channel {self.control_channel}"
            )

        except Exception as e:
            self._stats["publish_errors"] += 1
            raise RedisPubSubError(f"Failed to publish control message: {e}") from e

    async def subscribe(self, channel: str, callback: Callable) -> None:
        """
        Register a callback for messages on a channel.

        Args:
            channel: Channel to subscribe to
            callback: Async or sync callback function to handle messages
                     Signature: callback(message: Dict[str, Any]) -> None

        Raises:
            RedisPubSubError: If subscription fails
        """
        if not self._initialized:
            await self.initialize()

        async with self._callbacks_lock:
            if channel not in self._callbacks:
                self._callbacks[channel] = []

            self._callbacks[channel].append(callback)

        logger.debug(f"Registered callback for channel {channel}")

    async def unsubscribe(self, channel: str, callback: Callable) -> None:
        """
        Unregister a callback for a channel.

        Args:
            channel: Channel to unsubscribe from
            callback: Callback to remove
        """
        async with self._callbacks_lock:
            if channel in self._callbacks:
                try:
                    self._callbacks[channel].remove(callback)

                    # Clean up empty callback lists
                    if not self._callbacks[channel]:
                        del self._callbacks[channel]

                    logger.debug(f"Unregistered callback for channel {channel}")
                except ValueError:
                    # Callback not found, that's okay
                    pass

    def get_stats(self) -> Dict[str, Any]:
        """
        Get pub/sub statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "messages_published": self._stats["messages_published"],
            "messages_received": self._stats["messages_received"],
            "publish_errors": self._stats["publish_errors"],
            "receive_errors": self._stats["receive_errors"],
            "initialized": self._initialized,
            "active_channels": list(self._callbacks.keys()),
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = {
            "messages_published": 0,
            "messages_received": 0,
            "publish_errors": 0,
            "receive_errors": 0,
        }
        logger.info("Pub/sub statistics reset")

    async def close(self) -> None:
        """Close pub/sub connection and cleanup resources."""
        self._initialized = False

        # Cancel listener task
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        # Unsubscribe and close pub/sub
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(self.event_channel, self.control_channel)
                await self._pubsub.close()
            except Exception as e:
                logger.warning(f"Error closing pub/sub: {e}")
            self._pubsub = None

        # Clear callbacks
        async with self._callbacks_lock:
            self._callbacks.clear()

        logger.info("Redis pub/sub adapter closed")
