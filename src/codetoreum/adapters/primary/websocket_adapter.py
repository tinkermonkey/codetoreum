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
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from codetoreum.config import (
    DEFAULT_WS_HEARTBEAT_INTERVAL,
    DEFAULT_WS_HEARTBEAT_TIMEOUT,
    DEFAULT_WS_MAX_CONNECTIONS,
    DEFAULT_WS_MESSAGE_QUEUE_SIZE,
    DEFAULT_WS_RATE_LIMIT_MESSAGES,
    DEFAULT_WS_RATE_LIMIT_WINDOW,
)
from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.observability.websocket_instrumentation import (
    WebSocketMessageTracer,
    WebSocketSessionTracer,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes and Enums
# ============================================================================


@dataclass
class WebSocketConfig:
    """Configuration for WebSocket adapter"""

    max_buffer_size: int = DEFAULT_WS_MESSAGE_QUEUE_SIZE  # Max events buffered per client
    flow_control_threshold: float = 0.8  # Warn at 80% capacity
    disconnect_on_overflow: bool = True  # Disconnect overloaded clients
    heartbeat_interval: int = DEFAULT_WS_HEARTBEAT_INTERVAL  # Heartbeat interval in seconds
    heartbeat_timeout: int = DEFAULT_WS_HEARTBEAT_TIMEOUT  # Time after which to consider connection dead
    rate_limit_messages: int = DEFAULT_WS_RATE_LIMIT_MESSAGES  # Max messages per client per time window
    rate_limit_window: int = DEFAULT_WS_RATE_LIMIT_WINDOW  # Rate limit window in seconds
    max_connections: int = DEFAULT_WS_MAX_CONNECTIONS  # Maximum concurrent connections per instance
    enable_redis_pubsub: bool = True  # Enable Redis pub/sub for horizontal scaling
    enable_connection_persistence: bool = True  # Enable connection state persistence

    @classmethod
    def from_env(cls) -> "WebSocketConfig":
        """Create WebSocketConfig from environment variables."""
        return cls(
            max_buffer_size=int(os.getenv("WEBSOCKET_MAX_BUFFER_SIZE", str(DEFAULT_WS_MESSAGE_QUEUE_SIZE))),
            flow_control_threshold=float(os.getenv("WEBSOCKET_FLOW_CONTROL_THRESHOLD", "0.8")),
            disconnect_on_overflow=os.getenv("WEBSOCKET_DISCONNECT_ON_OVERFLOW", "true").lower() == "true",
            heartbeat_interval=int(os.getenv("WEBSOCKET_HEARTBEAT_INTERVAL", str(DEFAULT_WS_HEARTBEAT_INTERVAL))),
            heartbeat_timeout=int(os.getenv("WEBSOCKET_HEARTBEAT_TIMEOUT", str(DEFAULT_WS_HEARTBEAT_TIMEOUT))),
            rate_limit_messages=int(os.getenv("WEBSOCKET_RATE_LIMIT_MESSAGES", str(DEFAULT_WS_RATE_LIMIT_MESSAGES))),
            rate_limit_window=int(os.getenv("WEBSOCKET_RATE_LIMIT_WINDOW", str(DEFAULT_WS_RATE_LIMIT_WINDOW))),
            max_connections=int(os.getenv("WEBSOCKET_MAX_CONNECTIONS", str(DEFAULT_WS_MAX_CONNECTIONS))),
            enable_redis_pubsub=os.getenv("WEBSOCKET_ENABLE_REDIS_PUBSUB", "true").lower() == "true",
            enable_connection_persistence=os.getenv("WEBSOCKET_ENABLE_CONNECTION_PERSISTENCE", "true").lower()
            == "true",
        )


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
    workflow_run_id: str | None = None
    execution_id: str | None = None
    work_item_id: str | None = None  # New filter
    workflow_id: str | None = None  # New filter
    agent_id: str | None = None  # New filter
    project_name: str | None = None
    event_types: list[str] | None = None  # Multiple types use OR logic


class WebSocketMessage(BaseModel):
    """Base message for WebSocket communication"""

    type: str
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    workflow_run_id: str | None = None
    execution_id: str | None = None
    work_item_id: str | None = None
    workflow_id: str | None = None
    agent_id: str | None = None
    project_name: str | None = None
    event_types: list[str] | None = None


class UnsubscribeMessage(BaseModel):
    """Unsubscribe from event stream"""

    type: str = "unsubscribe"
    subscription_id: str


class EventMessage(BaseModel):
    """Event delivered to client"""

    type: str = "event"
    event_id: str
    event_type: str
    data: dict[str, Any]
    timestamp: datetime


class LogMessage(BaseModel):
    """Log message delivered to client"""

    type: str = "log"
    execution_id: str
    level: str
    message: str
    timestamp: datetime
    metadata: dict[str, Any] | None = None


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
class RateLimiter:
    """Token bucket rate limiter for per-client message rate limiting"""

    max_tokens: int  # Maximum number of tokens
    tokens: float  # Current number of tokens
    window: int  # Time window in seconds
    last_update: float  # Last token refill timestamp

    def try_consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens. Returns True if successful, False if rate limit exceeded.

        Args:
            tokens: Number of tokens to consume (default: 1)

        Returns:
            True if tokens consumed, False if rate limit exceeded
        """
        now = time.time()
        time_passed = now - self.last_update

        # Refill tokens based on time passed
        tokens_to_add = (time_passed / self.window) * self.max_tokens
        self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
        self.last_update = now

        # Try to consume
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


@dataclass
class ConnectionState:
    """State for a single WebSocket connection"""

    websocket: WebSocket
    subscriptions: list[EventFilter]
    buffer: list[dict[str, Any]]  # Buffered messages
    last_heartbeat: float  # Timestamp of last heartbeat
    authenticated: bool = True  # Authentication status
    rate_limiter: RateLimiter | None = None  # Rate limiter for incoming messages


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
    - Connection pooling with max connections limit
    - Redis pub/sub for horizontal scaling across multiple instances
    - Connection state persistence for crash recovery
    """

    def __init__(
        self,
        config: WebSocketConfig | None = None,
        redis_pubsub: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize connection manager.

        Args:
            config: WebSocket configuration (uses defaults if None)
            redis_pubsub: Redis pub/sub adapter for message distribution (optional)
            redis_client: Redis client for connection state persistence (optional)
        """
        self.config = config or WebSocketConfig()
        self.redis_pubsub = redis_pubsub
        self.redis_client = redis_client
        self._background_tasks: set[asyncio.Task] = set()

        # Active connections: connection_id -> ConnectionState
        self.connections: dict[str, ConnectionState] = {}

        # Reverse index: workflow_run_id -> Set[connection_id]
        self.workflow_subscribers: dict[str, set[str]] = {}

        # Reverse index: execution_id -> Set[connection_id]
        self.execution_subscribers: dict[str, set[str]] = {}

        # Reverse index: work_item_id -> Set[connection_id]
        self.work_item_subscribers: dict[str, set[str]] = {}

        # Reverse index: workflow_id -> Set[connection_id]
        self.workflow_definition_subscribers: dict[str, set[str]] = {}

        # Reverse index: agent_id -> Set[connection_id]
        self.agent_subscribers: dict[str, set[str]] = {}

        # Reverse index: project_name -> Set[connection_id]
        self.project_subscribers: dict[str, set[str]] = {}

        # Statistics
        self.stats = {
            "total_connections": 0,
            "current_connections": 0,
            "messages_sent": 0,
            "flow_control_warnings": 0,
            "disconnections_due_to_overflow": 0,
            "connection_rejections": 0,
        }

        # Redis pub/sub will be initialized on first connection
        self._redis_initialized = False

    async def _setup_redis_pubsub(self) -> None:
        """
        Set up Redis pub/sub subscriptions for message distribution.

        This is called automatically if Redis pub/sub is enabled.
        """
        if self._redis_initialized:
            return

        try:
            if self.redis_pubsub and self.config.enable_redis_pubsub:
                await self.redis_pubsub.initialize()
                await self.redis_pubsub.subscribe("websocket:events", self._handle_redis_event)
                self._redis_initialized = True
                logger.info("Redis pub/sub set up for WebSocket message distribution")
        except Exception as e:
            logger.error(
                f"Failed to setup Redis pub/sub: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )

    async def _handle_redis_event(self, message: dict[str, Any]) -> None:
        """
        Handle event received from Redis pub/sub.

        This is called when another server instance publishes an event.

        Args:
            message: Message from Redis pub/sub
        """
        try:
            if message.get("type") == "event":
                event_dict = message.get("event", {})
                # Broadcast to local connections only (not back to Redis)
                await self._broadcast_event_local(event_dict)
        except Exception as e:
            logger.error(
                f"Error handling Redis event: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )

    async def connect(self, websocket: WebSocket, connection_id: str) -> bool:
        """
        Accept a new WebSocket connection with connection pooling.

        Args:
            websocket: WebSocket connection
            connection_id: Unique connection identifier

        Returns:
            True if connection accepted, False if rejected (max connections reached)
        """
        # Initialize Redis pub/sub if needed (once only)
        await self._setup_redis_pubsub()

        # Check connection limit
        if len(self.connections) >= self.config.max_connections:
            logger.warning(
                f"Connection limit reached ({self.config.max_connections}), rejecting connection {connection_id}"
            )
            await websocket.close(code=1008, reason="Max connections reached")
            self.stats["connection_rejections"] += 1
            return False

        await websocket.accept()
        self.connections[connection_id] = ConnectionState(
            websocket=websocket,
            subscriptions=[],
            buffer=[],
            last_heartbeat=time.time(),
            authenticated=True,
            rate_limiter=RateLimiter(
                max_tokens=self.config.rate_limit_messages,
                tokens=self.config.rate_limit_messages,
                window=self.config.rate_limit_window,
                last_update=time.time(),
            ),
        )
        self.stats["total_connections"] += 1
        self.stats["current_connections"] = len(self.connections)

        # Persist connection state if enabled
        if self.config.enable_connection_persistence and self.redis_client:
            await self._persist_connection_state(connection_id)

        return True

    async def _persist_connection_state(self, connection_id: str) -> None:
        """
        Persist connection state to Redis for crash recovery.

        Args:
            connection_id: Connection identifier
        """
        try:
            if not self.redis_client or connection_id not in self.connections:
                return

            conn_state = self.connections[connection_id]

            # Store connection metadata including buffer and rate limiter state
            connection_data = {
                "connection_id": connection_id,
                "subscriptions": [
                    {
                        "subscription_type": f.subscription_type.value,
                        "workflow_run_id": f.workflow_run_id,
                        "execution_id": f.execution_id,
                        "work_item_id": f.work_item_id,
                        "workflow_id": f.workflow_id,
                        "agent_id": f.agent_id,
                        "project_name": f.project_name,
                        "event_types": f.event_types,
                    }
                    for f in conn_state.subscriptions
                ],
                "buffer_size": len(conn_state.buffer),
                "rate_limiter_tokens": conn_state.rate_limiter.tokens if conn_state.rate_limiter else None,
                "last_heartbeat": conn_state.last_heartbeat,
                "connected_at": time.time(),
            }

            # Store in Redis with expiration (2x heartbeat timeout)
            key = f"websocket:connection:{connection_id}"
            try:
                await self.redis_client.setex(
                    key,
                    self.config.heartbeat_timeout * 2,
                    json.dumps(connection_data),
                )
            except Exception as redis_error:
                logger.error(
                    f"Redis setex operation failed for connection {connection_id}: {redis_error}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_REDIS_ERROR},
                )
                raise

        except Exception as e:
            logger.error(
                f"Failed to persist connection state for {connection_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )

    async def _remove_persisted_connection_state(self, connection_id: str) -> None:
        """
        Remove persisted connection state from Redis.

        Args:
            connection_id: Connection identifier
        """
        try:
            if self.redis_client:
                key = f"websocket:connection:{connection_id}"
                try:
                    await self.redis_client.delete(key)
                except Exception as redis_error:
                    logger.error(
                        f"Redis delete operation failed for connection {connection_id}: {redis_error}",
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_REDIS_ERROR},
                    )
                    # Don't raise - this is cleanup, best effort
        except Exception as e:
            logger.error(
                f"Failed to remove persisted connection state for {connection_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )

    def _create_tracked_task(self, coro):
        """
        Create a background task and track it for cleanup.

        Args:
            coro: Coroutine to run in background

        Returns:
            The created asyncio.Task
        """
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def close(self):
        """
        Close the connection manager and wait for all background tasks to complete.
        """
        # Cancel all pending background tasks
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()

        # Wait for all tasks to finish (they'll get CancelledError)
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

    def disconnect(self, connection_id: str):
        """
        Remove a WebSocket connection and clean up all associated resources.

        Args:
            connection_id: Connection identifier
        """
        if connection_id not in self.connections:
            return

        conn_state = self.connections[connection_id]

        # Track indices to clean up (batch cleanup for efficiency)
        empty_workflow_runs = []
        empty_executions = []
        empty_work_items = []
        empty_workflows = []
        empty_agents = []
        empty_projects = []

        # Clean up reverse indices
        for filter in conn_state.subscriptions:
            if filter.workflow_run_id and filter.workflow_run_id in self.workflow_subscribers:
                self.workflow_subscribers[filter.workflow_run_id].discard(connection_id)
                if not self.workflow_subscribers[filter.workflow_run_id]:
                    empty_workflow_runs.append(filter.workflow_run_id)

            if filter.execution_id and filter.execution_id in self.execution_subscribers:
                self.execution_subscribers[filter.execution_id].discard(connection_id)
                if not self.execution_subscribers[filter.execution_id]:
                    empty_executions.append(filter.execution_id)

            if filter.work_item_id and filter.work_item_id in self.work_item_subscribers:
                self.work_item_subscribers[filter.work_item_id].discard(connection_id)
                if not self.work_item_subscribers[filter.work_item_id]:
                    empty_work_items.append(filter.work_item_id)

            if filter.workflow_id and filter.workflow_id in self.workflow_definition_subscribers:
                self.workflow_definition_subscribers[filter.workflow_id].discard(connection_id)
                if not self.workflow_definition_subscribers[filter.workflow_id]:
                    empty_workflows.append(filter.workflow_id)

            if filter.agent_id and filter.agent_id in self.agent_subscribers:
                self.agent_subscribers[filter.agent_id].discard(connection_id)
                if not self.agent_subscribers[filter.agent_id]:
                    empty_agents.append(filter.agent_id)

            if filter.project_name and filter.project_name in self.project_subscribers:
                self.project_subscribers[filter.project_name].discard(connection_id)
                if not self.project_subscribers[filter.project_name]:
                    empty_projects.append(filter.project_name)

        # Batch cleanup of empty sets to prevent memory leaks
        for workflow_run_id in empty_workflow_runs:
            del self.workflow_subscribers[workflow_run_id]
        for execution_id in empty_executions:
            del self.execution_subscribers[execution_id]
        for work_item_id in empty_work_items:
            del self.work_item_subscribers[work_item_id]
        for workflow_id in empty_workflows:
            del self.workflow_definition_subscribers[workflow_id]
        for agent_id in empty_agents:
            del self.agent_subscribers[agent_id]
        for project_name in empty_projects:
            del self.project_subscribers[project_name]

        # Remove connection
        del self.connections[connection_id]
        self.stats["current_connections"] = len(self.connections)

        # Remove persisted state
        if self.config.enable_connection_persistence and self.redis_client:
            self._create_tracked_task(self._remove_persisted_connection_state(connection_id))

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

    async def send_personal_message(self, message: dict[str, Any], connection_id: str) -> bool:
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
            elif len(conn_state.buffer) >= self.config.max_buffer_size * self.config.flow_control_threshold:
                # Send flow control warning
                await self._send_flow_control_warning(connection_id)

            return True

        except Exception as e:
            logger.error(
                f"Error sending message to {connection_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            # Connection closed, clean up
            self.disconnect(connection_id)
            return False

    async def _send_flow_control_warning(self, connection_id: str) -> None:
        """Send flow control warning to client."""
        if connection_id not in self.connections:
            return

        conn_state = self.connections[connection_id]
        buffer_usage = len(conn_state.buffer) / self.config.max_buffer_size

        warning_message = FlowControlMessage(
            buffer_usage=buffer_usage,
            buffer_size=len(conn_state.buffer),
            max_buffer_size=self.config.max_buffer_size,
            message=f"Warning: Buffer at {buffer_usage * 100:.1f}% capacity. "
            f"Please consume messages faster or you will be disconnected.",
            timestamp=datetime.now(UTC),
        ).model_dump(mode="json")

        try:
            await conn_state.websocket.send_json(warning_message)
            self.stats["flow_control_warnings"] += 1
        except Exception as e:
            logger.error(
                f"Failed to send flow control warning: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )

    async def _send_error_and_close(self, connection_id: str, code: int, reason: str) -> None:
        """Send error message and close connection."""
        if connection_id not in self.connections:
            return

        conn_state = self.connections[connection_id]

        try:
            # Try to send error message before closing
            error_msg = ErrorMessage(
                code=str(code),
                message=reason,
                timestamp=datetime.now(UTC),
            ).model_dump(mode="json")
            await conn_state.websocket.send_json(error_msg)
        except Exception as e:
            logger.debug(f"Failed to send error message for connection {connection_id}: {e}", exc_info=True)

        try:
            await conn_state.websocket.close(code=code, reason=reason)
        except Exception as e:
            logger.debug(f"Failed to close connection {connection_id}: {e}", exc_info=True)

        self.disconnect(connection_id)

    def _extract_event_attributes(self, event_dict: dict[str, Any]) -> dict[str, str | None]:
        """
        Extract standard attributes from event data with consistent fallbacks.

        Args:
            event_dict: Event as dictionary

        Returns:
            Dictionary with extracted attributes
        """
        payload = event_dict.get("payload", {})

        return {
            "workflow_run_id": event_dict.get("workflow_run_id") or payload.get("workflow_run_id"),
            "execution_id": event_dict.get("execution_id") or payload.get("execution_id"),
            "work_item_id": event_dict.get("work_item_id") or payload.get("work_item_id"),
            "workflow_id": event_dict.get("workflow_id") or payload.get("workflow_id"),
            "agent_id": event_dict.get("agent_id") or payload.get("agent_id"),
            "project_name": event_dict.get("project_name") or payload.get("project_name"),
        }

    async def _broadcast_event_local(self, event_dict: dict[str, Any]) -> None:
        """
        Broadcast event to local connections only (not via Redis).

        This is used when receiving events from Redis pub/sub to avoid loops.

        Args:
            event_dict: Event as dictionary
        """
        # Extract attributes using helper method
        attributes = self._extract_event_attributes(event_dict)
        event_type = event_dict.get("event_type", "UnknownEvent")

        # Start with empty set, then union all matching index lookups
        relevant_connections: set[str] | None = None

        # Find subscribers using reverse indices (fast set operations)
        if attributes["workflow_run_id"] and attributes["workflow_run_id"] in self.workflow_subscribers:
            candidate_set = self.workflow_subscribers[attributes["workflow_run_id"]]
            relevant_connections = (
                candidate_set.copy() if relevant_connections is None else relevant_connections | candidate_set
            )

        if attributes["execution_id"] and attributes["execution_id"] in self.execution_subscribers:
            candidate_set = self.execution_subscribers[attributes["execution_id"]]
            relevant_connections = (
                candidate_set.copy() if relevant_connections is None else relevant_connections | candidate_set
            )

        if attributes["work_item_id"] and attributes["work_item_id"] in self.work_item_subscribers:
            candidate_set = self.work_item_subscribers[attributes["work_item_id"]]
            relevant_connections = (
                candidate_set.copy() if relevant_connections is None else relevant_connections | candidate_set
            )

        if attributes["workflow_id"] and attributes["workflow_id"] in self.workflow_definition_subscribers:
            candidate_set = self.workflow_definition_subscribers[attributes["workflow_id"]]
            relevant_connections = (
                candidate_set.copy() if relevant_connections is None else relevant_connections | candidate_set
            )

        if attributes["agent_id"] and attributes["agent_id"] in self.agent_subscribers:
            candidate_set = self.agent_subscribers[attributes["agent_id"]]
            relevant_connections = (
                candidate_set.copy() if relevant_connections is None else relevant_connections | candidate_set
            )

        if attributes["project_name"] and attributes["project_name"] in self.project_subscribers:
            candidate_set = self.project_subscribers[attributes["project_name"]]
            relevant_connections = (
                candidate_set.copy() if relevant_connections is None else relevant_connections | candidate_set
            )

        # If no index-based matches, check all connections with complex filters
        connections_to_check = (
            relevant_connections if relevant_connections is not None else set(self.connections.keys())
        )

        # Determine final recipients by applying detailed filter matching
        recipient_ids: set[str] = set()
        for connection_id in connections_to_check:
            if connection_id not in self.connections:
                continue

            conn_state = self.connections[connection_id]
            for filter in conn_state.subscriptions:
                if self._event_matches_filter_dict(event_type, event_dict, filter):
                    recipient_ids.add(connection_id)
                    break  # No need to check other filters for this connection

        # Send event to all recipients
        event_message = EventMessage(
            event_id=str(event_dict.get("event_id", "")),
            event_type=event_type,
            data=event_dict,
            timestamp=event_dict.get("occurred_at") or datetime.now(UTC),
        )

        message_dict = event_message.model_dump(mode="json")

        # Send to all recipients (with backpressure handling)
        for connection_id in recipient_ids:
            await self.send_personal_message(message_dict, connection_id)

    async def broadcast_event(self, event: CodetoreumEvent) -> None:
        """
        Broadcast event to all subscribed connections with filtering.

        If Redis pub/sub is enabled, publishes to Redis for distribution
        across all server instances. Otherwise, broadcasts locally only.

        Args:
            event: Domain event to broadcast
        """
        # Get event attributes for filtering
        event_dict = event.to_dict() if hasattr(event, "to_dict") else event.__dict__

        # If Redis pub/sub is enabled, publish to Redis
        # (all instances including this one will receive it)
        if self.redis_pubsub and self.config.enable_redis_pubsub:
            try:
                await self.redis_pubsub.publish_event(event)
            except Exception as e:
                logger.error(
                    f"Failed to publish event to Redis: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_REDIS_ERROR},
                )
                # Fall back to local broadcast
                await self._broadcast_event_local(event_dict)
        else:
            # No Redis, broadcast locally only
            await self._broadcast_event_local(event_dict)

    def _event_matches_filter_dict(self, event_type: str, event_dict: dict[str, Any], filter: EventFilter) -> bool:
        """
        Check if event matches filter criteria (dictionary version).

        Args:
            event_type: Event type name
            event_dict: Event as dictionary
            filter: Event filter

        Returns:
            True if event matches filter
        """
        # Check subscription type
        if filter.subscription_type == SubscriptionType.ALL_EVENTS:
            pass  # Match all types
        elif filter.subscription_type == SubscriptionType.WORKFLOW_EVENTS:
            if "workflow" not in event_type.lower():
                return False
        elif filter.subscription_type == SubscriptionType.EXECUTION_EVENTS:
            if "execution" not in event_type.lower():
                return False

        # Check event types (OR logic - any type can match)
        if filter.event_types:
            if event_type not in filter.event_types:
                return False

        # Check specific ID filters (AND logic - all must match if specified)
        if filter.workflow_run_id:
            workflow_run_id = event_dict.get("workflow_run_id") or event_dict.get("payload", {}).get("workflow_run_id")
            if workflow_run_id != filter.workflow_run_id:
                return False

        if filter.execution_id:
            execution_id = event_dict.get("execution_id") or event_dict.get("payload", {}).get("execution_id")
            if execution_id != filter.execution_id:
                return False

        if filter.work_item_id:
            work_item_id = event_dict.get("work_item_id") or event_dict.get("payload", {}).get("work_item_id")
            if work_item_id != filter.work_item_id:
                return False

        if filter.workflow_id:
            workflow_id = event_dict.get("workflow_id") or event_dict.get("payload", {}).get("workflow_id")
            if workflow_id != filter.workflow_id:
                return False

        if filter.agent_id:
            agent_id = event_dict.get("agent_id") or event_dict.get("payload", {}).get("agent_id")
            if agent_id != filter.agent_id:
                return False

        if filter.project_name:
            project_name = event_dict.get("project_name") or event_dict.get("payload", {}).get("project_name")
            if project_name != filter.project_name:
                return False

        return True

    def _event_matches_filter(self, event: CodetoreumEvent, event_dict: dict[str, Any], filter: EventFilter) -> bool:
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
            workflow_run_id = event_dict.get("workflow_run_id") or event_dict.get("payload", {}).get("workflow_run_id")
            if workflow_run_id != filter.workflow_run_id:
                return False

        if filter.execution_id:
            execution_id = event_dict.get("execution_id") or event_dict.get("payload", {}).get("execution_id")
            if execution_id != filter.execution_id:
                return False

        if filter.work_item_id:
            work_item_id = event_dict.get("work_item_id") or event_dict.get("payload", {}).get("work_item_id")
            if work_item_id != filter.work_item_id:
                return False

        if filter.workflow_id:
            workflow_id = event_dict.get("workflow_id") or event_dict.get("payload", {}).get("workflow_id")
            if workflow_id != filter.workflow_id:
                return False

        if filter.agent_id:
            agent_id = event_dict.get("agent_id") or event_dict.get("payload", {}).get("agent_id")
            if agent_id != filter.agent_id:
                return False

        if filter.project_name:
            project_name = event_dict.get("project_name") or event_dict.get("payload", {}).get("project_name")
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

    Features:
    - Connection pooling with max connections limit
    - Redis pub/sub for horizontal scaling across multiple server instances
    - Connection state persistence for crash recovery
    - Backpressure handling and flow control
    - Heartbeat/ping-pong for connection health monitoring
    """

    def __init__(
        self,
        config: WebSocketConfig | None = None,
        auth_manager: Any | None = None,
        redis_pubsub: Any | None = None,
        redis_client: Any | None = None,
    ):
        """
        Initialize WebSocket adapter.

        Args:
            config: WebSocket configuration (defaults if None)
            auth_manager: Authentication manager for token validation
            redis_pubsub: Redis pub/sub adapter for horizontal scaling (optional)
            redis_client: Redis client for connection persistence (optional)
        """
        self.manager = ConnectionManager(config, redis_pubsub, redis_client)
        self.auth_manager = auth_manager
        self._connection_counter = 0
        self._heartbeat_task: asyncio.Task | None = None
        self._background_tasks: set[asyncio.Task] = set()

        # Instrumentation for distributed tracing
        self._session_tracer = WebSocketSessionTracer()
        self._session_spans: dict[str, Any | None] = {}
        self._message_tracers: dict[str, WebSocketMessageTracer | None] = {}

    def get_next_connection_id(self) -> str:
        """
        Generate unique connection ID.

        Returns:
            Connection ID
        """
        self._connection_counter += 1
        return f"ws-{self._connection_counter}"

    async def handle_websocket(self, websocket: WebSocket, token: str | None = None) -> None:
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

        # Start session span for distributed tracing
        session_span = self._session_tracer.start_session(
            connection_id=connection_id,
            client_ip=websocket.client.host if websocket.client else None,
            token_present=bool(token),
        )
        self._session_spans[connection_id] = session_span
        self._message_tracers[connection_id] = WebSocketMessageTracer(session_span)

        heartbeat_task = None
        try:
            # Accept connection
            await self.manager.connect(websocket, connection_id)

            # Send welcome message with client_id
            await self.manager.send_personal_message(
                ConnectedMessage(
                    client_id=connection_id,
                    message="Connected to Codetoreum event stream",
                    timestamp=datetime.now(UTC),
                ).model_dump(mode="json"),
                connection_id,
            )

            # Start heartbeat monitoring in background
            heartbeat_task = asyncio.create_task(self._heartbeat_monitor(connection_id))

            try:
                # Message handling loop
                while True:
                    # Receive message from client
                    data = await websocket.receive_text()

                    # Validate message size (prevent memory exhaustion)
                    MAX_MESSAGE_SIZE = 10_000  # 10KB max message size
                    if len(data) > MAX_MESSAGE_SIZE:
                        logger.warning(f"Message too large from connection {connection_id}: {len(data)} bytes")
                        await self.manager.send_personal_message(
                            ErrorMessage(
                                code="message_too_large",
                                message=f"Message size {len(data)} bytes exceeds maximum {MAX_MESSAGE_SIZE} bytes",
                                timestamp=datetime.now(UTC),
                            ).model_dump(mode="json"),
                            connection_id,
                        )
                        continue

                    message = json.loads(data)

                    # Validate message structure
                    if not isinstance(message, dict):
                        logger.warning(f"Invalid message structure from connection {connection_id}: not a JSON object")
                        await self.manager.send_personal_message(
                            ErrorMessage(
                                code="invalid_message",
                                message="Message must be a JSON object",
                                timestamp=datetime.now(UTC),
                            ).model_dump(mode="json"),
                            connection_id,
                        )
                        continue

                    if "type" not in message:
                        logger.warning(f"Message missing 'type' field from connection {connection_id}")
                        await self.manager.send_personal_message(
                            ErrorMessage(
                                code="invalid_message",
                                message="Message must contain 'type' field",
                                timestamp=datetime.now(UTC),
                            ).model_dump(mode="json"),
                            connection_id,
                        )
                        continue

                    # Check rate limit
                    if connection_id in self.manager.connections:
                        conn_state = self.manager.connections[connection_id]

                        # Update last heartbeat timestamp
                        conn_state.last_heartbeat = time.time()

                        # Apply rate limiting
                        if conn_state.rate_limiter and not conn_state.rate_limiter.try_consume():
                            logger.warning(f"Rate limit exceeded for connection {connection_id}")
                            await self.manager.send_personal_message(
                                ErrorMessage(
                                    code="rate_limit_exceeded",
                                    message="Rate limit exceeded. Slow down message rate.",
                                    timestamp=datetime.now(UTC),
                                ).model_dump(mode="json"),
                                connection_id,
                            )
                            # Don't disconnect, just skip processing this message
                            continue

                    # Handle message based on type
                    message_type = message.get("type")

                    if message_type == "subscribe":
                        await self._handle_subscribe_with_instrumentation(connection_id, message)
                    elif message_type == "unsubscribe":
                        await self._handle_unsubscribe_with_instrumentation(connection_id, message)
                    elif message_type == "ping":
                        await self._handle_ping_with_instrumentation(connection_id)
                    else:
                        # Unknown message type
                        await self.manager.send_personal_message(
                            ErrorMessage(
                                code="unknown_message_type",
                                message=f"Unknown message type: {message_type}",
                                timestamp=datetime.now(UTC),
                            ).model_dump(mode="json"),
                            connection_id,
                        )

            except WebSocketDisconnect:
                # Client disconnected
                logger.info(f"WebSocket client {connection_id} disconnected")
                self._cleanup_session_span(connection_id, reason="client_disconnect")
                self.manager.disconnect(connection_id)
            except ValueError as e:
                # Invalid message format or data
                logger.error(
                    f"ValueError in WebSocket handler for {connection_id}: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INVALID_INPUT},
                )
                try:
                    await self.manager.send_personal_message(
                        ErrorMessage(
                            code="invalid_message",
                            message=f"Invalid message: {e!s}",
                            timestamp=datetime.now(UTC),
                        ).model_dump(mode="json"),
                        connection_id,
                    )
                except Exception as send_error:
                    logger.debug(
                        f"Failed to send invalid message error for connection {connection_id}: {send_error}",
                        exc_info=True,
                    )
                finally:
                    self._cleanup_session_span(connection_id, reason="invalid_message")
                    self.manager.disconnect(connection_id)
            except json.JSONDecodeError as e:
                # JSON parsing error
                logger.error(
                    f"JSON decode error for {connection_id}: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_INVALID_INPUT},
                )
                try:
                    await self.manager.send_personal_message(
                        ErrorMessage(
                            code="json_error",
                            message=f"Invalid JSON: {e!s}",
                            timestamp=datetime.now(UTC),
                        ).model_dump(mode="json"),
                        connection_id,
                    )
                except Exception as send_error:
                    logger.debug(
                        f"Failed to send JSON error message for connection {connection_id}: {send_error}",
                        exc_info=True,
                    )
                finally:
                    self._cleanup_session_span(connection_id, reason="json_parse_error")
                    self.manager.disconnect(connection_id)
            except Exception as e:
                # Unexpected error
                logger.error(
                    f"Unexpected WebSocket error for client {connection_id}: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_UNHANDLED_EXCEPTION},
                )
                try:
                    await self.manager.send_personal_message(
                        ErrorMessage(
                            code="internal_error",
                            message=f"Internal error: {e!s}",
                            timestamp=datetime.now(UTC),
                        ).model_dump(mode="json"),
                        connection_id,
                    )
                except Exception as send_error:
                    logger.debug(
                        f"Failed to send internal error message for connection {connection_id}: {send_error}",
                        exc_info=True,
                    )
                finally:
                    self._cleanup_session_span(connection_id, reason="unexpected_error")
                    self.manager.disconnect(connection_id)
            finally:
                # Make sure session span is cleaned up
                if connection_id in self._session_spans:
                    self._cleanup_session_span(connection_id, reason="final_cleanup")
        finally:
            # Cancel heartbeat task
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _heartbeat_monitor(self, connection_id: str) -> None:
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
                        f"Connection {connection_id} timed out (no heartbeat for {time_since_heartbeat:.1f}s)"
                    )
                    await self.manager._send_error_and_close(
                        connection_id,
                        code=4000,
                        reason="Connection timeout - no heartbeat received",
                    )
                    return

                # Send ping to client
                try:
                    await conn_state.websocket.send_json({"type": "ping", "timestamp": datetime.now(UTC).isoformat()})
                except Exception as e:
                    logger.error(
                        f"Failed to send heartbeat ping: {e}",
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
                    )
                    return

        except asyncio.CancelledError:
            # Task cancelled, connection closing - expected behavior
            logger.debug(f"Heartbeat monitor cancelled for connection {connection_id}")

    def _cleanup_session_span(self, connection_id: str, reason: str = "normal_closure") -> None:
        """
        Clean up session span for a disconnected connection.

        Args:
            connection_id: Connection identifier
            reason: Reason for disconnection
        """
        session_span = self._session_spans.pop(connection_id, None)
        self._message_tracers.pop(connection_id, None)

        if connection_id in self.manager.connections:
            conn_state = self.manager.connections[connection_id]
            message_count = len(conn_state.buffer)
            buffered_events = len(conn_state.subscriptions)
        else:
            message_count = 0
            buffered_events = 0

        self._session_tracer.end_session(
            session_span,
            reason=reason,
            message_count=message_count,
            buffered_events=buffered_events,
        )

    async def _handle_subscribe_with_instrumentation(self, connection_id: str, message: dict[str, Any]) -> None:
        """
        Handle subscribe message with instrumentation.

        Args:
            connection_id: Connection identifier
            message: Subscribe message
        """
        message_tracer = self._message_tracers.get(connection_id)
        if not message_tracer:
            await self._handle_subscribe(connection_id, message)
            return

        # Count filters
        filter_attrs = [
            message.get("event_types"),
            message.get("work_item_id"),
            message.get("workflow_id"),
            message.get("agent_id"),
            message.get("project_name"),
        ]
        filter_count = sum(1 for attr in filter_attrs if attr)

        # Start message span
        message_span = message_tracer.start_subscribe_message(
            connection_id=connection_id,
            subscription_type=message.get("subscription_type", "all_events"),
            filter_count=filter_count,
        )

        try:
            await self._handle_subscribe(connection_id, message)
            message_tracer.end_message_span(message_span, success=True)
        except Exception:
            message_tracer.end_message_span(
                message_span,
                success=False,
                error_code="subscribe_error",
            )
            raise

    async def _handle_unsubscribe_with_instrumentation(self, connection_id: str, message: dict[str, Any]) -> None:
        """
        Handle unsubscribe message with instrumentation.

        Args:
            connection_id: Connection identifier
            message: Unsubscribe message
        """
        message_tracer = self._message_tracers.get(connection_id)
        if not message_tracer:
            await self._handle_unsubscribe(connection_id, message)
            return

        subscription_id = message.get("subscription_id", "unknown")

        # Start message span
        message_span = message_tracer.start_unsubscribe_message(connection_id, subscription_id)

        try:
            await self._handle_unsubscribe(connection_id, message)
            message_tracer.end_message_span(message_span, success=True)
        except Exception:
            message_tracer.end_message_span(
                message_span,
                success=False,
                error_code="unsubscribe_error",
            )
            raise

    async def _handle_ping_with_instrumentation(self, connection_id: str) -> None:
        """
        Handle ping message with instrumentation.

        Args:
            connection_id: Connection identifier
        """
        message_tracer = self._message_tracers.get(connection_id)
        if not message_tracer:
            await self._handle_ping(connection_id)
            return

        # Start message span
        message_span = message_tracer.start_ping_message(connection_id)

        try:
            await self._handle_ping(connection_id)
            message_tracer.end_message_span(message_span, success=True)
        except Exception:
            message_tracer.end_message_span(
                message_span,
                success=False,
                error_code="ping_error",
            )
            raise

    async def _handle_subscribe(self, connection_id: str, message: dict[str, Any]) -> None:
        """
        Handle subscribe message with extended filtering support.

        Args:
            connection_id: Connection identifier
            message: Subscribe message with filter criteria
        """
        try:
            # Parse subscription type
            subscription_type = SubscriptionType[message.get("subscription_type", "ALL_EVENTS").upper()]

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
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                connection_id,
            )

        except Exception as e:
            logger.error(
                f"Failed to process subscribe message: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION},
            )
            await self.manager.send_personal_message(
                ErrorMessage(
                    code="subscribe_failed",
                    message=f"Failed to subscribe: {e!s}",
                    timestamp=datetime.now(UTC),
                ).model_dump(mode="json"),
                connection_id,
            )

    async def _handle_unsubscribe(self, connection_id: str, message: dict[str, Any]) -> None:
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
                "timestamp": datetime.now(UTC).isoformat(),
            },
            connection_id,
        )

    async def _handle_ping(self, connection_id: str) -> None:
        """
        Handle ping message (keepalive).

        Args:
            connection_id: Connection identifier
        """
        await self.manager.send_personal_message(
            {"type": "pong", "timestamp": datetime.now(UTC).isoformat()},
            connection_id,
        )

    async def broadcast_event(self, event: CodetoreumEvent):
        """
        Broadcast domain event to subscribed connections.

        This method is called by the event bus when domain events are published.
        Creates MESSAGE spans for each client that receives the event, linking
        to the event's trace context for distributed tracing.

        Args:
            event: Domain event to broadcast
        """
        # Delegate to manager to actually broadcast
        await self.manager.broadcast_event(event)

        # Record event deliveries with instrumentation
        # (async, doesn't block broadcasting)
        self._record_event_deliveries(event)

    def _record_event_deliveries(self, event: CodetoreumEvent) -> None:
        """
        Record event delivery to clients for tracing purposes.

        Creates MESSAGE spans for each subscribed client, linking to the event's
        trace context. This enables end-to-end tracing from event creation
        through publication to client delivery.

        Args:
            event: Domain event being delivered
        """
        try:
            for connection_id, message_tracer in self._message_tracers.items():
                if not message_tracer:
                    continue

                try:
                    # Check if this connection has subscriptions that match the event
                    if connection_id not in self.manager.connections:
                        continue

                    conn_state = self.manager.connections[connection_id]
                    for subscription in conn_state.subscriptions:
                        # Check if subscription matches event
                        if self._subscription_matches_event(subscription, event):
                            # Create MESSAGE span for this delivery
                            span = message_tracer.start_event_delivery_span(
                                connection_id=connection_id,
                                event_type=event.event_type,
                                event_id=str(event.event_id),
                                subscription_type=subscription.subscription_type.value,
                            )

                            # Link to event's trace context for distributed tracing
                            message_tracer.link_to_event_trace_context(span, event)

                            # End span (in production, might be held open while
                            # message is in buffer for more accurate timing)
                            message_tracer.end_message_span(span, success=True)
                except Exception as e:
                    logger.warning(
                        f"Error recording event delivery for {connection_id}: {e}",
                        exc_info=True,
                    )
        except Exception as e:
            logger.warning(f"Error in _record_event_deliveries: {e}", exc_info=True)

    @staticmethod
    def _subscription_matches_event(subscription: Any, event: CodetoreumEvent) -> bool:
        """
        Check if a subscription matches an event.

        Args:
            subscription: EventFilter subscription
            event: Domain event

        Returns:
            True if event matches subscription filters
        """
        try:
            # Check event type filters (OR logic)
            if subscription.event_types:
                if event.event_type not in subscription.event_types:
                    return False

            # Check aggregate ID filters (AND logic)
            if subscription.work_item_id:
                if hasattr(event, "work_item_id") and event.work_item_id != subscription.work_item_id:
                    return False

            if subscription.workflow_id:
                if hasattr(event, "workflow_id") and event.workflow_id != subscription.workflow_id:
                    return False

            if subscription.agent_id:
                if hasattr(event, "agent_id") and event.agent_id != subscription.agent_id:
                    return False

            if subscription.project_name:
                if hasattr(event, "project_name") and event.project_name != subscription.project_name:
                    return False

            return True
        except Exception as e:
            logger.warning(
                f"Error matching subscription to event: {e}",
                exc_info=True,
            )
            return False

    async def close(self):
        """
        Close the WebSocket adapter and clean up all background tasks.

        This should be called during application shutdown to ensure
        all pending tasks complete gracefully.
        """
        await self.manager.close()
