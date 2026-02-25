"""Event Bus Instrumentation with OpenTelemetry Spans

Provides InstrumentedEventBus wrapper that adds OpenTelemetry span creation
to the event bus with W3C Trace Context propagation.

Creates:
- PRODUCER spans when publishing events
- CONSUMER spans when handling events

All spans are linked via trace context to enable complete distributed tracing.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

try:
    from opentelemetry import context as otel_context
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    SpanKind = None
    otel_context = None

from codetoreum.domain.events import DomainEvent
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.observability.trace_context_propagation import (
    TraceContextPropagator,
    extract_and_activate_trace_context,
    inject_current_trace_context_into_event,
)

if TYPE_CHECKING:
    from codetoreum.infrastructure.event_bus import EventBus, EventHandler

logger = logging.getLogger(__name__)


class InstrumentedEventBus:
    """
    Wraps EventBus with OpenTelemetry instrumentation for distributed tracing.

    Creates PRODUCER and CONSUMER spans for all events published/handled through
    the bus, with proper parent-child relationships via W3C Trace Context.

    Usage:
        event_bus = EventBus()
        instrumented_bus = InstrumentedEventBus(event_bus)

        # PRODUCER span created automatically
        await instrumented_bus.publish(event)

        # CONSUMER spans created automatically for handlers
    """

    def __init__(self, event_bus: "EventBus"):
        """
        Initialize instrumented event bus.

        Args:
            event_bus: EventBus instance to wrap
        """
        self._event_bus = event_bus
        self._tracer = trace.get_tracer(__name__) if OPENTELEMETRY_AVAILABLE else None

    async def publish(self, event: DomainEvent) -> None:
        """
        Publish event with PRODUCER span and trace context injection.

        Creates a PRODUCER span capturing:
        - event.type: Event class name
        - event.id: Unique event ID
        - aggregate.id: Aggregate being modified
        - aggregate.type: Type of aggregate

        If the event already has trace context, the PRODUCER span will be created
        as part of the existing trace. Otherwise, a new trace is started.

        Args:
            event: Domain event to publish

        Raises:
            EventBusError: If publishing fails
        """
        if not self._tracer:
            # OpenTelemetry not available - delegate to wrapped bus
            await self._event_bus.publish(event)
            return

        span_name = f"event.publish.{event.event_type}"

        # Extract trace context from event (if present) to continue upstream trace in PRODUCER span.
        # This does NOT modify the event. Instead, it extracts the context and creates a new
        # context token in the current execution context, allowing the PRODUCER span to be
        # a child of the upstream trace.
        trace_context = extract_and_activate_trace_context(event)
        token = None

        try:
            if trace_context:
                # Attach existing trace context before creating PRODUCER span
                token = otel_context.attach(trace_context)

            with self._tracer.start_as_current_span(
                span_name,
                kind=SpanKind.PRODUCER,
                attributes={
                    "event.type": event.event_type,
                    "event.id": str(event.event_id),
                    "aggregate.id": str(event.aggregate_id),
                    "aggregate.type": event.aggregate_type,
                },
            ) as span:
                logger.debug(
                    f"Created PRODUCER span for {event.event_type}",
                    extra={"span_id": span.get_span_context().span_id},
                )

                # Inject trace context into event for downstream handlers
                # Only inject if not already present to preserve existing context
                if not TraceContextPropagator.extract_trace_context(event):
                    inject_current_trace_context_into_event(event)

                # Delegate to wrapped event bus
                await self._event_bus.publish(event)
        finally:
            if token:
                otel_context.detach(token)

    async def publish_batch(self, events: list[DomainEvent]) -> None:
        """
        Publish multiple events.

        Each event gets its own PRODUCER span.

        Args:
            events: List of domain events to publish

        Raises:
            EventBusError: If publishing fails
        """
        for event in events:
            await self.publish(event)

    def register_handler(self, handler: "EventHandler") -> None:
        """
        Register an event handler.

        Args:
            handler: Event handler instance

        Raises:
            EventBusError: If registration fails
        """
        # Wrap handler to add CONSUMER span
        wrapped_handler = InstrumentedEventHandler(handler, self._tracer)
        self._event_bus.register_handler(wrapped_handler)

    def unregister_handler(self, handler: "EventHandler") -> None:
        """
        Unregister an event handler.

        **Design Note on Private Attribute Access:**
        This method directly accesses private EventBus attributes (_handlers, _wildcard_handlers)
        to find and remove instrumented handler wrappers. This is intentional to support the
        decorator pattern: we wrap each handler to add instrumentation, then need to find the
        wrapped version to unregister.

        The alternative would be to add public methods like get_registered_handlers() to EventBus,
        but this adds API surface for a single use case. The current design:
        - Keeps EventBus API minimal
        - Documents the encapsulation boundary clearly
        - Remains resilient: EventBus refactoring is documented in this location
        - Follows Python conventions: accessing internals with clear intent is acceptable when documented

        Args:
            handler: Event handler instance
        """
        # Find and remove wrapped handler
        for event_type, handlers in list(self._event_bus._handlers.items()):
            for h in handlers:
                if isinstance(h, InstrumentedEventHandler) and h._handler == handler:
                    self._event_bus.unregister_handler(h)
                    return

        # Check wildcard handlers
        for h in self._event_bus._wildcard_handlers:
            if isinstance(h, InstrumentedEventHandler) and h._handler == handler:
                self._event_bus.unregister_handler(h)
                return

    def subscribe(
        self, event_type: str | None, callback: Callable[[DomainEvent], Any]
    ) -> None:
        """
        Subscribe to events with a callback function.

        Args:
            event_type: Event type to subscribe to (None for all events)
            callback: Async callback function

        Raises:
            EventBusError: If subscription fails
        """
        # Wrap callback to add CONSUMER span
        wrapped_callback = self._create_instrumented_callback(callback)
        self._event_bus.subscribe(event_type, wrapped_callback)

    def unsubscribe(
        self, event_type: str | None, callback: Callable[[DomainEvent], Any]
    ) -> None:
        """
        Unsubscribe a callback.

        Args:
            event_type: Event type (None for wildcard)
            callback: Callback to unsubscribe
        """
        # Find and remove wrapped callback
        callbacks = (
            self._event_bus._wildcard_callbacks
            if event_type is None
            else self._event_bus._callbacks.get(event_type, [])
        )

        # Look for wrapped version
        for i, cb in enumerate(callbacks):
            if hasattr(cb, "__wrapped__") and cb.__wrapped__ == callback:
                self._event_bus.unsubscribe(event_type, cb)
                return

    def get_stats(self) -> dict:
        """
        Get event bus statistics.

        Returns:
            Dictionary of stats from wrapped bus
        """
        return self._event_bus.get_statistics()

    def _create_instrumented_callback(
        self, callback: Callable[[DomainEvent], Any]
    ) -> Callable[[DomainEvent], Any]:
        """
        Create instrumented version of callback that adds CONSUMER span.

        Args:
            callback: Original callback function

        Returns:
            Wrapped callback with CONSUMER span
        """
        if not self._tracer:
            return callback

        async def instrumented_callback(event: DomainEvent) -> Any:
            span_name = f"event.handle.{event.event_type}"

            # Extract trace context from event to link CONSUMER to PRODUCER
            trace_context = extract_and_activate_trace_context(event)

            with self._tracer.start_as_current_span(
                span_name,
                context=trace_context,
                kind=SpanKind.CONSUMER,
                attributes={
                    "event.type": event.event_type,
                    "event.id": str(event.event_id),
                    "aggregate.id": str(event.aggregate_id),
                    "aggregate.type": event.aggregate_type,
                    "handler.class": callback.__name__,
                },
            ) as span:
                logger.debug(
                    f"Created CONSUMER span for callback {callback.__name__}",
                    extra={"span_id": span.get_span_context().span_id},
                )

                # Call original callback with exception handling
                try:
                    if hasattr(callback, "__call__"):
                        result = callback(event)
                        if hasattr(result, "__await__"):
                            return await result
                        return result
                except Exception as e:
                    # Record exception in span
                    span.set_attribute("exception.type", type(e).__name__)
                    span.set_attribute("exception.message", str(e))
                    span.record_exception(e)
                    raise

        # Store reference to original callback for unsubscribe
        instrumented_callback.__wrapped__ = callback
        return instrumented_callback


class InstrumentedEventHandler:
    """
    Wraps EventHandler to add CONSUMER span creation.

    The wrapper creates a CONSUMER span when the handler processes an event,
    linking it to the PRODUCER span via extracted trace context.
    """

    def __init__(
        self, handler: "EventHandler", tracer: Any | None = None
    ):
        """
        Initialize instrumented event handler.

        Args:
            handler: Event handler to wrap
            tracer: OpenTelemetry tracer (None if not available)
        """
        self._handler = handler
        self._tracer = tracer

    async def handle(self, event: DomainEvent) -> None:
        """
        Handle event with CONSUMER span.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handler fails
        """
        if not self._tracer:
            # OpenTelemetry not available - delegate to wrapped handler
            await self._handler.handle(event)
            return

        span_name = f"event.handle.{event.event_type}"

        # Extract trace context from event to link CONSUMER to PRODUCER
        trace_context = extract_and_activate_trace_context(event)

        with self._tracer.start_as_current_span(
            span_name,
            context=trace_context,
            kind=SpanKind.CONSUMER,
            attributes={
                "event.type": event.event_type,
                "event.id": str(event.event_id),
                "aggregate.id": str(event.aggregate_id),
                "aggregate.type": event.aggregate_type,
                "handler.class": self._handler.__class__.__name__,
            },
        ) as span:
            logger.debug(
                f"Created CONSUMER span for handler {self._handler.__class__.__name__}",
                extra={"span_id": span.get_span_context().span_id},
            )

            # Delegate to wrapped handler with exception instrumentation
            try:
                await self._handler.handle(event)
            except Exception as e:
                # Record exception in span for distributed tracing
                span.set_attribute("exception.type", type(e).__name__)
                span.set_attribute("exception.message", str(e))
                span.record_exception(e)

                # Log to application logger for operator visibility
                logger.error(
                    f"Event handler {self._handler.__class__.__name__} failed "
                    f"processing {event.event_type}: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION}
                )
                raise

    def get_event_types(self) -> list[str]:
        """
        Get event types handled by wrapped handler.

        Returns:
            List of event type names
        """
        return self._handler.get_event_types()
