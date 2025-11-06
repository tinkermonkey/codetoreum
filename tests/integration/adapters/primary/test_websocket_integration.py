"""
Integration tests for WebSocket adapter.

Tests real-time event streaming, filtering, authentication, and backpressure handling.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.websocket_adapter import (
    WebSocketAdapter,
    WebSocketConfig,
)
from codetoreum.domain.events import (
    DomainEvent,
    ExecutionStarted,
    ExecutionCompleted,
    WorkItemCreated,
)
from codetoreum.infrastructure.event_bus import EventBus


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def websocket_config():
    """WebSocket configuration for testing."""
    return WebSocketConfig(
        max_buffer_size=100,
        flow_control_threshold=0.8,
        disconnect_on_overflow=True,
        heartbeat_interval=10,
        heartbeat_timeout=30,
    )


@pytest.fixture
def websocket_adapter(websocket_config):
    """Create WebSocket adapter for testing."""
    return WebSocketAdapter(config=websocket_config, auth_manager=None)


@pytest.fixture
def event_bus():
    """Create event bus for testing."""
    bus = EventBus()
    yield bus
    # Cleanup handlers
    for handlers in list(bus._handlers.values()):
        for handler in list(handlers):
            bus.unregister_handler(handler)
    for handler in list(bus._wildcard_handlers):
        bus.unregister_handler(handler)
    bus.reset_statistics()


@pytest.fixture
async def connected_websocket_adapter(websocket_adapter, event_bus):
    """WebSocket adapter wired to event bus."""
    # Subscribe adapter to all events
    event_bus.subscribe(None, websocket_adapter.broadcast_event)
    return websocket_adapter, event_bus


# ============================================================================
# Connection Tests
# ============================================================================


@pytest.mark.asyncio
async def test_websocket_connection(websocket_adapter):
    """Test basic WebSocket connection and welcome message."""
    # This test requires a mock WebSocket, which is complex to set up
    # For now, we test the connection manager directly
    connection_id = "test-conn-1"

    # Create mock websocket
    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            self.last_message = data

    ws = MockWebSocket()
    await websocket_adapter.manager.connect(ws, connection_id)

    assert connection_id in websocket_adapter.manager.connections
    assert websocket_adapter.manager.stats["total_connections"] == 1


@pytest.mark.asyncio
async def test_websocket_disconnection(websocket_adapter):
    """Test WebSocket disconnection and cleanup."""
    connection_id = "test-conn-1"

    class MockWebSocket:
        async def accept(self):
            pass

    ws = MockWebSocket()
    await websocket_adapter.manager.connect(ws, connection_id)

    # Disconnect
    websocket_adapter.manager.disconnect(connection_id)

    assert connection_id not in websocket_adapter.manager.connections


# ============================================================================
# Subscription and Filtering Tests
# ============================================================================


@pytest.mark.asyncio
async def test_subscribe_with_event_type_filter(websocket_adapter):
    """Test subscription with event type filtering."""
    connection_id = "test-conn-1"

    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            self.messages = getattr(self, "messages", [])
            self.messages.append(data)

    ws = MockWebSocket()
    await websocket_adapter.manager.connect(ws, connection_id)

    # Subscribe with event type filter
    await websocket_adapter._handle_subscribe(
        connection_id,
        {
            "type": "subscribe",
            "subscription_type": "all_events",
            "event_types": ["ExecutionStarted", "ExecutionCompleted"],
        },
    )

    # Check subscription was registered
    conn_state = websocket_adapter.manager.connections[connection_id]
    assert len(conn_state.subscriptions) == 1
    assert conn_state.subscriptions[0].event_types == [
        "ExecutionStarted",
        "ExecutionCompleted",
    ]


@pytest.mark.asyncio
async def test_subscribe_with_work_item_filter(websocket_adapter):
    """Test subscription with work item ID filter."""
    connection_id = "test-conn-1"

    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            pass

    ws = MockWebSocket()
    await websocket_adapter.manager.connect(ws, connection_id)

    # Subscribe with work item filter
    work_item_id = "wi-123"
    await websocket_adapter._handle_subscribe(
        connection_id,
        {
            "type": "subscribe",
            "subscription_type": "all_events",
            "work_item_id": work_item_id,
        },
    )

    # Check reverse index
    assert work_item_id in websocket_adapter.manager.work_item_subscribers
    assert connection_id in websocket_adapter.manager.work_item_subscribers[work_item_id]


# ============================================================================
# Event Broadcasting Tests
# ============================================================================


@pytest.mark.asyncio
async def test_broadcast_event_to_subscribers(websocket_adapter):
    """Test event broadcasting to subscribed connections."""
    connection_id = "test-conn-1"
    received_messages: List[dict] = []

    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            received_messages.append(data)

    ws = MockWebSocket()
    await websocket_adapter.manager.connect(ws, connection_id)

    # Subscribe to all events
    await websocket_adapter._handle_subscribe(
        connection_id,
        {
            "type": "subscribe",
            "subscription_type": "all_events",
        },
    )

    # Broadcast event
    event = ExecutionStarted(
        aggregate_id="exec-123",
        payload={
            "started_at": datetime.now(timezone.utc).isoformat(),
            "container_name": "test-container",
        },
    )

    await websocket_adapter.broadcast_event(event)

    # Check that event was received
    event_messages = [m for m in received_messages if m.get("type") == "event"]
    assert len(event_messages) == 1
    assert event_messages[0]["event_type"] == "ExecutionStarted"


@pytest.mark.asyncio
async def test_event_filtering_by_type(websocket_adapter):
    """Test that events are filtered by type."""
    connection_id = "test-conn-1"
    received_messages: List[dict] = []

    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            received_messages.append(data)

    ws = MockWebSocket()
    await websocket_adapter.manager.connect(ws, connection_id)

    # Subscribe only to ExecutionStarted events
    await websocket_adapter._handle_subscribe(
        connection_id,
        {
            "type": "subscribe",
            "subscription_type": "all_events",
            "event_types": ["ExecutionStarted"],
        },
    )

    # Broadcast ExecutionStarted event
    event1 = ExecutionStarted(
        aggregate_id="exec-123",
        payload={"started_at": datetime.now(timezone.utc).isoformat()},
    )
    await websocket_adapter.broadcast_event(event1)

    # Broadcast ExecutionCompleted event (should be filtered out)
    event2 = ExecutionCompleted(
        aggregate_id="exec-123",
        payload={
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "input_tokens": 100,
            "output_tokens": 200,
        },
    )
    await websocket_adapter.broadcast_event(event2)

    # Check that only ExecutionStarted was received
    event_messages = [m for m in received_messages if m.get("type") == "event"]
    assert len(event_messages) == 1
    assert event_messages[0]["event_type"] == "ExecutionStarted"


# ============================================================================
# Backpressure Tests
# ============================================================================


@pytest.mark.asyncio
async def test_backpressure_flow_control_warning(websocket_adapter):
    """Test that flow control warning is sent when buffer threshold reached."""
    connection_id = "test-conn-1"
    received_messages: List[dict] = []

    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            received_messages.append(data)

    ws = MockWebSocket()
    await websocket_adapter.manager.connect(ws, connection_id)

    # Subscribe to all events
    await websocket_adapter._handle_subscribe(
        connection_id,
        {"type": "subscribe", "subscription_type": "all_events"},
    )

    # Fill buffer past threshold (80% of 100 = 80 messages)
    conn_state = websocket_adapter.manager.connections[connection_id]
    for i in range(85):
        conn_state.buffer.append({"type": "test", "seq": i})

    # Send one more message to trigger flow control warning
    await websocket_adapter.manager.send_personal_message(
        {"type": "test", "seq": 86}, connection_id
    )

    # Check for flow control warning
    flow_control_messages = [
        m for m in received_messages if m.get("type") == "flow_control"
    ]
    assert len(flow_control_messages) >= 1
    assert flow_control_messages[0]["buffer_usage"] >= 0.8


@pytest.mark.asyncio
async def test_backpressure_disconnect_on_overflow(websocket_adapter):
    """Test that client is disconnected when buffer overflows."""
    connection_id = "test-conn-1"

    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            pass

        async def close(self, code=None, reason=None):
            self.closed = True
            self.close_code = code
            self.close_reason = reason

    ws = MockWebSocket()
    await websocket_adapter.manager.connect(ws, connection_id)

    # Fill buffer to max (100 messages)
    conn_state = websocket_adapter.manager.connections[connection_id]
    for i in range(100):
        conn_state.buffer.append({"type": "test", "seq": i})

    # Try to send one more message (should trigger disconnect)
    await websocket_adapter.manager.send_personal_message(
        {"type": "test", "seq": 101}, connection_id
    )

    # Check that connection was closed
    assert connection_id not in websocket_adapter.manager.connections
    assert websocket_adapter.manager.stats["disconnections_due_to_overflow"] == 1


# ============================================================================
# Integration with Event Bus Tests
# ============================================================================


@pytest.mark.asyncio
async def test_integration_with_event_bus():
    """Test full integration: event bus → WebSocket adapter → clients."""
    # Create event bus and websocket adapter
    event_bus = EventBus()
    websocket_adapter = WebSocketAdapter()

    # Register adapter with event bus
    event_bus.subscribe(None, websocket_adapter.broadcast_event)

    # Connect mock client
    connection_id = "test-conn-1"
    received_messages: List[dict] = []

    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            received_messages.append(data)

    ws = MockWebSocket()
    await websocket_adapter.manager.connect(ws, connection_id)

    # Subscribe to all events
    await websocket_adapter._handle_subscribe(
        connection_id,
        {"type": "subscribe", "subscription_type": "all_events"},
    )

    # Publish event via event bus
    event = WorkItemCreated(
        aggregate_id="wi-123",
        payload={
            "title": "Test Work Item",
            "description": "Test description",
            "project_id": "proj-1",
            "labels": ["test"],
            "priority": 1,
        },
    )

    await event_bus.publish(event)

    # Give time for event to propagate
    await asyncio.sleep(0.1)

    # Check that client received the event
    event_messages = [m for m in received_messages if m.get("type") == "event"]
    assert len(event_messages) >= 1
    assert any(m["event_type"] == "WorkItemCreated" for m in event_messages)


# ============================================================================
# Statistics Tests
# ============================================================================


def test_connection_statistics(websocket_adapter):
    """Test that connection statistics are tracked correctly."""
    stats = websocket_adapter.manager.stats

    # Initial stats
    assert stats["total_connections"] == 0
    assert stats["messages_sent"] == 0
    assert stats["flow_control_warnings"] == 0
    assert stats["disconnections_due_to_overflow"] == 0
