"""Unit tests for Redis Pub/Sub Adapter."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.secondary.redis_pubsub_adapter import (
    RedisPubSubAdapter,
    RedisPubSubError,
)
from codetoreum.domain.events import DomainEvent


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = AsyncMock()
    redis.pubsub = MagicMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def mock_pubsub():
    """Create mock pubsub with get_message configured to prevent hanging."""

    async def mock_get_message(ignore_subscribe_messages=True, timeout=1.0):
        """Mock get_message that sleeps to simulate timeout behavior."""
        await asyncio.sleep(0.01)  # Small delay to prevent tight loop
        return None

    pubsub = AsyncMock()
    # Mock get_message to sleep before returning None to prevent tight loop
    pubsub.get_message = mock_get_message
    return pubsub


@pytest.fixture
async def adapter(mock_redis):
    """Create Redis pub/sub adapter with mock Redis."""
    adapter = RedisPubSubAdapter(
        redis_client=mock_redis,
        event_channel="test:events",
        control_channel="test:control",
    )
    yield adapter
    # Cleanup: close the adapter to stop background tasks
    await adapter.close()


@pytest.mark.asyncio
async def test_initialize(adapter, mock_redis, mock_pubsub):
    """Test adapter initialization."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Initialize
    await adapter.initialize()

    # Verify
    assert adapter._initialized is True
    mock_redis.pubsub.assert_called_once()
    mock_pubsub.subscribe.assert_called_once_with("test:events", "test:control")
    assert adapter._listener_task is not None


@pytest.mark.asyncio
async def test_initialize_idempotent(adapter, mock_redis, mock_pubsub):
    """Test that initialize can be called multiple times safely."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Initialize twice
    await adapter.initialize()
    await adapter.initialize()

    # Should only be called once
    assert mock_redis.pubsub.call_count == 1


@pytest.mark.asyncio
async def test_publish_event(adapter, mock_redis, mock_pubsub):
    """Test publishing domain event to Redis."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Create test event
    event = DomainEvent(
        aggregate_id="test-123",
        aggregate_type="Test",
    )

    # Publish event
    await adapter.publish_event(event)

    # Verify Redis publish was called
    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args
    assert call_args[0][0] == "test:events"

    # Verify message structure
    message = json.loads(call_args[0][1])
    assert message["type"] == "event"
    assert message["event_type"] == "DomainEvent"
    assert "event_id" in message["event"]

    # Verify stats
    stats = adapter.get_stats()
    assert stats["messages_published"] == 1


@pytest.mark.asyncio
async def test_publish_control_message(adapter, mock_redis, mock_pubsub):
    """Test publishing control message to Redis."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Publish control message
    await adapter.publish_control_message(
        "disconnect", {"connection_id": "ws-123", "reason": "timeout"}
    )

    # Verify Redis publish was called
    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args
    assert call_args[0][0] == "test:control"

    # Verify message structure
    message = json.loads(call_args[0][1])
    assert message["type"] == "disconnect"
    assert message["data"]["connection_id"] == "ws-123"

    # Verify stats
    stats = adapter.get_stats()
    assert stats["messages_published"] == 1


@pytest.mark.asyncio
async def test_subscribe_callback(adapter, mock_redis, mock_pubsub):
    """Test subscribing to channel with callback."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Create callback
    callback_called = False
    received_message = None

    async def callback(message):
        nonlocal callback_called, received_message
        callback_called = True
        received_message = message

    # Subscribe
    await adapter.subscribe("test:events", callback)

    # Verify callback registered
    assert "test:events" in adapter._callbacks
    assert callback in adapter._callbacks["test:events"]


@pytest.mark.asyncio
async def test_unsubscribe_callback(adapter, mock_redis, mock_pubsub):
    """Test unsubscribing callback from channel."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Create and subscribe callback
    async def callback(message):
        pass

    await adapter.subscribe("test:events", callback)

    # Unsubscribe
    await adapter.unsubscribe("test:events", callback)

    # Verify callback removed
    assert "test:events" not in adapter._callbacks


@pytest.mark.asyncio
async def test_message_dispatch(adapter, mock_redis, mock_pubsub):
    """Test message dispatch to callbacks."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Create callback
    received_messages = []

    async def callback(message):
        received_messages.append(message)

    # Subscribe
    await adapter.subscribe("test:events", callback)

    # Simulate message dispatch
    test_message = {"type": "event", "data": "test"}
    message_bytes = json.dumps(test_message).encode("utf-8")

    await adapter._dispatch_message("test:events", message_bytes)

    # Verify callback was called
    assert len(received_messages) == 1
    assert received_messages[0]["type"] == "event"


@pytest.mark.asyncio
async def test_multiple_callbacks(adapter, mock_redis, mock_pubsub):
    """Test multiple callbacks on same channel."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Create callbacks
    received_messages_1 = []
    received_messages_2 = []

    async def callback1(message):
        received_messages_1.append(message)

    async def callback2(message):
        received_messages_2.append(message)

    # Subscribe both
    await adapter.subscribe("test:events", callback1)
    await adapter.subscribe("test:events", callback2)

    # Dispatch message
    test_message = {"type": "event", "data": "test"}
    message_bytes = json.dumps(test_message).encode("utf-8")

    await adapter._dispatch_message("test:events", message_bytes)

    # Verify both callbacks were called
    assert len(received_messages_1) == 1
    assert len(received_messages_2) == 1


@pytest.mark.asyncio
async def test_sync_callback(adapter, mock_redis, mock_pubsub):
    """Test synchronous callback (non-async)."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Create sync callback
    received_messages = []

    def callback(message):
        received_messages.append(message)

    # Subscribe
    await adapter.subscribe("test:events", callback)

    # Dispatch message
    test_message = {"type": "event", "data": "test"}
    message_bytes = json.dumps(test_message).encode("utf-8")

    await adapter._dispatch_message("test:events", message_bytes)

    # Verify callback was called
    assert len(received_messages) == 1


@pytest.mark.asyncio
async def test_callback_error_handling(adapter, mock_redis, mock_pubsub):
    """Test that errors in callbacks don't crash the adapter."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Create callback that raises error
    async def failing_callback(message):
        raise ValueError("Callback error")

    # Create callback that works
    received_messages = []

    async def working_callback(message):
        received_messages.append(message)

    # Subscribe both
    await adapter.subscribe("test:events", failing_callback)
    await adapter.subscribe("test:events", working_callback)

    # Dispatch message
    test_message = {"type": "event", "data": "test"}
    message_bytes = json.dumps(test_message).encode("utf-8")

    # Should not raise exception
    await adapter._dispatch_message("test:events", message_bytes)

    # Working callback should still receive message
    assert len(received_messages) == 1


@pytest.mark.asyncio
async def test_invalid_json_handling(adapter, mock_redis, mock_pubsub):
    """Test handling of invalid JSON in messages."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Create callback
    received_messages = []

    async def callback(message):
        received_messages.append(message)

    # Subscribe
    await adapter.subscribe("test:events", callback)

    # Dispatch invalid JSON
    invalid_json = b"not valid json {"

    # Should not raise exception
    await adapter._dispatch_message("test:events", invalid_json)

    # Callback should not have been called
    assert len(received_messages) == 0


@pytest.mark.asyncio
async def test_get_stats(adapter, mock_redis, mock_pubsub):
    """Test getting statistics."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Publish some messages
    event = DomainEvent(
        aggregate_id="test-123",
        aggregate_type="Test",
    )

    await adapter.publish_event(event)
    await adapter.publish_control_message("test", {})

    # Get stats
    stats = adapter.get_stats()

    assert stats["messages_published"] == 2
    assert stats["messages_received"] == 0
    assert stats["publish_errors"] == 0
    assert stats["initialized"] is True


@pytest.mark.asyncio
async def test_reset_stats(adapter):
    """Test resetting statistics."""
    # Set some stats
    adapter._stats["messages_published"] = 100
    adapter._stats["messages_received"] = 50

    # Reset
    adapter.reset_stats()

    # Verify reset
    stats = adapter.get_stats()
    assert stats["messages_published"] == 0
    assert stats["messages_received"] == 0


@pytest.mark.asyncio
async def test_close(adapter, mock_redis, mock_pubsub):
    """Test closing the adapter."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Initialize
    await adapter.initialize()

    # Close
    await adapter.close()

    # Verify cleanup
    assert adapter._initialized is False
    assert adapter._listener_task is None
    assert adapter._pubsub is None
    assert len(adapter._callbacks) == 0


@pytest.mark.asyncio
async def test_publish_error_handling(adapter, mock_redis, mock_pubsub):
    """Test error handling in publish."""
    # Setup mock pubsub
    mock_redis.pubsub.return_value = mock_pubsub

    # Make publish fail
    mock_redis.publish.side_effect = Exception("Redis connection error")

    # Create event
    event = DomainEvent(
        aggregate_id="test-123",
        aggregate_type="Test",
    )

    # Publish should raise error
    with pytest.raises(RedisPubSubError):
        await adapter.publish_event(event)

    # Verify error was counted
    stats = adapter.get_stats()
    assert stats["publish_errors"] == 1
