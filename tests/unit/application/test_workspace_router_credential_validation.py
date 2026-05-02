"""Tests for WorkspaceRouter credential injection prevention."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from codetoreum.application.workspace_router import WorkspaceRouter, WorkspaceRouterConfig
from codetoreum.domain.agent import Agent, AgentType, CommitPolicy
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.workspace_context import WorkspaceContext, WorkspaceType
from codetoreum.ports.exceptions import ExternalServiceError


@pytest.fixture
def workspace_router():
    """Create a WorkspaceRouter instance for testing."""
    return WorkspaceRouter(config=WorkspaceRouterConfig())


@pytest.fixture
def base_project_context():
    """Create a base ProjectContext for testing."""
    return ProjectContext(
        id="test-project",
        name="Test Project",
        display_name="Test Project",
        repository_url="https://github.com/test/repo.git",
        default_branch="main",
        branch_prefix="feature/",
        tech_stack=["python"],
        primary_language="python",
        environment_variables={},  # Start with empty env vars
    )


@pytest.fixture
def workspace_context():
    """Create a WorkspaceContext for testing."""
    return WorkspaceContext.for_issue(
        project_id="test-project",
        work_item_id="issue-1",
        branch_name="feature/test",
        create_pr=True,
    )


@pytest.fixture
def agent():
    """Create an Agent for testing."""
    return Agent(
        id="agent-1",
        name="Test Agent",
        display_name="Test Agent",
        agent_type=AgentType.SPECIALIST,
    )


@pytest.mark.asyncio
async def test_prepare_container_environment_with_forbidden_github_token(
    workspace_router, workspace_context, base_project_context, agent
):
    """Test that GITHUB_TOKEN in project env vars raises error."""
    base_project_context.environment_variables = {"GITHUB_TOKEN": "ghp_secret123"}

    with pytest.raises(ExternalServiceError) as exc_info:
        await workspace_router.prepare_container_environment(
            workspace_context, base_project_context, agent
        )

    assert "Forbidden credential pattern" in str(exc_info.value)
    assert "GITHUB_TOKEN" in str(exc_info.value)


@pytest.mark.asyncio
async def test_prepare_container_environment_with_forbidden_aws_credentials(
    workspace_router, workspace_context, base_project_context, agent
):
    """Test that AWS_* variables in project env vars raise error."""
    base_project_context.environment_variables = {"AWS_SECRET_ACCESS_KEY": "aws_secret"}

    with pytest.raises(ExternalServiceError) as exc_info:
        await workspace_router.prepare_container_environment(
            workspace_context, base_project_context, agent
        )

    assert "Forbidden credential pattern" in str(exc_info.value)


@pytest.mark.asyncio
async def test_prepare_container_environment_with_forbidden_password(
    workspace_router, workspace_context, base_project_context, agent
):
    """Test that PASSWORD variables in project env vars raise error."""
    base_project_context.environment_variables = {"DB_PASSWORD": "secret123"}

    with pytest.raises(ExternalServiceError) as exc_info:
        await workspace_router.prepare_container_environment(
            workspace_context, base_project_context, agent
        )

    assert "Forbidden credential pattern" in str(exc_info.value)


@pytest.mark.asyncio
async def test_prepare_container_environment_with_forbidden_docker_config(
    workspace_router, workspace_context, base_project_context, agent
):
    """Test that DOCKER_* variables in project env vars raise error."""
    base_project_context.environment_variables = {"DOCKER_HOST": "unix:///var/run/docker.sock"}

    with pytest.raises(ExternalServiceError) as exc_info:
        await workspace_router.prepare_container_environment(
            workspace_context, base_project_context, agent
        )

    assert "Forbidden credential pattern" in str(exc_info.value)


@pytest.mark.asyncio
async def test_prepare_container_environment_with_allowed_project_variables(
    workspace_router, workspace_context, base_project_context, agent
):
    """Test that non-credential project variables are allowed."""
    base_project_context.environment_variables = {
        "CUSTOM_BUILD_OPTION": "value1",
        "LOG_LEVEL": "DEBUG",
        "FEATURE_FLAG_TEST": "true",
    }

    # Should not raise
    env_vars = await workspace_router.prepare_container_environment(
        workspace_context, base_project_context, agent
    )

    # Verify custom variables are included
    assert env_vars["CUSTOM_BUILD_OPTION"] == "value1"
    assert env_vars["LOG_LEVEL"] == "DEBUG"
    assert env_vars["FEATURE_FLAG_TEST"] == "true"


@pytest.mark.asyncio
async def test_prepare_container_environment_with_empty_project_variables(
    workspace_router, workspace_context, base_project_context, agent
):
    """Test behavior with no project environment variables."""
    base_project_context.environment_variables = {}

    # Should not raise
    env_vars = await workspace_router.prepare_container_environment(
        workspace_context, base_project_context, agent
    )

    # Verify core variables are present
    assert "CODETOREUM_PROJECT_ID" in env_vars
    assert "GIT_AUTHOR_NAME" in env_vars
    assert "GIT_AUTHOR_EMAIL" in env_vars


@pytest.mark.asyncio
async def test_prepare_container_environment_without_project_variables_attribute(
    workspace_router, workspace_context, base_project_context, agent
):
    """Test behavior when project has no environment_variables attribute."""
    # Remove environment_variables attribute
    delattr(base_project_context, "environment_variables")

    # Should not raise, gracefully handle missing attribute
    env_vars = await workspace_router.prepare_container_environment(
        workspace_context, base_project_context, agent
    )

    # Verify core variables are still present
    assert "CODETOREUM_PROJECT_ID" in env_vars
    assert env_vars["CODETOREUM_PROJECT_ID"] == "test-project"


@pytest.mark.asyncio
async def test_prepare_container_environment_case_insensitive_pattern_matching(
    workspace_router, workspace_context, base_project_context, agent
):
    """Test that credential pattern matching is case-insensitive."""
    # Test with lowercase
    base_project_context.environment_variables = {"github_token": "secret"}

    with pytest.raises(ExternalServiceError) as exc_info:
        await workspace_router.prepare_container_environment(
            workspace_context, base_project_context, agent
        )

    assert "Forbidden credential pattern" in str(exc_info.value)


@pytest.mark.asyncio
async def test_prepare_container_environment_forbidden_patterns_comprehensive(
    workspace_router, workspace_context, base_project_context, agent
):
    """Test that all forbidden patterns are properly rejected."""
    # Test various forbidden patterns
    forbidden_vars = [
        ("API_KEY_PROD", "API_KEY"),
        ("SECRET_TOKEN", "SECRET_"),
        ("PRIVATE_KEY_PATH", "PRIVATE_"),
        ("SSH_KEY", "SSH_"),
        ("AZURE_SUBSCRIPTION", "AZURE_"),
        ("GCP_PROJECT", "GCP_"),
        ("KUBE_CONFIG", "KUBE_"),
        ("REGISTRY_PASSWORD", "REGISTRY_"),
        ("MONGODB_PASSWORD", "PASSWORD"),
    ]

    for var_name, pattern in forbidden_vars:
        base_project_context.environment_variables = {var_name: "value"}

        with pytest.raises(ExternalServiceError) as exc_info:
            await workspace_router.prepare_container_environment(
                workspace_context, base_project_context, agent
            )

        assert "Forbidden credential pattern" in str(exc_info.value), f"Failed for {var_name}"


@pytest.mark.asyncio
async def test_prepare_container_environment_core_variables_always_present(
    workspace_router, workspace_context, base_project_context, agent
):
    """Test that all core Codetoreum variables are always present."""
    env_vars = await workspace_router.prepare_container_environment(
        workspace_context, base_project_context, agent
    )

    # Verify all core variables
    assert env_vars["CODETOREUM_PROJECT_ID"] == "test-project"
    assert env_vars["CODETOREUM_WORK_ITEM_ID"] == "issue-1"
    assert env_vars["CODETOREUM_WORKSPACE_TYPE"] == "issue"
    assert env_vars["CODETOREUM_ALLOW_CODE_CHANGES"] == "True"
    assert env_vars["CODETOREUM_AGENT_ID"] == "agent-1"
    assert "GIT_AUTHOR_NAME" in env_vars
    assert "GIT_AUTHOR_EMAIL" in env_vars
    assert "GIT_COMMITTER_NAME" in env_vars
    assert "GIT_COMMITTER_EMAIL" in env_vars
    assert "CODETOREUM_BRANCH_NAME" in env_vars
