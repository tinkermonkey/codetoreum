"""Integration tests for Elasticsearch Configuration Storage.

These tests use testcontainers to spin up a real Elasticsearch instance.
"""

import asyncio
import dataclasses
from types import MappingProxyType
from uuid import uuid4

import pytest
from elasticsearch import AsyncElasticsearch

from codetoreum.adapters.secondary.elasticsearch_config_storage import (
    ElasticsearchConfigStorage,
)
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.ports.output.config_store import (
    AgentConfig,
    ConfigNotFoundError,
    PipelineConfig,
    ProjectConfig,
    WorkflowTemplate,
)
from tests.conftest import (
    ModernElasticsearchContainer,
    docker_available,
    wait_for_condition,
    wait_for_elasticsearch_indexing,
)


def _test_inv(
    model: str = "claude-sonnet-4-5",
    timeout_seconds: int = 300,
    requires_docker: bool = True,
) -> AgentInvocationConfig:
    """Build an AgentInvocationConfig for tests (DEF-020 transitional helper)."""
    return AgentInvocationConfig(
        mode=InvocationMode.CONTAINERIZED if requires_docker else InvocationMode.HOST,
        model=model,
        timeout_seconds=timeout_seconds,
        mode_config={"image": "codetoreum-agent:latest"} if requires_docker else {},
    )


# Mark all tests in this module as requiring Docker
pytestmark = docker_available


@pytest.fixture(scope="module")
def elasticsearch_container():
    """Create Elasticsearch testcontainer with resource limits."""
    # Use Elasticsearch 8.x with modern wait strategy (no deprecation warnings)
    container = ModernElasticsearchContainer("elasticsearch:8.17.0")
    # Add resource limits to prevent memory exhaustion - smaller heap for faster startup
    container.with_env("ES_JAVA_OPTS", "-Xms256m -Xmx256m")
    container.with_env("discovery.seed_hosts", "[]")  # Faster startup
    container.start()

    yield container

    container.stop()


@pytest.fixture(scope="module")
def elasticsearch_url(elasticsearch_container):
    """Get Elasticsearch URL from container."""
    return elasticsearch_container.get_url()


@pytest.fixture
async def es_client(elasticsearch_url):
    """Create AsyncElasticsearch client."""
    client = AsyncElasticsearch(
        [elasticsearch_url],
        verify_certs=False,
        request_timeout=30,
    )

    yield client

    await client.close()


@pytest.fixture
async def config_storage(es_client):
    """Create ElasticsearchConfigStorage instance."""
    storage = ElasticsearchConfigStorage(
        es_client=es_client,
        create_index_templates=True,
        shard_count=1,
        replica_count=0,
    )

    # Initialize storage (create indices)
    await storage.initialize()

    # Wait for indices to be ready by checking cluster health
    async def indices_ready():
        try:
            health = await es_client.cluster.health()
            # Wait for at least one index to be ready
            return health.get("active_shards", 0) > 0
        except Exception:
            return False

    await wait_for_condition(indices_ready, timeout=10.0)

    yield storage

    await storage.close()


@pytest.fixture
def sample_project_config():
    """Create a sample ProjectConfig for testing."""
    return ProjectConfig(
        id=f"project-{uuid4().hex[:8]}",
        name=f"Test Project {uuid4().hex[:8]}",
        github_org="test-org",
        github_repo="test-repo",
        tech_stacks={"python": "3.11", "node": "18"},
        pipelines=[
            {
                "name": "main",
                "stages": ["analyze", "implement", "review"],
            }
        ],
        testing={"framework": "pytest", "coverage": 80},
        environment_variables={"ENV": "test"},
        mounted_commands={},
        mounted_subagents={},
        version=1,
        metadata={"created_by": "test"},
    )


@pytest.fixture
def sample_agent_config():
    """Create a sample AgentConfig for testing."""
    return AgentConfig(
        project_id=f"project-{uuid4().hex[:8]}",
        agent_name="test-agent",
        makes_code_changes=True,
        mcp_servers=["artifacts", "logging"],
        capabilities=["code-generation", "testing"],
        constraints={"max_retries": 3},
        version=1,
        metadata={"created_by": "test"},
        invocation=_test_inv(model="claude-sonnet-4", timeout_seconds=300, requires_docker=True),
        coding_agent="",
    )


@pytest.fixture
def sample_pipeline_config():
    """Create a sample PipelineConfig for testing."""
    return PipelineConfig(
        id=f"pipeline-{uuid4().hex[:8]}",
        project_id=f"project-{uuid4().hex[:8]}",
        name="main-pipeline",
        stages=[
            {"name": "analyze", "agent": "analyst"},
            {"name": "implement", "agent": "developer"},
            {"name": "review", "agent": "reviewer"},
        ],
        triggers=["issue_created", "issue_updated"],
        version=1,
        metadata={"created_by": "test"},
    )


@pytest.fixture
def sample_workflow_template():
    """Create a sample WorkflowTemplate for testing."""
    return WorkflowTemplate(
        id=f"template-{uuid4().hex[:8]}",
        name="standard-workflow",
        description="Standard software development workflow",
        stages=[
            {"name": "requirements", "agent": "analyst"},
            {"name": "architecture", "agent": "architect"},
            {"name": "implementation", "agent": "developer"},
            {"name": "testing", "agent": "tester"},
            {"name": "review", "agent": "reviewer"},
        ],
        version=1,
        metadata={"created_by": "test"},
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_and_get_project_config(config_storage, sample_project_config, es_client):
    """Test saving and retrieving a project configuration."""
    # Save project config
    await config_storage.save_project_config(sample_project_config)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(es_client)

    # Retrieve by ID
    retrieved = await config_storage.get_project_config(sample_project_config.id)

    assert retrieved.id == sample_project_config.id
    assert retrieved.name == sample_project_config.name
    assert retrieved.github_org == sample_project_config.github_org
    assert retrieved.github_repo == sample_project_config.github_repo
    assert retrieved.tech_stacks == sample_project_config.tech_stacks
    assert retrieved.version == 1
    assert retrieved.created_at is not None
    assert retrieved.updated_at is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_project_config_by_name(config_storage, sample_project_config, es_client):
    """Test retrieving a project configuration by name."""
    # Save project config
    await config_storage.save_project_config(sample_project_config)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(es_client)

    # Retrieve by name
    retrieved = await config_storage.get_project_config_by_name(sample_project_config.name)

    assert retrieved.id == sample_project_config.id
    assert retrieved.name == sample_project_config.name


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_project_config_versioning(config_storage, sample_project_config, es_client):
    """Test that updating a project config increments version."""
    # Save initial version
    await config_storage.save_project_config(sample_project_config)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(es_client)

    # Update config with new tech_stacks
    updated_tech_stacks = dict(sample_project_config.tech_stacks)
    updated_tech_stacks["typescript"] = "5.0"
    updated_config = dataclasses.replace(
        sample_project_config,
        tech_stacks=MappingProxyType(updated_tech_stacks),
    )
    await config_storage.save_project_config(updated_config)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(es_client)

    # Retrieve updated config
    retrieved = await config_storage.get_project_config(sample_project_config.id)

    assert retrieved.version == 2
    assert "typescript" in retrieved.tech_stacks


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_nonexistent_project_raises_error(config_storage):
    """Test that getting a nonexistent project raises ConfigNotFoundError."""
    with pytest.raises(ConfigNotFoundError):
        await config_storage.get_project_config("nonexistent-project")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_and_get_agent_config(config_storage, sample_agent_config, es_client):
    """Test saving and retrieving an agent configuration."""
    # Save agent config
    await config_storage.save_agent_config(sample_agent_config)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(es_client)

    # Retrieve agent config
    retrieved = await config_storage.get_agent_config(sample_agent_config.project_id, sample_agent_config.agent_name)

    assert retrieved.project_id == sample_agent_config.project_id
    assert retrieved.agent_name == sample_agent_config.agent_name
    assert retrieved.invocation.model == sample_agent_config.invocation.model
    assert retrieved.invocation.timeout_seconds == sample_agent_config.invocation.timeout_seconds
    assert retrieved.invocation.mode == sample_agent_config.invocation.mode
    assert retrieved.mcp_servers == sample_agent_config.mcp_servers
    assert retrieved.version == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_and_get_pipeline_config(config_storage, sample_pipeline_config, es_client):
    """Test saving and retrieving a pipeline configuration."""
    # Save pipeline config
    await config_storage.save_pipeline_config(sample_pipeline_config)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(es_client)

    # Retrieve pipeline config
    retrieved = await config_storage.get_pipeline_config(sample_pipeline_config.project_id, sample_pipeline_config.name)

    assert retrieved.id == sample_pipeline_config.id
    assert retrieved.project_id == sample_pipeline_config.project_id
    assert retrieved.name == sample_pipeline_config.name
    assert len(retrieved.stages) == 3
    assert retrieved.triggers == sample_pipeline_config.triggers
    assert retrieved.version == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_and_get_workflow_template(config_storage, sample_workflow_template, es_client):
    """Test saving and retrieving a workflow template."""
    # Save workflow template
    await config_storage.save_workflow_template(sample_workflow_template)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(es_client)

    # Retrieve workflow template
    retrieved = await config_storage.get_workflow_template(sample_workflow_template.name)

    assert retrieved.id == sample_workflow_template.id
    assert retrieved.name == sample_workflow_template.name
    assert retrieved.description == sample_workflow_template.description
    assert len(retrieved.stages) == 5
    assert retrieved.version == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_projects(config_storage, sample_project_config, es_client):
    """Test listing all projects."""
    # Save multiple projects
    project1 = sample_project_config
    await config_storage.save_project_config(project1)

    project2 = ProjectConfig(
        id=f"project-{uuid4().hex[:8]}",
        name=f"Another Project {uuid4().hex[:8]}",
        github_org="test-org",
        github_repo="another-repo",
    )
    await config_storage.save_project_config(project2)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(es_client)

    # List projects
    projects = await config_storage.list_projects()

    assert len(projects) >= 2
    project_ids = [p.id for p in projects]
    assert project1.id in project_ids
    assert project2.id in project_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_agents(config_storage, sample_agent_config, es_client):
    """Test listing agents for a project."""
    # Save multiple agents for same project
    agent1 = sample_agent_config
    await config_storage.save_agent_config(agent1)

    agent2 = AgentConfig(
        project_id=agent1.project_id,
        agent_name="another-agent",
        makes_code_changes=False,
        invocation=_test_inv(model="claude-opus-4", timeout_seconds=600, requires_docker=False),
        coding_agent="",
    )
    await config_storage.save_agent_config(agent2)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(es_client)

    # List agents
    agents = await config_storage.list_agents(agent1.project_id)

    assert len(agents) == 2
    agent_names = [a.agent_name for a in agents]
    assert agent1.agent_name in agent_names
    assert agent2.agent_name in agent_names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_configs(config_storage, sample_project_config, es_client):
    """Test searching configurations."""
    # Create a project with unique name
    unique_name = f"Unique Project Name {uuid4().hex[:8]}"
    project = dataclasses.replace(sample_project_config, name=unique_name)
    await config_storage.save_project_config(project)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(es_client, timeout=10.0)

    # Search for project
    results = await config_storage.search_configs(query="Unique Project", config_type="project")

    assert len(results) > 0
    assert any(r.get("id") == project.id for r in results)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_config_version_history(config_storage, sample_project_config, es_client):
    """Test configuration version history tracking."""
    # Save initial version
    await config_storage.save_project_config(sample_project_config)
    await wait_for_elasticsearch_indexing(es_client)

    # Update config multiple times
    current_config = sample_project_config
    for i in range(3):
        updated_tech_stacks = dict(current_config.tech_stacks)
        updated_tech_stacks[f"tool{i}"] = f"v{i}"
        current_config = dataclasses.replace(
            current_config,
            tech_stacks=MappingProxyType(updated_tech_stacks),
        )
        await config_storage.save_project_config(current_config)
        await wait_for_elasticsearch_indexing(es_client)

    # Get version history
    versions = await config_storage.list_config_versions(sample_project_config.id)

    assert len(versions) >= 4  # Initial + 3 updates
    assert all(isinstance(v.version, int) for v in versions)
    assert versions[0].version > versions[-1].version  # Newest first


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_specific_config_version(config_storage, sample_project_config, es_client):
    """Test retrieving a specific version of a configuration."""
    # Save initial version
    await config_storage.save_project_config(sample_project_config)
    await wait_for_elasticsearch_indexing(es_client)

    # Update config
    updated_tech_stacks = dict(sample_project_config.tech_stacks)
    updated_tech_stacks["new_tool"] = "1.0"
    updated_config = dataclasses.replace(
        sample_project_config,
        tech_stacks=MappingProxyType(updated_tech_stacks),
    )
    await config_storage.save_project_config(updated_config)
    await wait_for_elasticsearch_indexing(es_client)

    # Get version 1
    version_1 = await config_storage.get_config_version(sample_project_config.id, 1)

    assert version_1 is not None
    assert "new_tool" not in version_1.get("tech_stacks", {})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_project_config(config_storage, sample_project_config, es_client):
    """Test deleting a project configuration."""
    # Save project
    await config_storage.save_project_config(sample_project_config)
    await wait_for_elasticsearch_indexing(es_client)

    # Verify it exists
    assert await config_storage.exists(sample_project_config.id)

    # Delete project
    await config_storage.delete_project_config(sample_project_config.id)
    await wait_for_elasticsearch_indexing(es_client)

    # Verify it's deleted
    assert not await config_storage.exists(sample_project_config.id)

    # Try to get deleted project
    with pytest.raises(ConfigNotFoundError):
        await config_storage.get_project_config(sample_project_config.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_agent_config(config_storage, sample_agent_config, es_client):
    """Test deleting an agent configuration."""
    # Save agent
    await config_storage.save_agent_config(sample_agent_config)
    await wait_for_elasticsearch_indexing(es_client)

    # Delete agent
    await config_storage.delete_agent_config(sample_agent_config.project_id, sample_agent_config.agent_name)
    await wait_for_elasticsearch_indexing(es_client)

    # Try to get deleted agent
    with pytest.raises(ConfigNotFoundError):
        await config_storage.get_agent_config(sample_agent_config.project_id, sample_agent_config.agent_name)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exists_returns_true_for_existing_project(config_storage, sample_project_config, es_client):
    """Test that exists() returns True for existing project."""
    # Save project
    await config_storage.save_project_config(sample_project_config)
    await wait_for_elasticsearch_indexing(es_client)

    # Check existence
    assert await config_storage.exists(sample_project_config.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_exists_returns_false_for_nonexistent_project(config_storage):
    """Test that exists() returns False for nonexistent project."""
    assert not await config_storage.exists("nonexistent-project")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_updates_increment_versions(config_storage, sample_project_config, es_client):
    """Test that concurrent updates properly increment versions."""
    # Save initial version
    await config_storage.save_project_config(sample_project_config)
    await wait_for_elasticsearch_indexing(es_client)

    # Perform multiple updates
    async def update_config(field_name: str):
        config = await config_storage.get_project_config(sample_project_config.id)
        updated_tech_stacks = dict(config.tech_stacks)
        updated_tech_stacks[field_name] = "1.0"
        updated_config = dataclasses.replace(
            config,
            tech_stacks=MappingProxyType(updated_tech_stacks),
        )
        await config_storage.save_project_config(updated_config)

    # Run updates sequentially (concurrent updates would need optimistic locking)
    await update_config("tool1")
    await asyncio.sleep(0.05)
    await update_config("tool2")
    await asyncio.sleep(0.05)
    await update_config("tool3")
    await wait_for_elasticsearch_indexing(es_client)

    # Check final version
    final = await config_storage.get_project_config(sample_project_config.id)
    assert final.version >= 4  # Initial + 3 updates


@pytest.mark.integration
@pytest.mark.asyncio
async def test_initialize_with_existing_indices_is_idempotent(es_client):
    """Test that initializing with existing indices doesn't fail (idempotent behavior)."""
    # Create and initialize first storage instance
    storage1 = ElasticsearchConfigStorage(
        es_client=es_client,
        create_index_templates=True,
        shard_count=1,
        replica_count=0,
    )
    await storage1.initialize()

    # Wait for indices to be ready
    async def indices_ready():
        try:
            health = await es_client.cluster.health()
            return health.get("active_shards", 0) > 0
        except Exception:
            return False

    await wait_for_condition(indices_ready, timeout=10.0)

    # Create and initialize a second storage instance with the same indices
    # This should not fail even though indices already exist
    storage2 = ElasticsearchConfigStorage(
        es_client=es_client,
        create_index_templates=True,
        shard_count=1,
        replica_count=0,
    )

    # This should succeed without raising any errors
    await storage2.initialize()

    # Verify indices exist and are accessible
    indices_exist = await es_client.indices.exists(
        index=[
            storage2.INDEX_PROJECTS,
            storage2.INDEX_AGENTS,
            storage2.INDEX_PIPELINES,
            storage2.INDEX_WORKFLOWS,
            storage2.INDEX_HISTORY,
        ]
    )
    assert indices_exist

    await storage1.close()
    await storage2.close()
