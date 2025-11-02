"""
WebSocket API Adapter

This module implements the WebSocket adapter for real-time event streaming
and log delivery.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from codetoreum.domain.events import DomainEvent


# ============================================================================
# Data Classes and Enums
# ============================================================================


class SubscriptionType(Enum):
    """Type of subscription"""

    WORKFLOW_EVENTS = "workflow_events"
    EXECUTION_EVENTS = "execution_events"
    ALL_EVENTS = "all_events"
    LOGS = "logs"


@dataclass
class EventFilter:
    """Filter for event subscriptions"""

    subscription_type: SubscriptionType
    workflow_run_id: Optional[str] = None
    execution_id: Optional[str] = None
    project_name: Optional[str] = None
    event_types: Optional[List[str]] = None


class WebSocketMessage(BaseModel):
    """Base message for WebSocket communication"""

    type: str
    data: Dict[str, Any]
    timestamp: datetime = datetime.utcnow()


class SubscribeMessage(BaseModel):
    """Subscribe to event stream"""

    type: str = "subscribe"
    subscription_type: str
    workflow_run_id: Optional[str] = None
    execution_id: Optional[str] = None
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


# ============================================================================
# Connection Manager
# ============================================================================


class ConnectionManager:
    """
    Manages WebSocket connections and subscriptions.

    This class handles connection lifecycle, subscription management,
    and message broadcasting to connected clients.
    """

    def __init__(self):
        """Initialize connection manager"""
        # Active connections: connection_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

        # Subscriptions: connection_id -> List[EventFilter]
        self.subscriptions: Dict[str, List[EventFilter]] = {}

        # Reverse index: workflow_run_id -> Set[connection_id]
        self.workflow_subscribers: Dict[str, Set[str]] = {}

        # Reverse index: execution_id -> Set[connection_id]
        self.execution_subscribers: Dict[str, Set[str]] = {}

        # Reverse index: project_name -> Set[connection_id]
        self.project_subscribers: Dict[str, Set[str]] = {}

    async def connect(self, websocket: WebSocket, connection_id: str):
        """
        Accept a new WebSocket connection.

        Args:
            websocket: WebSocket connection
            connection_id: Unique connection identifier
        """
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.subscriptions[connection_id] = []

    def disconnect(self, connection_id: str):
        """
        Remove a WebSocket connection.

        Args:
            connection_id: Connection identifier
        """
        # Remove from active connections
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        # Remove subscriptions
        if connection_id in self.subscriptions:
            # Clean up reverse indices
            for filter in self.subscriptions[connection_id]:
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

                if filter.project_name:
                    if filter.project_name in self.project_subscribers:
                        self.project_subscribers[filter.project_name].discard(
                            connection_id
                        )

            del self.subscriptions[connection_id]

    def subscribe(self, connection_id: str, filter: EventFilter):
        """
        Add a subscription for a connection.

        Args:
            connection_id: Connection identifier
            filter: Event filter for subscription
        """
        if connection_id not in self.subscriptions:
            return

        self.subscriptions[connection_id].append(filter)

        # Update reverse indices
        if filter.workflow_run_id:
            if filter.workflow_run_id not in self.workflow_subscribers:
                self.workflow_subscribers[filter.workflow_run_id] = set()
            self.workflow_subscribers[filter.workflow_run_id].add(connection_id)

        if filter.execution_id:
            if filter.execution_id not in self.execution_subscribers:
                self.execution_subscribers[filter.execution_id] = set()
            self.execution_subscribers[filter.execution_id].add(connection_id)

        if filter.project_name:
            if filter.project_name not in self.project_subscribers:
                self.project_subscribers[filter.project_name] = set()
            self.project_subscribers[filter.project_name].add(connection_id)

    async def send_personal_message(
        self, message: Dict[str, Any], connection_id: str
    ):
        """
        Send a message to a specific connection.

        Args:
            message: Message to send
            connection_id: Target connection
        """
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            try:
                await websocket.send_json(message)
            except Exception:
                # Connection closed, clean up
                self.disconnect(connection_id)

    async def broadcast_event(self, event: DomainEvent):
        """
        Broadcast event to all subscribed connections.

        Args:
            event: Domain event to broadcast
        """
        # Determine which connections should receive this event
        recipient_ids: Set[str] = set()

        # Get event attributes for filtering
        event_type = type(event).__name__
        event_dict = event.__dict__

        workflow_run_id = event_dict.get("workflow_run_id")
        execution_id = event_dict.get("execution_id")
        project_name = event_dict.get("project_name")

        # Find subscribers by workflow
        if workflow_run_id and workflow_run_id in self.workflow_subscribers:
            recipient_ids.update(self.workflow_subscribers[workflow_run_id])

        # Find subscribers by execution
        if execution_id and execution_id in self.execution_subscribers:
            recipient_ids.update(self.execution_subscribers[execution_id])

        # Find subscribers by project
        if project_name and project_name in self.project_subscribers:
            recipient_ids.update(self.project_subscribers[project_name])

        # Check all subscriptions for matches
        for connection_id, filters in self.subscriptions.items():
            for filter in filters:
                if self._event_matches_filter(event, event_dict, filter):
                    recipient_ids.add(connection_id)

        # Send event to all recipients
        event_message = EventMessage(
            event_id=event_dict.get("event_id", ""),
            event_type=event_type,
            data=event_dict,
            timestamp=event_dict.get("timestamp", datetime.utcnow()),
        )

        message_dict = event_message.model_dump(mode='json')

        # Send to all recipients
        disconnected = []
        for connection_id in recipient_ids:
            if connection_id in self.active_connections:
                try:
                    await self.active_connections[connection_id].send_json(
                        message_dict
                    )
                except Exception:
                    disconnected.append(connection_id)

        # Clean up disconnected clients
        for connection_id in disconnected:
            self.disconnect(connection_id)

    def _event_matches_filter(
        self, event: DomainEvent, event_dict: Dict[str, Any], filter: EventFilter
    ) -> bool:
        """
        Check if event matches filter criteria.

        Args:
            event: Domain event
            event_dict: Event as dictionary
            filter: Event filter

        Returns:
            True if event matches filter
        """
        # Check subscription type
        if filter.subscription_type == SubscriptionType.ALL_EVENTS:
            return True

        if filter.subscription_type == SubscriptionType.WORKFLOW_EVENTS:
            if "workflow" not in type(event).__name__.lower():
                return False

        if filter.subscription_type == SubscriptionType.EXECUTION_EVENTS:
            if "execution" not in type(event).__name__.lower():
                return False

        # Check specific filters
        if filter.workflow_run_id:
            if event_dict.get("workflow_run_id") != filter.workflow_run_id:
                return False

        if filter.execution_id:
            if event_dict.get("execution_id") != filter.execution_id:
                return False

        if filter.project_name:
            if event_dict.get("project_name") != filter.project_name:
                return False

        # Check event types
        if filter.event_types:
            event_type = type(event).__name__
            if event_type not in filter.event_types:
                return False

        return True


# ============================================================================
# WebSocket Adapter
# ============================================================================


class WebSocketAdapter:
    """
    WebSocket adapter for real-time event streaming.

    Provides WebSocket endpoints for subscribing to workflow and execution
    events in real-time.
    """

    def __init__(self):
        """Initialize WebSocket adapter"""
        self.manager = ConnectionManager()
        self._connection_counter = 0

    def get_next_connection_id(self) -> str:
        """
        Generate unique connection ID.

        Returns:
            Connection ID
        """
        self._connection_counter += 1
        return f"ws-{self._connection_counter}"

    async def handle_websocket(self, websocket: WebSocket):
        """
        Handle WebSocket connection.

        This is the main entry point for WebSocket connections. It manages
        the connection lifecycle and message handling.

        Args:
            websocket: WebSocket connection
        """
        connection_id = self.get_next_connection_id()

        try:
            # Accept connection
            await self.manager.connect(websocket, connection_id)

            # Send welcome message
            await self.manager.send_personal_message(
                {
                    "type": "connected",
                    "connection_id": connection_id,
                    "message": "Connected to Codetoreum event stream",
                    "timestamp": datetime.utcnow().isoformat(),
                },
                connection_id,
            )

            # Message handling loop
            while True:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)

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
                        ).model_dump(mode='json'),
                        connection_id,
                    )

        except WebSocketDisconnect:
            # Client disconnected
            self.manager.disconnect(connection_id)
        except Exception as e:
            # Error occurred
            try:
                await self.manager.send_personal_message(
                    ErrorMessage(
                        code="internal_error",
                        message=f"Internal error: {str(e)}",
                        timestamp=datetime.utcnow(),
                    ).model_dump(mode='json'),
                    connection_id,
                )
            except:
                pass
            finally:
                self.manager.disconnect(connection_id)

    async def _handle_subscribe(self, connection_id: str, message: Dict[str, Any]):
        """
        Handle subscribe message.

        Args:
            connection_id: Connection identifier
            message: Subscribe message
        """
        try:
            # Parse subscription
            subscription_type = SubscriptionType[
                message.get("subscription_type", "ALL_EVENTS").upper()
            ]

            filter = EventFilter(
                subscription_type=subscription_type,
                workflow_run_id=message.get("workflow_run_id"),
                execution_id=message.get("execution_id"),
                project_name=message.get("project_name"),
                event_types=message.get("event_types"),
            )

            # Add subscription
            self.manager.subscribe(connection_id, filter)

            # Send confirmation
            await self.manager.send_personal_message(
                {
                    "type": "subscribed",
                    "subscription_type": subscription_type.value,
                    "filters": {
                        "workflow_run_id": filter.workflow_run_id,
                        "execution_id": filter.execution_id,
                        "project_name": filter.project_name,
                        "event_types": filter.event_types,
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                },
                connection_id,
            )

        except Exception as e:
            await self.manager.send_personal_message(
                ErrorMessage(
                    code="subscribe_failed",
                    message=f"Failed to subscribe: {str(e)}",
                    timestamp=datetime.utcnow(),
                ).model_dump(mode='json'),
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
