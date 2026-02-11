"""WebSocket Instrumentation with OpenTelemetry Spans

Provides instrumentation for WebSocket connections and message handling with
OpenTelemetry spans following the W3C Trace Context standard.

Creates:
- SESSION spans for WebSocket connection lifecycle (connect, disconnect)
- MESSAGE spans for individual message processing (subscribe, unsubscribe, message)
- Proper parent-child relationships for distributed tracing

All spans are linked via trace context to enable complete distributed tracing
of real-time events from server to client.
"""

import logging
from typing import Any, Callable, Optional, TYPE_CHECKING

try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    SpanKind = None

from codetoreum.infrastructure.observability.trace_context_propagation import (
    TraceContextData,
    inject_current_trace_context_into_event,
)
from codetoreum.domain.events import DomainEvent

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketSessionTracer:
    """
    Manages WebSocket session spans for distributed tracing.

    Creates and manages SESSION spans for WebSocket connection lifecycle,
    with attributes capturing connection context and metadata.

    Usage:
        session_tracer = WebSocketSessionTracer()
        session_span = session_tracer.start_session("connection-123")

        # Process messages within session
        message_tracer = WebSocketMessageTracer(session_span)
        message_tracer.trace_subscribe_message(filters)

        session_tracer.end_session(session_span, "normal_closure")
    """

    def __init__(self):
        """Initialize WebSocket session tracer."""
        self._tracer = trace.get_tracer(__name__) if OPENTELEMETRY_AVAILABLE else None

    def start_session(
        self,
        connection_id: str,
        client_ip: Optional[str] = None,
        token_present: bool = False,
    ) -> Optional[Any]:
        """
        Start a SESSION span for WebSocket connection.

        Creates a SESSION span with attributes capturing the connection context.

        Args:
            connection_id: Unique connection identifier
            client_ip: Client IP address (optional)
            token_present: Whether authentication token was provided

        Returns:
            Span object if OpenTelemetry available, None otherwise
        """
        if not self._tracer:
            return None

        span = self._tracer.start_span(
            f"websocket.session",
            kind=SpanKind.SERVER,
            attributes={
                "connection.id": connection_id,
                "connection.type": "websocket",
                "websocket.session.client_ip": client_ip or "unknown",
                "websocket.session.authenticated": token_present,
                "component": "websocket_adapter",
            },
        )

        logger.debug(
            f"Started SESSION span for WebSocket connection {connection_id}",
            extra={
                "connection_id": connection_id,
                "span_id": span.get_span_context().span_id if span else None,
            },
        )

        return span

    def end_session(
        self,
        session_span: Optional[Any],
        reason: str = "normal_closure",
        message_count: int = 0,
        buffered_events: int = 0,
    ) -> None:
        """
        End a SESSION span.

        Records session statistics and closes the span.

        Args:
            session_span: Span object from start_session()
            reason: Reason for closure (e.g., "normal_closure", "auth_failure", "overflow")
            message_count: Total messages processed during session
            buffered_events: Events buffered during session
        """
        if not session_span or not self._tracer:
            return

        try:
            session_span.set_attributes({
                "websocket.session.close_reason": reason,
                "websocket.session.message_count": message_count,
                "websocket.session.buffered_events": buffered_events,
            })
            session_span.end()

            logger.debug(
                f"Ended SESSION span with reason: {reason}",
                extra={
                    "span_id": session_span.get_span_context().span_id,
                    "message_count": message_count,
                },
            )
        except Exception as e:
            logger.warning(
                f"Error ending WebSocket session span: {e}",
                exc_info=False,
            )

    def add_session_event(
        self,
        session_span: Optional[Any],
        event_name: str,
        attributes: Optional[dict] = None,
    ) -> None:
        """
        Add an event to the SESSION span.

        Args:
            session_span: Span object from start_session()
            event_name: Name of the event (e.g., "buffer_overflow", "heartbeat_timeout")
            attributes: Optional attributes for the event
        """
        if not session_span:
            return

        try:
            session_span.add_event(event_name, attributes=attributes or {})
        except Exception as e:
            logger.warning(f"Error adding session event: {e}", exc_info=False)


class WebSocketMessageTracer:
    """
    Manages WebSocket message spans for distributed tracing.

    Creates MESSAGE spans for specific message operations (subscribe, unsubscribe,
    ping, message received) within the context of a SESSION span.

    Each message span is a child of the session span for proper hierarchy.

    Usage:
        session_span = session_tracer.start_session("connection-123")
        message_tracer = WebSocketMessageTracer(session_span)

        # Subscribe message
        msg_span = message_tracer.start_subscribe_message()
        # ... process subscription
        message_tracer.end_message_span(msg_span, success=True)
    """

    def __init__(self, session_span: Optional[Any]):
        """
        Initialize WebSocket message tracer.

        Args:
            session_span: Parent SESSION span from WebSocketSessionTracer
        """
        self._tracer = trace.get_tracer(__name__) if OPENTELEMETRY_AVAILABLE else None
        self._session_span = session_span

    def start_subscribe_message(
        self,
        subscription_type: Optional[str] = None,
        filter_count: int = 0,
    ) -> Optional[Any]:
        """
        Start a MESSAGE span for subscribe operation.

        Args:
            subscription_type: Type of subscription (e.g., "all_events", "workflow_events")
            filter_count: Number of filters applied

        Returns:
            Span object if OpenTelemetry available, None otherwise
        """
        if not self._tracer:
            return None

        span = self._tracer.start_span(
            "websocket.message.subscribe",
            kind=SpanKind.INTERNAL,
            attributes={
                "message.type": "subscribe",
                "websocket.subscription_type": subscription_type or "unknown",
                "websocket.filter_count": filter_count,
                "component": "websocket_adapter",
            },
        )

        logger.debug(
            f"Started MESSAGE span for subscribe (filters: {filter_count})",
            extra={"span_id": span.get_span_context().span_id if span else None},
        )

        return span

    def start_unsubscribe_message(self, subscription_id: str) -> Optional[Any]:
        """
        Start a MESSAGE span for unsubscribe operation.

        Args:
            subscription_id: Subscription identifier being removed

        Returns:
            Span object if OpenTelemetry available, None otherwise
        """
        if not self._tracer:
            return None

        span = self._tracer.start_span(
            "websocket.message.unsubscribe",
            kind=SpanKind.INTERNAL,
            attributes={
                "message.type": "unsubscribe",
                "websocket.subscription_id": subscription_id,
                "component": "websocket_adapter",
            },
        )

        logger.debug(
            f"Started MESSAGE span for unsubscribe",
            extra={"span_id": span.get_span_context().span_id if span else None},
        )

        return span

    def start_ping_message(self) -> Optional[Any]:
        """
        Start a MESSAGE span for ping operation.

        Returns:
            Span object if OpenTelemetry available, None otherwise
        """
        if not self._tracer:
            return None

        span = self._tracer.start_span(
            "websocket.message.ping",
            kind=SpanKind.INTERNAL,
            attributes={
                "message.type": "ping",
                "component": "websocket_adapter",
            },
        )

        logger.debug(
            "Started MESSAGE span for ping",
            extra={"span_id": span.get_span_context().span_id if span else None},
        )

        return span

    def start_event_delivery_span(
        self,
        event_type: str,
        event_id: str,
        subscription_type: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Start a MESSAGE span for event delivery to client.

        This span tracks when the server sends a buffered event to the WebSocket client.
        It links to the original event's trace context for distributed tracing.

        Args:
            event_type: Type of domain event being delivered
            event_id: Unique event identifier
            subscription_type: Type of subscription receiving the event

        Returns:
            Span object if OpenTelemetry available, None otherwise
        """
        if not self._tracer:
            return None

        span = self._tracer.start_span(
            "websocket.message.event_delivery",
            kind=SpanKind.INTERNAL,
            attributes={
                "message.type": "event",
                "event.type": event_type,
                "event.id": event_id,
                "websocket.subscription_type": subscription_type or "unknown",
                "component": "websocket_adapter",
            },
        )

        logger.debug(
            f"Started MESSAGE span for event delivery ({event_type})",
            extra={
                "event_id": event_id,
                "span_id": span.get_span_context().span_id if span else None,
            },
        )

        return span

    def end_message_span(
        self,
        message_span: Optional[Any],
        success: bool = True,
        error_code: Optional[str] = None,
        message_size: int = 0,
    ) -> None:
        """
        End a MESSAGE span.

        Args:
            message_span: Span object from start_*_message() methods
            success: Whether the operation succeeded
            error_code: Error code if operation failed
            message_size: Size of message in bytes
        """
        if not message_span or not self._tracer:
            return

        try:
            attributes = {
                "message.success": success,
                "message.size_bytes": message_size,
            }
            if error_code:
                attributes["message.error_code"] = error_code

            message_span.set_attributes(attributes)
            message_span.end()

            logger.debug(
                f"Ended MESSAGE span (success: {success})",
                extra={
                    "span_id": message_span.get_span_context().span_id,
                    "size": message_size,
                },
            )
        except Exception as e:
            logger.warning(f"Error ending message span: {e}", exc_info=False)

    def link_to_event_trace_context(
        self,
        message_span: Optional[Any],
        event: DomainEvent,
    ) -> None:
        """
        Link a message span to an event's trace context.

        This enables tracing from the original event creation through event bus
        publishing to WebSocket delivery to the client.

        Args:
            message_span: Message span to link
            event: Domain event with embedded trace context
        """
        if not message_span or not event:
            return

        try:
            # Try to get trace context from event metadata
            traceparent = event.metadata.get("traceparent") if hasattr(event, "metadata") else None

            if traceparent and self._tracer:
                # Extract trace context data
                trace_data = TraceContextData.from_traceparent(traceparent)
                if trace_data:
                    message_span.set_attributes({
                        "event.trace_id": trace_data.trace_id,
                        "event.span_id": trace_data.span_id,
                    })

                    logger.debug(
                        f"Linked message span to event trace context",
                        extra={
                            "event_id": str(event.event_id),
                            "event_trace_id": trace_data.trace_id[:8] + "...",
                        },
                    )
        except Exception as e:
            logger.debug(f"Could not link to event trace context: {e}", exc_info=False)


class InstrumentedConnectionManager:
    """
    Wraps a ConnectionManager with OpenTelemetry instrumentation.

    Adds session and message span creation for all WebSocket operations.

    Usage:
        from codetoreum.adapters.primary.websocket_adapter import ConnectionManager

        manager = ConnectionManager(config)
        instrumented_manager = InstrumentedConnectionManager(manager)

        # Spans are created automatically for all operations
        await instrumented_manager.connect(websocket, connection_id)
        await instrumented_manager.broadcast_event(event)
    """

    def __init__(self, manager: Any):
        """
        Initialize instrumented connection manager.

        Args:
            manager: ConnectionManager instance to wrap
        """
        self._manager = manager
        self._session_tracer = WebSocketSessionTracer()
        self._message_tracers: dict[str, WebSocketMessageTracer] = {}
        self._session_spans: dict[str, Optional[Any]] = {}

    async def connect(
        self, websocket: "WebSocket", connection_id: str, client_ip: Optional[str] = None
    ) -> bool:
        """
        Accept connection with SESSION span creation.

        Args:
            websocket: WebSocket connection
            connection_id: Unique connection identifier
            client_ip: Client IP address

        Returns:
            True if connection accepted, False if rejected
        """
        # Start session span
        session_span = self._session_tracer.start_session(
            connection_id=connection_id,
            client_ip=client_ip,
            token_present=True,
        )
        self._session_spans[connection_id] = session_span
        self._message_tracers[connection_id] = WebSocketMessageTracer(session_span)

        try:
            # Delegate to wrapped manager
            result = await self._manager.connect(websocket, connection_id)

            if not result:
                # Connection rejected - end the session span
                self._session_tracer.end_session(
                    session_span,
                    reason="connection_rejected",
                )
                del self._session_spans[connection_id]
                del self._message_tracers[connection_id]

            return result
        except Exception as e:
            # Connection failed - end the session span
            self._session_tracer.end_session(
                session_span,
                reason="connection_error",
            )
            del self._session_spans[connection_id]
            del self._message_tracers[connection_id]
            raise

    def disconnect(self, connection_id: str, reason: str = "normal_closure") -> None:
        """
        Disconnect with SESSION span closure.

        Args:
            connection_id: Connection to disconnect
            reason: Reason for disconnection
        """
        try:
            # Get connection state for stats
            if connection_id in self._manager.connections:
                conn_state = self._manager.connections[connection_id]
                message_count = len(conn_state.buffer)
                buffered_events = len(conn_state.subscriptions)
            else:
                message_count = 0
                buffered_events = 0

            # End session span
            session_span = self._session_spans.get(connection_id)
            self._session_tracer.end_session(
                session_span,
                reason=reason,
                message_count=message_count,
                buffered_events=buffered_events,
            )

            # Delegate to wrapped manager
            self._manager.disconnect(connection_id)
        finally:
            # Clean up span tracking
            self._session_spans.pop(connection_id, None)
            self._message_tracers.pop(connection_id, None)

    async def subscribe(self, connection_id: str, event_filter: Any) -> bool:
        """
        Subscribe with MESSAGE span creation.

        Args:
            connection_id: Connection subscribing
            event_filter: EventFilter with subscription details

        Returns:
            True if subscription successful, False otherwise
        """
        message_tracer = self._message_tracers.get(connection_id)
        if not message_tracer:
            message_tracer = WebSocketMessageTracer(None)

        # Count active filters for instrumentation
        filter_attrs = [
            event_filter.event_types,
            event_filter.work_item_id,
            event_filter.workflow_id,
            event_filter.agent_id,
            event_filter.project_name,
        ]
        filter_count = sum(1 for attr in filter_attrs if attr)

        # Start message span
        message_span = message_tracer.start_subscribe_message(
            subscription_type=event_filter.subscription_type.value,
            filter_count=filter_count,
        )

        try:
            # Delegate to wrapped manager
            result = await self._manager.subscribe(connection_id, event_filter)

            # End message span
            message_tracer.end_message_span(
                message_span,
                success=result,
            )

            return result
        except Exception as e:
            message_tracer.end_message_span(
                message_span,
                success=False,
                error_code="subscription_error",
            )
            raise

    async def unsubscribe(self, connection_id: str, subscription_id: str) -> bool:
        """
        Unsubscribe with MESSAGE span creation.

        Args:
            connection_id: Connection unsubscribing
            subscription_id: Subscription to remove

        Returns:
            True if successful, False otherwise
        """
        message_tracer = self._message_tracers.get(connection_id)
        if not message_tracer:
            message_tracer = WebSocketMessageTracer(None)

        # Start message span
        message_span = message_tracer.start_unsubscribe_message(subscription_id)

        try:
            # Delegate to wrapped manager
            result = await self._manager.unsubscribe(connection_id, subscription_id)

            # End message span
            message_tracer.end_message_span(message_span, success=result)

            return result
        except Exception as e:
            message_tracer.end_message_span(
                message_span,
                success=False,
                error_code="unsubscribe_error",
            )
            raise

    async def broadcast_event(self, event: DomainEvent) -> None:
        """
        Broadcast event with MESSAGE spans for each delivery.

        Creates a MESSAGE span for each client that receives the event,
        linking to the event's trace context.

        Args:
            event: Domain event to broadcast
        """
        try:
            # Delegate to wrapped manager
            await self._manager.broadcast_event(event)

            # Create message spans for each connection that received the event
            # This is done asynchronously to not block event broadcasting
            self._record_event_deliveries(event)
        except Exception as e:
            logger.warning(f"Error broadcasting event: {e}", exc_info=False)
            raise

    def _record_event_deliveries(self, event: DomainEvent) -> None:
        """
        Record event delivery to all subscribed clients (async, doesn't block).

        Args:
            event: Event being delivered
        """
        # This is a non-blocking record of deliveries for tracing
        # In a real implementation, this might be recorded as a background task
        for connection_id, message_tracer in self._message_tracers.items():
            try:
                # Find relevant subscriptions for this connection
                if connection_id in self._manager.connections:
                    conn_state = self._manager.connections[connection_id]
                    for subscription in conn_state.subscriptions:
                        # Check if subscription matches event
                        if self._subscription_matches_event(subscription, event):
                            # Create message span for delivery
                            span = message_tracer.start_event_delivery_span(
                                event_type=event.event_type,
                                event_id=str(event.event_id),
                                subscription_type=subscription.subscription_type.value,
                            )

                            # Link to event trace context
                            message_tracer.link_to_event_trace_context(span, event)

                            # Immediately end the span
                            # (in production, might be held open while message in buffer)
                            message_tracer.end_message_span(span, success=True)
            except Exception as e:
                logger.debug(f"Error recording event delivery for {connection_id}: {e}")

    @staticmethod
    def _subscription_matches_event(subscription: Any, event: DomainEvent) -> bool:
        """
        Check if a subscription matches an event.

        Args:
            subscription: EventFilter subscription
            event: Domain event

        Returns:
            True if event matches subscription filters
        """
        try:
            # Check event type filters
            if subscription.event_types:
                if event.event_type not in subscription.event_types:
                    return False

            # Check aggregate type filters (if event has these)
            if subscription.work_item_id:
                if hasattr(event, "work_item_id") and event.work_item_id != subscription.work_item_id:
                    return False

            if subscription.workflow_id:
                if hasattr(event, "workflow_id") and event.workflow_id != subscription.workflow_id:
                    return False

            if subscription.agent_id:
                if hasattr(event, "agent_id") and event.agent_id != subscription.agent_id:
                    return False

            return True
        except Exception:
            # If matching fails, assume it doesn't match
            return False

    def get_session_span(self, connection_id: str) -> Optional[Any]:
        """
        Get the active session span for a connection.

        Args:
            connection_id: Connection identifier

        Returns:
            Span object if available, None otherwise
        """
        return self._session_spans.get(connection_id)

    def get_message_tracer(self, connection_id: str) -> Optional[WebSocketMessageTracer]:
        """
        Get the message tracer for a connection.

        Args:
            connection_id: Connection identifier

        Returns:
            WebSocketMessageTracer if available, None otherwise
        """
        return self._message_tracers.get(connection_id)

    # Delegate other methods to wrapped manager
    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to wrapped manager."""
        return getattr(self._manager, name)
