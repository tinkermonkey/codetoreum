"""Factory functions for creating event store instances.

This module provides convenience functions for setting up production-ready
event stores with Elasticsearch for cross-process event distribution and persistence.
"""

import logging
import os

from elasticsearch import AsyncElasticsearch

from codetoreum.adapters.secondary.elasticsearch_event_store import ElasticsearchEventStore
from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


def create_elasticsearch_event_store(
    es_client: AsyncElasticsearch,
    index_prefix: str = "events",
    create_index_template: bool = True,
    shard_count: int = 2,
    replica_count: int = 1,
) -> ElasticsearchEventStore:
    """
    Create Elasticsearch event store adapter for production.

    Args:
        es_client: AsyncElasticsearch client
        index_prefix: Prefix for event indices (default: "events")
        create_index_template: Whether to create index template on init
        shard_count: Number of shards for indices (default: 2)
        replica_count: Number of replicas for indices (default: 1)

    Returns:
        ElasticsearchEventStore instance
    """
    store = ElasticsearchEventStore(
        es_client=es_client,
        index_prefix=index_prefix,
        create_index_template=create_index_template,
        shard_count=shard_count,
        replica_count=replica_count,
    )

    logger.info(
        f"Created Elasticsearch event store with prefix '{index_prefix}' "
        f"(shards={shard_count}, replicas={replica_count})"
    )

    return store


def create_elasticsearch_client(url: str | None = None) -> AsyncElasticsearch:
    """
    Create an Elasticsearch async client.

    Args:
        url: Elasticsearch URL (default: from ELASTICSEARCH_URL env var or http://localhost:9200)

    Returns:
        AsyncElasticsearch client

    Raises:
        ValueError: If URL is invalid or cannot connect
    """
    if not url:
        url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

    logger.info(f"Creating Elasticsearch client for {url}")

    try:
        client = AsyncElasticsearch([url])
        return client
    except Exception as e:
        msg = f"Failed to create Elasticsearch client: {e}"
        logger.error(msg, exc_info=True)
        raise ValueError(msg) from e


async def initialize_event_store(event_store: IEventStore) -> None:
    """
    Initialize an event store (create indices, etc.).

    This is a convenience function that handles initialization for different
    store types.

    Args:
        event_store: Event store instance to initialize

    Example:
        ```python
        es_client = create_elasticsearch_client()
        event_store = create_elasticsearch_event_store(es_client)
        await initialize_event_store(event_store)
        ```
    """
    if isinstance(event_store, ElasticsearchEventStore):
        logger.info("Initializing Elasticsearch event store...")
        await event_store.initialize()
        logger.info("Elasticsearch event store initialized successfully")

    # For other implementations, call initialize if available
    elif hasattr(event_store, "initialize"):
        logger.info(f"Initializing event store: {type(event_store).__name__}")
        await event_store.initialize()
        logger.info("Event store initialized successfully")
    else:
        logger.info(f"Event store {type(event_store).__name__} requires no initialization")


async def close_event_store(event_store: IEventStore) -> None:
    """
    Close an event store (cleanup resources).

    Args:
        event_store: Event store instance to close

    Example:
        ```python
        await close_event_store(event_store)
        ```
    """
    if isinstance(event_store, ElasticsearchEventStore):
        logger.info("Closing Elasticsearch event store...")
        await event_store.close()
        logger.info("Elasticsearch event store closed")

    elif hasattr(event_store, "close"):
        logger.info(f"Closing event store: {type(event_store).__name__}")
        await event_store.close()
        logger.info("Event store closed")
