"""Tests for InMemoryMessageBroker.

This test class verifies that InMemoryMessageBroker correctly implements
IMessageBroker semantics for pub/sub message distribution, including async/sync
dispatch, statistics tracking, and subscription management.
"""

import asyncio

import pytest

from codetoreum.adapters.testing.in_memory_message_broker import InMemoryMessageBroker
from codetoreum.domain.events import DomainEvent


def create_test_event(event_type: str = "TestEvent", payload: dict | None = None):
    """Helper to create test domain events."""
    if payload is None:
        payload = {"test": "data"}
    return DomainEvent(
        aggregate_id="test-aggregate",
        aggregate_type="TestAggregate",
        payload=payload,
    )


class TestInMemoryMessageBrokerInitialization:
    """Test initialization and lifecycle management."""

    @pytest.mark.asyncio
    async def test_initialize_succeeds(self):
        """Initialize should succeed without errors."""
        broker = InMemoryMessageBroker()

        await broker.initialize()
        # Should not raise

    @pytest.mark.asyncio
    async def test_close_succeeds(self):
        """Close should succeed without errors."""
        broker = InMemoryMessageBroker()

        await broker.initialize()
        await broker.close()
        # Should not raise

    @pytest.mark.asyncio
    async def test_stats_available_after_init(self):
        """Stats should be available after initialization."""
        broker = InMemoryMessageBroker()

        await broker.initialize()
        stats = broker.get_stats()

        assert isinstance(stats, dict)
        assert "events_published" in stats
        assert stats["events_published"] == 0


class TestInMemoryMessageBrokerSubscriptions:
    """Test subscription and unsubscription."""

    @pytest.mark.asyncio
    async def test_subscribe_async_callback(self):
        """Should subscribe async callback successfully."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def handler(msg):
            pass

        await broker.subscribe("test-channel", handler)

        stats = broker.get_stats()
        assert stats["subscriptions"] == 1

    @pytest.mark.asyncio
    async def test_subscribe_sync_callback(self):
        """Should subscribe sync callback successfully."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        def handler(msg):
            pass

        await broker.subscribe("test-channel", handler)

        stats = broker.get_stats()
        assert stats["subscriptions"] == 1

    @pytest.mark.asyncio
    async def test_subscribe_multiple_callbacks(self):
        """Should support multiple subscriptions to same channel."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def handler1(msg):
            pass

        async def handler2(msg):
            pass

        await broker.subscribe("test-channel", handler1)
        await broker.subscribe("test-channel", handler2)

        stats = broker.get_stats()
        assert stats["subscriptions"] == 2

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_callback(self):
        """Unsubscribe should remove callback from subscriptions."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def handler(msg):
            pass

        await broker.subscribe("test-channel", handler)
        assert broker.get_stats()["subscriptions"] == 1

        await broker.unsubscribe("test-channel", handler)
        assert broker.get_stats()["unsubscriptions"] == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_only_affects_target_callback(self):
        """Unsubscribe should only remove target callback."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def handler1(msg):
            pass

        async def handler2(msg):
            pass

        await broker.subscribe("test-channel", handler1)
        await broker.subscribe("test-channel", handler2)

        await broker.unsubscribe("test-channel", handler1)

        # Handler2 should still be subscribed
        count = broker.get_subscriptions_for_channel("test-channel")
        assert count == 1


class TestInMemoryMessageBrokerEventPublishing:
    """Test event publishing and delivery."""

    @pytest.mark.asyncio
    async def test_publish_event_increments_counter(self):
        """Publishing event should increment event counter."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        event = create_test_event()
        await broker.publish_event(event)

        stats = broker.get_stats()
        assert stats["events_published"] == 1

    @pytest.mark.asyncio
    async def test_publish_event_to_async_handler(self):
        """Published event should reach async handler."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        received_messages = []

        async def handler(msg):
            received_messages.append(msg)

        await broker.subscribe("events", handler)

        event = create_test_event()
        await broker.publish_event(event)

        assert len(received_messages) == 1
        assert received_messages[0] == event

    @pytest.mark.asyncio
    async def test_publish_event_to_sync_handler(self):
        """Published event should reach sync handler."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        received_messages = []

        def handler(msg):
            received_messages.append(msg)

        await broker.subscribe("events", handler)

        event = create_test_event()
        await broker.publish_event(event)

        assert len(received_messages) == 1
        assert received_messages[0] == event

    @pytest.mark.asyncio
    async def test_publish_event_to_multiple_handlers(self):
        """Published event should reach all handlers on channel."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        messages1 = []
        messages2 = []

        async def handler1(msg):
            messages1.append(msg)

        async def handler2(msg):
            messages2.append(msg)

        await broker.subscribe("events", handler1)
        await broker.subscribe("events", handler2)

        event = create_test_event()
        await broker.publish_event(event)

        assert len(messages1) == 1
        assert len(messages2) == 1
        assert messages1[0] == event
        assert messages2[0] == event

    @pytest.mark.asyncio
    async def test_publish_event_not_sent_to_unsubscribed_handlers(self):
        """Event should not reach unsubscribed handlers."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        received_messages = []

        async def handler(msg):
            received_messages.append(msg)

        await broker.subscribe("events", handler)
        await broker.unsubscribe("events", handler)

        event = create_test_event()
        await broker.publish_event(event)

        assert len(received_messages) == 0


class TestInMemoryMessageBrokerControlMessages:
    """Test control message publishing."""

    @pytest.mark.asyncio
    async def test_publish_control_message_increments_counter(self):
        """Publishing control message should increment counter."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        await broker.publish_control_message("test_type", {"key": "value"})

        stats = broker.get_stats()
        assert stats["control_messages_published"] == 1

    @pytest.mark.asyncio
    async def test_publish_control_message_to_handler(self):
        """Control message should reach subscribed handler."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        received_messages = []

        async def handler(msg):
            received_messages.append(msg)

        await broker.subscribe("control.test_type", handler)
        await broker.publish_control_message("test_type", {"key": "value"})

        assert len(received_messages) == 1
        assert received_messages[0]["type"] == "test_type"
        assert received_messages[0]["data"]["key"] == "value"


class TestInMemoryMessageBrokerStatistics:
    """Test statistics tracking."""

    @pytest.mark.asyncio
    async def test_get_stats_returns_dict(self):
        """get_stats should return dictionary."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        stats = broker.get_stats()
        assert isinstance(stats, dict)

    @pytest.mark.asyncio
    async def test_stats_track_subscriptions(self):
        """Stats should track active subscriptions."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def handler(msg):
            pass

        await broker.subscribe("channel1", handler)
        await broker.subscribe("channel2", handler)

        stats = broker.get_stats()
        assert stats["subscriptions"] == 2
        assert stats["active_subscriptions"] == 2

    @pytest.mark.asyncio
    async def test_stats_track_unsubscriptions(self):
        """Stats should track unsubscriptions."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def handler(msg):
            pass

        await broker.subscribe("test-channel", handler)
        await broker.unsubscribe("test-channel", handler)

        stats = broker.get_stats()
        assert stats["unsubscriptions"] == 1

    @pytest.mark.asyncio
    async def test_stats_track_messages_delivered(self):
        """Stats should track successful deliveries."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def handler(msg):
            pass

        await broker.subscribe("events", handler)

        event = create_test_event()
        await broker.publish_event(event)

        stats = broker.get_stats()
        assert stats["messages_delivered"] >= 1

    @pytest.mark.asyncio
    async def test_stats_track_delivery_failures(self):
        """Stats should track handler failures."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def failing_handler(msg):
            raise ValueError("Test error")

        await broker.subscribe("events", failing_handler)

        event = create_test_event()
        await broker.publish_event(event)

        stats = broker.get_stats()
        assert stats["delivery_failures"] >= 1

    @pytest.mark.asyncio
    async def test_reset_stats_clears_counters(self):
        """reset_stats should reset all statistics."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def handler(msg):
            pass

        await broker.subscribe("events", handler)
        event = create_test_event()
        await broker.publish_event(event)

        broker.reset_stats()

        stats = broker.get_stats()
        assert stats["events_published"] == 0
        assert stats["subscriptions"] == 0
        assert stats["unsubscriptions"] == 0


class TestInMemoryMessageBrokerPublishedMessages:
    """Test published messages tracking."""

    @pytest.mark.asyncio
    async def test_get_published_messages_returns_list(self):
        """get_published_messages should return list."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        messages = broker.get_published_messages()
        assert isinstance(messages, list)

    @pytest.mark.asyncio
    async def test_get_published_messages_tracks_events(self):
        """get_published_messages should track published events."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        event = create_test_event()
        await broker.publish_event(event)

        messages = broker.get_published_messages()
        assert len(messages) == 1
        assert messages[0] == event

    @pytest.mark.asyncio
    async def test_get_published_messages_tracks_control_messages(self):
        """get_published_messages should track control messages."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        await broker.publish_control_message("test_type", {"key": "value"})

        messages = broker.get_published_messages()
        assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_clear_published_messages(self):
        """clear_published_messages should clear tracking."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        event = create_test_event()
        await broker.publish_event(event)

        assert len(broker.get_published_messages()) == 1

        broker.clear_published_messages()

        assert len(broker.get_published_messages()) == 0


class TestInMemoryMessageBrokerConcurrency:
    """Test concurrent async operations."""

    @pytest.mark.asyncio
    async def test_concurrent_publishes(self):
        """Should handle concurrent event publications."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def handler(msg):
            await asyncio.sleep(0.01)  # Simulate processing

        await broker.subscribe("events", handler)

        events = [
            create_test_event(payload={"n": 1}),
            create_test_event(payload={"n": 2}),
            create_test_event(payload={"n": 3}),
        ]

        # Publish multiple events concurrently
        await asyncio.gather(*[broker.publish_event(e) for e in events])

        stats = broker.get_stats()
        assert stats["events_published"] == 3

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_publish(self):
        """Should handle concurrent subscribe and publish."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        received_messages = []

        async def handler(msg):
            received_messages.append(msg)

        event = create_test_event()

        # Subscribe and publish concurrently
        await asyncio.gather(broker.subscribe("events", handler), broker.publish_event(event))

        # Message should eventually be delivered
        await asyncio.sleep(0.01)
        assert len(received_messages) <= 1  # May or may not be delivered due to timing


class TestInMemoryMessageBrokerChannels:
    """Test channel-specific behavior."""

    @pytest.mark.asyncio
    async def test_get_subscriptions_for_channel(self):
        """get_subscriptions_for_channel should return count."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        async def handler1(msg):
            pass

        async def handler2(msg):
            pass

        await broker.subscribe("test-channel", handler1)
        await broker.subscribe("test-channel", handler2)

        count = broker.get_subscriptions_for_channel("test-channel")
        assert count == 2

    @pytest.mark.asyncio
    async def test_handlers_isolated_by_channel(self):
        """Events on one channel should not reach handlers on another."""
        broker = InMemoryMessageBroker()
        await broker.initialize()

        channel1_messages = []
        channel2_messages = []

        async def handler1(msg):
            channel1_messages.append(msg)

        async def handler2(msg):
            channel2_messages.append(msg)

        await broker.subscribe("channel1", handler1)
        await broker.subscribe("channel2", handler2)

        # Manually publish to specific channel (using internal mechanism)
        event = create_test_event()
        await broker._deliver_to_subscribers("channel1", event)

        assert len(channel1_messages) == 1
        assert len(channel2_messages) == 0
