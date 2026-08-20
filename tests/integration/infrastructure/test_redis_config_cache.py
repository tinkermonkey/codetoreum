"""Integration tests for Redis configuration cache.

Tests the RedisConfigCache class which provides:
- Write-through caching for configuration updates
- Cache invalidation on updates (pub/sub pattern)
- TTL-based expiration with automatic refresh
- Monitoring of cache hit rates
- Buffering layer between application and Elasticsearch
"""

import asyncio
from datetime import UTC, datetime

import pytest
from redis import asyncio as aioredis

from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.infrastructure.redis_config_cache import RedisConfigCache, RedisConfigCacheError
from codetoreum.ports.output.config_store import (
    AgentConfig,
    PipelineConfig,
    ProjectConfig,
    WorkflowTemplate,
)
from tests.conftest import ModernRedisContainer, docker_available

pytestmark = docker_available


@pytest.fixture(scope="function")
def redis_container():
    """Redis test container with automatic cleanup."""
    container = ModernRedisContainer(image="redis:7-alpine")
    try:
        container.start()
    except Exception:
        # start() may have created and started the underlying Docker
        # container before its readiness check raised (e.g. a startup
        # TimeoutError). Since this is outside the try/finally below,
        # nothing else will clean it up — stop it here before re-raising.
        try:
            container.stop()
        except Exception:
            pass  # session-level pytest_sessionfinish hook will force-remove it
        raise
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="function")
async def redis_client(redis_container):
    """Redis async client connected to test container."""
    url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
    client = aioredis.from_url(url, decode_responses=True)

    try:
        await client.ping()
        yield client
    finally:
        await client.close()


@pytest.fixture
async def config_cache(redis_client):
    """Redis configuration cache instance."""
    cache = RedisConfigCache(redis_client, key_prefix="test_config", default_ttl=60)
    await cache.initialize()
    try:
        yield cache
    finally:
        await cache.close()


@pytest.fixture
def sample_project_config():
    """Create a sample project configuration."""
    return ProjectConfig(
        id="proj-001",
        name="test-project",
        github_org="org",
        github_repo="repo",
        tech_stacks={"lang": "python"},
        pipelines=[],
        testing={"framework": "pytest"},
        environment_variables={"KEY": "value"},
        mounted_commands={},
        mounted_subagents={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        version=1,
        metadata={"type": "test"},
    )


@pytest.fixture
def sample_agent_config():
    """Create a sample agent configuration."""
    return AgentConfig(
        project_id="proj-001",
        agent_name="code-agent",
        makes_code_changes=True,
        mcp_servers=["mcp-server-1"],
        capabilities=["read", "write"],
        constraints={"timeout": "3600"},
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        metadata={"type": "test"},
        coding_agent="claude",
        invocation=AgentInvocationConfig(
            mode=InvocationMode.CONTAINERIZED,
            model="claude-sonnet-4",
            timeout_seconds=3600,
            mode_config={"image": "codetoreum-agent:latest"},
        ),
    )


@pytest.fixture
def sample_pipeline_config():
    """Create a sample pipeline configuration."""
    return PipelineConfig(
        id="pipe-001",
        project_id="proj-001",
        name="test-pipeline",
        stages=[{"name": "stage1", "action": "test"}],
        triggers=["push"],
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        metadata={"type": "test"},
    )


@pytest.fixture
def sample_workflow_template():
    """Create a sample workflow template."""
    return WorkflowTemplate(
        id="wf-001",
        name="test-workflow",
        description="Test workflow",
        stages=[{"name": "stage1"}],
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        metadata={"type": "test"},
    )


@pytest.mark.asyncio
async def test_cache_initialization(redis_client):
    """Test cache initialization and pub/sub setup."""
    cache = RedisConfigCache(redis_client)

    # Not initialized yet
    assert not cache._initialized

    # Initialize
    await cache.initialize()
    assert cache._initialized

    # Calling again should be idempotent
    await cache.initialize()
    assert cache._initialized

    await cache.close()


@pytest.mark.asyncio
async def test_project_config_cache_hit(config_cache, sample_project_config):
    """Test project config cache hit."""
    # Set config in cache
    await config_cache.set_project_config(sample_project_config)

    # Retrieve should hit cache
    retrieved = await config_cache.get_project_config("proj-001")

    assert retrieved is not None
    assert retrieved.id == "proj-001"
    assert retrieved.name == "test-project"

    # Check cache statistics
    stats = await config_cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 0


@pytest.mark.asyncio
async def test_project_config_cache_miss_and_populate(redis_client, config_cache, sample_project_config):
    """Test project config cache miss on clean cache."""
    # Get from empty cache
    retrieved = await config_cache.get_project_config("proj-001")

    assert retrieved is None

    # Check cache statistics
    stats = await config_cache.get_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 1


@pytest.mark.asyncio
async def test_project_config_by_name(config_cache, sample_project_config):
    """Test retrieving project config by name."""
    # Set config
    await config_cache.set_project_config(sample_project_config)

    # Retrieve by name
    retrieved = await config_cache.get_project_config_by_name("test-project")

    assert retrieved is not None
    assert retrieved.id == "proj-001"
    assert retrieved.name == "test-project"


@pytest.mark.asyncio
async def test_agent_config_cache(config_cache, sample_agent_config):
    """Test agent configuration caching."""
    # Set agent config
    await config_cache.set_agent_config(sample_agent_config)

    # Retrieve should hit cache
    retrieved = await config_cache.get_agent_config("proj-001", "code-agent")

    assert retrieved is not None
    assert retrieved.agent_name == "code-agent"
    assert retrieved.makes_code_changes is True


@pytest.mark.asyncio
async def test_pipeline_config_cache(config_cache, sample_pipeline_config):
    """Test pipeline configuration caching."""
    # Set pipeline config
    await config_cache.set_pipeline_config(sample_pipeline_config)

    # Retrieve should hit cache
    retrieved = await config_cache.get_pipeline_config("proj-001", "test-pipeline")

    assert retrieved is not None
    assert retrieved.name == "test-pipeline"


@pytest.mark.asyncio
async def test_workflow_template_cache(config_cache, sample_workflow_template):
    """Test workflow template caching."""
    # Set workflow template
    await config_cache.set_workflow_template(sample_workflow_template)

    # Retrieve should hit cache
    retrieved = await config_cache.get_workflow_template("test-workflow")

    assert retrieved is not None
    assert retrieved.name == "test-workflow"
    assert retrieved.description == "Test workflow"


@pytest.mark.asyncio
async def test_cache_invalidation_project(config_cache, sample_project_config):
    """Test project cache invalidation."""
    # Set config
    await config_cache.set_project_config(sample_project_config)

    # Verify it's cached
    retrieved = await config_cache.get_project_config("proj-001")
    assert retrieved is not None

    # Invalidate
    await config_cache.invalidate_project("proj-001")

    # Cache should be cleared
    retrieved = await config_cache.get_project_config("proj-001")
    assert retrieved is None

    # Stats should show invalidation
    stats = await config_cache.get_stats()
    assert stats["invalidations"] >= 1


@pytest.mark.asyncio
async def test_cache_invalidation_agent(config_cache, sample_agent_config):
    """Test agent cache invalidation."""
    # Set config
    await config_cache.set_agent_config(sample_agent_config)

    # Verify it's cached
    retrieved = await config_cache.get_agent_config("proj-001", "code-agent")
    assert retrieved is not None

    # Invalidate
    await config_cache.invalidate_agent("proj-001", "code-agent")

    # Cache should be cleared
    retrieved = await config_cache.get_agent_config("proj-001", "code-agent")
    assert retrieved is None


@pytest.mark.asyncio
async def test_cache_invalidation_pipeline(config_cache, sample_pipeline_config):
    """Test pipeline cache invalidation."""
    # Set config
    await config_cache.set_pipeline_config(sample_pipeline_config)

    # Verify it's cached
    retrieved = await config_cache.get_pipeline_config("proj-001", "test-pipeline")
    assert retrieved is not None

    # Invalidate
    await config_cache.invalidate_pipeline("proj-001", "test-pipeline")

    # Cache should be cleared
    retrieved = await config_cache.get_pipeline_config("proj-001", "test-pipeline")
    assert retrieved is None


@pytest.mark.asyncio
async def test_cache_invalidation_workflow(config_cache, sample_workflow_template):
    """Test workflow template cache invalidation."""
    # Set config
    await config_cache.set_workflow_template(sample_workflow_template)

    # Verify it's cached
    retrieved = await config_cache.get_workflow_template("test-workflow")
    assert retrieved is not None

    # Invalidate
    await config_cache.invalidate_workflow("test-workflow")

    # Cache should be cleared
    retrieved = await config_cache.get_workflow_template("test-workflow")
    assert retrieved is None


@pytest.mark.asyncio
async def test_cache_invalidate_all(config_cache, sample_project_config, sample_agent_config):
    """Test invalidate all cache."""
    # Set multiple configs
    await config_cache.set_project_config(sample_project_config)
    await config_cache.set_agent_config(sample_agent_config)

    # Verify they're cached
    project = await config_cache.get_project_config("proj-001")
    agent = await config_cache.get_agent_config("proj-001", "code-agent")
    assert project is not None
    assert agent is not None

    # Invalidate all
    await config_cache.invalidate_all()

    # All should be cleared
    project = await config_cache.get_project_config("proj-001")
    agent = await config_cache.get_agent_config("proj-001", "code-agent")
    assert project is None
    assert agent is None


@pytest.mark.asyncio
async def test_cache_statistics(config_cache, sample_project_config):
    """Test cache statistics tracking."""
    # Start with clean stats
    await config_cache.reset_stats()
    stats = await config_cache.get_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["writes"] == 0

    # Write
    await config_cache.set_project_config(sample_project_config)
    stats = await config_cache.get_stats()
    assert stats["writes"] == 1

    # Hit
    await config_cache.get_project_config("proj-001")
    stats = await config_cache.get_stats()
    assert stats["hits"] == 1

    # Miss
    await config_cache.get_project_config("unknown")
    stats = await config_cache.get_stats()
    assert stats["misses"] == 1

    # Hit rate
    assert stats["hit_rate"] == 0.5
    assert stats["miss_rate"] == 0.5


@pytest.mark.asyncio
async def test_cache_ttl_expiration(redis_client, sample_project_config):
    """Test that cached items expire after TTL."""
    cache = RedisConfigCache(redis_client, key_prefix="ttl_test", default_ttl=1)
    await cache.initialize()

    try:
        # Set with short TTL
        await cache.set_project_config(sample_project_config)

        # Should be available immediately
        retrieved = await cache.get_project_config("proj-001")
        assert retrieved is not None

        # Wait for TTL to expire
        await asyncio.sleep(1.2)

        # Should be expired
        retrieved = await cache.get_project_config("proj-001")
        assert retrieved is None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cache_custom_ttl(redis_client, sample_project_config):
    """Test setting custom TTL for individual items."""
    cache = RedisConfigCache(redis_client, key_prefix="custom_ttl_test", default_ttl=60)
    await cache.initialize()

    try:
        # Set with custom short TTL
        await cache.set_project_config(sample_project_config, ttl=1)

        # Should be available immediately
        retrieved = await cache.get_project_config("proj-001")
        assert retrieved is not None

        # Wait for TTL to expire
        await asyncio.sleep(1.2)

        # Should be expired
        retrieved = await cache.get_project_config("proj-001")
        assert retrieved is None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cache_handles_missing_values(config_cache):
    """Test that cache gracefully handles missing values."""
    # Get non-existent project
    result = await config_cache.get_project_config("nonexistent")
    assert result is None

    # Get non-existent agent
    result = await config_cache.get_agent_config("proj-999", "nonexistent")
    assert result is None

    # Get non-existent pipeline
    result = await config_cache.get_pipeline_config("proj-999", "nonexistent")
    assert result is None

    # Get non-existent workflow
    result = await config_cache.get_workflow_template("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_cache_auto_initialization(redis_client, sample_project_config):
    """Test that cache auto-initializes on first access."""
    cache = RedisConfigCache(redis_client, key_prefix="auto_init_test")

    # Should not be initialized yet
    assert not cache._initialized

    # First access should trigger initialization
    await cache.set_project_config(sample_project_config)

    # Should be initialized now
    assert cache._initialized

    await cache.close()


@pytest.mark.asyncio
async def test_cache_concurrent_operations(redis_client, sample_project_config, sample_agent_config):
    """Test cache handles concurrent operations correctly."""
    cache = RedisConfigCache(redis_client, key_prefix="concurrent_test")
    await cache.initialize()

    try:
        # Run concurrent operations
        tasks = [
            cache.set_project_config(sample_project_config),
            cache.set_agent_config(sample_agent_config),
            cache.get_project_config("proj-001"),
            cache.get_agent_config("proj-001", "code-agent"),
        ]

        results = await asyncio.gather(*tasks)

        # Should all complete without error
        assert len(results) == 4
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cache_stats_reset(config_cache, sample_project_config):
    """Test resetting cache statistics."""
    # Add some activity
    await config_cache.set_project_config(sample_project_config)
    await config_cache.get_project_config("proj-001")

    stats = await config_cache.get_stats()
    assert stats["writes"] > 0
    assert stats["hits"] > 0

    # Reset stats
    await config_cache.reset_stats()

    stats = await config_cache.get_stats()
    assert stats["writes"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0


@pytest.mark.asyncio
async def test_cache_serialization_roundtrip(redis_client, sample_project_config):
    """Test that configuration objects survive serialization/deserialization."""
    cache = RedisConfigCache(redis_client, key_prefix="serialization_test")
    await cache.initialize()

    try:
        # Set original config
        original = sample_project_config
        await cache.set_project_config(original)

        # Retrieve and verify
        retrieved = await cache.get_project_config("proj-001")

        # Compare key fields
        assert retrieved.id == original.id
        assert retrieved.name == original.name
        assert retrieved.github_org == original.github_org
        assert retrieved.github_repo == original.github_repo
        assert retrieved.version == original.version
    finally:
        await cache.close()
