"""
Integration tests for WebSocket scalability features.

Tests:
- Connection pooling and max connections limit
- Redis pub/sub message distribution across instances
- Connection state persistence and recovery
- Horizontal scaling scenarios
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from codetoreum.adapters.primary.websocket_adapter import (
    ConnectionManager,
    WebSocketAdapter,
    WebSocketConfig,
)
from codetoreum.adapters.secondary.redis_pubsub_adapter import RedisPubSubAdapter
from codetoreum.domain.events import DomainEvent


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = AsyncMock()
    redis.pubsub = MagicMock()
    redis.publish = AsyncMock()
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.get = AsyncMock()
    return redis


@pytest.fixture
def websocket_config():
    """Create WebSocket config for testing."""
    return WebSocketConfig(
        max_connections=5,  # Small limit for testing
        max_buffer_size=100,
        heartbeat_interval=10,
        heartbeat_timeout=30,
        enable_redis_pubsub=True,
        enable_connection_persistence=True,
    )


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection."""
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connection_pooling_limit(websocket_config, mock_redis):
    """Test that connection limit is enforced."""
    # Create connection manager
    manager = ConnectionManager(websocket_config, None, mock_redis)

    # Accept connections up to the limit
    connections = []
    for i in range(websocket_config.max_connections):
        ws = AsyncMock(spec=WebSocket)
        ws.accept = AsyncMock()
        success = await manager.connect(ws, f"conn-{i}")
        assert success is True
        connections.append(ws)

    # Verify all connections accepted
    assert len(manager.connections) == websocket_config.max_connections

    # Try to add one more (should be rejected)
    ws_overflow = AsyncMock(spec=WebSocket)
    ws_overflow.accept = AsyncMock()
    ws_overflow.close = AsyncMock()

    success = await manager.connect(ws_overflow, "conn-overflow")

    # Should be rejected
    assert success is False
    ws_overflow.close.assert_called_once()
    assert manager.stats["connection_rejections"] == 1


@pytest.mark.asyncio
async def test_connection_persistence(websocket_config, mock_redis):
    """Test that connection state is persisted to Redis."""
    # Create connection manager
    manager = ConnectionManager(websocket_config, None, mock_redis)

    # Create and accept connection
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    await manager.connect(ws, "conn-test")

    # Verify connection state was persisted
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args[0]

    # Check key format
    assert call_args[0] == "websocket:connection:conn-test"

    # Check TTL
    assert call_args[1] == websocket_config.heartbeat_timeout * 2

    # Check connection data
    connection_data = json.loads(call_args[2])
    assert connection_data["connection_id"] == "conn-test"
    assert "subscriptions" in connection_data
    assert "last_heartbeat" in connection_data


@pytest.mark.asyncio
async def test_connection_cleanup_removes_persistence(websocket_config, mock_redis):
    """Test that disconnecting removes persisted state."""
    # Create connection manager
    manager = ConnectionManager(websocket_config, None, mock_redis)

    # Create and accept connection
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    await manager.connect(ws, "conn-test")

    # Disconnect
    manager.disconnect("conn-test")

    # Wait for async cleanup
    await asyncio.sleep(0.1)

    # Verify persisted state was removed
    mock_redis.delete.assert_called()


@pytest.mark.asyncio
async def test_redis_pubsub_integration(websocket_config, mock_redis):
    """Test Redis pub/sub integration for multi-instance broadcasting."""
    # Create Redis pub/sub adapter
    mock_pubsub_client = AsyncMock()
    mock_pubsub_client.subscribe = AsyncMock()
    mock_redis.pubsub.return_value = mock_pubsub_client

    redis_pubsub = RedisPubSubAdapter(mock_redis)

    # Create connection manager with Redis pub/sub
    manager = ConnectionManager(websocket_config, redis_pubsub, mock_redis)

    # Create test event
    event = DomainEvent(
        event_type="TestEvent",
        aggregate_id="test-123",
        aggregate_type="Test",
    )
    event.to_dict = lambda: {
        "event_id": "evt-123",
        "event_type": "TestEvent",
        "aggregate_id": "test-123",
    }

    # Broadcast event
    await manager.broadcast_event(event)

    # Verify event was published to Redis
    mock_redis.publish.assert_called_once()


@pytest.mark.asyncio
async def test_multi_instance_message_distribution(websocket_config, mock_redis):
    """Test that messages are distributed across multiple instances via Redis."""
    # Create two connection managers (simulating two server instances)
    mock_pubsub_client_1 = AsyncMock()
    mock_pubsub_client_1.subscribe = AsyncMock()
    mock_redis.pubsub.return_value = mock_pubsub_client_1

    redis_pubsub_1 = RedisPubSubAdapter(mock_redis)
    manager_1 = ConnectionManager(websocket_config, redis_pubsub_1, mock_redis)

    redis_pubsub_2 = RedisPubSubAdapter(mock_redis)
    manager_2 = ConnectionManager(websocket_config, redis_pubsub_2, mock_redis)

    # Connect clients to each instance
    ws_1 = AsyncMock(spec=WebSocket)
    ws_1.accept = AsyncMock()
    ws_1.send_json = AsyncMock()
    await manager_1.connect(ws_1, "conn-1")

    ws_2 = AsyncMock(spec=WebSocket)
    ws_2.accept = AsyncMock()
    ws_2.send_json = AsyncMock()
    await manager_2.connect(ws_2, "conn-2")

    # Subscribe both connections to all events
    from codetoreum.adapters.primary.websocket_adapter import (
        EventFilter,
        SubscriptionType,
    )

    manager_1.subscribe(
        "conn-1", EventFilter(subscription_type=SubscriptionType.ALL_EVENTS)
    )
    manager_2.subscribe(
        "conn-2", EventFilter(subscription_type=SubscriptionType.ALL_EVENTS)
    )

    # Create test event
    event = DomainEvent(
        event_type="TestEvent",
        aggregate_id="test-123",
        aggregate_type="Test",
    )
    event.to_dict = lambda: {
        "event_id": "evt-123",
        "event_type": "TestEvent",
        "aggregate_id": "test-123",
    }

    # Broadcast from instance 1
    await manager_1.broadcast_event(event)

    # Verify Redis publish was called (for distribution)
    assert mock_redis.publish.call_count >= 1


@pytest.mark.asyncio
async def test_connection_stats_tracking(websocket_config, mock_redis):
    """Test that connection statistics are tracked correctly."""
    # Create connection manager
    manager = ConnectionManager(websocket_config, None, mock_redis)

    # Initial stats
    assert manager.stats["total_connections"] == 0
    assert manager.stats["current_connections"] == 0

    # Add connections
    for i in range(3):
        ws = AsyncMock(spec=WebSocket)
        ws.accept = AsyncMock()
        await manager.connect(ws, f"conn-{i}")

    # Check stats
    assert manager.stats["total_connections"] == 3
    assert manager.stats["current_connections"] == 3

    # Disconnect one
    manager.disconnect("conn-1")

    # Check stats updated
    assert manager.stats["total_connections"] == 3  # Total doesn't decrease
    assert manager.stats["current_connections"] == 2  # Current does


@pytest.mark.asyncio
async def test_websocket_adapter_with_redis(websocket_config, mock_redis):
    """Test WebSocketAdapter initialization with Redis dependencies."""
    # Create Redis pub/sub adapter
    mock_pubsub_client = AsyncMock()
    mock_pubsub_client.subscribe = AsyncMock()
    mock_redis.pubsub.return_value = mock_pubsub_client

    redis_pubsub = RedisPubSubAdapter(mock_redis)

    # Create WebSocket adapter
    adapter = WebSocketAdapter(
        config=websocket_config,
        redis_pubsub=redis_pubsub,
        redis_client=mock_redis,
    )

    # Verify adapter initialized correctly
    assert adapter.manager.config == websocket_config
    assert adapter.manager.redis_pubsub == redis_pubsub
    assert adapter.manager.redis_client == mock_redis


@pytest.mark.asyncio
async def test_connection_limit_with_concurrent_requests(websocket_config, mock_redis):
    """Test connection limit with many concurrent connection attempts."""
    # Create connection manager with small limit
    config = WebSocketConfig(
        max_connections=10,
        enable_redis_pubsub=False,
        enable_connection_persistence=False,
    )
    manager = ConnectionManager(config, None, None)

    # Attempt many concurrent connections
    async def try_connect(conn_id):
        ws = AsyncMock(spec=WebSocket)
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        return await manager.connect(ws, conn_id)

    # Try to create 20 connections (limit is 10)
    results = await asyncio.gather(
        *[try_connect(f"conn-{i}") for i in range(20)]
    )

    # Count successes and failures
    successes = sum(1 for r in results if r is True)
    failures = sum(1 for r in results if r is False)

    # Should have exactly 10 successes and 10 failures
    assert successes == 10
    assert failures == 10
    assert manager.stats["connection_rejections"] == 10


@pytest.mark.asyncio
async def test_broadcast_fallback_on_redis_failure(websocket_config, mock_redis):
    """Test that broadcast falls back to local on Redis failure."""
    # Create Redis pub/sub that will fail
    mock_pubsub_client = AsyncMock()
    mock_pubsub_client.subscribe = AsyncMock()
    mock_redis.pubsub.return_value = mock_pubsub_client
    mock_redis.publish.side_effect = Exception("Redis connection error")

    redis_pubsub = RedisPubSubAdapter(mock_redis)
    manager = ConnectionManager(websocket_config, redis_pubsub, mock_redis)

    # Connect local client
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    await manager.connect(ws, "conn-1")

    from codetoreum.adapters.primary.websocket_adapter import (
        EventFilter,
        SubscriptionType,
    )

    manager.subscribe(
        "conn-1", EventFilter(subscription_type=SubscriptionType.ALL_EVENTS)
    )

    # Create test event
    event = DomainEvent(
        event_type="TestEvent",
        aggregate_id="test-123",
        aggregate_type="Test",
    )
    event.to_dict = lambda: {
        "event_id": "evt-123",
        "event_type": "TestEvent",
        "aggregate_id": "test-123",
    }

    # Broadcast (should fall back to local despite Redis error)
    await manager.broadcast_event(event)

    # Local connection should still receive message
    ws.send_json.assert_called()


@pytest.mark.asyncio
async def test_config_from_environment(monkeypatch):
    """Test loading WebSocket configuration from environment variables."""
    # Set environment variables
    monkeypatch.setenv("CODETOREUM_WS_MAX_CONNECTIONS", "500")
    monkeypatch.setenv("CODETOREUM_WS_MAX_BUFFER_SIZE", "2000")
    monkeypatch.setenv("CODETOREUM_WS_HEARTBEAT_INTERVAL", "60")
    monkeypatch.setenv("CODETOREUM_WS_ENABLE_REDIS_PUBSUB", "false")

    # Load config from environment
    config = WebSocketConfig.from_env()

    # Verify values
    assert config.max_connections == 500
    assert config.max_buffer_size == 2000
    assert config.heartbeat_interval == 60
    assert config.enable_redis_pubsub is False
