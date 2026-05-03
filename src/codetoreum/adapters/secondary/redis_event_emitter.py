"""Redis-backed Event Emitter for distributed event emission.

This adapter provides a production-ready implementation of IEventEmitter
using Redis pub/sub for event distribution across multiple instances.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from redis import asyncio as aioredis

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.event_emitter import IEventEmitter

if TYPE_CHECKING:
    from codetoreum.domain.events.adapter_events import CodetoreumEvent

logger = logging.getLogger(__name__)


class RedisEventEmitterError(Exception):
    """Raised when Redis event emitter operations fail."""


class RedisEventEmitter(IEventEmitter):
    """
    Redis-based event emitter for distributed adapter event emission.

    Implements IEventEmitter using Redis pub/sub to distribute events
    across multiple server instances.

    This provides a production-ready alternative to MockEventEmitter,
    enabling event emission and subscription across distributed systems.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        channel_prefix: str = "adapter:events",
    ):
        """
        Initialize Redis event emitter.

        Args:
            redis_client: Redis async client
            channel_prefix: Prefix for Redis channels
        """
        self.redis = redis_client
        self.channel_prefix = channel_prefix

        # Track subscriptions: event_type -> List[callback]
        self._subscribers: dict[str, list[Callable]] = {}
        self._wildcard_subscribers: list[Callable] = []

        # Pub/sub instance for listening
        self._pubsub: aioredis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "events_emitted": 0,
            "events_received": 0,
            "emit_errors": 0,
            "receive_errors": 0,
        }

    async def initialize(self) -> None:
        """
        Initialize pub/sub listener for event subscription.

        Safe to call concurrently - only one initialization will occur.

        Raises:
            RedisEventEmitterError: If initialization fails
        """
        async with self._init_lock:
            if self._initialized:
                return

            try:
                self._pubsub = self.redis.pubsub()
                # Start listener task
                self._listener_task = asyncio.create_task(self._listen_for_events())
                self._initialized = True
                logger.info("Redis event emitter initialized")
            except Exception as e:
                msg = f"Failed to initialize event emitter: {e}"
                logger.error(msg, exc_info=True, extra={"error_id": ErrorRegistry.ERR_REDIS_ERROR})
                raise RedisEventEmitterError(msg) from e

    async def _listen_for_events(self) -> None:
        """
        Listen for events from Redis pub/sub channels in background task.
        """
        if not self._pubsub:
            return

        try:
            # Subscribe to all event channels
            await self._pubsub.psubscribe(f"{self.channel_prefix}:*")

            while self._initialized and self._pubsub:
                try:
                    message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

                    if message and message["type"] == "pmessage":
                        channel = message["channel"].decode("utf-8")
                        data = message["data"]

                        # Extract event type from channel
                        event_type = channel.replace(f"{self.channel_prefix}:", "")
                        await self._dispatch_event(event_type, data)

                except TimeoutError:
                    continue
                except Exception as e:
                    logger.error(
                        f"Error receiving event: {e}",
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR},
                    )
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Event listener cancelled")
        except Exception as e:
            logger.error(
                f"Fatal error in event listener: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR},
            )

    async def _dispatch_event(self, event_type: str, data: bytes) -> None:
        """
        Dispatch event to registered subscribers.

        Args:
            event_type: Type of event
            data: Event data (JSON-encoded)
        """
        try:
            event_dict = json.loads(data.decode("utf-8"))

            # Call type-specific subscribers
            for callback in self._subscribers.get(event_type, []):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event_dict)
                    else:
                        callback(event_dict)
                except Exception as e:
                    logger.error(
                        f"Error in event callback for {event_type}: {e}",
                        exc_info=True,
                    )

            # Call wildcard subscribers
            for callback in self._wildcard_subscribers:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event_dict)
                    else:
                        callback(event_dict)
                except Exception as e:
                    logger.error(
                        f"Error in wildcard event callback: {e}",
                        exc_info=True,
                    )

            self._stats["events_received"] += 1
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode event: {e}", exc_info=True)
            self._stats["receive_errors"] += 1

    def on(self, event_type: str, handler: Callable) -> None:
        """
        Subscribe to events of a specific type.

        Args:
            event_type: Type of event to subscribe to
            handler: Callback function that accepts event data

        Raises:
            ValueError: If event_type is invalid or handler is not callable
        """
        if not event_type or not event_type.strip():
            raise ValueError("event_type must be non-empty")
        if not callable(handler):
            raise ValueError("handler must be callable")

        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed to event type: {event_type}")

    def off(self, event_type: str, handler: Callable) -> None:
        """
        Unsubscribe from events.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove

        Raises:
            ValueError: If handler was not previously subscribed
        """
        if event_type not in self._subscribers or handler not in self._subscribers[event_type]:
            raise ValueError(f"Handler not subscribed to {event_type}")

        self._subscribers[event_type].remove(handler)
        logger.debug(f"Unsubscribed from event type: {event_type}")

    def emit(self, event: "CodetoreumEvent") -> None:
        """
        Emit an event to all subscribers.

        **Important**: This is a fire-and-forget implementation that schedules
        event publication to Redis asynchronously. The method returns immediately
        without waiting for delivery confirmation. Callers should not rely on
        immediate delivery guarantees.

        Events are published to Redis pub/sub for distribution to subscribers
        across all instances. If an error occurs during publication, it is logged
        but does not propagate to the caller.

        Args:
            event: CodetoreumEvent instance to emit

        Raises:
            ValueError: If event is invalid
            RuntimeError: If called outside an async context and asyncio cannot schedule the task
        """
        if not event:
            raise ValueError("event must not be None")

        try:
            # Get event type from event class name or event_type attribute
            event_type = getattr(event, "event_type", event.__class__.__name__)
            channel = f"{self.channel_prefix}:{event_type}"

            # Serialize event to JSON
            # Handle dataclass events by converting to dict
            if hasattr(event, "__dataclass_fields__"):
                import dataclasses

                event_dict = dataclasses.asdict(event)
            else:
                event_dict = {"type": event_type, "data": str(event)}

            event_json = json.dumps(event_dict, default=str)

            # Try to publish asynchronously to Redis
            try:
                asyncio.create_task(self._publish_event(channel, event_json))
                self._stats["events_emitted"] += 1
            except RuntimeError as e:
                # No running event loop - this is an error condition
                # Fire-and-forget pattern requires an async context
                logger.error(
                    f"Cannot emit event outside async context: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_EVENT_PUBLICATION_ERROR},
                )
                self._stats["emit_errors"] += 1
                raise
        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(
                f"Error preparing event for emission: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_EVENT_PUBLICATION_ERROR},
            )
            self._stats["emit_errors"] += 1

    async def _publish_event(self, channel: str, event_json: str) -> None:
        """
        Publish event to Redis asynchronously.

        Args:
            channel: Redis channel to publish to
            event_json: JSON-serialized event
        """
        try:
            await self.redis.publish(channel, event_json)
        except Exception as e:
            logger.error(
                f"Failed to publish event to {channel}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_REDIS_ERROR},
            )

    async def shutdown(self) -> None:
        """
        Gracefully shutdown the event emitter.

        Closes pub/sub connection and cancels listener task.
        """
        self._initialized = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.close()
        logger.info("Redis event emitter shut down")

    def get_stats(self) -> dict[str, int]:
        """Get event emission statistics."""
        return dict(self._stats)
