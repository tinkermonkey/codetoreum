"""Unit tests for RedisActiveWorkflowRunRegistry using fakeredis."""

from __future__ import annotations

from datetime import UTC, datetime

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
        started_at = datetime.now(UTC).isoformat()
        await registry.set_active_run(
            work_item_id="wi-1",
            run_id="run-1",
            stage_name="In Progress",
            project_id="proj-1",
            board_id="board-1",
            started_at=started_at,
        )
        info = await registry.get_active_run("wi-1")
        assert info == ActiveRunInfo(
            work_item_id="wi-1",
            run_id="run-1",
            stage_name="In Progress",
            project_id="proj-1",
            board_id="board-1",
            started_at=started_at,
        )

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, registry):
        assert await registry.get_active_run("does-not-exist") is None

    @pytest.mark.asyncio
    async def test_clear_run(self, registry):
        await registry.set_active_run(work_item_id="wi-1", run_id="run-1", stage_name="In Progress", project_id="proj-1", board_id="board-1", started_at=datetime.now(UTC).isoformat())
        await registry.clear_run("wi-1")
        assert await registry.get_active_run("wi-1") is None

    @pytest.mark.asyncio
    async def test_set_overwrites_existing(self, registry):
        await registry.set_active_run(work_item_id="wi-1", run_id="run-1", stage_name="stage-A", project_id="proj-1", board_id="board-1", started_at=datetime.now(UTC).isoformat())
        await registry.set_active_run(work_item_id="wi-1", run_id="run-2", stage_name="stage-B", project_id="proj-1", board_id="board-1", started_at=datetime.now(UTC).isoformat())
        info = await registry.get_active_run("wi-1")
        assert info is not None
        assert info.run_id == "run-2"
        assert info.stage_name == "stage-B"


class TestRedisActiveWorkflowRunRegistryGetAllRuns:
    @pytest.mark.asyncio
    async def test_get_all_runs_returns_all_active(self, registry):
        await registry.set_active_run(work_item_id="wi-1", run_id="run-1", stage_name="In Progress", project_id="proj-1", board_id="board-1", started_at=datetime.now(UTC).isoformat())
        await registry.set_active_run(work_item_id="wi-2", run_id="run-2", stage_name="In Progress", project_id="proj-1", board_id="board-1", started_at=datetime.now(UTC).isoformat())
        await registry.set_active_run(work_item_id="wi-3", run_id="run-3", stage_name="In Review", project_id="proj-2", board_id="board-2", started_at=datetime.now(UTC).isoformat())

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
        await r1.set_active_run(work_item_id="wi-1", run_id="run-1", stage_name="In Progress", project_id="proj-1", board_id="board-1", started_at=datetime.now(UTC).isoformat())

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
        await registry.set_active_run(work_item_id="wi-good", run_id="run-1", stage_name="In Progress", project_id="proj-1", board_id="board-1", started_at=datetime.now(UTC).isoformat())
        await redis_client.set(registry._key("wi-bad"), "{corrupt}", ex=60)
        runs = await registry.get_all_runs()
        wids = {wid for wid, _ in runs}
        assert "wi-good" in wids
        assert "wi-bad" not in wids
