"""Unit tests for RedisExecutionStateTracker using fakeredis."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from codetoreum.adapters.secondary.redis_execution_state_tracker import (
    RedisExecutionStateTracker,
)


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.close()


@pytest.fixture
async def tracker(redis_client):
    return RedisExecutionStateTracker(redis_client=redis_client, ttl_seconds=60)


class TestRedisExecutionStateTrackerRoundTrip:
    @pytest.mark.asyncio
    async def test_load_state_after_mark_failed(self, tracker):
        await tracker.mark_execution_failed(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
            reason="Container lost connection",
        )
        state = await tracker.load_state("myproject", "item-123")
        assert state is not None
        assert state["status"] == "failed"
        assert state["agent"] == "claude"
        assert state["reason"] == "Container lost connection"

    @pytest.mark.asyncio
    async def test_load_missing_state_returns_none(self, tracker):
        assert await tracker.load_state("myproject", "does-not-exist") is None

    @pytest.mark.asyncio
    async def test_mark_execution_failed_multiple_times_is_idempotent(self, tracker):
        await tracker.mark_execution_failed(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
            reason="First failure",
        )
        await tracker.mark_execution_failed(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
            reason="Second failure",
        )
        state = await tracker.load_state("myproject", "item-123")
        assert state is not None
        assert state["reason"] == "Second failure"


class TestRedisExecutionStateTrackerMultiProject:
    @pytest.mark.asyncio
    async def test_different_projects_isolated(self, tracker):
        await tracker.mark_execution_failed(
            project="project-a",
            work_item_id="item-1",
            agent="claude",
            reason="Error in A",
        )
        await tracker.mark_execution_failed(
            project="project-b",
            work_item_id="item-1",
            agent="claude",
            reason="Error in B",
        )
        state_a = await tracker.load_state("project-a", "item-1")
        state_b = await tracker.load_state("project-b", "item-1")
        assert state_a["reason"] == "Error in A"
        assert state_b["reason"] == "Error in B"


class TestRedisExecutionStateTrackerPersistence:
    @pytest.mark.asyncio
    async def test_state_survives_tracker_recreation(self, redis_client):
        t1 = RedisExecutionStateTracker(redis_client=redis_client, ttl_seconds=60)
        await t1.mark_execution_failed(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
            reason="Test failure",
        )

        # Simulate restart: drop tracker, build a new one against the same Redis.
        del t1
        t2 = RedisExecutionStateTracker(redis_client=redis_client, ttl_seconds=60)
        state = await t2.load_state("myproject", "item-123")
        assert state is not None
        assert state["agent"] == "claude"


class TestRedisExecutionStateTrackerCorruption:
    @pytest.mark.asyncio
    async def test_corrupt_json_returns_none(self, tracker, redis_client):
        await redis_client.set(tracker._key("myproject", "item-123"), "{not-json}")
        assert await tracker.load_state("myproject", "item-123") is None
