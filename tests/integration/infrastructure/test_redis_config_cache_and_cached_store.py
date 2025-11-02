"""Integration tests for Redis Config Cache and Cached Config Store.

These tests use testcontainers to spin up real Redis and Elasticsearch instances.
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from elasticsearch import AsyncElasticsearch
from redis import asyncio as aioredis
from testcontainers.elasticsearch import ElasticSearchContainer
from testcontainers.redis import RedisContainer

from codetoreum.adapters.secondary.cached_config_store import CachedConfigStore
from codetoreum.adapters.secondary.elasticsearch_config_storage import (
    ElasticsearchConfigStorage,
)
from codetoreum.infrastructure.redis_config_cache import RedisConfigCache
from codetoreum.ports.output.config_store import (
    AgentConfig,
    ConfigNotFoundError,
    PipelineConfig,
    ProjectConfig,
    WorkflowTemplate,
)
from tests.conftest import docker_available

# Mark all tests in this module as requiring Docker
pytestmark = docker_available


@pytest.fixture(scope="module")
def redis_container():
    """Create Redis testcontainer."""
    container = RedisContainer("redis:7-alpine")
    container.start()

    yield container

    container.stop()


@pytest.fixture(scope="module")
def elasticsearch_container():
    """Create Elasticsearch testcontainer."""
    container = ElasticSearchContainer("elasticsearch:8.11.0")
    container.with_env("xpack.security.enabled", "false")
    container.with_env("discovery.type", "single-node")
    container.start()

    yield container

    container.stop()


@pytest.fixture
async def redis_client(redis_container):
    """Create Redis async client."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)

    client = aioredis.Redis(
        host=host,
        port=int(port),
        decode_responses=False,
        socket_connect_timeout=10,
    )

    yield client

    await client.close()


@pytest.fixture
async def es_client(elasticsearch_container):
    """Create AsyncElasticsearch client."""
    client = AsyncElasticsearch(
        [elasticsearch_container.get_url()],
        verify_certs=False,
        request_timeout=30,
    )

    yield client

    await client.close()


@pytest.fixture
async def redis_cache(redis_client):
    """Create RedisConfigCache instance."""
    cache = RedisConfigCache(
        redis_client=redis_client,
        key_prefix=f"test-config-{uuid4().hex[:8]}",
        default_ttl=60,
        invalidation_channel=f"test-invalidation-{uuid4().hex[:8]}",
    )

    await cache.initialize()

    yield cache

    await cache.close()


@pytest.fixture
async def elasticsearch_storage(es_client):
    """Create ElasticsearchConfigStorage instance."""
    storage = ElasticsearchConfigStorage(
        es_client=es_client,
        create_index_templates=True,
        shard_count=1,
        replica_count=0,
    )

    await storage.initialize()
    await asyncio.sleep(1)

    yield storage

    await storage.close()


@pytest.fixture
async def cached_config_store(elasticsearch_storage, redis_cache):
    """Create CachedConfigStore instance."""
    return CachedConfigStore(
        storage=elasticsearch_storage,
        cache=redis_cache,
    )


@pytest.fixture
def sample_project_config():
    """Create a sample ProjectConfig for testing."""
    return ProjectConfig(
        id=f"project-{uuid4().hex[:8]}",
        name=f"Test Project {uuid4().hex[:8]}",
        github_org="test-org",
        github_repo="test-repo",
        tech_stacks={"python": "3.11", "node": "18"},
        pipelines=[{"name": "main", "stages": ["analyze", "implement", "review"]}],
        testing={"framework": "pytest", "coverage": 80},
        environment_variables={"ENV": "test"},
        version=1,
        metadata={"created_by": "test"},
    )


@pytest.fixture
def sample_agent_config():
    """Create a sample AgentConfig for testing."""
    return AgentConfig(
        project_id=f"project-{uuid4().hex[:8]}",
        agent_name="test-agent",
        model="claude-sonnet-4",
        timeout=300,
        requires_docker=True,
        makes_code_changes=True,
        mcp_servers=["artifacts", "logging"],
        capabilities=["code-generation", "testing"],
        version=1,
        metadata={"created_by": "test"},
    )


# Redis Config Cache Tests


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_cache_set_and_get_project(redis_cache, sample_project_config):
    """Test setting and getting project config from Redis cache."""
    # Set project config
    await redis_cache.set_project_config(sample_project_config)

    # Get project config
    retrieved = await redis_cache.get_project_config(sample_project_config.id)

    assert retrieved is not None
    assert retrieved.id == sample_project_config.id
    assert retrieved.name == sample_project_config.name
    assert retrieved.tech_stacks == sample_project_config.tech_stacks


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_cache_get_nonexistent_returns_none(redis_cache):
    """Test that getting nonexistent config from cache returns None."""
    retrieved = await redis_cache.get_project_config("nonexistent-project")

    assert retrieved is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_cache_set_and_get_by_name(redis_cache, sample_project_config):
    """Test getting project config by name from cache."""
    # Set project config
    await redis_cache.set_project_config(sample_project_config)

    # Get by name
    retrieved = await redis_cache.get_project_config_by_name(sample_project_config.name)

    assert retrieved is not None
    assert retrieved.id == sample_project_config.id
    assert retrieved.name == sample_project_config.name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_cache_invalidate_project(redis_cache, sample_project_config):
    """Test invalidating project config from cache."""
    # Set project config
    await redis_cache.set_project_config(sample_project_config)

    # Verify it's cached
    retrieved = await redis_cache.get_project_config(sample_project_config.id)
    assert retrieved is not None

    # Invalidate
    await redis_cache.invalidate_project(sample_project_config.id)

    # Wait for invalidation to propagate
    await asyncio.sleep(0.5)

    # Verify it's removed
    retrieved = await redis_cache.get_project_config(sample_project_config.id)
    assert retrieved is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_cache_agent_config(redis_cache, sample_agent_config):
    """Test caching agent configuration."""
    # Set agent config
    await redis_cache.set_agent_config(sample_agent_config)

    # Get agent config
    retrieved = await redis_cache.get_agent_config(
        sample_agent_config.project_id, sample_agent_config.agent_name
    )

    assert retrieved is not None
    assert retrieved.project_id == sample_agent_config.project_id
    assert retrieved.agent_name == sample_agent_config.agent_name
    assert retrieved.model == sample_agent_config.model


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_cache_stats(redis_cache, sample_project_config):
    """Test cache statistics tracking."""
    # Reset stats
    await redis_cache.reset_stats()

    # Perform operations
    await redis_cache.set_project_config(sample_project_config)  # Write
    await redis_cache.get_project_config(sample_project_config.id)  # Hit
    await redis_cache.get_project_config("nonexistent")  # Miss

    # Get stats
    stats = await redis_cache.get_stats()

    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["writes"] == 1
    assert stats["total_requests"] == 2
    assert stats["hit_rate"] == 0.5


# Cached Config Store Tests (Integration with both Redis and Elasticsearch)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_store_write_through(cached_config_store, sample_project_config):
    """Test write-through caching (writes to storage then cache)."""
    # Save project (should write to both storage and cache)
    await cached_config_store.save_project_config(sample_project_config)

    # Wait for Elasticsearch indexing
    await asyncio.sleep(1)

    # Get from cache (should hit cache, not storage)
    retrieved = await cached_config_store.get_project_config(sample_project_config.id)

    assert retrieved is not None
    assert retrieved.id == sample_project_config.id
    assert retrieved.name == sample_project_config.name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_store_read_through(
    cached_config_store, elasticsearch_storage, sample_project_config
):
    """Test read-through caching (cache miss falls back to storage)."""
    # Save directly to storage (bypass cache)
    await elasticsearch_storage.save_project_config(sample_project_config)

    # Wait for indexing
    await asyncio.sleep(1)

    # Get from cached store (should miss cache, hit storage, then populate cache)
    retrieved = await cached_config_store.get_project_config(sample_project_config.id)

    assert retrieved is not None
    assert retrieved.id == sample_project_config.id

    # Second get should hit cache
    retrieved_again = await cached_config_store.get_project_config(
        sample_project_config.id
    )

    assert retrieved_again is not None
    assert retrieved_again.id == sample_project_config.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_store_get_by_name(cached_config_store, sample_project_config):
    """Test getting project by name with caching."""
    # Save project
    await cached_config_store.save_project_config(sample_project_config)

    # Wait for indexing
    await asyncio.sleep(1)

    # Get by name (should populate cache)
    retrieved = await cached_config_store.get_project_config_by_name(
        sample_project_config.name
    )

    assert retrieved is not None
    assert retrieved.id == sample_project_config.id
    assert retrieved.name == sample_project_config.name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_store_update_invalidates_and_updates_cache(
    cached_config_store, sample_project_config
):
    """Test that updates properly update both storage and cache."""
    # Save initial version
    await cached_config_store.save_project_config(sample_project_config)
    await asyncio.sleep(1)

    # Update config
    sample_project_config.tech_stacks["typescript"] = "5.0"
    await cached_config_store.save_project_config(sample_project_config)
    await asyncio.sleep(1)

    # Get from cache (should have updated version)
    retrieved = await cached_config_store.get_project_config(sample_project_config.id)

    assert "typescript" in retrieved.tech_stacks
    assert retrieved.tech_stacks["typescript"] == "5.0"
    assert retrieved.version == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_store_agent_config(cached_config_store, sample_agent_config):
    """Test caching agent configuration through cached store."""
    # Save agent config
    await cached_config_store.save_agent_config(sample_agent_config)
    await asyncio.sleep(1)

    # Get agent config (should hit cache)
    retrieved = await cached_config_store.get_agent_config(
        sample_agent_config.project_id, sample_agent_config.agent_name
    )

    assert retrieved is not None
    assert retrieved.project_id == sample_agent_config.project_id
    assert retrieved.agent_name == sample_agent_config.agent_name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_store_delete_invalidates_cache(
    cached_config_store, redis_cache, sample_project_config
):
    """Test that delete operation invalidates cache."""
    # Save project
    await cached_config_store.save_project_config(sample_project_config)
    await asyncio.sleep(1)

    # Verify it's in cache
    cached = await redis_cache.get_project_config(sample_project_config.id)
    assert cached is not None

    # Delete project
    await cached_config_store.delete_project_config(sample_project_config.id)
    await asyncio.sleep(1)

    # Verify it's removed from cache
    cached_after = await redis_cache.get_project_config(sample_project_config.id)
    assert cached_after is None

    # Verify it's removed from storage
    with pytest.raises(ConfigNotFoundError):
        await cached_config_store.get_project_config(sample_project_config.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_store_list_operations_bypass_cache(
    cached_config_store, sample_project_config
):
    """Test that list operations go directly to storage (no caching)."""
    # Save multiple projects
    project1 = sample_project_config
    await cached_config_store.save_project_config(project1)

    project2 = ProjectConfig(
        id=f"project-{uuid4().hex[:8]}",
        name=f"Another Project {uuid4().hex[:8]}",
        github_org="test-org",
        github_repo="another-repo",
    )
    await cached_config_store.save_project_config(project2)

    # Wait for indexing
    await asyncio.sleep(1)

    # List projects (should bypass cache and query storage)
    projects = await cached_config_store.list_projects()

    assert len(projects) >= 2
    project_ids = [p.id for p in projects]
    assert project1.id in project_ids
    assert project2.id in project_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_store_search_bypasses_cache(
    cached_config_store, sample_project_config
):
    """Test that search operations go directly to storage."""
    # Save project with unique name
    project = sample_project_config
    project.name = f"Searchable Project {uuid4().hex[:8]}"
    await cached_config_store.save_project_config(project)

    # Wait for indexing
    await asyncio.sleep(2)

    # Search (should bypass cache)
    results = await cached_config_store.search_configs(
        query="Searchable Project", config_type="project"
    )

    assert len(results) > 0
    assert any(r.get("id") == project.id for r in results)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_store_version_history_bypasses_cache(
    cached_config_store, sample_project_config
):
    """Test that version history operations go directly to storage."""
    # Save and update project multiple times
    await cached_config_store.save_project_config(sample_project_config)
    await asyncio.sleep(1)

    for i in range(3):
        sample_project_config.tech_stacks[f"tool{i}"] = f"v{i}"
        await cached_config_store.save_project_config(sample_project_config)
        await asyncio.sleep(1)

    # Get version history (should bypass cache)
    versions = await cached_config_store.list_config_versions(sample_project_config.id)

    assert len(versions) >= 4


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cached_store_exists_bypasses_cache(
    cached_config_store, sample_project_config
):
    """Test that exists() checks go directly to storage."""
    # Save project
    await cached_config_store.save_project_config(sample_project_config)
    await asyncio.sleep(1)

    # Check existence (should bypass cache)
    exists = await cached_config_store.exists(sample_project_config.id)

    assert exists is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_hit_rate_with_repeated_reads(
    cached_config_store, redis_cache, sample_project_config
):
    """Test that repeated reads increase cache hit rate."""
    # Reset stats
    await redis_cache.reset_stats()

    # Save project
    await cached_config_store.save_project_config(sample_project_config)
    await asyncio.sleep(1)

    # Read multiple times (should hit cache after first read)
    for _ in range(10):
        await cached_config_store.get_project_config(sample_project_config.id)

    # Check stats
    stats = await redis_cache.get_stats()

    # After first write, all 10 reads should hit cache
    assert stats["hits"] == 10
    assert stats["hit_rate"] == 1.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_cached_store_operations(
    cached_config_store, sample_project_config
):
    """Test concurrent operations on cached config store."""
    # Save initial project
    await cached_config_store.save_project_config(sample_project_config)
    await asyncio.sleep(1)

    # Perform concurrent reads
    async def read_project():
        return await cached_config_store.get_project_config(sample_project_config.id)

    results = await asyncio.gather(*[read_project() for _ in range(10)])

    # All reads should succeed
    assert len(results) == 10
    assert all(r.id == sample_project_config.id for r in results)
