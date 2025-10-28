"""Integration tests for WorkspaceRouter."""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from codetoreum.application.workspace_router import (
    WorkspaceRouter,
    WorkspacePreparationResult,
    WorkspaceFinalizationResult,
)
from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.domain.agent import Agent, AgentType, AgentCapability
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.work_item import WorkItem, WorkItemStatus, WorkItemPriority
from codetoreum.domain.workspace_context import WorkspaceType
from codetoreum.ports.output.repository import RepositoryStatus


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_repository():
    """Create mock repository adapter."""
    repo = AsyncMock()

    # Default behavior for common operations
    repo.list_branches = AsyncMock(return_value=[])
    repo.create_branch = AsyncMock()
    repo.checkout = AsyncMock()
    repo.pull = AsyncMock()
    repo.commit = AsyncMock(return_value="abc123")
    repo.push = AsyncMock()
    repo.status = AsyncMock(return_value=RepositoryStatus(
        current_branch="main",
        is_dirty=False,
        staged_files=[],
        unstaged_files=[],
        untracked_files=[],
        ahead_count=0,
        behind_count=0,
    ))

    return repo


@pytest.fixture
def mock_container():
    """Create mock container adapter."""
    container = AsyncMock()
    return container


@pytest.fixture
def mock_event_store():
    """Create mock event store."""
    return InMemoryEventStore()


@pytest.fixture
def workspace_router(mock_repository, mock_container, mock_event_store):
    """Create WorkspaceRouter instance with mocks."""
    return WorkspaceRouter(
        repository=mock_repository,
        container=mock_container,
        event_store=mock_event_store,
    )


@pytest.fixture
def sample_work_item():
    """Create sample work item for testing."""
    return WorkItem(
        id="work-item-1",
        project_id="test-project",
        title="Implement user authentication",
        description="Add OAuth2 authentication flow",
        status=WorkItemStatus.NEW,
        priority=WorkItemPriority.MEDIUM,
        labels=["feature"],
        external_id="123",
        external_url="https://github.com/test/repo/issues/123",
        assigned_agent_id=None,
        assigned_at=None,
        current_workflow_id=None,
        current_stage=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        completed_at=None,
    )


@pytest.fixture
def discussion_work_item():
    """Create work item with discussion label."""
    return WorkItem(
        id="work-item-2",
        project_id="test-project",
        title="Research API design patterns",
        description="Explore different API design approaches",
        status=WorkItemStatus.NEW,
        priority=WorkItemPriority.LOW,
        labels=["research", "discussion"],
        external_id="124",
        external_url="https://github.com/test/repo/issues/124",
        assigned_agent_id=None,
        assigned_at=None,
        current_workflow_id=None,
        current_stage=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        completed_at=None,
    )


@pytest.fixture
def sample_agent():
    """Create sample agent that makes code changes."""
    return Agent(
        id="developer-agent",
        name="developer",
        display_name="Developer Agent",
        agent_type=AgentType.DEVELOPER,
        capabilities={
            "code_generation": AgentCapability(skill="code_generation", proficiency=0.9),
            "makes_code_changes": True,
        },
        role_description="Develops code",
        model="claude-sonnet-4-5",
        timeout_seconds=300,
        max_retries=3,
        requires_docker=True,
        requires_dev_container=True,
        makes_code_changes=True,
        filesystem_write_allowed=True,
        mcp_servers=[],
        metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def analyst_agent():
    """Create analyst agent that doesn't make code changes."""
    return Agent(
        id="analyst-agent",
        name="analyst",
        display_name="Analyst Agent",
        agent_type=AgentType.REQUIREMENTS_ANALYST,
        capabilities={
            "analysis": AgentCapability(skill="analysis", proficiency=0.95),
            "makes_code_changes": False,
        },
        role_description="Analyzes requirements",
        model="claude-sonnet-4-5",
        timeout_seconds=300,
        max_retries=3,
        requires_docker=False,
        requires_dev_container=False,
        makes_code_changes=False,
        filesystem_write_allowed=False,
        mcp_servers=[],
        metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_project():
    """Create sample project context."""
    return ProjectContext(
        id="test-project",
        name="Test Project",
        display_name="Test Project",
        repository_url="https://github.com/test/repo.git",
        default_branch="main",
        branch_prefix="feature/",
        tech_stack=["python"],
        primary_language="python",
        test_command="pytest",
        test_framework="pytest",
        has_ci_cd=True,
        default_workflow_template_id="default",
        custom_workflows={},
        has_dockerfile=True,
        dockerfile_path="Dockerfile",
        requires_dev_container=True,
        environment_variables={
            "ENV": "test",
            "PROJECT_KEY": "test-key",
        },
        secrets=[],
        mcp_servers=[],
        metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ============================================================================
# Tests: Workspace Routing
# ============================================================================


@pytest.mark.asyncio
async def test_route_workspace_issue_type(workspace_router, sample_work_item, sample_agent, sample_project):
    """Test routing to issue workspace for regular work items."""
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    assert context.workspace_type == WorkspaceType.ISSUE
    assert context.can_make_code_changes() is True
    assert context.should_create_branch() is True
    assert context.branch_name.startswith("feature/issue-123-")


@pytest.mark.asyncio
async def test_route_workspace_discussion_label(workspace_router, discussion_work_item, sample_agent, sample_project):
    """Test routing to discussion workspace when work item has discussion label."""
    context = await workspace_router.route_workspace(
        work_item=discussion_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    assert context.workspace_type == WorkspaceType.DISCUSSION
    assert context.can_make_code_changes() is False
    assert context.should_create_branch() is False
    assert context.discussion_id == "124"


@pytest.mark.asyncio
async def test_route_workspace_analyst_agent(workspace_router, sample_work_item, analyst_agent, sample_project):
    """Test routing to discussion workspace when agent doesn't make code changes."""
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=analyst_agent,
        project=sample_project,
    )

    assert context.workspace_type == WorkspaceType.DISCUSSION
    assert context.can_make_code_changes() is False


@pytest.mark.asyncio
async def test_branch_name_generation(workspace_router, sample_work_item, sample_agent, sample_project):
    """Test branch name is generated correctly."""
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    assert context.branch_name == "feature/issue-123-implement-user-authentication"


# ============================================================================
# Tests: Workspace Preparation
# ============================================================================


@pytest.mark.asyncio
async def test_prepare_workspace_new_branch(workspace_router, sample_work_item, sample_agent, sample_project, mock_repository):
    """Test preparing workspace with new branch creation."""
    # Arrange
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )
    mock_repository.list_branches.return_value = []  # No existing branches

    # Act
    result = await workspace_router.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=sample_work_item,
    )

    # Assert
    assert result.success is True
    assert result.metadata["branch_action"] == "create_new"
    mock_repository.create_branch.assert_called_once()
    mock_repository.checkout.assert_called_once()
    mock_repository.pull.assert_called_once()


@pytest.mark.asyncio
async def test_prepare_workspace_existing_branch(workspace_router, sample_work_item, sample_agent, sample_project, mock_repository):
    """Test preparing workspace with existing branch."""
    # Arrange
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )
    mock_repository.list_branches.return_value = [context.branch_name]  # Branch exists

    # Act
    result = await workspace_router.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=sample_work_item,
    )

    # Assert
    assert result.success is True
    assert result.metadata["branch_action"] == "checkout_existing"
    mock_repository.create_branch.assert_not_called()
    mock_repository.checkout.assert_called_once()


@pytest.mark.asyncio
async def test_prepare_workspace_discussion(workspace_router, discussion_work_item, analyst_agent, sample_project):
    """Test preparing discussion workspace requires no git operations."""
    # Arrange
    context = await workspace_router.route_workspace(
        work_item=discussion_work_item,
        agent=analyst_agent,
        project=sample_project,
    )

    # Act
    result = await workspace_router.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=discussion_work_item,
    )

    # Assert
    assert result.success is True
    assert "branch_action" not in result.metadata


# ============================================================================
# Tests: Workspace Finalization
# ============================================================================


@pytest.mark.asyncio
async def test_finalize_workspace_with_changes(workspace_router, sample_work_item, sample_agent, sample_project, mock_repository):
    """Test finalizing workspace with code changes."""
    # Arrange
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Mock repository status with changes
    mock_repository.status.return_value = RepositoryStatus(
        current_branch=context.branch_name,
        is_dirty=True,
        staged_files=["file1.py"],
        unstaged_files=["file2.py"],
        untracked_files=[],
        ahead_count=0,
        behind_count=0,
    )

    execution_result = {
        "agent_id": "developer-agent",
        "summary": "Implemented authentication",
    }

    # Act
    result = await workspace_router.finalize_workspace(
        context=context,
        project=sample_project,
        execution_result=execution_result,
    )

    # Assert
    assert result.success is True
    assert result.commit_sha == "abc123"
    assert result.metadata["pushed"] is True
    mock_repository.commit.assert_called_once()
    mock_repository.push.assert_called_once()


@pytest.mark.asyncio
async def test_finalize_workspace_no_changes(workspace_router, sample_work_item, sample_agent, sample_project, mock_repository):
    """Test finalizing workspace with no changes."""
    # Arrange
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Mock repository status without changes
    mock_repository.status.return_value = RepositoryStatus(
        current_branch=context.branch_name,
        is_dirty=False,
        staged_files=[],
        unstaged_files=[],
        untracked_files=[],
        ahead_count=0,
        behind_count=0,
    )

    execution_result = {"agent_id": "developer-agent"}

    # Act
    result = await workspace_router.finalize_workspace(
        context=context,
        project=sample_project,
        execution_result=execution_result,
    )

    # Assert
    assert result.success is True
    assert result.commit_sha is None
    mock_repository.commit.assert_not_called()
    mock_repository.push.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_workspace_discussion(workspace_router, discussion_work_item, analyst_agent, sample_project):
    """Test finalizing discussion workspace is no-op."""
    # Arrange
    context = await workspace_router.route_workspace(
        work_item=discussion_work_item,
        agent=analyst_agent,
        project=sample_project,
    )

    execution_result = {"agent_id": "analyst-agent"}

    # Act
    result = await workspace_router.finalize_workspace(
        context=context,
        project=sample_project,
        execution_result=execution_result,
    )

    # Assert
    assert result.success is True
    assert result.commit_sha is None


# ============================================================================
# Tests: Container Environment & Volumes
# ============================================================================


def test_prepare_container_environment(workspace_router, sample_work_item, sample_agent, sample_project):
    """Test environment variable preparation for containers."""
    context = WorkspaceRouter.route_workspace.__wrapped__(
        workspace_router,
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    env_vars = workspace_router.prepare_container_environment(
        context=context,
        project=sample_project,
        agent=sample_agent,
    )

    assert env_vars["CODETOREUM_PROJECT_ID"] == "test-project"
    assert env_vars["CODETOREUM_WORK_ITEM_ID"] == "work-item-1"
    assert env_vars["CODETOREUM_WORKSPACE_TYPE"] == "issue"
    assert env_vars["CODETOREUM_AGENT_ID"] == "developer-agent"
    assert env_vars["ENV"] == "test"  # From project env vars


def test_prepare_container_volumes_read_write(workspace_router, sample_work_item, sample_agent, sample_project):
    """Test volume mounts for code-changing agents."""
    context = WorkspaceRouter.route_workspace.__wrapped__(
        workspace_router,
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    volumes = workspace_router.prepare_container_volumes(
        context=context,
        project=sample_project,
    )

    # Should have read-write mount
    assert any(":rw" in v for v in volumes.values())


def test_prepare_container_volumes_read_only(workspace_router, discussion_work_item, analyst_agent, sample_project):
    """Test volume mounts for non-code-changing agents."""
    context = WorkspaceRouter.route_workspace.__wrapped__(
        workspace_router,
        work_item=discussion_work_item,
        agent=analyst_agent,
        project=sample_project,
    )

    volumes = workspace_router.prepare_container_volumes(
        context=context,
        project=sample_project,
    )

    # Should have read-only mount
    assert any(":ro" in v for v in volumes.values())
