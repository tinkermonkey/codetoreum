"""In-process event bus for real-time event handling with optional Redis persistence."""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Type

from codetoreum.domain.events import DomainEvent

logger = logging.getLogger(__name__)

# Optional Redis support
try:
    from redis import asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class EventBusError(Exception):
    """Raised when event bus operations fail."""

    pass


class EventHandler:
    """
    Base class for event handlers.

    Event handlers process events in real-time as they are published
    to the event bus.
    """

    async def handle(self, event: DomainEvent) -> None:
        """
        Handle an event.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails
        """
        raise NotImplementedError("Subclasses must implement handle()")

    def get_event_types(self) -> List[str]:
        """
        Get list of event types this handler processes.

        Returns:
            List of event type names (class names)
        """
        raise NotImplementedError("Subclasses must implement get_event_types()")


class EventBus:
    """
    In-process event bus for pub/sub event handling.

    Features:
    - Pub/sub pattern for event handlers
    - Async event dispatching
    - Error handling and retry logic
    - Handler ordering and dependencies
    - Event filtering by type
    - Metrics and monitoring

    Usage:
        # Register handlers
        bus = EventBus()
        bus.register_handler(MyEventHandler())

        # Publish events
        await bus.publish(WorkItemCreated(...))

        # Or subscribe with callback
        async def my_callback(event: DomainEvent):
            print(f"Received: {event.event_type}")

        bus.subscribe("WorkItemCreated", my_callback)
        await bus.publish(WorkItemCreated(...))
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
        redis_client: Optional[Any] = None,
        redis_stream_prefix: str = "events",
    ):
        """
        Initialize event bus.

        Args:
            max_retries: Maximum retry attempts for failed handlers
            retry_delay_seconds: Delay between retries
            redis_client: Optional Redis async client for event persistence
            redis_stream_prefix: Prefix for Redis streams (e.g., "events:workitem.column_changed")
        """
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.redis_client = redis_client
        self.redis_stream_prefix = redis_stream_prefix

        # Handler registry: event_type -> list of handlers
        self._handlers: Dict[str, List[EventHandler]] = {}

        # Callback registry: event_type -> list of callbacks
        self._callbacks: Dict[str, List[Callable]] = {}

        # Wildcard handlers (receive all events)
        self._wildcard_handlers: List[EventHandler] = []
        self._wildcard_callbacks: List[Callable] = []

        # Statistics
        self._stats = {
            "events_published": 0,
            "events_handled": 0,
            "handler_errors": 0,
            "events_persisted": 0,
            "persistence_errors": 0,
        }

    def register_handler(self, handler: EventHandler) -> None:
        """
        Register an event handler.

        Args:
            handler: Event handler instance

        Raises:
            EventBusError: If registration fails
        """
        try:
            event_types = handler.get_event_types()

            if not event_types:
                # Wildcard handler (receives all events)
                self._wildcard_handlers.append(handler)
                logger.info(
                    f"Registered wildcard handler: {handler.__class__.__name__}"
                )
            else:
                for event_type in event_types:
                    if event_type not in self._handlers:
                        self._handlers[event_type] = []

                    self._handlers[event_type].append(handler)

                logger.info(
                    f"Registered handler {handler.__class__.__name__} "
                    f"for event types: {event_types}"
                )

        except Exception as e:
            logger.error(
                f"Failed to register handler {handler.__class__.__name__}: {e}",
                exc_info=True,
                extra={
                    "handler_class": handler.__class__.__name__,
                    "error_id": "ERR_HANDLER_REGISTRATION"
                }
            )
            raise EventBusError(f"Failed to register handler: {e}") from e

    def unregister_handler(self, handler: EventHandler) -> None:
        """
        Unregister an event handler.

        Args:
            handler: Event handler instance
        """
        # Remove from wildcard handlers
        if handler in self._wildcard_handlers:
            self._wildcard_handlers.remove(handler)

        # Remove from type-specific handlers
        for event_type, handlers in list(self._handlers.items()):
            if handler in handlers:
                handlers.remove(handler)

            # Clean up empty lists
            if not handlers:
                del self._handlers[event_type]

        logger.info(f"Unregistered handler: {handler.__class__.__name__}")

    def subscribe(
        self, event_type: Optional[str], callback: Callable[[DomainEvent], Any]
    ) -> None:
        """
        Subscribe to events with a callback function.

        Args:
            event_type: Event type to subscribe to (None for all events)
            callback: Async callback function

        Raises:
            EventBusError: If subscription fails
        """
        try:
            if event_type is None:
                # Wildcard subscription
                self._wildcard_callbacks.append(callback)
                logger.info(f"Subscribed callback to all events")
            else:
                if event_type not in self._callbacks:
                    self._callbacks[event_type] = []

                self._callbacks[event_type].append(callback)

                logger.info(f"Subscribed callback to event type: {event_type}")

        except Exception as e:
            logger.error(
                f"Failed to subscribe callback to event {event_type}: {e}",
                exc_info=True,
                extra={
                    "event_type": event_type,
                    "callback": callback.__name__ if hasattr(callback, '__name__') else str(callback),
                    "error_id": "ERR_CALLBACK_SUBSCRIPTION"
                }
            )
            raise EventBusError(f"Failed to subscribe callback: {e}") from e

    def unsubscribe(
        self, event_type: Optional[str], callback: Callable[[DomainEvent], Any]
    ) -> None:
        """
        Unsubscribe a callback.

        Args:
            event_type: Event type (None for wildcard)
            callback: Callback to unsubscribe
        """
        if event_type is None:
            if callback in self._wildcard_callbacks:
                self._wildcard_callbacks.remove(callback)
        else:
            if event_type in self._callbacks:
                if callback in self._callbacks[event_type]:
                    self._callbacks[event_type].remove(callback)

                # Clean up empty lists
                if not self._callbacks[event_type]:
                    del self._callbacks[event_type]

        logger.info(f"Unsubscribed callback from event type: {event_type}")

    async def publish(self, event: DomainEvent) -> None:
        """
        Publish an event to all registered handlers and callbacks.

        Also persists event to Redis Streams if Redis client is configured.

        Error Handling:
        - asyncio.CancelledError: Always propagated (not caught)
        - ConnectionError/TimeoutError: Logged with retry hint (transient)
        - ValueError: Logged with validation hint (permanent)
        - Unexpected exceptions: Logged as critical

        Args:
            event: Domain event to publish

        Raises:
            EventBusError: If publishing fails (with context about error type)
            asyncio.CancelledError: Always propagated without catching
        """
        self._stats["events_published"] += 1

        try:
            # Persist event to Redis Streams if available
            if self.redis_client:
                await self._persist_to_redis(event)

            # Get handlers for this event type
            handlers = self._get_handlers_for_event(event)

            # Get callbacks for this event type
            callbacks = self._get_callbacks_for_event(event)

            # Dispatch to all handlers and callbacks
            tasks = []

            for handler in handlers:
                tasks.append(self._dispatch_to_handler(handler, event))

            for callback in callbacks:
                tasks.append(self._dispatch_to_callback(callback, event))

            # Wait for all handlers to complete
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Check for errors
                for idx, result in enumerate(results):
                    if isinstance(result, Exception):
                        handler_name = f"handler_{idx}"
                        logger.error(
                            f"Handler {handler_name} failed for event {event.event_type}: {result}",
                            exc_info=result,
                            extra={
                                "event_type": event.event_type,
                                "event_id": event.event_id,
                                "handler_index": idx,
                                "error_type": type(result).__name__
                            }
                        )
                        self._stats["handler_errors"] += 1

            self._stats["events_handled"] += len(handlers) + len(callbacks)

            logger.debug(
                f"Published event {event.event_type} to "
                f"{len(handlers)} handlers and {len(callbacks)} callbacks"
            )

        except asyncio.CancelledError:
            # Always propagate cancellation - don't suppress system signals
            logger.info(f"Event publishing cancelled for {event.event_type}")
            raise
        except (ConnectionError, TimeoutError) as e:
            # Network/Redis issues - transient errors that may resolve on retry
            logger.error(
                f"Connection error publishing event {event.event_type}: {e}",
                exc_info=True,
                extra={
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "error_id": "ERR_EVENT_BUS_CONNECTION"
                }
            )
            raise EventBusError(
                f"Connection error publishing event: {e}. This may be transient - please retry."
            ) from e
        except ValueError as e:
            # Validation errors - permanent issues with event data
            logger.error(
                f"Validation error publishing event {event.event_type}: {e}",
                exc_info=True,
                extra={
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "error_id": "ERR_EVENT_BUS_VALIDATION"
                }
            )
            raise EventBusError(
                f"Invalid event data: {e}. Please check event structure."
            ) from e
        except Exception as e:
            # Unexpected errors that don't fit other categories
            logger.critical(
                f"Unexpected error publishing event {event.event_type}: {e}",
                exc_info=True,
                extra={
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "error_id": "ERR_EVENT_BUS_UNEXPECTED"
                }
            )
            raise EventBusError(f"Unexpected error publishing event: {e}") from e

    async def publish_batch(self, events: List[DomainEvent]) -> None:
        """
        Publish multiple events.

        Args:
            events: List of domain events to publish

        Raises:
            EventBusError: If publishing fails
        """
        for event in events:
            await self.publish(event)

    def _get_handlers_for_event(self, event: DomainEvent) -> List[EventHandler]:
        """Get all handlers for a given event."""
        handlers = []

        # Type-specific handlers
        event_type = event.event_type
        if event_type in self._handlers:
            handlers.extend(self._handlers[event_type])

        # Wildcard handlers
        handlers.extend(self._wildcard_handlers)

        return handlers

    def _get_callbacks_for_event(self, event: DomainEvent) -> List[Callable]:
        """Get all callbacks for a given event."""
        callbacks = []

        # Type-specific callbacks
        event_type = event.event_type
        if event_type in self._callbacks:
            callbacks.extend(self._callbacks[event_type])

        # Wildcard callbacks
        callbacks.extend(self._wildcard_callbacks)

        return callbacks

    async def _dispatch_to_handler(
        self, handler: EventHandler, event: DomainEvent
    ) -> None:
        """
        Dispatch event to a handler with retry logic.

        Args:
            handler: Event handler
            event: Domain event

        Raises:
            Exception: If handler fails after retries
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                await handler.handle(event)
                return  # Success!

            except Exception as e:
                last_exception = e

                logger.warning(
                    f"Handler {handler.__class__.__name__} failed "
                    f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                )

                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay_seconds * (attempt + 1))

        # All retries exhausted
        raise last_exception

    async def _dispatch_to_callback(
        self, callback: Callable, event: DomainEvent
    ) -> None:
        """
        Dispatch event to a callback with retry logic.

        Args:
            callback: Callback function
            event: Domain event

        Raises:
            Exception: If callback fails after retries
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                # Check if callback is async
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)

                return  # Success!

            except Exception as e:
                last_exception = e

                logger.warning(
                    f"Callback failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                )

                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay_seconds * (attempt + 1))

        # All retries exhausted
        raise last_exception

    async def _persist_to_redis(self, event: DomainEvent) -> None:
        """
        Persist event to Redis Streams.

        Args:
            event: Domain event to persist

        Raises:
            asyncio.CancelledError: Always propagated
            Exception: If persistence fails
        """
        if not self.redis_client:
            return

        try:
            # Create stream key from event type (e.g., "events:WorkItemCreated")
            stream_key = f"{self.redis_stream_prefix}:{event.event_type}"

            # Serialize event to dictionary
            event_dict = event.to_dict()

            # Add to Redis Stream
            await self.redis_client.xadd(
                name=stream_key,
                fields={
                    "event_id": str(event.event_id),
                    "aggregate_id": event.aggregate_id,
                    "aggregate_type": event.aggregate_type,
                    "timestamp": event.occurred_at.isoformat(),
                    "payload": str(event_dict),
                },
            )

            self._stats["events_persisted"] += 1

            logger.debug(
                f"Persisted event {event.event_type} "
                f"(ID: {event.event_id}) to Redis stream {stream_key}"
            )

        except asyncio.CancelledError:
            # Always propagate cancellation - don't suppress system signals
            raise
        except ConnectionError as e:
            self._stats["persistence_errors"] += 1
            logger.error(
                f"Redis connection error persisting event {event.event_type}: {e}",
                exc_info=True,
                extra={
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "error_type": "redis_connection"
                }
            )
            # Don't raise - persistence failure shouldn't block event handling
        except Exception as e:
            self._stats["persistence_errors"] += 1
            logger.critical(
                f"Unexpected error persisting event {event.event_type}: {e}",
                exc_info=True,
                extra={
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "error_type": "unexpected"
                }
            )
            # Don't raise - persistence failure shouldn't block event handling

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get event bus statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            **self._stats,
            "total_handlers": sum(len(handlers) for handlers in self._handlers.values())
            + len(self._wildcard_handlers),
            "total_callbacks": sum(
                len(callbacks) for callbacks in self._callbacks.values()
            )
            + len(self._wildcard_callbacks),
            "handlers_by_type": {
                event_type: len(handlers)
                for event_type, handlers in self._handlers.items()
            },
            "wildcard_handlers": len(self._wildcard_handlers),
            "wildcard_callbacks": len(self._wildcard_callbacks),
            "redis_enabled": bool(self.redis_client),
        }

    def reset_statistics(self) -> None:
        """Reset statistics (for testing)."""
        self._stats = {
            "events_published": 0,
            "events_handled": 0,
            "handler_errors": 0,
        }


# Decorator for easy handler registration

def event_handler(*event_types: str):
    """
    Decorator to mark a class as an event handler.

    Usage:
        @event_handler("WorkItemCreated", "WorkItemCompleted")
        class MyHandler(EventHandler):
            async def handle(self, event: DomainEvent):
                # Process event
                pass

    Args:
        *event_types: Event types to handle (class names)
    """

    def decorator(cls: Type[EventHandler]) -> Type[EventHandler]:
        # Store event types on the class
        def get_event_types(self) -> List[str]:
            return list(event_types)

        cls.get_event_types = get_event_types

        return cls

    return decorator
