"""Unit tests for RedisPubSubEventEmitter using fakeredis."""

from __future__ import annotations

import asyncio

import fakeredis.aioredis
import pytest

from codetoreum.adapters.secondary.redis_pubsub_event_emitter import (
    RedisPubSubEventEmitter,
)
from codetoreum.domain.events.adapter_events import CodetoreumEvent


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.close()


@pytest.fixture
async def emitter(redis_client):
    em = RedisPubSubEventEmitter(redis_client=redis_client)
    try:
        yield em
    finally:
        await em.close()


def _make_event(event_type: str = "test.event") -> CodetoreumEvent:
    return CodetoreumEvent(type=event_type, timestamp="2026-05-29T00:00:00+00:00", source="test")


class TestRedisPubSubEventEmitterLocalDelivery:
    """Local in-process delivery preserves MockEventEmitter semantics."""

    @pytest.mark.asyncio
    async def test_emit_calls_local_handler_synchronously(self, emitter):
        received: list[CodetoreumEvent] = []
        emitter.on("test.event", received.append)
        event = _make_event()
        emitter.emit(event)
        assert received == [event]

    @pytest.mark.asyncio
    async def test_off_removes_handler(self, emitter):
        received: list[CodetoreumEvent] = []
        emitter.on("test.event", received.append)
        emitter.off("test.event", received.append)
        emitter.emit(_make_event())
        assert received == []

    @pytest.mark.asyncio
    async def test_emit_for_unsubscribed_type_is_noop_locally(self, emitter):
        received: list[CodetoreumEvent] = []
        emitter.on("other.event", received.append)
        emitter.emit(_make_event("test.event"))
        assert received == []

    @pytest.mark.asyncio
    async def test_emit_with_failing_handler_does_not_raise(self, emitter):
        emitter.on("test.event", lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
        # Should not raise; failure is logged.
        emitter.emit(_make_event())


class TestRedisPubSubEventEmitterValidation:
    @pytest.mark.asyncio
    async def test_on_rejects_empty_event_type(self, emitter):
        with pytest.raises(ValueError):
            emitter.on("", lambda e: None)

    @pytest.mark.asyncio
    async def test_on_rejects_non_callable(self, emitter):
        with pytest.raises(ValueError):
            emitter.on("test.event", "not-a-callable")

    @pytest.mark.asyncio
    async def test_emit_rejects_non_event(self, emitter):
        with pytest.raises(ValueError):
            emitter.emit("not-an-event")

    @pytest.mark.asyncio
    async def test_off_unknown_handler_raises(self, emitter):
        with pytest.raises(ValueError):
            emitter.off("test.event", lambda e: None)


class TestRedisPubSubEventEmitterCrossProcess:
    """Two emitter instances over the same Redis exchange events."""

    @pytest.mark.asyncio
    async def test_remote_subscriber_receives_published_event(self, redis_client):
        publisher = RedisPubSubEventEmitter(redis_client=redis_client)
        subscriber = RedisPubSubEventEmitter(redis_client=redis_client)
        received: list[CodetoreumEvent] = []
        subscriber.on("test.event", received.append)
        try:
            # Yield to let the subscriber task subscribe.
            await asyncio.sleep(0.05)
            publisher.emit(_make_event())
            # Yield long enough for the publish task to run and the subscriber
            # to receive.
            await asyncio.sleep(0.15)
            assert any(e.type == "test.event" for e in received)
        finally:
            await publisher.close()
            await subscriber.close()


class TestRedisPubSubEventEmitterLifecycle:
    @pytest.mark.asyncio
    async def test_close_cancels_subscribers(self, redis_client):
        em = RedisPubSubEventEmitter(redis_client=redis_client)
        em.on("test.event", lambda e: None)
        await asyncio.sleep(0.02)
        # A subscriber task should be running.
        assert "test.event" in em._subscriber_tasks
        await em.close()
        assert em._subscriber_tasks == {}
