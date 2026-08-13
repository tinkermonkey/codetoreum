"""Integration tests for CachedConfigStore.

Tests the CachedConfigStore decorator which combines Elasticsearch storage
with Redis caching, providing:
- Read-through caching (cache-first, fallback to storage)
- Write-through caching (storage first, then cache update)
- Cache invalidation on deletes
- Transparent IConfigStore implementation
"""

import asyncio
import pytest
from datetime import datetime, UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from redis import asyncio as aioredis

from codetoreum.adapters.secondary.cached_config_store import CachedConfigStore
from tests.conftest import ModernRedisContainer, docker_available
from codetoreum.infrastructure.redis_config_cache import RedisConfigCache
from codetoreum.ports.output.config_store import (
    AgentConfig,
    ConfigNotFoundError,
    ConfigVersion,
    IConfigStore,
    PipelineConfig,
    ProjectConfig,
    WorkflowTemplate,
)
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode

pytest_plugins = ["pytest_asyncio"]

pytestmark = docker_available


@pytest.fixture(scope="function")
def redis_container():
    """Redis test container with automatic cleanup."""
    container = ModernRedisContainer(image="redis:7-alpine")
    container.start()
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
def mock_storage():
    """Create a mock storage adapter."""
    storage = AsyncMock(spec=IConfigStore)
    storage.search_configs = AsyncMock(return_value=[])
    storage.list_config_versions = AsyncMock(return_value=[])
    return storage


@pytest.fixture
async def cached_store(mock_storage, config_cache):
    """Create cached config store with mock storage."""
    return CachedConfigStore(storage=mock_storage, cache=config_cache)


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
async def test_get_project_config_from_cache(cached_store, mock_storage, sample_project_config):
    """Test retrieving project config from cache (cache hit)."""
    # Set up cache directly
    await cached_store.cache.set_project_config(sample_project_config)

    # Should get from cache without calling storage
    result = await cached_store.get_project_config("proj-001")

    assert result.id == "proj-001"
    assert result.name == "test-project"

    # Storage should not be called
    mock_storage.get_project_config.assert_not_called()


@pytest.mark.asyncio
async def test_get_project_config_cache_miss(cached_store, mock_storage, sample_project_config):
    """Test retrieving project config from storage on cache miss."""
    # Set up storage to return config
    mock_storage.get_project_config.return_value = sample_project_config

    # Get from empty cache
    result = await cached_store.get_project_config("proj-001")

    # Should get from storage
    assert result.id == "proj-001"
    mock_storage.get_project_config.assert_called_once_with("proj-001")

    # Second call should hit cache
    mock_storage.get_project_config.reset_mock()
    result = await cached_store.get_project_config("proj-001")

    assert result.id == "proj-001"
    # Storage should not be called this time
    mock_storage.get_project_config.assert_not_called()


@pytest.mark.asyncio
async def test_get_project_config_by_name(cached_store, mock_storage, sample_project_config):
    """Test retrieving project config by name."""
    # Set up storage
    mock_storage.get_project_config_by_name.return_value = sample_project_config

    # First call hits storage
    result = await cached_store.get_project_config_by_name("test-project")

    assert result.name == "test-project"
    mock_storage.get_project_config_by_name.assert_called_once_with("test-project")

    # Second call should hit cache
    mock_storage.get_project_config_by_name.reset_mock()
    result = await cached_store.get_project_config_by_name("test-project")

    assert result.name == "test-project"
    # Storage should not be called
    mock_storage.get_project_config_by_name.assert_not_called()


@pytest.mark.asyncio
async def test_save_project_config_write_through(cached_store, mock_storage, sample_project_config):
    """Test write-through caching for project config save."""
    # Set up storage to return the same config
    mock_storage.save_project_config = AsyncMock()
    mock_storage.get_project_config.return_value = sample_project_config

    # Save config
    await cached_store.save_project_config(sample_project_config)

    # Should write to storage
    mock_storage.save_project_config.assert_called_once_with(sample_project_config)

    # Should fetch updated version from storage
    mock_storage.get_project_config.assert_called_once_with("proj-001")

    # Second read should come from cache
    mock_storage.get_project_config.reset_mock()
    result = await cached_store.get_project_config("proj-001")

    assert result.id == "proj-001"
    # Storage should not be called
    mock_storage.get_project_config.assert_not_called()


@pytest.mark.asyncio
async def test_get_agent_config_cache_hit(cached_store, sample_agent_config):
    """Test retrieving agent config from cache."""
    # Set up cache directly
    await cached_store.cache.set_agent_config(sample_agent_config)

    # Should get from cache
    result = await cached_store.get_agent_config("proj-001", "code-agent")

    assert result.agent_name == "code-agent"


@pytest.mark.asyncio
async def test_get_agent_config_cache_miss(cached_store, mock_storage, sample_agent_config):
    """Test retrieving agent config from storage on cache miss."""
    # Set up storage
    mock_storage.get_agent_config.return_value = sample_agent_config

    # Get from empty cache
    result = await cached_store.get_agent_config("proj-001", "code-agent")

    assert result.agent_name == "code-agent"
    mock_storage.get_agent_config.assert_called_once_with("proj-001", "code-agent")

    # Second call should hit cache
    mock_storage.get_agent_config.reset_mock()
    result = await cached_store.get_agent_config("proj-001", "code-agent")

    assert result.agent_name == "code-agent"
    mock_storage.get_agent_config.assert_not_called()


@pytest.mark.asyncio
async def test_save_agent_config_write_through(cached_store, mock_storage, sample_agent_config):
    """Test write-through caching for agent config save."""
    mock_storage.save_agent_config = AsyncMock()

    # Save config
    await cached_store.save_agent_config(sample_agent_config)

    # Should write to storage
    mock_storage.save_agent_config.assert_called_once_with(sample_agent_config)

    # Should update cache
    cached = await cached_store.cache.get_agent_config("proj-001", "code-agent")
    assert cached is not None


@pytest.mark.asyncio
async def test_get_pipeline_config_cache_hit(cached_store, sample_pipeline_config):
    """Test retrieving pipeline config from cache."""
    # Set up cache
    await cached_store.cache.set_pipeline_config(sample_pipeline_config)

    # Should get from cache
    result = await cached_store.get_pipeline_config("proj-001", "test-pipeline")

    assert result.name == "test-pipeline"


@pytest.mark.asyncio
async def test_get_pipeline_config_cache_miss(cached_store, mock_storage, sample_pipeline_config):
    """Test retrieving pipeline config from storage on cache miss."""
    mock_storage.get_pipeline_config.return_value = sample_pipeline_config

    # Get from empty cache
    result = await cached_store.get_pipeline_config("proj-001", "test-pipeline")

    assert result.name == "test-pipeline"
    mock_storage.get_pipeline_config.assert_called_once_with("proj-001", "test-pipeline")


@pytest.mark.asyncio
async def test_save_pipeline_config_write_through(cached_store, mock_storage, sample_pipeline_config):
    """Test write-through caching for pipeline config save."""
    mock_storage.save_pipeline_config = AsyncMock()

    # Save config
    await cached_store.save_pipeline_config(sample_pipeline_config)

    # Should write to storage
    mock_storage.save_pipeline_config.assert_called_once_with(sample_pipeline_config)

    # Should update cache
    cached = await cached_store.cache.get_pipeline_config("proj-001", "test-pipeline")
    assert cached is not None


@pytest.mark.asyncio
async def test_get_workflow_template_cache_hit(cached_store, sample_workflow_template):
    """Test retrieving workflow template from cache."""
    # Set up cache
    await cached_store.cache.set_workflow_template(sample_workflow_template)

    # Should get from cache
    result = await cached_store.get_workflow_template("test-workflow")

    assert result.name == "test-workflow"


@pytest.mark.asyncio
async def test_get_workflow_template_cache_miss(cached_store, mock_storage, sample_workflow_template):
    """Test retrieving workflow template from storage on cache miss."""
    mock_storage.get_workflow_template.return_value = sample_workflow_template

    # Get from empty cache
    result = await cached_store.get_workflow_template("test-workflow")

    assert result.name == "test-workflow"
    mock_storage.get_workflow_template.assert_called_once_with("test-workflow")


@pytest.mark.asyncio
async def test_save_workflow_template_write_through(cached_store, mock_storage, sample_workflow_template):
    """Test write-through caching for workflow template save."""
    mock_storage.save_workflow_template = AsyncMock()

    # Save template
    await cached_store.save_workflow_template(sample_workflow_template)

    # Should write to storage
    mock_storage.save_workflow_template.assert_called_once_with(sample_workflow_template)

    # Should update cache
    cached = await cached_store.cache.get_workflow_template("test-workflow")
    assert cached is not None


@pytest.mark.asyncio
async def test_delete_project_config_invalidates_cache(
    cached_store, mock_storage, sample_project_config
):
    """Test that deleting project config invalidates cache."""
    mock_storage.delete_project_config = AsyncMock()

    # Set up cache
    await cached_store.cache.set_project_config(sample_project_config)

    # Verify it's cached
    cached = await cached_store.cache.get_project_config("proj-001")
    assert cached is not None

    # Delete config
    await cached_store.delete_project_config("proj-001")

    # Should call storage delete
    mock_storage.delete_project_config.assert_called_once_with("proj-001")

    # Cache should be invalidated
    cached = await cached_store.cache.get_project_config("proj-001")
    assert cached is None


@pytest.mark.asyncio
async def test_delete_agent_config_invalidates_cache(
    cached_store, mock_storage, sample_agent_config
):
    """Test that deleting agent config invalidates cache."""
    mock_storage.delete_agent_config = AsyncMock()

    # Set up cache
    await cached_store.cache.set_agent_config(sample_agent_config)

    # Verify it's cached
    cached = await cached_store.cache.get_agent_config("proj-001", "code-agent")
    assert cached is not None

    # Delete config
    await cached_store.delete_agent_config("proj-001", "code-agent")

    # Should call storage delete
    mock_storage.delete_agent_config.assert_called_once_with("proj-001", "code-agent")

    # Cache should be invalidated
    cached = await cached_store.cache.get_agent_config("proj-001", "code-agent")
    assert cached is None


@pytest.mark.asyncio
async def test_list_projects_bypasses_cache(cached_store, mock_storage):
    """Test that list_projects goes directly to storage (not cached)."""
    projects = [
        ProjectConfig(
            id=f"proj-{i}",
            name=f"project-{i}",
            github_org="org",
            github_repo="repo",
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        for i in range(3)
    ]
    mock_storage.list_projects.return_value = projects

    # Call list_projects
    result = await cached_store.list_projects()

    # Should go to storage
    assert len(result) == 3
    mock_storage.list_projects.assert_called_once()


@pytest.mark.asyncio
async def test_list_agents_bypasses_cache(cached_store, mock_storage):
    """Test that list_agents goes directly to storage (not cached)."""
    agents = [
        AgentConfig(
            project_id="proj-001",
            agent_name=f"agent-{i}",
            makes_code_changes=True,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            invocation=AgentInvocationConfig(
                mode=InvocationMode.HOST,
                model="claude-sonnet-4",
                timeout_seconds=3600,
            ),
        )
        for i in range(3)
    ]
    mock_storage.list_agents.return_value = agents

    # Call list_agents
    result = await cached_store.list_agents("proj-001")

    # Should go to storage
    assert len(result) == 3
    mock_storage.list_agents.assert_called_once_with("proj-001")


@pytest.mark.asyncio
async def test_list_pipelines_bypasses_cache(cached_store, mock_storage):
    """Test that list_pipelines goes directly to storage (not cached)."""
    pipelines = [
        PipelineConfig(
            id=f"pipe-{i}",
            project_id="proj-001",
            name=f"pipeline-{i}",
            stages=[],
            triggers=[],
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        for i in range(3)
    ]
    mock_storage.list_pipelines.return_value = pipelines

    # Call list_pipelines
    result = await cached_store.list_pipelines("proj-001")

    # Should go to storage
    assert len(result) == 3
    mock_storage.list_pipelines.assert_called_once_with("proj-001")


@pytest.mark.asyncio
async def test_search_configs_bypasses_cache(cached_store, mock_storage):
    """Test that search_configs goes directly to storage (not cached)."""
    results = [{"id": "proj-001", "name": "test-project"}]
    mock_storage.search_configs.return_value = results

    # Call search_configs
    result = await cached_store.search_configs("test")

    # Should go to storage
    assert len(result) == 1
    mock_storage.search_configs.assert_called_once_with("test", None)


@pytest.mark.asyncio
async def test_get_config_version_bypasses_cache(cached_store, mock_storage):
    """Test that get_config_version goes directly to storage (not cached)."""
    version_data = {"id": "proj-001", "version": 2}
    mock_storage.get_config_version.return_value = version_data

    # Call get_config_version
    result = await cached_store.get_config_version("proj-001", 2)

    # Should go to storage
    assert result == version_data
    mock_storage.get_config_version.assert_called_once_with("proj-001", 2)


@pytest.mark.asyncio
async def test_list_config_versions_bypasses_cache(cached_store, mock_storage):
    """Test that list_config_versions goes directly to storage (not cached)."""
    versions = [
        ConfigVersion(id="proj-001", version=2, created_at=datetime.now(UTC)),
        ConfigVersion(id="proj-001", version=1, created_at=datetime.now(UTC)),
    ]
    mock_storage.list_config_versions.return_value = versions

    # Call list_config_versions
    result = await cached_store.list_config_versions("proj-001")

    # Should go to storage
    assert len(result) == 2
    mock_storage.list_config_versions.assert_called_once_with("proj-001", 10)


@pytest.mark.asyncio
async def test_exists_bypasses_cache(cached_store, mock_storage):
    """Test that exists check goes directly to storage (not cached)."""
    mock_storage.exists.return_value = True

    # Call exists
    result = await cached_store.exists("proj-001")

    # Should go to storage
    assert result is True
    mock_storage.exists.assert_called_once_with("proj-001")


@pytest.mark.asyncio
async def test_concurrent_reads_use_cache(cached_store, mock_storage, sample_project_config):
    """Test that concurrent reads benefit from caching."""
    mock_storage.get_project_config.return_value = sample_project_config

    # First read hits storage
    result1 = await cached_store.get_project_config("proj-001")
    assert result1.id == "proj-001"

    # Concurrent reads should all hit cache
    results = await asyncio.gather(
        cached_store.get_project_config("proj-001"),
        cached_store.get_project_config("proj-001"),
        cached_store.get_project_config("proj-001"),
    )

    # All should succeed
    assert all(r.id == "proj-001" for r in results)

    # Storage should only be called once (for first read)
    assert mock_storage.get_project_config.call_count == 1


@pytest.mark.asyncio
async def test_cache_isolation_between_types(cached_store, mock_storage, sample_project_config):
    """Test that different config types don't interfere in cache."""
    # Cache a project config
    await cached_store.cache.set_project_config(sample_project_config)

    # Verify it's there
    cached_project = await cached_store.cache.get_project_config("proj-001")
    assert cached_project is not None

    # Agent cache should still be empty
    cached_agent = await cached_store.cache.get_agent_config("proj-001", "code-agent")
    assert cached_agent is None

    # Storage should not be called
    mock_storage.get_agent_config.assert_not_called()
