"""Factory functions for creating configuration storage instances.

This module provides convenience functions for setting up production-ready
configuration storage with Elasticsearch + Redis caching.
"""

import logging
from typing import Optional

from elasticsearch import AsyncElasticsearch
from redis import asyncio as aioredis

from codetoreum.adapters.secondary.cached_config_store import CachedConfigStore
from codetoreum.adapters.secondary.elasticsearch_config_storage import (
    ElasticsearchConfigStorage,
)
from codetoreum.infrastructure.redis_config_cache import RedisConfigCache
from codetoreum.ports.output.config_store import IConfigStore

logger = logging.getLogger(__name__)


def create_elasticsearch_config_storage(
    es_client: AsyncElasticsearch,
    create_index_templates: bool = True,
    shard_count: int = 2,
    replica_count: int = 1,
) -> ElasticsearchConfigStorage:
    """
    Create Elasticsearch configuration storage adapter.

    Args:
        es_client: AsyncElasticsearch client
        create_index_templates: Whether to create index templates on init
        shard_count: Number of shards for indices (default: 2 for production)
        replica_count: Number of replicas for indices (default: 1 for production)

    Returns:
        ElasticsearchConfigStorage instance
    """
    storage = ElasticsearchConfigStorage(
        es_client=es_client,
        create_index_templates=create_index_templates,
        shard_count=shard_count,
        replica_count=replica_count,
    )

    logger.info(
        f"Created Elasticsearch config storage "
        f"(shards={shard_count}, replicas={replica_count})"
    )

    return storage


def create_redis_config_cache(
    redis_client: aioredis.Redis,
    key_prefix: str = "config",
    default_ttl: int = 3600,
    invalidation_channel: str = "config:invalidation",
) -> RedisConfigCache:
    """
    Create Redis configuration cache.

    Args:
        redis_client: Redis async client
        key_prefix: Prefix for cache keys (default: "config")
        default_ttl: Default TTL in seconds (default: 3600 = 1 hour)
        invalidation_channel: Pub/sub channel for invalidation (default: "config:invalidation")

    Returns:
        RedisConfigCache instance
    """
    cache = RedisConfigCache(
        redis_client=redis_client,
        key_prefix=key_prefix,
        default_ttl=default_ttl,
        invalidation_channel=invalidation_channel,
    )

    logger.info(
        f"Created Redis config cache "
        f"(prefix={key_prefix}, ttl={default_ttl}s)"
    )

    return cache


def create_cached_config_store(
    es_client: AsyncElasticsearch,
    redis_client: aioredis.Redis,
    create_index_templates: bool = True,
    shard_count: int = 2,
    replica_count: int = 1,
    cache_key_prefix: str = "config",
    cache_ttl: int = 3600,
    invalidation_channel: str = "config:invalidation",
) -> CachedConfigStore:
    """
    Create cached configuration store with Elasticsearch + Redis.

    This is the recommended production setup, combining Elasticsearch for
    persistent storage with Redis for fast caching.

    Architecture:
        Application → CachedConfigStore → Redis Cache → Elasticsearch

    Args:
        es_client: AsyncElasticsearch client
        redis_client: Redis async client
        create_index_templates: Whether to create ES index templates
        shard_count: Number of ES shards (default: 2)
        replica_count: Number of ES replicas (default: 1)
        cache_key_prefix: Redis cache key prefix (default: "config")
        cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
        invalidation_channel: Pub/sub channel for cache invalidation

    Returns:
        CachedConfigStore instance ready for use

    Example:
        ```python
        from elasticsearch import AsyncElasticsearch
        from redis import asyncio as aioredis
        from codetoreum.adapters.secondary.config_storage_factory import (
            create_cached_config_store
        )

        # Create clients
        es_client = AsyncElasticsearch(["http://localhost:9200"])
        redis_client = aioredis.Redis(host="localhost", port=6379)

        # Create cached config store
        config_store = create_cached_config_store(es_client, redis_client)

        # Initialize
        await config_store.storage.initialize()
        await config_store.cache.initialize()

        # Use it
        project = ProjectConfig(id="proj1", name="My Project", ...)
        await config_store.save_project_config(project)

        # Clean up
        await es_client.close()
        await redis_client.close()
        ```
    """
    # Create Elasticsearch storage
    storage = create_elasticsearch_config_storage(
        es_client=es_client,
        create_index_templates=create_index_templates,
        shard_count=shard_count,
        replica_count=replica_count,
    )

    # Create Redis cache
    cache = create_redis_config_cache(
        redis_client=redis_client,
        key_prefix=cache_key_prefix,
        default_ttl=cache_ttl,
        invalidation_channel=invalidation_channel,
    )

    # Combine into cached store
    cached_store = CachedConfigStore(
        storage=storage,
        cache=cache,
    )

    logger.info(
        "Created cached config store with Elasticsearch storage and Redis cache"
    )

    return cached_store


async def initialize_config_store(config_store: IConfigStore) -> None:
    """
    Initialize a configuration store (create indices, set up cache, etc.).

    This is a convenience function that handles initialization for different
    store types.

    Args:
        config_store: Configuration store instance to initialize

    Example:
        ```python
        config_store = create_cached_config_store(es_client, redis_client)
        await initialize_config_store(config_store)
        ```
    """
    if isinstance(config_store, CachedConfigStore):
        # Initialize both storage and cache
        logger.info("Initializing cached config store...")
        await config_store.storage.initialize()
        await config_store.cache.initialize()
        logger.info("Cached config store initialized successfully")

    elif isinstance(config_store, ElasticsearchConfigStorage):
        # Initialize storage only
        logger.info("Initializing Elasticsearch config storage...")
        await config_store.initialize()
        logger.info("Elasticsearch config storage initialized successfully")

    else:
        # For other implementations, call initialize if available
        if hasattr(config_store, "initialize"):
            logger.info(f"Initializing config store: {type(config_store).__name__}")
            await config_store.initialize()
            logger.info("Config store initialized successfully")
        else:
            logger.info(f"Config store {type(config_store).__name__} requires no initialization")


async def close_config_store(config_store: IConfigStore) -> None:
    """
    Close a configuration store (cleanup resources).

    Args:
        config_store: Configuration store instance to close

    Example:
        ```python
        await close_config_store(config_store)
        ```
    """
    if isinstance(config_store, CachedConfigStore):
        # Close both cache and storage
        logger.info("Closing cached config store...")
        await config_store.cache.close()
        await config_store.storage.close()
        logger.info("Cached config store closed")

    elif hasattr(config_store, "close"):
        logger.info(f"Closing config store: {type(config_store).__name__}")
        await config_store.close()
        logger.info("Config store closed")
