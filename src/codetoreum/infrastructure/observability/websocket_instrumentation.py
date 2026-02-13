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
            "websocket.session",
            kind=SpanKind.SERVER,
            attributes={
                "websocket.client.id": connection_id,
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
                exc_info=True,
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
            logger.warning(f"Error adding session event: {e}", exc_info=True)


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
        connection_id: str,
        subscription_type: Optional[str] = None,
        filter_count: int = 0,
    ) -> Optional[Any]:
        """
        Start a MESSAGE span for subscribe operation.

        Args:
            connection_id: Client connection ID
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
                "websocket.client.id": connection_id,
                "websocket.message.type": "subscribe",
                "websocket.event": "subscribe",
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

    def start_unsubscribe_message(
        self, connection_id: str, subscription_id: str
    ) -> Optional[Any]:
        """
        Start a MESSAGE span for unsubscribe operation.

        Args:
            connection_id: Client connection ID
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
                "websocket.client.id": connection_id,
                "websocket.message.type": "unsubscribe",
                "websocket.event": "unsubscribe",
                "websocket.subscription_id": subscription_id,
                "component": "websocket_adapter",
            },
        )

        logger.debug(
            f"Started MESSAGE span for unsubscribe",
            extra={"span_id": span.get_span_context().span_id if span else None},
        )

        return span

    def start_ping_message(self, connection_id: str) -> Optional[Any]:
        """
        Start a MESSAGE span for ping operation.

        Args:
            connection_id: Client connection ID

        Returns:
            Span object if OpenTelemetry available, None otherwise
        """
        if not self._tracer:
            return None

        span = self._tracer.start_span(
            "websocket.message.ping",
            kind=SpanKind.INTERNAL,
            attributes={
                "websocket.client.id": connection_id,
                "websocket.message.type": "ping",
                "websocket.event": "ping",
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
        connection_id: str,
        event_type: str,
        event_id: str,
        subscription_type: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Start a MESSAGE span for event delivery to client.

        This span tracks when the server sends a buffered event to the WebSocket client.
        It links to the original event's trace context for distributed tracing.

        Args:
            connection_id: Client connection ID
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
                "websocket.client.id": connection_id,
                "websocket.message.type": "event_delivery",
                "websocket.event": "event_delivery",
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
            logger.warning(f"Error ending message span: {e}", exc_info=True)

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
            logger.debug(f"Could not link to event trace context: {e}", exc_info=True)
