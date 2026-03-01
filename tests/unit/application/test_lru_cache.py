"""
Unit tests for LRUCache in workflow_run_query_service.

Tests cover:
- LRU eviction behavior
- TTL expiration
- Concurrent access scenarios
- Edge cases (empty cache, single item, etc.)
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from codetoreum.application.workflow_run_query_service import LRUCache


class TestLRUCacheBasicOperations:
    """Test basic LRU cache operations."""

    @pytest.mark.asyncio
    async def test_get_set_basic(self):
        """Test basic get/set operations."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        # Initially empty
        assert await cache.get("key1") is None

        # Set and retrieve
        await cache.set("key1", "value1")
        assert await cache.get("key1") == "value1"

        # Set another key
        await cache.set("key2", "value2")
        assert await cache.get("key2") == "value2"
        assert await cache.get("key1") == "value1"  # First key still exists

    @pytest.mark.asyncio
    async def test_cache_size(self):
        """Test cache size tracking."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        assert await cache.size() == 0

        await cache.set("key1", "value1")
        assert await cache.size() == 1

        await cache.set("key2", "value2")
        assert await cache.size() == 2

        # Updating existing key doesn't change size
        await cache.set("key1", "new_value1")
        assert await cache.size() == 2
        assert await cache.get("key1") == "new_value1"

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing the cache."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        assert await cache.size() == 2

        await cache.clear()
        assert await cache.size() == 0
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None


class TestLRUEviction:
    """Test LRU eviction behavior."""

    @pytest.mark.asyncio
    async def test_eviction_on_max_size(self):
        """Test that least recently used items are evicted when max size is reached."""
        cache = LRUCache(max_size=3, ttl_seconds=300)

        # Fill cache to max size
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        assert await cache.size() == 3

        # Add one more - should evict key1 (least recently used)
        await cache.set("key4", "value4")
        assert await cache.size() == 3
        assert await cache.get("key1") is None  # Evicted
        assert await cache.get("key2") == "value2"
        assert await cache.get("key3") == "value3"
        assert await cache.get("key4") == "value4"

    @pytest.mark.asyncio
    async def test_eviction_preserves_recently_accessed(self):
        """Test that accessing an item makes it less likely to be evicted."""
        cache = LRUCache(max_size=3, ttl_seconds=300)

        # Fill cache
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        # Access key1 - moves it to end (most recently used)
        await cache.get("key1")

        # Add new item - should evict key2 (now least recently used)
        await cache.set("key4", "value4")
        assert await cache.get("key1") == "value1"  # Still exists
        assert await cache.get("key2") is None  # Evicted
        assert await cache.get("key3") == "value3"
        assert await cache.get("key4") == "value4"

    @pytest.mark.asyncio
    async def test_eviction_with_updates(self):
        """Test that updating an existing key doesn't trigger eviction."""
        cache = LRUCache(max_size=2, ttl_seconds=300)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        assert await cache.size() == 2

        # Update existing key - should not evict anything
        await cache.set("key1", "updated_value1")
        assert await cache.size() == 2
        assert await cache.get("key1") == "updated_value1"
        assert await cache.get("key2") == "value2"

    @pytest.mark.asyncio
    async def test_single_item_cache(self):
        """Test edge case of max_size=1."""
        cache = LRUCache(max_size=1, ttl_seconds=300)

        await cache.set("key1", "value1")
        assert await cache.get("key1") == "value1"

        # Adding second item evicts first
        await cache.set("key2", "value2")
        assert await cache.get("key1") is None
        assert await cache.get("key2") == "value2"


class TestTTLExpiration:
    """Test TTL (time-to-live) expiration behavior."""

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        """Test that items expire after TTL."""
        cache = LRUCache(max_size=10, ttl_seconds=1)  # 1 second TTL

        await cache.set("key1", "value1")
        assert await cache.get("key1") == "value1"

        # Wait for TTL to expire
        await asyncio.sleep(1.1)

        # Should be expired and removed
        assert await cache.get("key1") is None
        assert await cache.size() == 0  # Expired item was removed

    @pytest.mark.asyncio
    async def test_ttl_with_time_mock(self):
        """Test TTL expiration using time mocking."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        base_time = datetime.now(UTC)

        with patch("codetoreum.application.workflow_run_query_service.datetime") as mock_datetime:
            # Set initial time
            mock_datetime.now.return_value = base_time
            await cache.set("key1", "value1")

            # Advance time by 200 seconds (within TTL)
            mock_datetime.now.return_value = base_time + timedelta(seconds=200)
            assert await cache.get("key1") == "value1"

            # Advance time beyond TTL (310 seconds total)
            mock_datetime.now.return_value = base_time + timedelta(seconds=310)
            assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_ttl_affects_size(self):
        """Test that expired items are removed from cache size."""
        cache = LRUCache(max_size=10, ttl_seconds=1)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        assert await cache.size() == 2

        # Wait for TTL to expire
        await asyncio.sleep(1.1)

        # Accessing one expired item removes it
        assert await cache.get("key1") is None
        assert await cache.size() == 1  # key1 removed, key2 still there (until accessed)

        # Accessing second expired item removes it too
        assert await cache.get("key2") is None
        assert await cache.size() == 0


class TestConcurrentAccess:
    """Test concurrent access scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_reads(self):
        """Test that concurrent reads don't cause issues."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        await cache.set("key1", "value1")

        # Concurrent reads
        results = await asyncio.gather(
            cache.get("key1"),
            cache.get("key1"),
            cache.get("key1"),
            cache.get("key1"),
            cache.get("key1"),
        )

        assert all(r == "value1" for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_writes(self):
        """Test that concurrent writes are serialized correctly."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        # Concurrent writes to different keys
        await asyncio.gather(
            cache.set("key1", "value1"),
            cache.set("key2", "value2"),
            cache.set("key3", "value3"),
            cache.set("key4", "value4"),
            cache.set("key5", "value5"),
        )

        # All writes should succeed
        assert await cache.size() == 5
        assert await cache.get("key1") == "value1"
        assert await cache.get("key2") == "value2"
        assert await cache.get("key3") == "value3"
        assert await cache.get("key4") == "value4"
        assert await cache.get("key5") == "value5"

    @pytest.mark.asyncio
    async def test_concurrent_writes_same_key(self):
        """Test that concurrent writes to same key are handled correctly."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        # Concurrent writes to same key
        await asyncio.gather(
            cache.set("key1", "value_a"),
            cache.set("key1", "value_b"),
            cache.set("key1", "value_c"),
        )

        # One of the values should win (last writer wins)
        value = await cache.get("key1")
        assert value in ["value_a", "value_b", "value_c"]
        assert await cache.size() == 1

    @pytest.mark.asyncio
    async def test_concurrent_eviction(self):
        """Test that concurrent writes triggering eviction work correctly."""
        cache = LRUCache(max_size=3, ttl_seconds=300)

        # Fill cache
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        # Concurrent writes that trigger evictions
        await asyncio.gather(
            cache.set("key4", "value4"),
            cache.set("key5", "value5"),
            cache.set("key6", "value6"),
        )

        # Cache should be at max size
        assert await cache.size() == 3

        # At least some of the new keys should exist
        new_keys_exist = sum(
            [
                await cache.get("key4") is not None,
                await cache.get("key5") is not None,
                await cache.get("key6") is not None,
            ]
        )
        assert new_keys_exist >= 1


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_cache_operations(self):
        """Test operations on empty cache."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        assert await cache.get("nonexistent") is None
        assert await cache.size() == 0

        await cache.clear()  # Should not raise
        assert await cache.size() == 0

    @pytest.mark.asyncio
    async def test_zero_ttl(self):
        """Test edge case of zero TTL (immediate expiration)."""
        cache = LRUCache(max_size=10, ttl_seconds=0)

        await cache.set("key1", "value1")

        # May or may not be expired depending on timing
        # But should not crash
        result = await cache.get("key1")
        assert result in [None, "value1"]

    @pytest.mark.asyncio
    async def test_large_values(self):
        """Test caching large values."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        large_value = "x" * 1000000  # 1MB string
        await cache.set("large_key", large_value)

        assert await cache.get("large_key") == large_value

    @pytest.mark.asyncio
    async def test_special_characters_in_keys(self):
        """Test keys with special characters."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        special_keys = [
            "key/with/slashes",
            "key:with:colons",
            "key with spaces",
            "key.with.dots",
            "key-with-dashes",
            "key_with_underscores",
        ]

        for i, key in enumerate(special_keys):
            await cache.set(key, f"value{i}")

        for i, key in enumerate(special_keys):
            assert await cache.get(key) == f"value{i}"

    @pytest.mark.asyncio
    async def test_none_value(self):
        """Test caching None values."""
        cache = LRUCache(max_size=10, ttl_seconds=300)

        await cache.set("key1", None)
        # None is a valid cached value, different from "not in cache"
        # However, our implementation can't distinguish these
        # This is a known limitation - document it
        result = await cache.get("key1")
        # The cache returns the actual None value that was stored
        assert result is None
