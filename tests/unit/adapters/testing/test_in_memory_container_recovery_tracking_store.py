"""Unit tests for InMemoryContainerRecoveryTrackingStore."""

from __future__ import annotations

import pytest

from codetoreum.adapters.testing.in_memory_container_recovery_tracking_store import (
    InMemoryContainerRecoveryTrackingStore,
)


@pytest.fixture
def store():
    return InMemoryContainerRecoveryTrackingStore()


class TestInMemoryContainerRecoveryTrackingStoreRoundTrip:
    @pytest.mark.asyncio
    async def test_set_then_get(self, store):
        await store.set(
            "agent:container:myagent-123",
            {"project": "myproject", "work_item_id": "item-456"},
            ttl=7200,
        )
        value = await store.get("agent:container:myagent-123")
        assert value == {"project": "myproject", "work_item_id": "item-456"}

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, store):
        assert await store.get("does-not-exist") is None

    @pytest.mark.asyncio
    async def test_set_overwrites_existing(self, store):
        await store.set("test:key", {"value": 1}, ttl=3600)
        await store.set("test:key", {"value": 2}, ttl=3600)
        value = await store.get("test:key")
        assert value == {"value": 2}

    @pytest.mark.asyncio
    async def test_set_with_no_ttl_is_accepted(self, store):
        await store.set("test:key", {"value": "data"})
        value = await store.get("test:key")
        assert value == {"value": "data"}


class TestInMemoryContainerRecoveryTrackingStoreScan:
    @pytest.mark.asyncio
    async def test_scan_execution_state_keys(self, store):
        await store.set("execution:state:proj-a:item-1", {"status": "active"}, ttl=14400)
        await store.set("execution:state:proj-a:item-2", {"status": "active"}, ttl=14400)
        await store.set("execution:state:proj-b:item-1", {"status": "active"}, ttl=14400)
        await store.set("agent:container:agent-1", {"data": "test"}, ttl=7200)

        keys = await store.scan("execution:state:*")
        assert len(keys) == 3
        assert all(k.startswith("execution:state:") for k in keys)

    @pytest.mark.asyncio
    async def test_scan_repair_cycle_results(self, store):
        await store.set(
            "repair_cycle:result:proj-a:item-1:run-1",
            {"status": "completed"},
            ttl=86400,
        )
        await store.set(
            "repair_cycle:result:proj-a:item-2:run-1",
            {"status": "completed"},
            ttl=86400,
        )
        await store.set("other:key", {"data": "test"}, ttl=3600)

        keys = await store.scan("repair_cycle:result:*")
        assert len(keys) == 2
        assert all(k.startswith("repair_cycle:result:") for k in keys)

    @pytest.mark.asyncio
    async def test_scan_no_matches_returns_empty_list(self, store):
        await store.set("some:key", {"data": "test"}, ttl=3600)
        keys = await store.scan("no-matches:*")
        assert keys == []

    @pytest.mark.asyncio
    async def test_scan_glob_pattern_matching(self, store):
        await store.set("agent:container:agent-1", {"data": "1"}, ttl=7200)
        await store.set("agent:container:agent-2", {"data": "2"}, ttl=7200)
        await store.set("agent:container:agent-3", {"data": "3"}, ttl=7200)
        await store.set("other:container:other-1", {"data": "x"}, ttl=7200)

        keys = await store.scan("agent:container:*")
        assert len(keys) == 3
        assert all("agent:container:" in k for k in keys)


class TestInMemoryContainerRecoveryTrackingStoreValidation:
    @pytest.mark.asyncio
    async def test_set_empty_key_raises_value_error(self, store):
        with pytest.raises(ValueError):
            await store.set("", {"value": "test"})

    @pytest.mark.asyncio
    async def test_set_complex_value_types(self, store):
        complex_value = {
            "strings": ["a", "b", "c"],
            "numbers": [1, 2, 3],
            "nested": {"level": 1, "deeper": {"level": 2}},
            "boolean": True,
            "null": None,
        }
        await store.set("complex:key", complex_value, ttl=3600)
        retrieved = await store.get("complex:key")
        assert retrieved == complex_value
