"""Unit tests for RedisExecutionStateTracker using fakeredis."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from codetoreum.adapters.secondary.redis_execution_state_tracker import (
    RedisExecutionStateTracker,
)
from codetoreum.ports.exceptions import StorageError


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
        assert state.outcome == "failed"
        assert state.agent == "claude"
        assert state.reason == "Container lost connection"

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
        assert state.reason == "Second failure"


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
        assert state_a.reason == "Error in A"
        assert state_b.reason == "Error in B"


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
        assert state.agent == "claude"


class TestRedisExecutionStateTrackerStarted:
    @pytest.mark.asyncio
    async def test_mark_execution_started_stores_in_progress_state(self, tracker):
        await tracker.mark_execution_started(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
        )
        state = await tracker.load_state("myproject", "item-123")
        assert state is not None
        assert state.outcome == "in_progress"
        assert state.agent == "claude"

    @pytest.mark.asyncio
    async def test_mark_execution_started_overwrites_failed_state(self, tracker):
        await tracker.mark_execution_failed(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
            reason="Previous failure",
        )
        await tracker.mark_execution_started(
            project="myproject",
            work_item_id="item-123",
            agent="claude",
        )
        state = await tracker.load_state("myproject", "item-123")
        assert state is not None
        assert state.outcome == "in_progress"
        assert state.agent == "claude"
        assert state.reason is None


class TestRedisExecutionStateTrackerCorruption:
    @pytest.mark.asyncio
    async def test_corrupt_json_raises_storage_error(self, tracker, redis_client):
        await redis_client.set(tracker._key("myproject", "item-123"), "{not-json}")
        with pytest.raises(StorageError):
            await tracker.load_state("myproject", "item-123")


class TestRedisExecutionStateTrackerValidation:
    @pytest.mark.asyncio
    async def test_mark_execution_started_rejects_empty_agent(self, tracker):
        with pytest.raises(StorageError) as exc_info:
            await tracker.mark_execution_started(
                project="myproject",
                work_item_id="item-123",
                agent="",
            )
        assert "agent must be a non-empty string" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_mark_execution_failed_rejects_empty_agent(self, tracker):
        with pytest.raises(StorageError) as exc_info:
            await tracker.mark_execution_failed(
                project="myproject",
                work_item_id="item-123",
                agent="",
                reason="Some reason",
            )
        assert "agent must be a non-empty string" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_mark_execution_failed_rejects_empty_reason(self, tracker):
        with pytest.raises(StorageError) as exc_info:
            await tracker.mark_execution_failed(
                project="myproject",
                work_item_id="item-123",
                agent="claude",
                reason="",
            )
        assert "reason must be None or a non-empty string" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validation_errors_caught_at_write_time(self, tracker, redis_client):
        with pytest.raises(StorageError):
            await tracker.mark_execution_failed(
                project="myproject",
                work_item_id="item-123",
                agent="invalid",
                reason="",
            )
        # Verify nothing was written to Redis
        assert await redis_client.get(tracker._key("myproject", "item-123")) is None
