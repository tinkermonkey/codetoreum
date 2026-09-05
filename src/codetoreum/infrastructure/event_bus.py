"""In-process event bus for real-time event handling with optional Redis persistence.

Includes W3C Trace Context propagation to support distributed tracing through
the event bus. Trace context is automatically:
- Injected into events when published (captures current span)
- Extracted from events when handling them (activates parent span)
- Stored in event.metadata['traceparent'] in W3C format

This enables complete trace correlation across async event handlers.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.observability.trace_context_propagation import (
    extract_and_activate_trace_context,
    inject_current_trace_context_into_event,
)

logger = logging.getLogger(__name__)

# Optional OpenTelemetry support for span creation
try:
    from opentelemetry import context
    from opentelemetry.trace import SpanKind

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    SpanKind = None
    context = None

# Optional Redis support (client passed in at construction time)
try:
    import redis  # noqa: F401 - import for availability check

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class EventBusError(Exception):
    """Raised when event bus operations fail."""


class EventHandler:
    """
    Base class for event handlers.

    Event handlers process events in real-time as they are published
    to the event bus.
    """

    async def handle(self, event: CodetoreumEvent) -> None:
        """
        Handle an event.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails
        """
        message = "Subclasses must implement handle()"
        raise NotImplementedError(message)

    def get_event_types(self) -> list[str]:
        """
        Get list of event types this handler processes.

        Returns:
            List of event type names (class names)
        """
        message = "Subclasses must implement get_event_types()"
        raise NotImplementedError(message)


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
        async def my_callback(event: CodetoreumEvent):
            print(f"Received: {event.event_type}")

        bus.subscribe("WorkItemCreated", my_callback)
        await bus.publish(WorkItemCreated(...))
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
        redis_client: Any | None = None,
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
        self._handlers: dict[str, list[EventHandler]] = {}

        # Callback registry: event_type -> list of callbacks
        self._callbacks: dict[str, list[Callable]] = {}

        # Wildcard handlers (receive all events)
        self._wildcard_handlers: list[EventHandler] = []
        self._wildcard_callbacks: list[Callable] = []

        # In-flight detached (fire-and-forget) publishes, tracked so drain() can
        # await them on shutdown. See publish_detached()/drain().
        self._detached_publishes: set[asyncio.Task] = set()

        # Statistics
        self._stats = {
            "events_published": 0,
            "events_published_detached": 0,
            "events_handled": 0,
            "handler_errors": 0,
            "detached_publish_errors": 0,
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
                logger.info(f"Registered wildcard handler: {handler.__class__.__name__}")
            else:
                for event_type in event_types:
                    if event_type not in self._handlers:
                        self._handlers[event_type] = []

                    self._handlers[event_type].append(handler)

                logger.info(f"Registered handler {handler.__class__.__name__} for event types: {event_types}")

        except Exception as e:
            logger.error(
                f"Failed to register handler {handler.__class__.__name__}: {e}",
                exc_info=True,
                extra={
                    "handler_class": handler.__class__.__name__,
                    "error_id": "ERR_HANDLER_REGISTRATION",
                },
            )
            message = f"Failed to register handler: {e}"
            raise EventBusError(message) from e

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

    def subscribe(self, event_type: str | None, callback: Callable[[CodetoreumEvent], Any]) -> None:
        """
        Subscribe to events with a callback function.

        Args:
            event_type: Event type to subscribe to (None for all events)
            callback: Callback function (can be sync or async)

        Raises:
            EventBusError: If subscription fails
        """
        try:
            if event_type is None:
                # Wildcard subscription
                self._wildcard_callbacks.append(callback)
                logger.info("Subscribed callback to all events")
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
                    "callback": callback.__name__ if hasattr(callback, "__name__") else str(callback),
                    "error_id": "ERR_CALLBACK_SUBSCRIPTION",
                },
            )
            message = f"Failed to subscribe callback: {e}"
            raise EventBusError(message) from e

    def unsubscribe(self, event_type: str | None, callback: Callable[[CodetoreumEvent], Any]) -> None:
        """
        Unsubscribe a callback.

        Args:
            event_type: Event type (None for wildcard)
            callback: Callback to unsubscribe
        """
        if event_type is None:
            if callback in self._wildcard_callbacks:
                self._wildcard_callbacks.remove(callback)
        elif event_type in self._callbacks:
            if callback in self._callbacks[event_type]:
                self._callbacks[event_type].remove(callback)

            # Clean up empty lists
            if not self._callbacks[event_type]:
                del self._callbacks[event_type]

        logger.info(f"Unsubscribed callback from event type: {event_type}")

    async def publish(self, event: CodetoreumEvent) -> None:
        """
        Publish an event to all registered handlers and callbacks.

        Also persists event to Redis Streams if Redis client is configured.

        W3C Trace Context Propagation:
        - Injects trace context into event.metadata['traceparent']
        - Handlers can extract and continue the trace
        - Use InstrumentedEventBus wrapper for PRODUCER/CONSUMER span creation

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
            # Inject current trace context into event for downstream propagation
            inject_current_trace_context_into_event(event)

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
                                "error_type": type(result).__name__,
                                "error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR,
                            },
                        )
                        self._stats["handler_errors"] += 1

            self._stats["events_handled"] += len(handlers) + len(callbacks)

            logger.debug(
                f"Published event {event.event_type} to {len(handlers)} handlers and {len(callbacks)} callbacks"
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
                    "error_id": "ERR_EVENT_BUS_CONNECTION",
                },
            )
            message = f"Connection error publishing event: {e}. This may be transient - please retry."
            raise EventBusError(message) from e
        except ValueError as e:
            # Validation errors - permanent issues with event data
            logger.error(
                f"Validation error publishing event {event.event_type}: {e}",
                exc_info=True,
                extra={
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "error_id": "ERR_EVENT_BUS_VALIDATION",
                },
            )
            message = f"Invalid event data: {e}. Please check event structure."
            raise EventBusError(message) from e
        except Exception as e:
            # Unexpected errors that don't fit other categories
            logger.critical(
                f"Unexpected error publishing event {event.event_type}: {e}",
                exc_info=True,
                extra={
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "error_id": "ERR_EVENT_BUS_UNEXPECTED",
                },
            )
            message = f"Unexpected error publishing event: {e}"
            raise EventBusError(message) from e

    async def publish_batch(self, events: list[CodetoreumEvent]) -> None:
        """
        Publish multiple events.

        Args:
            events: List of domain events to publish

        Raises:
            EventBusError: If publishing fails
        """
        for event in events:
            await self.publish(event)

    def publish_detached(
        self,
        event: CodetoreumEvent,
        *,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> "asyncio.Task[None]":
        """
        Fire-and-forget publish, tracked by the bus so drain() can await it.

        This is the ONE standardized primitive for detached event publication.
        Callers that must not block on the handler chain (e.g. the agent
        executor publishing `AgentExecutionCompletedEvent` -- awaiting it inline
        would keep the work item "executing" across auto-progression and risk a
        re-trigger loop) use this instead of a raw `asyncio.create_task(
        publish(...))`. Centralizing it gives every such publish uniform error
        logging AND makes the in-flight task drainable on shutdown.

        **Durability boundary (read before relying on this for correctness):**
        The publish is still at-most-once across a process restart. `drain()`
        (called from bootstrap teardown) closes the *graceful* shutdown window by
        awaiting in-flight publishes; it does NOT protect against a hard crash in
        the ~handler-chain window. Crash recovery requires durable delivery
        (consumer group / transactional outbox) for the must-not-lose handler
        class -- see ADR-0001. The advance/side-effect handlers reached this way
        MUST therefore remain idempotent.

        Args:
            event: Domain event to publish.
            on_error: Optional callback invoked (synchronously, from the task's
                done-callback) with the exception if the publish task fails. The
                bus already logs the failure at error level; use this only to
                trigger additional remediation (e.g. a recovery service). Any
                task the callback schedules is the caller's to track.

        Returns:
            The created task. Callers generally do not need it (the bus tracks
            and drains it), but it is returned for tests and advanced callers.
        """
        task = asyncio.create_task(self.publish(event))
        self._detached_publishes.add(task)
        self._stats["events_published_detached"] += 1

        def _on_done(t: "asyncio.Task[None]") -> None:
            self._detached_publishes.discard(t)
            try:
                exc = t.exception()
            except asyncio.CancelledError:
                return
            if exc is None:
                return
            self._stats["detached_publish_errors"] += 1
            logger.error(
                f"Detached publish failed for {event.event_type} (id={event.event_id}): {exc}",
                exc_info=exc,
                extra={
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR,
                },
            )
            if on_error is not None:
                try:
                    on_error(exc)
                except Exception:
                    logger.error(
                        f"on_error callback raised while handling detached-publish " f"failure for {event.event_type}",
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR},
                    )

        task.add_done_callback(_on_done)
        return task

    async def drain(self, timeout: float = 10.0) -> int:
        """
        Await all in-flight detached publishes so their handler side effects
        complete before shutdown.

        Closes the graceful-shutdown loss window for `publish_detached()`: a
        completion publish issued just before teardown gets a chance to finish
        its handler chain (lock release, board advance, persistence) instead of
        being killed with the event loop. Call this in bootstrap teardown AFTER
        stopping the sources of new events (scheduler, board polls) and BEFORE
        closing the event/persistence stores the handlers write to.

        Args:
            timeout: Max seconds to wait for in-flight publishes to finish.

        Returns:
            Number of detached publishes still pending after the timeout
            (0 == fully drained). A non-zero return is logged at WARNING because
            those handler side effects may be lost.
        """
        pending = [t for t in self._detached_publishes if not t.done()]
        if not pending:
            return 0
        logger.info(f"Draining {len(pending)} in-flight detached event publish(es) (timeout={timeout:.1f}s)...")
        _done, still_pending = await asyncio.wait(pending, timeout=timeout)
        if still_pending:
            logger.warning(
                f"Event bus drain timed out: {len(still_pending)} detached publish(es) did not "
                f"complete within {timeout:.1f}s; their handler side effects may be lost.",
                extra={"error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR},
            )
            return len(still_pending)
        logger.info(f"Event bus drain complete: {len(pending)} detached publish(es) finished.")
        return 0

    def _get_handlers_for_event(self, event: CodetoreumEvent) -> list[EventHandler]:
        """Get all handlers for a given event."""
        handlers = []

        # Type-specific handlers
        event_type = event.event_type
        if event_type in self._handlers:
            handlers.extend(self._handlers[event_type])

        # Wildcard handlers
        handlers.extend(self._wildcard_handlers)

        return handlers

    def _get_callbacks_for_event(self, event: CodetoreumEvent) -> list[Callable]:
        """Get all callbacks for a given event."""
        callbacks = []

        # Type-specific callbacks
        event_type = event.event_type
        if event_type in self._callbacks:
            callbacks.extend(self._callbacks[event_type])

        # Wildcard callbacks
        callbacks.extend(self._wildcard_callbacks)

        return callbacks

    async def _dispatch_to_handler(self, handler: EventHandler, event: CodetoreumEvent) -> None:
        """
        Dispatch event to a handler with retry logic and trace context.

        W3C Trace Context Propagation:
        - Extracts trace context from event.metadata['traceparent']
        - Activates it in the current execution context
        - Enables CONSUMER spans to be created as children of the event's trace
        - Use InstrumentedEventBus wrapper for automatic CONSUMER span creation

        Args:
            handler: Event handler
            event: Domain event

        Raises:
            Exception: If handler fails after retries
        """
        last_exception = None

        # Extract and activate trace context from event once (outside retry loop)
        # This ensures the handler's spans are children of the event's trace
        ctx = extract_and_activate_trace_context(event)

        for attempt in range(self.max_retries + 1):
            try:
                # Attach context BEFORE calling handler so trace context is active
                token = None
                if ctx:
                    token = context.attach(ctx)

                try:
                    # Call handler
                    # Note: CONSUMER span creation is handled by InstrumentedEventBus wrapper
                    # to avoid duplicate spans. EventBus only provides trace context propagation.
                    await handler.handle(event)
                    return  # Success!

                finally:
                    if token:
                        context.detach(token)

            except Exception as e:
                last_exception = e

                logger.warning(
                    f"Handler {handler.__class__.__name__} failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}",
                    exc_info=True,
                )

                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay_seconds * (attempt + 1))

        # All retries exhausted
        raise last_exception

    async def _dispatch_to_callback(self, callback: Callable, event: CodetoreumEvent) -> None:
        """
        Dispatch event to a callback with retry logic and trace context.

        W3C Trace Context Propagation:
        - Extracts trace context from event.metadata['traceparent']
        - Activates it in the current execution context
        - Enables CONSUMER spans to be created as children of the event's trace
        - Use InstrumentedEventBus wrapper for automatic CONSUMER span creation

        Args:
            callback: Callback function
            event: Domain event

        Raises:
            Exception: If callback fails after retries
        """
        last_exception = None

        # Extract and activate trace context from event once (outside retry loop)
        # This ensures the callback's spans are children of the event's trace
        ctx = extract_and_activate_trace_context(event)

        for attempt in range(self.max_retries + 1):
            try:
                # Attach context BEFORE calling callback so trace context is active
                token = None
                if ctx:
                    token = context.attach(ctx)

                try:
                    # Check if callback is async
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)

                    return  # Success!

                finally:
                    if token:
                        context.detach(token)

            except Exception as e:
                last_exception = e

                logger.warning(
                    f"Callback failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}",
                    exc_info=True,
                )

                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay_seconds * (attempt + 1))

        # All retries exhausted
        raise last_exception

    async def _persist_to_redis(self, event: CodetoreumEvent) -> None:
        """
        Persist event to Redis Streams with INTERNAL span.

        OpenTelemetry Instrumentation:
        - Creates INTERNAL span for Redis persistence operation
        - Includes event attributes in span

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

            # Serialize event to dictionary (includes metadata with trace context)
            event_dict = event.to_dict()

            # Add to Redis Stream
            await self.redis_client.xadd(
                name=stream_key,
                fields={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "timestamp": event.timestamp,
                    "source": event.source,
                    "payload": str(event_dict),
                },
            )

            self._stats["events_persisted"] += 1

            logger.debug(f"Persisted event {event.event_type} (ID: {event.event_id}) to Redis stream {stream_key}")

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
                    "error_type": "redis_connection",
                    "error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR,
                },
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
                    "error_type": "unexpected",
                },
            )
            # Don't raise - persistence failure shouldn't block event handling

    def get_statistics(self) -> dict[str, Any]:
        """
        Get event bus statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            **self._stats,
            "total_handlers": sum(len(handlers) for handlers in self._handlers.values()) + len(self._wildcard_handlers),
            "total_callbacks": sum(len(callbacks) for callbacks in self._callbacks.values())
            + len(self._wildcard_callbacks),
            "handlers_by_type": {event_type: len(handlers) for event_type, handlers in self._handlers.items()},
            "wildcard_handlers": len(self._wildcard_handlers),
            "wildcard_callbacks": len(self._wildcard_callbacks),
            "redis_enabled": bool(self.redis_client),
            "detached_publishes_inflight": sum(1 for t in self._detached_publishes if not t.done()),
        }

    def reset_statistics(self) -> None:
        """Reset statistics (for testing)."""
        self._stats = {
            "events_published": 0,
            "events_published_detached": 0,
            "events_handled": 0,
            "handler_errors": 0,
            "detached_publish_errors": 0,
            "events_persisted": 0,
            "persistence_errors": 0,
        }


# Decorator for easy handler registration


def event_handler(*event_types: str):
    """
    Decorator to mark a class as an event handler.

    Usage:
        @event_handler("WorkItemCreated", "WorkItemCompleted")
        class MyHandler(EventHandler):
            async def handle(self, event: CodetoreumEvent):
                # Process event
                pass

    Args:
        *event_types: Event types to handle (class names)
    """

    def decorator(cls: type[EventHandler]) -> type[EventHandler]:
        # Store event types on the class as both a class attribute and a method
        cls.event_types = list(event_types)

        def get_event_types(self) -> list[str]:
            return list(event_types)

        cls.get_event_types = get_event_types

        return cls

    return decorator
