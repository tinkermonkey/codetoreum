"""Unit tests for RedisActiveWorkflowRunRegistry using fakeredis."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from codetoreum.adapters.secondary.redis_active_workflow_run_registry import (
    RedisActiveWorkflowRunRegistry,
)
from codetoreum.ports.output.active_workflow_run_registry import ActiveRunInfo


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.close()


@pytest.fixture
async def registry(redis_client):
    return RedisActiveWorkflowRunRegistry(redis_client=redis_client, ttl_seconds=60)


class TestRedisActiveWorkflowRunRegistryRoundTrip:
    @pytest.mark.asyncio
    async def test_set_then_get(self, registry):
        await registry.set_active_run(
            work_item_id="wi-1",
            run_id="run-1",
            stage_name="In Progress",
            project_id="proj-1",
            board_id="board-1",
        )
        info = await registry.get_active_run("wi-1")
        assert info == ActiveRunInfo(
            work_item_id="wi-1",
            run_id="run-1",
            stage_name="In Progress",
            project_id="proj-1",
            board_id="board-1",
        )

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, registry):
        assert await registry.get_active_run("does-not-exist") is None

    @pytest.mark.asyncio
    async def test_clear_run(self, registry):
        await registry.set_active_run("wi-1", "run-1", "In Progress", "proj-1", "board-1")
        await registry.clear_run("wi-1")
        assert await registry.get_active_run("wi-1") is None

    @pytest.mark.asyncio
    async def test_set_overwrites_existing(self, registry):
        await registry.set_active_run("wi-1", "run-1", "stage-A", "proj-1", "board-1")
        await registry.set_active_run("wi-1", "run-2", "stage-B", "proj-1", "board-1")
        info = await registry.get_active_run("wi-1")
        assert info is not None
        assert info.run_id == "run-2"
        assert info.stage_name == "stage-B"


class TestRedisActiveWorkflowRunRegistryGetAllRuns:
    @pytest.mark.asyncio
    async def test_get_all_runs_returns_all_active(self, registry):
        await registry.set_active_run("wi-1", "run-1", "In Progress", "proj-1", "board-1")
        await registry.set_active_run("wi-2", "run-2", "In Progress", "proj-1", "board-1")
        await registry.set_active_run("wi-3", "run-3", "In Review", "proj-2", "board-2")

        runs = await registry.get_all_runs()
        assert len(runs) == 3
        work_item_ids = {wid for wid, _info in runs}
        assert work_item_ids == {"wi-1", "wi-2", "wi-3"}

    @pytest.mark.asyncio
    async def test_get_all_runs_empty(self, registry):
        assert await registry.get_all_runs() == []


class TestRedisActiveWorkflowRunRegistryPersistence:
    @pytest.mark.asyncio
    async def test_run_state_survives_registry_recreation(self, redis_client):
        r1 = RedisActiveWorkflowRunRegistry(redis_client=redis_client, ttl_seconds=60)
        await r1.set_active_run("wi-1", "run-1", "In Progress", "proj-1", "board-1")

        # Simulate restart: drop registry, build a new one against the same Redis.
        del r1
        r2 = RedisActiveWorkflowRunRegistry(redis_client=redis_client, ttl_seconds=60)
        info = await r2.get_active_run("wi-1")
        assert info is not None
        assert info.run_id == "run-1"


class TestRedisActiveWorkflowRunRegistryCorruption:
    @pytest.mark.asyncio
    async def test_corrupt_json_returns_none(self, registry, redis_client):
        await redis_client.set(registry._key("wi-1"), "{not-json}")
        assert await registry.get_active_run("wi-1") is None

    @pytest.mark.asyncio
    async def test_corrupt_in_get_all_runs_is_skipped(self, registry, redis_client):
        await registry.set_active_run("wi-good", "run-1", "In Progress", "proj-1", "board-1")
        await redis_client.set(registry._key("wi-bad"), "{corrupt}", ex=60)
        runs = await registry.get_all_runs()
        wids = {wid for wid, _ in runs}
        assert "wi-good" in wids
        assert "wi-bad" not in wids
