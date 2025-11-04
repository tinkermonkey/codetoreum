"""
WebSocket API Adapter

This module implements the WebSocket adapter for real-time event streaming
and log delivery with authentication, backpressure handling, and filtering.

Features:
- Token-based authentication via query parameter
- Client-side filtering by event type, work item, workflow, agent
- Backpressure handling with buffer limits and flow control warnings
- Automatic disconnection for slow consumers
- Heartbeat/ping-pong for connection health monitoring
- Real-time event streaming from Event Store via Redis pub/sub
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from codetoreum.domain.events import DomainEvent

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes and Enums
# ============================================================================


@dataclass
class WebSocketConfig:
    """Configuration for WebSocket adapter"""

    max_buffer_size: int = 1000  # Max events buffered per client
    flow_control_threshold: float = 0.8  # Warn at 80% capacity
    disconnect_on_overflow: bool = True  # Disconnect overloaded clients
    heartbeat_interval: int = 30  # Heartbeat interval in seconds
    heartbeat_timeout: int = 90  # Time after which to consider connection dead


class SubscriptionType(Enum):
    """Type of subscription"""

    WORKFLOW_EVENTS = "workflow_events"
    EXECUTION_EVENTS = "execution_events"
    ALL_EVENTS = "all_events"
    LOGS = "logs"


@dataclass
class EventFilter:
    """
    Filter for event subscriptions.

    Supports multiple filter types:
    - event_types: List of event type names (OR logic)
    - work_item_id: Filter by work item
    - workflow_id: Filter by workflow
    - agent_id: Filter by agent
    - project_name: Filter by project

    Multiple IDs use AND logic (e.g., work_item_id AND workflow_id).
    """

    subscription_type: SubscriptionType
    workflow_run_id: Optional[str] = None
    execution_id: Optional[str] = None
    work_item_id: Optional[str] = None  # New filter
    workflow_id: Optional[str] = None  # New filter
    agent_id: Optional[str] = None  # New filter
    project_name: Optional[str] = None
    event_types: Optional[List[str]] = None  # Multiple types use OR logic


class WebSocketMessage(BaseModel):
    """Base message for WebSocket communication"""

    type: str
    data: Dict[str, Any]
    timestamp: datetime = datetime.utcnow()


class SubscribeMessage(BaseModel):
    """
    Subscribe to event stream.

    Filtering options:
    - event_types: List of event types to receive (OR logic)
    - work_item_id: Filter by work item ID
    - workflow_id: Filter by workflow ID
    - agent_id: Filter by agent ID
    - project_name: Filter by project name

    Combining filters uses AND logic.
    """

    type: str = "subscribe"
    subscription_type: str
    workflow_run_id: Optional[str] = None
    execution_id: Optional[str] = None
    work_item_id: Optional[str] = None
    workflow_id: Optional[str] = None
    agent_id: Optional[str] = None
    project_name: Optional[str] = None
    event_types: Optional[List[str]] = None


class UnsubscribeMessage(BaseModel):
    """Unsubscribe from event stream"""

    type: str = "unsubscribe"
    subscription_id: str


class EventMessage(BaseModel):
    """Event delivered to client"""

    type: str = "event"
    event_id: str
    event_type: str
    data: Dict[str, Any]
    timestamp: datetime


class LogMessage(BaseModel):
    """Log message delivered to client"""

    type: str = "log"
    execution_id: str
    level: str
    message: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class ErrorMessage(BaseModel):
    """Error message"""

    type: str = "error"
    code: str
    message: str
    timestamp: datetime


class FlowControlMessage(BaseModel):
    """Flow control warning message"""

    type: str = "flow_control"
    buffer_usage: float  # Percentage (0.0 to 1.0)
    buffer_size: int  # Current buffer size
    max_buffer_size: int  # Maximum buffer size
    message: str
    timestamp: datetime


class ConnectedMessage(BaseModel):
    """Connection established message"""

    type: str = "connected"
    client_id: str
    message: str
    timestamp: datetime


# ============================================================================
# Connection Manager
# ============================================================================


@dataclass
class ConnectionState:
    """State for a single WebSocket connection"""

    websocket: WebSocket
    subscriptions: List[EventFilter]
    buffer: List[Dict[str, Any]]  # Buffered messages
    last_heartbeat: float  # Timestamp of last heartbeat
    authenticated: bool = True  # Authentication status


class ConnectionManager:
    """
    Manages WebSocket connections and subscriptions with backpressure handling.

    This class handles connection lifecycle, subscription management,
    message broadcasting to connected clients, and backpressure management.

    Features:
    - Per-client message buffering
    - Flow control warnings at buffer threshold
    - Automatic disconnection on buffer overflow
    - Heartbeat/ping-pong for connection health
    """

    def __init__(self, config: Optional[WebSocketConfig] = None):
        """
        Initialize connection manager.

        Args:
            config: WebSocket configuration (uses defaults if None)
        """
        self.config = config or WebSocketConfig()

        # Active connections: connection_id -> ConnectionState
        self.connections: Dict[str, ConnectionState] = {}

        # Reverse index: workflow_run_id -> Set[connection_id]
        self.workflow_subscribers: Dict[str, Set[str]] = {}

        # Reverse index: execution_id -> Set[connection_id]
        self.execution_subscribers: Dict[str, Set[str]] = {}

        # Reverse index: work_item_id -> Set[connection_id]
        self.work_item_subscribers: Dict[str, Set[str]] = {}

        # Reverse index: workflow_id -> Set[connection_id]
        self.workflow_definition_subscribers: Dict[str, Set[str]] = {}

        # Reverse index: agent_id -> Set[connection_id]
        self.agent_subscribers: Dict[str, Set[str]] = {}

        # Reverse index: project_name -> Set[connection_id]
        self.project_subscribers: Dict[str, Set[str]] = {}

        # Statistics
        self.stats = {
            "total_connections": 0,
            "messages_sent": 0,
            "flow_control_warnings": 0,
            "disconnections_due_to_overflow": 0,
        }

    async def connect(self, websocket: WebSocket, connection_id: str):
        """
        Accept a new WebSocket connection.

        Args:
            websocket: WebSocket connection
            connection_id: Unique connection identifier
        """
        await websocket.accept()
        self.connections[connection_id] = ConnectionState(
            websocket=websocket,
            subscriptions=[],
            buffer=[],
            last_heartbeat=time.time(),
            authenticated=True,
        )
        self.stats["total_connections"] += 1

    def disconnect(self, connection_id: str):
        """
        Remove a WebSocket connection and clean up all associated resources.

        Args:
            connection_id: Connection identifier
        """
        if connection_id not in self.connections:
            return

        conn_state = self.connections[connection_id]

        # Clean up reverse indices
        for filter in conn_state.subscriptions:
            if filter.workflow_run_id:
                if filter.workflow_run_id in self.workflow_subscribers:
                    self.workflow_subscribers[filter.workflow_run_id].discard(
                        connection_id
                    )

            if filter.execution_id:
                if filter.execution_id in self.execution_subscribers:
                    self.execution_subscribers[filter.execution_id].discard(
                        connection_id
                    )

            if filter.work_item_id:
                if filter.work_item_id in self.work_item_subscribers:
                    self.work_item_subscribers[filter.work_item_id].discard(
                        connection_id
                    )

            if filter.workflow_id:
                if filter.workflow_id in self.workflow_definition_subscribers:
                    self.workflow_definition_subscribers[filter.workflow_id].discard(
                        connection_id
                    )

            if filter.agent_id:
                if filter.agent_id in self.agent_subscribers:
                    self.agent_subscribers[filter.agent_id].discard(connection_id)

            if filter.project_name:
                if filter.project_name in self.project_subscribers:
                    self.project_subscribers[filter.project_name].discard(
                        connection_id
                    )

        # Remove connection
        del self.connections[connection_id]

    def subscribe(self, connection_id: str, filter: EventFilter):
        """
        Add a subscription for a connection.

        Args:
            connection_id: Connection identifier
            filter: Event filter for subscription
        """
        if connection_id not in self.connections:
            return

        self.connections[connection_id].subscriptions.append(filter)

        # Update reverse indices for fast lookups
        if filter.workflow_run_id:
            if filter.workflow_run_id not in self.workflow_subscribers:
                self.workflow_subscribers[filter.workflow_run_id] = set()
            self.workflow_subscribers[filter.workflow_run_id].add(connection_id)

        if filter.execution_id:
            if filter.execution_id not in self.execution_subscribers:
                self.execution_subscribers[filter.execution_id] = set()
            self.execution_subscribers[filter.execution_id].add(connection_id)

        if filter.work_item_id:
            if filter.work_item_id not in self.work_item_subscribers:
                self.work_item_subscribers[filter.work_item_id] = set()
            self.work_item_subscribers[filter.work_item_id].add(connection_id)

        if filter.workflow_id:
            if filter.workflow_id not in self.workflow_definition_subscribers:
                self.workflow_definition_subscribers[filter.workflow_id] = set()
            self.workflow_definition_subscribers[filter.workflow_id].add(connection_id)

        if filter.agent_id:
            if filter.agent_id not in self.agent_subscribers:
                self.agent_subscribers[filter.agent_id] = set()
            self.agent_subscribers[filter.agent_id].add(connection_id)

        if filter.project_name:
            if filter.project_name not in self.project_subscribers:
                self.project_subscribers[filter.project_name] = set()
            self.project_subscribers[filter.project_name].add(connection_id)

    async def send_personal_message(
        self, message: Dict[str, Any], connection_id: str
    ):
        """
        Send a message to a specific connection with backpressure handling.

        Args:
            message: Message to send
            connection_id: Target connection

        Returns:
            True if message sent successfully, False if buffered or connection closed
        """
        if connection_id not in self.connections:
            return False

        conn_state = self.connections[connection_id]

        try:
            # Try to send directly if buffer is empty
            if not conn_state.buffer:
                await conn_state.websocket.send_json(message)
                self.stats["messages_sent"] += 1
                return True

            # Buffer has messages, add to buffer and check threshold
            conn_state.buffer.append(message)

            # Check for buffer overflow
            if len(conn_state.buffer) >= self.config.max_buffer_size:
                if self.config.disconnect_on_overflow:
                    # Disconnect client due to overflow
                    logger.warning(
                        f"Disconnecting client {connection_id} due to buffer overflow "
                        f"(buffer size: {len(conn_state.buffer)})"
                    )
                    await self._send_error_and_close(
                        connection_id,
                        code=4003,
                        reason="Buffer overflow - client too slow",
                    )
                    self.stats["disconnections_due_to_overflow"] += 1
                    return False
            # Check for flow control warning threshold
            elif (
                len(conn_state.buffer)
                >= self.config.max_buffer_size * self.config.flow_control_threshold
            ):
                # Send flow control warning
                await self._send_flow_control_warning(connection_id)

            return True

        except Exception as e:
            logger.error(f"Error sending message to {connection_id}: {e}")
            # Connection closed, clean up
            self.disconnect(connection_id)
            return False

    async def _send_flow_control_warning(self, connection_id: str):
        """Send flow control warning to client."""
        if connection_id not in self.connections:
            return

        conn_state = self.connections[connection_id]
        buffer_usage = len(conn_state.buffer) / self.config.max_buffer_size

        warning_message = FlowControlMessage(
            buffer_usage=buffer_usage,
            buffer_size=len(conn_state.buffer),
            max_buffer_size=self.config.max_buffer_size,
            message=f"Warning: Buffer at {buffer_usage*100:.1f}% capacity. "
            f"Please consume messages faster or you will be disconnected.",
            timestamp=datetime.utcnow(),
        ).model_dump(mode="json")

        try:
            await conn_state.websocket.send_json(warning_message)
            self.stats["flow_control_warnings"] += 1
        except Exception as e:
            logger.error(f"Failed to send flow control warning: {e}")

    async def _send_error_and_close(
        self, connection_id: str, code: int, reason: str
    ):
        """Send error message and close connection."""
        if connection_id not in self.connections:
            return

        conn_state = self.connections[connection_id]

        try:
            # Try to send error message before closing
            error_msg = ErrorMessage(
                code=str(code),
                message=reason,
                timestamp=datetime.utcnow(),
            ).model_dump(mode="json")
            await conn_state.websocket.send_json(error_msg)
        except:
            pass  # Best effort

        try:
            await conn_state.websocket.close(code=code, reason=reason)
        except:
            pass

        self.disconnect(connection_id)

    async def broadcast_event(self, event: DomainEvent):
        """
        Broadcast event to all subscribed connections with filtering.

        Uses reverse indices for fast lookup, then applies detailed filter matching.

        Args:
            event: Domain event to broadcast
        """
        # Determine which connections should receive this event
        recipient_ids: Set[str] = set()

        # Get event attributes for filtering
        event_type = type(event).__name__
        event_dict = event.to_dict() if hasattr(event, "to_dict") else event.__dict__

        # Extract potential filter values from event
        workflow_run_id = event_dict.get("workflow_run_id") or event_dict.get(
            "payload", {}
        ).get("workflow_run_id")
        execution_id = event_dict.get("execution_id") or event_dict.get(
            "payload", {}
        ).get("execution_id")
        work_item_id = event_dict.get("work_item_id") or event_dict.get(
            "payload", {}
        ).get("work_item_id")
        workflow_id = event_dict.get("workflow_id") or event_dict.get("payload", {}).get(
            "workflow_id"
        )
        agent_id = event_dict.get("agent_id") or event_dict.get("payload", {}).get(
            "agent_id"
        )
        project_name = event_dict.get("project_name") or event_dict.get(
            "payload", {}
        ).get("project_name")

        # Find subscribers using reverse indices (fast lookup)
        if workflow_run_id and workflow_run_id in self.workflow_subscribers:
            recipient_ids.update(self.workflow_subscribers[workflow_run_id])

        if execution_id and execution_id in self.execution_subscribers:
            recipient_ids.update(self.execution_subscribers[execution_id])

        if work_item_id and work_item_id in self.work_item_subscribers:
            recipient_ids.update(self.work_item_subscribers[work_item_id])

        if workflow_id and workflow_id in self.workflow_definition_subscribers:
            recipient_ids.update(self.workflow_definition_subscribers[workflow_id])

        if agent_id and agent_id in self.agent_subscribers:
            recipient_ids.update(self.agent_subscribers[agent_id])

        if project_name and project_name in self.project_subscribers:
            recipient_ids.update(self.project_subscribers[project_name])

        # Check all connections for filter matches (for complex filters)
        for connection_id, conn_state in self.connections.items():
            for filter in conn_state.subscriptions:
                if self._event_matches_filter(event, event_dict, filter):
                    recipient_ids.add(connection_id)

        # Send event to all recipients
        event_message = EventMessage(
            event_id=str(event_dict.get("event_id", "")),
            event_type=event_type,
            data=event_dict,
            timestamp=event_dict.get("occurred_at") or datetime.utcnow(),
        )

        message_dict = event_message.model_dump(mode="json")

        # Send to all recipients (with backpressure handling)
        for connection_id in recipient_ids:
            await self.send_personal_message(message_dict, connection_id)

    def _event_matches_filter(
        self, event: DomainEvent, event_dict: Dict[str, Any], filter: EventFilter
    ) -> bool:
        """
        Check if event matches filter criteria.

        Uses AND logic for combining filters (all must match).
        Uses OR logic for multiple event_types (any can match).

        Args:
            event: Domain event
            event_dict: Event as dictionary
            filter: Event filter

        Returns:
            True if event matches filter
        """
        # Check subscription type
        if filter.subscription_type == SubscriptionType.ALL_EVENTS:
            pass  # Match all types
        elif filter.subscription_type == SubscriptionType.WORKFLOW_EVENTS:
            if "workflow" not in type(event).__name__.lower():
                return False
        elif filter.subscription_type == SubscriptionType.EXECUTION_EVENTS:
            if "execution" not in type(event).__name__.lower():
                return False

        # Check event types (OR logic - any type can match)
        if filter.event_types:
            event_type = type(event).__name__
            if event_type not in filter.event_types:
                return False

        # Check specific ID filters (AND logic - all must match if specified)
        if filter.workflow_run_id:
            workflow_run_id = event_dict.get("workflow_run_id") or event_dict.get(
                "payload", {}
            ).get("workflow_run_id")
            if workflow_run_id != filter.workflow_run_id:
                return False

        if filter.execution_id:
            execution_id = event_dict.get("execution_id") or event_dict.get(
                "payload", {}
            ).get("execution_id")
            if execution_id != filter.execution_id:
                return False

        if filter.work_item_id:
            work_item_id = event_dict.get("work_item_id") or event_dict.get(
                "payload", {}
            ).get("work_item_id")
            if work_item_id != filter.work_item_id:
                return False

        if filter.workflow_id:
            workflow_id = event_dict.get("workflow_id") or event_dict.get(
                "payload", {}
            ).get("workflow_id")
            if workflow_id != filter.workflow_id:
                return False

        if filter.agent_id:
            agent_id = event_dict.get("agent_id") or event_dict.get("payload", {}).get(
                "agent_id"
            )
            if agent_id != filter.agent_id:
                return False

        if filter.project_name:
            project_name = event_dict.get("project_name") or event_dict.get(
                "payload", {}
            ).get("project_name")
            if project_name != filter.project_name:
                return False

        return True


# ============================================================================
# WebSocket Adapter
# ============================================================================


class WebSocketAdapter:
    """
    WebSocket adapter for real-time event streaming.

    Provides WebSocket endpoints for subscribing to workflow and execution
    events in real-time with authentication, filtering, and backpressure handling.
    """

    def __init__(
        self,
        config: Optional[WebSocketConfig] = None,
        auth_manager: Optional[Any] = None,
    ):
        """
        Initialize WebSocket adapter.

        Args:
            config: WebSocket configuration (defaults if None)
            auth_manager: Authentication manager for token validation
        """
        self.manager = ConnectionManager(config)
        self.auth_manager = auth_manager
        self._connection_counter = 0
        self._heartbeat_task: Optional[asyncio.Task] = None

    def get_next_connection_id(self) -> str:
        """
        Generate unique connection ID.

        Returns:
            Connection ID
        """
        self._connection_counter += 1
        return f"ws-{self._connection_counter}"

    async def handle_websocket(self, websocket: WebSocket, token: Optional[str] = None):
        """
        Handle WebSocket connection with authentication.

        This is the main entry point for WebSocket connections. It manages
        the connection lifecycle and message handling.

        Args:
            websocket: WebSocket connection
            token: Authentication token from query parameter
        """
        # Authenticate before accepting connection
        if self.auth_manager and not self.auth_manager.validate_token(token or ""):
            logger.warning("WebSocket connection rejected: invalid token")
            await websocket.close(code=4001, reason="Unauthorized")
            return

        connection_id = self.get_next_connection_id()

        try:
            # Accept connection
            await self.manager.connect(websocket, connection_id)

            # Send welcome message with client_id
            await self.manager.send_personal_message(
                ConnectedMessage(
                    client_id=connection_id,
                    message="Connected to Codetoreum event stream",
                    timestamp=datetime.utcnow(),
                ).model_dump(mode="json"),
                connection_id,
            )

            # Start heartbeat monitoring in background
            heartbeat_task = asyncio.create_task(
                self._heartbeat_monitor(connection_id)
            )

            # Message handling loop
            while True:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)

                # Update last heartbeat timestamp
                if connection_id in self.manager.connections:
                    self.manager.connections[connection_id].last_heartbeat = time.time()

                # Handle message based on type
                message_type = message.get("type")

                if message_type == "subscribe":
                    await self._handle_subscribe(connection_id, message)
                elif message_type == "unsubscribe":
                    await self._handle_unsubscribe(connection_id, message)
                elif message_type == "ping":
                    await self._handle_ping(connection_id)
                else:
                    # Unknown message type
                    await self.manager.send_personal_message(
                        ErrorMessage(
                            code="unknown_message_type",
                            message=f"Unknown message type: {message_type}",
                            timestamp=datetime.utcnow(),
                        ).model_dump(mode="json"),
                        connection_id,
                    )

        except WebSocketDisconnect:
            # Client disconnected
            logger.info(f"WebSocket client {connection_id} disconnected")
            self.manager.disconnect(connection_id)
        except Exception as e:
            # Error occurred
            logger.error(f"WebSocket error for client {connection_id}: {e}")
            try:
                await self.manager.send_personal_message(
                    ErrorMessage(
                        code="internal_error",
                        message=f"Internal error: {str(e)}",
                        timestamp=datetime.utcnow(),
                    ).model_dump(mode="json"),
                    connection_id,
                )
            except:
                pass
            finally:
                self.manager.disconnect(connection_id)
        finally:
            # Cancel heartbeat task
            if heartbeat_task:
                heartbeat_task.cancel()

    async def _heartbeat_monitor(self, connection_id: str):
        """
        Monitor heartbeat for a connection and disconnect if timeout occurs.

        Args:
            connection_id: Connection to monitor
        """
        try:
            while True:
                await asyncio.sleep(self.manager.config.heartbeat_interval)

                if connection_id not in self.manager.connections:
                    return  # Connection already closed

                conn_state = self.manager.connections[connection_id]
                time_since_heartbeat = time.time() - conn_state.last_heartbeat

                if time_since_heartbeat > self.manager.config.heartbeat_timeout:
                    logger.warning(
                        f"Connection {connection_id} timed out "
                        f"(no heartbeat for {time_since_heartbeat:.1f}s)"
                    )
                    await self.manager._send_error_and_close(
                        connection_id,
                        code=4000,
                        reason="Connection timeout - no heartbeat received",
                    )
                    return

                # Send ping to client
                try:
                    await conn_state.websocket.send_json(
                        {"type": "ping", "timestamp": datetime.utcnow().isoformat()}
                    )
                except Exception as e:
                    logger.error(f"Failed to send heartbeat ping: {e}")
                    self.manager.disconnect(connection_id)
                    return

        except asyncio.CancelledError:
            # Task cancelled, connection closing
            pass

    async def _handle_subscribe(self, connection_id: str, message: Dict[str, Any]):
        """
        Handle subscribe message with extended filtering support.

        Args:
            connection_id: Connection identifier
            message: Subscribe message with filter criteria
        """
        try:
            # Parse subscription type
            subscription_type = SubscriptionType[
                message.get("subscription_type", "ALL_EVENTS").upper()
            ]

            # Create event filter with all supported fields
            filter = EventFilter(
                subscription_type=subscription_type,
                workflow_run_id=message.get("workflow_run_id"),
                execution_id=message.get("execution_id"),
                work_item_id=message.get("work_item_id"),
                workflow_id=message.get("workflow_id"),
                agent_id=message.get("agent_id"),
                project_name=message.get("project_name"),
                event_types=message.get("event_types"),
            )

            # Add subscription
            self.manager.subscribe(connection_id, filter)

            # Send confirmation with applied filters
            await self.manager.send_personal_message(
                {
                    "type": "subscribed",
                    "subscription_type": subscription_type.value,
                    "filters": {
                        "workflow_run_id": filter.workflow_run_id,
                        "execution_id": filter.execution_id,
                        "work_item_id": filter.work_item_id,
                        "workflow_id": filter.workflow_id,
                        "agent_id": filter.agent_id,
                        "project_name": filter.project_name,
                        "event_types": filter.event_types,
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                },
                connection_id,
            )

        except Exception as e:
            logger.error(f"Failed to process subscribe message: {e}")
            await self.manager.send_personal_message(
                ErrorMessage(
                    code="subscribe_failed",
                    message=f"Failed to subscribe: {str(e)}",
                    timestamp=datetime.utcnow(),
                ).model_dump(mode="json"),
                connection_id,
            )

    async def _handle_unsubscribe(self, connection_id: str, message: Dict[str, Any]):
        """
        Handle unsubscribe message.

        Args:
            connection_id: Connection identifier
            message: Unsubscribe message
        """
        # For now, just send confirmation
        # Full unsubscribe logic can be added later
        await self.manager.send_personal_message(
            {
                "type": "unsubscribed",
                "timestamp": datetime.utcnow().isoformat(),
            },
            connection_id,
        )

    async def _handle_ping(self, connection_id: str):
        """
        Handle ping message (keepalive).

        Args:
            connection_id: Connection identifier
        """
        await self.manager.send_personal_message(
            {"type": "pong", "timestamp": datetime.utcnow().isoformat()},
            connection_id,
        )

    async def broadcast_event(self, event: DomainEvent):
        """
        Broadcast domain event to subscribed connections.

        This method is called by the event bus when domain events are published.

        Args:
            event: Domain event to broadcast
        """
        await self.manager.broadcast_event(event)
