"""Integration tests for Elasticsearch configuration storage.

Tests the ElasticsearchConfigStorage adapter which provides:
- Separate indices for each configuration type
- Full-text search across all configurations
- Configuration versioning with audit trail
- Optimistic concurrency control using _version field
- Index lifecycle management (ILM) for retention
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from elasticsearch import AsyncElasticsearch

from codetoreum.adapters.secondary.elasticsearch_config_storage import ElasticsearchConfigStorage
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.ports.output.config_store import (
    AgentConfig,
    ConfigNotFoundError,
    PipelineConfig,
    ProjectConfig,
    WorkflowTemplate,
)
from tests.conftest import ModernElasticsearchContainer, docker_available, wait_for_elasticsearch_indexing

pytest_plugins = ["pytest_asyncio"]

pytestmark = docker_available


@pytest.fixture(scope="function")
def es_container():
    """Elasticsearch test container with automatic cleanup."""
    container = ModernElasticsearchContainer("elasticsearch:8.17.0")
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
async def es_client(es_container):
    """Elasticsearch async client connected to test container."""
    url = es_container.get_url()
    client = AsyncElasticsearch(
        [url],
        verify_certs=False,
        ssl_show_warn=False,
        request_timeout=30,
    )

    try:
        # Wait for Elasticsearch to be ready
        await wait_for_elasticsearch_indexing(client, timeout=30)
        yield client
    finally:
        await client.close()


@pytest.fixture
async def config_storage(es_client):
    """Elasticsearch configuration storage instance."""
    storage = ElasticsearchConfigStorage(es_client, create_index_templates=True, owns_client=False)
    await storage.initialize()
    return storage


@pytest.fixture
def sample_project_config():
    """Create a sample project configuration."""
    return ProjectConfig(
        id="proj-001",
        name="test-project",
        github_org="test-org",
        github_repo="test-repo",
        tech_stacks={"language": "python", "framework": "fastapi"},
        pipelines=[{"name": "ci", "stages": ["test", "deploy"]}],
        testing={"framework": "pytest", "coverage": 80},
        environment_variables={"API_KEY": "secret", "DEBUG": "false"},
        mounted_commands={"test": "pytest"},
        mounted_subagents={"code-reviewer": "reviewer-agent"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        version=1,
        metadata={"environment": "test", "owner": "team-a"},
    )


@pytest.fixture
def sample_agent_config():
    """Create a sample agent configuration."""
    return AgentConfig(
        project_id="proj-001",
        agent_name="code-agent",
        makes_code_changes=True,
        mcp_servers=["mcp-server-1", "mcp-server-2"],
        capabilities=["read", "write", "execute"],
        constraints={"timeout": "3600", "max_tokens": "10000"},
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        metadata={"type": "coding", "tier": "premium"},
        coding_agent="claude",
        invocation=AgentInvocationConfig(
            mode=InvocationMode.CONTAINERIZED,
            model="claude-sonnet-4",
            timeout_seconds=3600,
            mode_config={"image": "codetoreum-agent:latest", "cpus": "2"},
            cost_limit_usd=Decimal("5.00"),
        ),
    )


@pytest.fixture
def sample_pipeline_config():
    """Create a sample pipeline configuration."""
    return PipelineConfig(
        id="pipe-001",
        project_id="proj-001",
        name="test-pipeline",
        stages=[
            {"name": "build", "action": "build"},
            {"name": "test", "action": "test"},
            {"name": "deploy", "action": "deploy"},
        ],
        triggers=["push", "pull_request"],
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        metadata={"environment": "prod", "on_failure": "notify"},
    )


@pytest.fixture
def sample_workflow_template():
    """Create a sample workflow template."""
    return WorkflowTemplate(
        id="wf-001",
        name="code-review-workflow",
        description="Automated code review workflow",
        stages=[
            {"name": "static-analysis", "type": "analysis"},
            {"name": "security-scan", "type": "security"},
            {"name": "review", "type": "manual"},
        ],
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        metadata={"framework": "codetoreum", "retention_days": 90},
    )


@pytest.mark.asyncio
async def test_storage_initialization(es_client):
    """Test storage initialization and index creation."""
    storage = ElasticsearchConfigStorage(es_client, create_index_templates=True, owns_client=False)

    # Should not be initialized yet
    assert not storage._initialized

    # Initialize
    await storage.initialize()
    assert storage._initialized

    # Calling again should be idempotent
    await storage.initialize()
    assert storage._initialized


@pytest.mark.asyncio
async def test_save_and_retrieve_project_config(config_storage, sample_project_config):
    """Test saving and retrieving project configuration."""
    # Save config
    await config_storage.save_project_config(sample_project_config)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Retrieve config
    retrieved = await config_storage.get_project_config("proj-001")

    assert retrieved.id == "proj-001"
    assert retrieved.name == "test-project"
    assert retrieved.github_org == "test-org"
    assert retrieved.version == 1


@pytest.mark.asyncio
async def test_project_config_not_found(config_storage):
    """Test that ConfigNotFoundError is raised for missing project."""
    with pytest.raises(ConfigNotFoundError):
        await config_storage.get_project_config("nonexistent")


@pytest.mark.asyncio
async def test_save_and_retrieve_agent_config(config_storage, sample_agent_config):
    """Test saving and retrieving agent configuration."""
    # Save config
    await config_storage.save_agent_config(sample_agent_config)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Retrieve config
    retrieved = await config_storage.get_agent_config("proj-001", "code-agent")

    assert retrieved.agent_name == "code-agent"
    assert retrieved.makes_code_changes is True
    assert len(retrieved.mcp_servers) == 2


@pytest.mark.asyncio
async def test_agent_config_not_found(config_storage):
    """Test that ConfigNotFoundError is raised for missing agent."""
    with pytest.raises(ConfigNotFoundError):
        await config_storage.get_agent_config("proj-001", "nonexistent")


@pytest.mark.asyncio
async def test_save_and_retrieve_pipeline_config(config_storage, sample_pipeline_config):
    """Test saving and retrieving pipeline configuration."""
    # Save config
    await config_storage.save_pipeline_config(sample_pipeline_config)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Retrieve config
    retrieved = await config_storage.get_pipeline_config("proj-001", "test-pipeline")

    assert retrieved.name == "test-pipeline"
    assert len(retrieved.stages) == 3


@pytest.mark.asyncio
async def test_pipeline_config_not_found(config_storage):
    """Test that ConfigNotFoundError is raised for missing pipeline."""
    with pytest.raises(ConfigNotFoundError):
        await config_storage.get_pipeline_config("proj-001", "nonexistent")


@pytest.mark.asyncio
async def test_save_and_retrieve_workflow_template(config_storage, sample_workflow_template):
    """Test saving and retrieving workflow template."""
    # Save template
    await config_storage.save_workflow_template(sample_workflow_template)

    # Wait for indexing
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Retrieve template
    retrieved = await config_storage.get_workflow_template("code-review-workflow")

    assert retrieved.name == "code-review-workflow"
    assert retrieved.description == "Automated code review workflow"
    assert len(retrieved.stages) == 3


@pytest.mark.asyncio
async def test_workflow_template_not_found(config_storage):
    """Test that ConfigNotFoundError is raised for missing workflow template."""
    with pytest.raises(ConfigNotFoundError):
        await config_storage.get_workflow_template("nonexistent")


@pytest.mark.asyncio
async def test_update_project_config_increments_version(config_storage, sample_project_config):
    """Test that updating project config increments version."""
    # Save initial config
    await config_storage.save_project_config(sample_project_config)
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Retrieve and verify version
    retrieved = await config_storage.get_project_config("proj-001")
    assert retrieved.version == 1

    # Update config
    updated = ProjectConfig(
        id="proj-001",
        name="test-project-updated",
        github_org="test-org",
        github_repo="test-repo",
        version=1,
        created_at=retrieved.created_at,
        updated_at=datetime.now(UTC),
    )
    await config_storage.save_project_config(updated)
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Verify version incremented
    retrieved = await config_storage.get_project_config("proj-001")
    assert retrieved.version == 2
    assert retrieved.name == "test-project-updated"


@pytest.mark.asyncio
async def test_delete_project_config(config_storage, sample_project_config):
    """Test deleting project configuration."""
    # Save config
    await config_storage.save_project_config(sample_project_config)
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Verify it exists
    retrieved = await config_storage.get_project_config("proj-001")
    assert retrieved is not None

    # Delete config
    await config_storage.delete_project_config("proj-001")
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Verify it's deleted
    with pytest.raises(ConfigNotFoundError):
        await config_storage.get_project_config("proj-001")


@pytest.mark.asyncio
async def test_delete_agent_config(config_storage, sample_agent_config):
    """Test deleting agent configuration."""
    # Save config
    await config_storage.save_agent_config(sample_agent_config)
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Verify it exists
    retrieved = await config_storage.get_agent_config("proj-001", "code-agent")
    assert retrieved is not None

    # Delete config
    await config_storage.delete_agent_config("proj-001", "code-agent")
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Verify it's deleted
    with pytest.raises(ConfigNotFoundError):
        await config_storage.get_agent_config("proj-001", "code-agent")


@pytest.mark.asyncio
async def test_list_projects(config_storage):
    """Test listing all projects."""
    # Save multiple projects
    projects = [
        ProjectConfig(
            id=f"proj-{i}",
            name=f"project-{i}",
            github_org="org",
            github_repo=f"repo-{i}",
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        for i in range(3)
    ]

    for project in projects:
        await config_storage.save_project_config(project)

    await wait_for_elasticsearch_indexing(config_storage.client)

    # List projects
    retrieved = await config_storage.list_projects()

    assert len(retrieved) >= 3
    retrieved_ids = {p.id for p in retrieved}
    assert "proj-0" in retrieved_ids
    assert "proj-1" in retrieved_ids
    assert "proj-2" in retrieved_ids


@pytest.mark.asyncio
async def test_list_agents(config_storage):
    """Test listing agents for a project."""
    # Save multiple agents
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

    for agent in agents:
        await config_storage.save_agent_config(agent)

    await wait_for_elasticsearch_indexing(config_storage.client)

    # List agents
    retrieved = await config_storage.list_agents("proj-001")

    assert len(retrieved) >= 3
    retrieved_names = {a.agent_name for a in retrieved}
    assert "agent-0" in retrieved_names


@pytest.mark.asyncio
async def test_list_pipelines(config_storage):
    """Test listing pipelines for a project."""
    # Save multiple pipelines
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

    for pipeline in pipelines:
        await config_storage.save_pipeline_config(pipeline)

    await wait_for_elasticsearch_indexing(config_storage.client)

    # List pipelines
    retrieved = await config_storage.list_pipelines("proj-001")

    assert len(retrieved) >= 3


@pytest.mark.asyncio
async def test_search_configs(config_storage, sample_project_config):
    """Test searching configurations."""
    # Save config
    await config_storage.save_project_config(sample_project_config)
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Search
    results = await config_storage.search_configs("test-project")

    assert len(results) > 0
    assert any(r.get("name") == "test-project" for r in results)


@pytest.mark.asyncio
async def test_config_versions(config_storage, sample_project_config):
    """Test configuration versioning."""
    # Save initial config
    await config_storage.save_project_config(sample_project_config)
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Update config
    updated = ProjectConfig(
        id="proj-001",
        name="test-project-v2",
        github_org="test-org",
        github_repo="test-repo",
        version=1,
        created_at=sample_project_config.created_at,
        updated_at=datetime.now(UTC),
    )
    await config_storage.save_project_config(updated)
    await wait_for_elasticsearch_indexing(config_storage.client)

    # List versions
    versions = await config_storage.list_config_versions("proj-001")

    assert len(versions) >= 2
    assert versions[0].version >= 2


@pytest.mark.asyncio
async def test_exists_project(config_storage, sample_project_config):
    """Test checking if project exists."""
    # Initially should not exist
    exists = await config_storage.exists("proj-001")
    assert exists is False

    # Save project
    await config_storage.save_project_config(sample_project_config)
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Should exist now
    exists = await config_storage.exists("proj-001")
    assert exists is True


@pytest.mark.asyncio
async def test_multiple_projects(config_storage):
    """Test handling multiple distinct projects."""
    # Create and save multiple projects
    for i in range(3):
        project = ProjectConfig(
            id=f"proj-{i}",
            name=f"project-{i}",
            github_org=f"org-{i}",
            github_repo=f"repo-{i}",
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await config_storage.save_project_config(project)

    await wait_for_elasticsearch_indexing(config_storage.client)

    # Verify each project is independent
    for i in range(3):
        project = await config_storage.get_project_config(f"proj-{i}")
        assert project.name == f"project-{i}"
        assert project.github_org == f"org-{i}"


@pytest.mark.asyncio
async def test_agent_config_serialization(config_storage, sample_agent_config):
    """Test that agent config with complex types survives round-trip."""
    # Save agent with cost limit (Decimal) and invocation config
    await config_storage.save_agent_config(sample_agent_config)
    await wait_for_elasticsearch_indexing(config_storage.client)

    # Retrieve and verify
    retrieved = await config_storage.get_agent_config("proj-001", "code-agent")

    assert retrieved.invocation.model == "claude-sonnet-4"
    assert retrieved.invocation.timeout_seconds == 3600
    assert retrieved.invocation.mode == InvocationMode.CONTAINERIZED
    assert retrieved.invocation.cost_limit_usd == Decimal("5.00")


@pytest.mark.asyncio
async def test_project_config_with_complex_metadata(config_storage):
    """Test project config with complex nested metadata."""
    project = ProjectConfig(
        id="proj-001",
        name="complex-project",
        github_org="org",
        github_repo="repo",
        tech_stacks={
            "languages": ["python", "javascript"],
            "frameworks": {"backend": "fastapi", "frontend": "react"},
        },
        testing={
            "unit": {"framework": "pytest", "coverage": 85},
            "integration": {"framework": "testcontainers"},
        },
        environment_variables={
            "API_KEYS": "secret-key-1,secret-key-2",
            "DEBUG": "false",
        },
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        metadata={
            "team": "platform",
            "sla": {"uptime": "99.9", "response_time_ms": 200},
        },
    )

    # Save and retrieve
    await config_storage.save_project_config(project)
    await wait_for_elasticsearch_indexing(config_storage.client)

    retrieved = await config_storage.get_project_config("proj-001")

    assert retrieved.tech_stacks["frameworks"]["backend"] == "fastapi"
    assert retrieved.testing["unit"]["coverage"] == 85
    assert retrieved.metadata["sla"]["uptime"] == "99.9"
