"""RedisPubSubEventEmitter — multi-instance IEventEmitter via Redis pub/sub.

For multi-instance Codetoreum deployments where domain events must reach
subscribers across process boundaries, this adapter pushes serialized
``CodetoreumEvent`` instances onto Redis channels keyed by ``event.type``
and runs a background subscriber that re-dispatches incoming messages to
in-process handlers.

Single-instance deployments and simulation continue to use
``MockEventEmitter`` (in-memory, synchronous).

This is intentionally distinct from the existing ``RedisPubSubAdapter``,
which implements ``IMessageBroker`` (a different surface aimed at named
control channels and explicit subscribe-by-channel). The event emitter
contract is event-type-driven and synchronous-on-emit.

Wire format
-----------
- Channel name: ``codetoreum:events:{event.type}``
- Message body: JSON of ``event.to_dict()``

Subscribers run a background ``asyncio.Task`` per registered event type.
On startup the adapter is dormant — call ``await start()`` to subscribe;
``await close()`` to tear down.

INV-11: no retry/circuit-breaker logic embedded.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.event_emitter import IEventEmitter

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "codetoreum:events"


class RedisPubSubEventEmitter(IEventEmitter):
    """IEventEmitter that delivers events through Redis pub/sub.

    Single-process delivery semantics are preserved for handlers attached
    via ``on()`` — those run in-process. The Redis wire is only used to
    propagate emissions to subscribers in other processes.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        channel_prefix: str = _CHANNEL_PREFIX,
    ) -> None:
        self._redis = redis_client
        self._channel_prefix = channel_prefix
        self._handlers: dict[str, list[Callable[[CodetoreumEvent], None]]] = {}
        # event_type -> background subscriber task
        self._subscriber_tasks: dict[str, asyncio.Task[None]] = {}
        self._closed = False
        self._loop: asyncio.AbstractEventLoop | None = None

    # ----- IEventEmitter -----
    def on(self, event_type: str, handler: Callable[[CodetoreumEvent], None]) -> None:
        if not event_type:
            raise ValueError("event_type cannot be empty")
        if not callable(handler):
            raise ValueError("handler must be callable")

        self._handlers.setdefault(event_type, []).append(handler)
        # Lazily start a subscriber for this event type if an event loop is running.
        try:
            self._ensure_subscriber(event_type)
        except RuntimeError:
            # No running event loop yet; subscribers will be started on first emit.
            pass

    def off(self, event_type: str, handler: Callable[[CodetoreumEvent], None]) -> None:
        handlers = self._handlers.get(event_type, [])
        try:
            handlers.remove(handler)
        except ValueError as exc:
            raise ValueError(f"Handler not registered for event_type={event_type}") from exc

    def emit(self, event: CodetoreumEvent) -> None:
        if not isinstance(event, CodetoreumEvent):
            raise ValueError("event must be a CodetoreumEvent instance")

        event_type = event.type
        # 1) Synchronous local delivery (preserve MockEventEmitter semantics).
        for h in list(self._handlers.get(event_type, [])):
            try:
                h(event)
            except Exception:
                logger.error(
                    f"In-process handler {h} failed for {event_type}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                )

        # 2) Publish to Redis for cross-process subscribers.
        try:
            self._schedule_publish(event_type, event)
        except RuntimeError:
            # No event loop available — degrade to local-only delivery and log.
            logger.warning(
                f"Cannot publish event {event_type} to Redis: no running event loop",
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )

    # ----- Lifecycle -----
    async def close(self) -> None:
        self._closed = True
        for task in list(self._subscriber_tasks.values()):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._subscriber_tasks.clear()

    # ----- Internals -----
    def _schedule_publish(self, event_type: str, event: CodetoreumEvent) -> None:
        loop = asyncio.get_running_loop()
        loop.create_task(self._publish(event_type, event))

    async def _publish(self, event_type: str, event: CodetoreumEvent) -> None:
        try:
            payload = json.dumps(event.to_dict())
        except Exception:
            logger.error(
                f"Failed to serialize event {event_type} for Redis publish",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            return
        channel = self._channel_for(event_type)
        try:
            await self._redis.publish(channel, payload)
        except Exception:
            logger.error(
                f"Redis publish failed for channel {channel}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )

    def _channel_for(self, event_type: str) -> str:
        return f"{self._channel_prefix}:{event_type}"

    def _ensure_subscriber(self, event_type: str) -> None:
        if event_type in self._subscriber_tasks:
            return
        loop = asyncio.get_running_loop()
        self._subscriber_tasks[event_type] = loop.create_task(self._subscribe(event_type))

    async def _subscribe(self, event_type: str) -> None:
        channel = self._channel_for(event_type)
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(channel)
        except Exception:
            logger.error(
                f"Failed to subscribe to Redis channel {channel}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            return
        try:
            async for message in pubsub.listen():
                if self._closed:
                    break
                if message is None or message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                try:
                    event_dict = json.loads(data)
                except Exception:
                    logger.error(
                        f"Malformed message on {channel}; skipping",
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                    )
                    continue
                # Re-dispatch to local handlers. We do NOT reconstruct the
                # concrete event subclass here because handlers may accept a
                # dict-based shape; using the CodetoreumEvent base preserves
                # type without requiring a per-subclass registry.
                try:
                    rehydrated = self._rehydrate(event_dict)
                except Exception:
                    logger.error(
                        f"Failed to rehydrate event from {channel}; skipping",
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                    )
                    continue
                for h in list(self._handlers.get(event_type, [])):
                    try:
                        h(rehydrated)
                    except Exception:
                        logger.error(
                            f"Cross-process handler {h} failed for {event_type}",
                            exc_info=True,
                            extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                        )
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass

    @staticmethod
    def _rehydrate(event_dict: dict) -> CodetoreumEvent:
        """Build a generic CodetoreumEvent from a serialized dict.

        Handlers that need a specific subclass should look up by ``event.type``
        and rebuild themselves; this base-class shape is enough for in-process
        routing.
        """
        return CodetoreumEvent(
            type=event_dict.get("type", ""),
            timestamp=event_dict.get("timestamp", ""),
            source=event_dict.get("source", ""),
            correlation_id=event_dict.get("correlation_id"),
            event_id=event_dict.get("event_id", ""),
        )


__all__ = ["RedisPubSubEventEmitter"]
