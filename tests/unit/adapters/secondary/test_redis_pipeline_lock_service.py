"""Unit tests for RedisPipelineLockService using fakeredis."""

from __future__ import annotations

from typing import TYPE_CHECKING

import fakeredis.aioredis
import pytest

from codetoreum.adapters.secondary.redis_pipeline_lock_service import (
    LockHolder,
    RedisPipelineLockService,
)
from codetoreum.application.pipeline_lock_service import LockStatus


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.close()


@pytest.fixture
async def adapter(redis_client):
    return RedisPipelineLockService(redis_client=redis_client)


class TestRedisPipelineLockServiceAcquireRelease:
    @pytest.mark.asyncio
    async def test_first_acquire_returns_acquired(self, adapter):
        result = await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", board_position=0)
        assert result.status == LockStatus.ACQUIRED
        assert result.work_item_id == "wi-1"
        assert result.queue_position is None
        assert result.queue_length == 0

    @pytest.mark.asyncio
    async def test_second_acquire_returns_queued(self, adapter):
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", board_position=0)
        result = await adapter.try_acquire_lock("proj-1", "board-1", "wi-2", board_position=1)
        assert result.status == LockStatus.QUEUED
        assert result.queue_position == 0  # first in queue
        assert result.queue_length == 1

    @pytest.mark.asyncio
    async def test_same_holder_returns_already_held(self, adapter):
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", board_position=0)
        result = await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", board_position=0)
        assert result.status == LockStatus.ALREADY_HELD

    @pytest.mark.asyncio
    async def test_release_grants_to_queue_head(self, adapter):
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", 0)
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-2", 1)
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-3", 2)

        result = await adapter.release_lock("proj-1", "board-1", "wi-1")
        assert result.released_work_item_id == "wi-1"
        assert result.next_work_item_id == "wi-2"
        assert result.queue_length_after_release == 1  # wi-3 still queued

        # The lock now belongs to wi-2.
        lock = await adapter.get_lock("proj-1", "board-1")
        assert lock is not None
        assert lock.work_item_id == "wi-2"

    @pytest.mark.asyncio
    async def test_release_when_no_lock_raises(self, adapter):
        with pytest.raises(ValueError):
            await adapter.release_lock("proj-1", "board-1", "wi-1")

    @pytest.mark.asyncio
    async def test_release_by_non_holder_raises(self, adapter):
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", 0)
        with pytest.raises(ValueError):
            await adapter.release_lock("proj-1", "board-1", "wi-other")

    @pytest.mark.asyncio
    async def test_queue_order_by_board_position(self, adapter):
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", 0)
        # Insert out of order; lowest board_position wins.
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-late", 10)
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-early", 1)
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-mid", 5)

        release = await adapter.release_lock("proj-1", "board-1", "wi-1")
        assert release.next_work_item_id == "wi-early"


class TestRedisPipelineLockServiceGetters:
    @pytest.mark.asyncio
    async def test_get_lock_returns_none_when_not_held(self, adapter):
        assert await adapter.get_lock("proj-1", "board-1") is None

    @pytest.mark.asyncio
    async def test_get_all_locks_returns_all_held(self, adapter):
        await adapter.try_acquire_lock("proj-1", "board-A", "wi-A", 0)
        await adapter.try_acquire_lock("proj-1", "board-B", "wi-B", 0)
        await adapter.try_acquire_lock("proj-2", "board-A", "wi-C", 0)
        locks = await adapter.get_all_locks()
        assert len(locks) == 3
        holders = {(lock.project_id, lock.board_id, lock.work_item_id) for lock in locks}
        assert ("proj-1", "board-A", "wi-A") in holders
        assert ("proj-2", "board-A", "wi-C") in holders

    @pytest.mark.asyncio
    async def test_get_queue_state_shows_holder_and_queue(self, adapter):
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", 0)
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-2", 5)
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-3", 2)
        state = await adapter.get_queue_state("proj-1", "board-1")
        assert state.lock_holder == "wi-1"
        assert state.lock_acquired_at is not None
        # Queue ordered by board_position ascending
        wids = [e.work_item_id for e in state.queue]
        assert wids == ["wi-3", "wi-2"]

    @pytest.mark.asyncio
    async def test_get_all_lock_states_indexed_by_scoped_key(self, adapter):
        await adapter.try_acquire_lock("proj-1", "board-A", "wi-A", 0)
        states = await adapter.get_all_lock_states()
        assert "proj-1:board-A" in states


class TestRedisPipelineLockServiceQueueUpdates:
    @pytest.mark.asyncio
    async def test_update_queue_positions_reorders(self, adapter):
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", 0)
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-A", 5)
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-B", 6)

        # Move wi-B to the front of the queue.
        await adapter.update_queue_positions("proj-1", "board-1", {"wi-B": 1, "wi-A": 5})

        release = await adapter.release_lock("proj-1", "board-1", "wi-1")
        assert release.next_work_item_id == "wi-B"

    @pytest.mark.asyncio
    async def test_update_queue_positions_does_not_insert_new(self, adapter):
        await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", 0)
        await adapter.update_queue_positions("proj-1", "board-1", {"never-queued": 0})
        state = await adapter.get_queue_state("proj-1", "board-1")
        assert all(e.work_item_id != "never-queued" for e in state.queue)


class TestRedisPipelineLockServicePersistence:
    """Demonstrates the persistence property the in-memory impl lacks."""

    @pytest.mark.asyncio
    async def test_lock_state_survives_adapter_recreation(self, redis_client):
        a1 = RedisPipelineLockService(redis_client=redis_client)
        await a1.try_acquire_lock("proj-1", "board-1", "wi-1", 0)

        # Simulate restart: drop adapter, build a new one against the same Redis.
        del a1
        a2 = RedisPipelineLockService(redis_client=redis_client)
        lock = await a2.get_lock("proj-1", "board-1")
        assert lock is not None
        assert lock.work_item_id == "wi-1"


class TestRedisPipelineLockServiceCorruption:
    @pytest.mark.asyncio
    async def test_corrupt_lock_holder_json_treated_as_not_held(self, adapter, redis_client):
        # Directly write garbage to the lock key.
        await redis_client.set(adapter._lock_key("proj-1", "board-1"), "{not-json}")
        # Acquire should fail because SETNX sees the key as present.
        result = await adapter.try_acquire_lock("proj-1", "board-1", "wi-1", 0)
        # Corrupt holder is not "same as wi-1" → falls through to SETNX, which
        # fails (key exists) → queues wi-1.
        assert result.status == LockStatus.QUEUED


class TestLockHolderSerialization:
    def test_round_trip(self):
        h = LockHolder(work_item_id="wi-1", acquired_at="2026-01-01T00:00:00+00:00")
        raw = h.to_json()
        recovered = LockHolder.from_json(raw)
        assert recovered == h

    def test_from_bytes(self):
        h = LockHolder(work_item_id="wi-1", acquired_at="2026-01-01T00:00:00+00:00")
        recovered = LockHolder.from_json(h.to_json().encode("utf-8"))
        assert recovered == h
