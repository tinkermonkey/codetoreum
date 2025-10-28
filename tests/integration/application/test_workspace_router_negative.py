"""Negative test cases for WorkspaceRouter."""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from codetoreum.application.workspace_router import WorkspaceRouter
from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.domain.agent import Agent, AgentType, AgentCapability
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.work_item import WorkItem, WorkItemStatus, WorkItemPriority


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_repository():
    """Create mock repository adapter."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_container():
    """Create mock container adapter."""
    return AsyncMock()


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
def code_work_item():
    """Create work item that requires code changes."""
    return WorkItem(
        id="work-item-code",
        project_id="test-project",
        title="Implement feature",
        description="Implement new feature",
        status=WorkItemStatus.NEW,
        priority=WorkItemPriority.HIGH,
        labels=["feature", "backend"],
        external_id="100",
        external_url="https://github.com/test/repo/issues/100",
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
    """Create discussion work item."""
    return WorkItem(
        id="work-item-discuss",
        project_id="test-project",
        title="Research topic",
        description="Research and discuss",
        status=WorkItemStatus.NEW,
        priority=WorkItemPriority.LOW,
        labels=["discussion"],
        external_id="101",
        external_url="https://github.com/test/repo/issues/101",
        assigned_agent_id=None,
        assigned_at=None,
        current_workflow_id=None,
        current_stage=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        completed_at=None,
    )


@pytest.fixture
def analyst_agent():
    """Create analyst agent that doesn't make code changes."""
    return Agent(
        id="analyst",
        name="analyst",
        display_name="Analyst",
        agent_type=AgentType.REQUIREMENTS_ANALYST,
        capabilities={
            "analysis": AgentCapability(skill="analysis", proficiency=0.9),
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
def developer_agent():
    """Create developer agent that makes code changes."""
    return Agent(
        id="developer",
        name="developer",
        display_name="Developer",
        agent_type=AgentType.DEVELOPER,
        capabilities={
            "code_generation": AgentCapability(skill="code_generation", proficiency=0.9),
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
def sample_project():
    """Create sample project."""
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
        environment_variables={},
        secrets=[],
        mcp_servers=[],
        metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def repository_path(tmp_path):
    """Create temporary repository path."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()
    return str(repo_dir)


# ============================================================================
# Negative Tests: Agent Validation
# ============================================================================


@pytest.mark.asyncio
async def test_route_workspace_analyst_on_code_work_fails(
    workspace_router, code_work_item, analyst_agent, sample_project
):
    """Test that analyst agent cannot be assigned to code work item."""
    with pytest.raises(ValueError, match="cannot make code changes"):
        await workspace_router.route_workspace(
            work_item=code_work_item,
            agent=analyst_agent,
            project=sample_project,
        )


# ============================================================================
# Negative Tests: Repository Operations
# ============================================================================


@pytest.mark.asyncio
async def test_prepare_workspace_branch_creation_fails(
    workspace_router, code_work_item, developer_agent, sample_project,
    mock_repository, repository_path
):
    """Test workspace preparation when branch creation fails."""
    context = await workspace_router.route_workspace(
        work_item=code_work_item,
        agent=developer_agent,
        project=sample_project,
    )

    # Mock branch creation failure
    mock_repository.list_branches.return_value = []
    mock_repository.create_branch.side_effect = Exception("Git error: permission denied")

    result = await workspace_router.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=code_work_item,
        repository_path=repository_path,
    )

    assert result.success is False
    assert "permission denied" in result.reason.lower()


@pytest.mark.asyncio
async def test_finalize_workspace_commit_fails(
    workspace_router, code_work_item, developer_agent, sample_project,
    mock_repository, repository_path
):
    """Test workspace finalization when commit fails."""
    from codetoreum.ports.output.repository import RepositoryStatus

    context = await workspace_router.route_workspace(
        work_item=code_work_item,
        agent=developer_agent,
        project=sample_project,
    )

    # Mock repository with changes
    mock_repository.status.return_value = RepositoryStatus(
        current_branch=context.branch_name,
        is_dirty=True,
        staged_files=["file.py"],
        unstaged_files=[],
        untracked_files=[],
        ahead_count=0,
        behind_count=0,
    )

    # Mock commit failure
    mock_repository.commit.side_effect = Exception("Commit failed: merge conflict")

    result = await workspace_router.finalize_workspace(
        context=context,
        project=sample_project,
        execution_result={"agent_id": "developer"},
        repository_path=repository_path,
    )

    assert result.success is False
    assert "merge conflict" in result.reason.lower()


@pytest.mark.asyncio
async def test_finalize_workspace_push_fails(
    workspace_router, code_work_item, developer_agent, sample_project,
    mock_repository, repository_path
):
    """Test workspace finalization when push fails."""
    from codetoreum.ports.output.repository import RepositoryStatus

    context = await workspace_router.route_workspace(
        work_item=code_work_item,
        agent=developer_agent,
        project=sample_project,
    )

    # Mock repository with changes
    mock_repository.status.return_value = RepositoryStatus(
        current_branch=context.branch_name,
        is_dirty=True,
        staged_files=["file.py"],
        unstaged_files=[],
        untracked_files=[],
        ahead_count=0,
        behind_count=0,
    )

    # Mock successful commit but failed push
    mock_repository.commit.return_value = "abc123"
    mock_repository.push.side_effect = Exception("Push failed: authentication required")

    result = await workspace_router.finalize_workspace(
        context=context,
        project=sample_project,
        execution_result={"agent_id": "developer"},
        repository_path=repository_path,
    )

    assert result.success is False
    assert "authentication required" in result.reason.lower()


# ============================================================================
# Negative Tests: Edge Cases
# ============================================================================


# NOTE: This test was removed because it tests mock behavior, not actual service behavior.
# The mock repository adapter doesn't validate paths. This would need a real
# repository adapter to test properly, which is out of scope for integration tests.


@pytest.mark.asyncio
async def test_prepare_workspace_checkout_fails(
    workspace_router, code_work_item, developer_agent, sample_project,
    mock_repository, repository_path
):
    """Test workspace preparation when checkout fails."""
    context = await workspace_router.route_workspace(
        work_item=code_work_item,
        agent=developer_agent,
        project=sample_project,
    )

    # Mock existing branch but checkout fails
    mock_repository.list_branches.return_value = [context.branch_name]
    mock_repository.checkout.side_effect = Exception("Checkout failed: uncommitted changes")

    result = await workspace_router.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=code_work_item,
        repository_path=repository_path,
    )

    assert result.success is False
    assert "uncommitted changes" in result.reason.lower()
