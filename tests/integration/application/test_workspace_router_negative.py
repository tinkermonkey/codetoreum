"""Negative test cases for WorkspaceRouter."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.application.workspace_router import WorkspaceRouter
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus


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
    store = InMemoryEventStore()
    yield store
    store.clear()


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
        current_column=None,
        entered_column_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        completed_at=None,
    )


@pytest.fixture
def developer_agent():
    """Create developer agent that makes code changes."""
    return Agent(
        id="developer",
        name="developer",
        display_name="Developer",
        agent_type=AgentType.DEVELOPER,
        capabilities={"code_generation": AgentCapability(skill="code_generation", proficiency=0.9)},
        role_description="Develops code",
        max_retries=3,
        requires_dev_container=True,
        makes_code_changes=True,
        filesystem_write_allowed=True,
        mcp_servers=[],
        metadata={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        invocation=_test_inv(model="claude-sonnet-4-5", timeout_seconds=300, requires_docker=True),
        coding_agent="",
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
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def repository_path(tmp_path):
    """Create temporary repository path."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()
    return str(repo_dir)


# ============================================================================
# Negative Tests: Repository Operations
# ============================================================================


@pytest.mark.asyncio
async def test_prepare_workspace_branch_creation_fails(
    workspace_router,
    code_work_item,
    developer_agent,
    sample_project,
    mock_repository,
    repository_path,
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
    workspace_router,
    code_work_item,
    developer_agent,
    sample_project,
    mock_repository,
    repository_path,
):
    """Test finalize_workspace always succeeds — commit/push errors are now in ExecutionService.

    Commit and push were moved from WorkspaceRouter.finalize_workspace() to
    ExecutionService._commit_workspace() so that the commit happens synchronously
    before ExecutionCompleted fires.  finalize_workspace() is now cleanup-only.
    """
    context = await workspace_router.route_workspace(
        work_item=code_work_item,
        agent=developer_agent,
        project=sample_project,
    )

    # Even if the repository raises on commit, finalize_workspace doesn't call it
    mock_repository.commit.side_effect = Exception("Commit failed: merge conflict")

    result = await workspace_router.finalize_workspace(
        context=context,
        project=sample_project,
        execution_result={"agent_id": "developer"},
        repository_path=repository_path,
    )

    # finalize_workspace is cleanup-only — always succeeds, never calls commit
    assert result.success is True
    mock_repository.commit.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_workspace_push_fails(
    workspace_router,
    code_work_item,
    developer_agent,
    sample_project,
    mock_repository,
    repository_path,
):
    """Test finalize_workspace always succeeds — commit/push errors are now in ExecutionService.

    See test_finalize_workspace_commit_fails for background.
    """
    context = await workspace_router.route_workspace(
        work_item=code_work_item,
        agent=developer_agent,
        project=sample_project,
    )

    # Even if the repository raises on push, finalize_workspace doesn't call it
    mock_repository.push.side_effect = Exception("Push failed: authentication required")

    result = await workspace_router.finalize_workspace(
        context=context,
        project=sample_project,
        execution_result={"agent_id": "developer"},
        repository_path=repository_path,
    )

    # finalize_workspace is cleanup-only — always succeeds, never calls push
    assert result.success is True
    mock_repository.push.assert_not_called()


# ============================================================================
# Negative Tests: Edge Cases
# ============================================================================


# NOTE: This test was removed because it tests mock behavior, not actual service behavior.
# The mock repository adapter doesn't validate paths. This would need a real
# repository adapter to test properly, which is out of scope for integration tests.


@pytest.mark.asyncio
async def test_prepare_workspace_checkout_fails(
    workspace_router,
    code_work_item,
    developer_agent,
    sample_project,
    mock_repository,
    repository_path,
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
