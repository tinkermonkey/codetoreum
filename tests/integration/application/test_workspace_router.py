"""Integration tests for WorkspaceRouter."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.application.workspace_router import (
    WorkspaceRouter,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.project_context import ProjectContext
from codetoreum.domain.types import BranchName
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.domain.workspace_context import WorkspaceType
from codetoreum.ports.exceptions import ExternalServiceError
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
    repo.status = AsyncMock(
        return_value=RepositoryStatus(
            current_branch=BranchName("main"),
            is_dirty=False,
            staged_files=(),
            unstaged_files=(),
            untracked_files=(),
            ahead_count=0,
            behind_count=0,
        )
    )

    return repo


@pytest.fixture
def mock_container():
    """Create mock container adapter."""
    container = AsyncMock()
    return container


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
        current_column=None,
        entered_column_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
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
        current_column=None,
        entered_column_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
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
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
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
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
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
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def repository_path(tmp_path):
    """Create temporary repository path for testing."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()
    return str(repo_dir)


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
async def test_route_workspace_analyst_agent(workspace_router, discussion_work_item, analyst_agent, sample_project):
    """Test routing to discussion workspace when agent doesn't make code changes."""
    # Analyst agent should work on discussion work items
    context = await workspace_router.route_workspace(
        work_item=discussion_work_item,
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
async def test_prepare_workspace_new_branch(
    workspace_router,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_repository,
    repository_path,
):
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
        repository_path=repository_path,
    )

    # Assert
    assert result.success is True
    assert result.metadata["branch_action"] == "create_new"
    mock_repository.create_branch.assert_called_once()
    mock_repository.checkout.assert_called_once()
    mock_repository.pull.assert_called_once()


@pytest.mark.asyncio
async def test_prepare_workspace_existing_branch(
    workspace_router,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_repository,
    repository_path,
):
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
        repository_path=repository_path,
    )

    # Assert
    assert result.success is True
    assert result.metadata["branch_action"] == "checkout_existing"
    mock_repository.create_branch.assert_not_called()
    mock_repository.checkout.assert_called_once()


@pytest.mark.asyncio
async def test_prepare_workspace_discussion(
    workspace_router, discussion_work_item, analyst_agent, sample_project, repository_path
):
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
        repository_path=repository_path,
    )

    # Assert
    assert result.success is True
    assert "branch_action" not in result.metadata


# ============================================================================
# Tests: Workspace Finalization
# ============================================================================


@pytest.mark.asyncio
async def test_finalize_workspace_with_changes(
    workspace_router,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_repository,
    repository_path,
):
    """Test finalizing workspace cleans up branch cache (commit/push are now in ExecutionService)."""
    # Arrange
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
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
        repository_path=repository_path,
    )

    # Assert — finalize_workspace is now cleanup-only; commit/push happen in ExecutionService
    assert result.success is True
    assert result.commit_sha is None
    mock_repository.commit.assert_not_called()
    mock_repository.push.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_workspace_no_changes(
    workspace_router,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_repository,
    repository_path,
):
    """Test finalizing workspace with no changes."""
    # Arrange
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Mock repository status without changes
    mock_repository.status.return_value = RepositoryStatus(
        current_branch=BranchName(context.branch_name),
        is_dirty=False,
        staged_files=(),
        unstaged_files=(),
        untracked_files=(),
        ahead_count=0,
        behind_count=0,
    )

    execution_result = {"agent_id": "developer-agent"}

    # Act
    result = await workspace_router.finalize_workspace(
        context=context,
        project=sample_project,
        execution_result=execution_result,
        repository_path=repository_path,
    )

    # Assert
    assert result.success is True
    assert result.commit_sha is None
    mock_repository.commit.assert_not_called()
    mock_repository.push.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_workspace_discussion(
    workspace_router, discussion_work_item, analyst_agent, sample_project, repository_path
):
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
        repository_path=repository_path,
    )

    # Assert
    assert result.success is True
    assert result.commit_sha is None


# ============================================================================
# Tests: Container Environment & Volumes
# ============================================================================


@pytest.mark.asyncio
async def test_prepare_container_environment(workspace_router, sample_work_item, sample_agent, sample_project):
    """Test environment variable preparation for containers."""
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    env_vars = await workspace_router.prepare_container_environment(
        context=context,
        project=sample_project,
        agent=sample_agent,
    )

    assert env_vars["CODETOREUM_PROJECT_ID"] == "test-project"
    assert env_vars["CODETOREUM_WORK_ITEM_ID"] == "work-item-1"
    assert env_vars["CODETOREUM_WORKSPACE_TYPE"] == "issue"
    assert env_vars["CODETOREUM_AGENT_ID"] == "developer-agent"
    assert env_vars["ENV"] == "test"  # From project env vars
    # Git identity env vars (replaces .gitconfig bind mount for DinD compatibility)
    assert env_vars["GIT_AUTHOR_NAME"] == "Codetoreum"
    assert env_vars["GIT_AUTHOR_EMAIL"] == "noreply@codetoreum.ai"
    assert env_vars["GIT_COMMITTER_NAME"] == "Codetoreum"
    assert env_vars["GIT_COMMITTER_EMAIL"] == "noreply@codetoreum.ai"


@pytest.mark.asyncio
async def test_prepare_container_volumes_read_write(
    workspace_router, sample_work_item, sample_agent, sample_project, repository_path
):
    """Test volume mounts for code-changing agents."""
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    volumes = workspace_router.prepare_container_volumes(
        context=context,
        project=sample_project,
        repository_path=repository_path,
    )

    # Should have read-write mount
    assert any(":rw" in v for v in volumes.values())


@pytest.mark.asyncio
async def test_prepare_container_volumes_read_only(
    workspace_router, discussion_work_item, analyst_agent, sample_project, repository_path
):
    """Test volume mounts for non-code-changing agents."""
    context = await workspace_router.route_workspace(
        work_item=discussion_work_item,
        agent=analyst_agent,
        project=sample_project,
    )

    volumes = workspace_router.prepare_container_volumes(
        context=context,
        project=sample_project,
        repository_path=repository_path,
    )

    # Should have read-only mount
    assert any(":ro" in v for v in volumes.values())


# ============================================================================
# Tests: Branch Resolution Service Integration
# ============================================================================


@pytest.fixture
def mock_branch_resolution_service():
    """Create mock branch resolution service."""
    from codetoreum.adapters.testing import MockBranchResolutionAdapter
    from codetoreum.domain.value_objects import BranchResolution

    adapter = MockBranchResolutionAdapter()

    # Configure default behavior: create new branches
    default_resolution = BranchResolution(
        action="create",
        branch_name="feature/issue-default",
        confidence=1.0,
        reason="Default resolution for unconfigured cases",
        resolution_strategy="new",
        parent_issue_id=None,
    )
    adapter.set_default_resolution(default_resolution)

    return adapter


@pytest.fixture
def workspace_router_with_resolution(mock_repository, mock_container, mock_event_store, mock_branch_resolution_service):
    """Create WorkspaceRouter with branch resolution service."""
    return WorkspaceRouter(
        repository=mock_repository,
        container=mock_container,
        event_store=mock_event_store,
        branch_resolution_service=mock_branch_resolution_service,
    )


@pytest.mark.asyncio
async def test_route_workspace_with_branch_resolution_create(
    workspace_router_with_resolution,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_branch_resolution_service,
):
    """Test routing with branch resolution service returning create action."""
    from codetoreum.domain.value_objects import BranchResolution

    # Configure resolution service to create new branch
    resolution = BranchResolution(
        action="create",
        branch_name="feature/issue-123-auth-flow",
        confidence=1.0,
        reason="No existing branch found, creating new",
        resolution_strategy="new",
        parent_issue_id=None,
    )
    mock_branch_resolution_service.configure_resolution(sample_project.id, sample_work_item.id, resolution)

    # Act
    context = await workspace_router_with_resolution.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Assert - route_workspace returns generated name, resolution happens in prepare_workspace
    assert context.workspace_type.value == "issue"
    # Branch name should be generated from work item title
    assert "issue-123-" in context.branch_name
    assert context.create_pr is True


@pytest.mark.asyncio
async def test_route_workspace_with_branch_resolution_reuse(
    workspace_router_with_resolution,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_branch_resolution_service,
):
    """Test routing with branch resolution service returning reuse action."""
    from codetoreum.domain.value_objects import BranchResolution

    # Configure resolution service to reuse parent's branch
    parent_issue_id = "100"
    resolution = BranchResolution(
        action="reuse",
        branch_name="feature/issue-100-parent-task",
        confidence=0.95,
        reason="Parent issue has existing branch",
        resolution_strategy="parent_issue",
        parent_issue_id=parent_issue_id,
    )
    mock_branch_resolution_service.configure_resolution(sample_project.id, sample_work_item.id, resolution)

    # Act
    context = await workspace_router_with_resolution.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Assert - route_workspace returns generated name, resolution happens in prepare_workspace
    assert context.workspace_type.value == "issue"
    # Branch name should be generated from work item title
    assert "issue-123-" in context.branch_name
    assert context.create_pr is True


@pytest.mark.asyncio
async def test_prepare_workspace_with_branch_resolution_create(
    workspace_router_with_resolution,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_repository,
    mock_branch_resolution_service,
    repository_path,
):
    """Test prepare_workspace honors resolution service create decision."""
    from codetoreum.domain.value_objects import BranchResolution

    # Configure resolution service to create new branch
    resolution = BranchResolution(
        action="create",
        branch_name="feature/issue-123-new-feature",
        confidence=1.0,
        reason="No existing branch found",
        resolution_strategy="new",
        parent_issue_id=None,
    )
    mock_branch_resolution_service.configure_resolution(sample_project.id, sample_work_item.id, resolution)

    # Mock list_branches to return no existing branches
    mock_repository.list_branches.return_value = []

    # Route the workspace to populate the branch resolution cache
    context = await workspace_router_with_resolution.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Act - prepare the workspace
    result = await workspace_router_with_resolution.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=sample_work_item,
        repository_path=repository_path,
    )

    # Assert
    assert result.success is True
    assert result.metadata["branch_action"] == "create_resolved"
    assert result.metadata["resolution_strategy"] == "new"
    mock_repository.create_branch.assert_called_once()
    mock_repository.checkout.assert_called()


@pytest.mark.asyncio
async def test_prepare_workspace_with_branch_resolution_reuse(
    workspace_router_with_resolution,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_repository,
    mock_branch_resolution_service,
    repository_path,
):
    """Test prepare_workspace honors resolution service reuse decision."""
    from codetoreum.domain.value_objects import BranchResolution

    # Configure resolution service to reuse parent's branch
    parent_branch = "feature/issue-100-parent-task"
    resolution = BranchResolution(
        action="reuse",
        branch_name=parent_branch,
        confidence=0.95,
        reason="Parent issue has existing branch",
        resolution_strategy="parent_issue",
        parent_issue_id="100",
    )
    mock_branch_resolution_service.configure_resolution(sample_project.id, sample_work_item.id, resolution)

    # Route the workspace to populate the branch resolution cache
    context = await workspace_router_with_resolution.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Act - prepare the workspace
    result = await workspace_router_with_resolution.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=sample_work_item,
        repository_path=repository_path,
    )

    # Assert - should reuse the parent's branch (no create_branch call)
    assert result.success is True
    assert result.metadata["branch_action"] == "reuse_resolved"
    assert result.metadata["resolution_strategy"] == "parent_issue"
    mock_repository.create_branch.assert_not_called()
    # Should call checkout to switch to the parent's branch
    mock_repository.checkout.assert_called()


@pytest.mark.asyncio
async def test_route_workspace_without_resolution_service_is_backward_compatible(
    workspace_router,
    sample_work_item,
    sample_agent,
    sample_project,
):
    """Test that WorkspaceRouter without resolution service preserves old behavior."""
    # workspace_router fixture doesn't have branch_resolution_service

    # Act
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Assert - should use generated branch name
    assert context.workspace_type.value == "issue"
    assert "issue-123-" in context.branch_name  # Generated from issue title
    assert context.create_pr is True


@pytest.mark.asyncio
async def test_prepare_workspace_without_resolution_service_uses_fallback_logic(
    workspace_router,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_repository,
    repository_path,
):
    """Test that prepare_workspace without resolution uses existence checking."""
    # Mock list_branches to return no branches
    mock_repository.list_branches.return_value = []

    # Route to get context with generated branch name
    context = await workspace_router.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Act - prepare workspace
    result = await workspace_router.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=sample_work_item,
        repository_path=repository_path,
    )

    # Assert - should use default logic (create because branch doesn't exist)
    assert result.success is True
    assert result.metadata["branch_action"] == "create_new"
    assert "resolution_strategy" not in result.metadata  # No resolution strategy recorded
    mock_repository.create_branch.assert_called_once()


@pytest.mark.asyncio
async def test_prepare_workspace_with_resolution_service_failure_falls_back(
    workspace_router_with_resolution,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_repository,
    mock_branch_resolution_service,
    repository_path,
    caplog,
):
    """Test that prepare_workspace falls back to default logic when resolution service fails."""
    # Configure resolution service to raise exception
    mock_branch_resolution_service.configure_to_raise(ExternalServiceError("branch_resolution", "Service unavailable"))

    # Mock list_branches to return no branches (for fallback logic)
    mock_repository.list_branches.return_value = []

    # Route to get context with generated branch name
    context = await workspace_router_with_resolution.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Act - prepare workspace
    result = await workspace_router_with_resolution.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=sample_work_item,
        repository_path=repository_path,
    )

    # Assert - should fall back to default logic (create because branch doesn't exist)
    assert result.success is True
    assert result.metadata["branch_action"] == "create_new"
    assert "resolution_strategy" not in result.metadata  # No resolution strategy recorded
    # Verify fallback metadata fields are recorded
    assert result.metadata.get("branch_resolution_fallback") is True
    assert "branch_resolution_fallback_reason" in result.metadata
    assert result.metadata["branch_resolution_fallback_reason"] != ""
    mock_repository.create_branch.assert_called_once()


# ============================================================================
# Tests: Finalization with Branch Resolution
# ============================================================================


@pytest.mark.asyncio
async def test_finalize_workspace_with_branch_resolution_reuse_pushes_resolved_branch(
    workspace_router_with_resolution,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_repository,
    mock_branch_resolution_service,
    repository_path,
):
    """Test finalize_workspace pushes to resolved branch when reusing parent's branch.

    Verifies that when branch resolution decides to reuse a parent's branch,
    finalize_workspace correctly pushes to the resolved branch name, not the
    placeholder name from context.branch_name.

    This test ensures:
    - prepare_workspace caches the resolved branch name ("feature/issue-100-parent-task")
    - finalize_workspace retrieves the cached resolved name for push operation
    - The push uses the actual resolved branch, not the placeholder from context
    """
    from codetoreum.domain.value_objects import BranchResolution

    # Configure resolution service to reuse parent's branch
    parent_branch = "feature/issue-100-parent-task"
    resolution = BranchResolution(
        action="reuse",
        branch_name=parent_branch,
        confidence=0.95,
        reason="Parent issue has existing branch",
        resolution_strategy="parent_issue",
        parent_issue_id="100",
    )
    mock_branch_resolution_service.configure_resolution(sample_project.id, sample_work_item.id, resolution)

    # Mock repository status with changes
    mock_repository.status.return_value = RepositoryStatus(
        current_branch=BranchName(parent_branch),  # Currently on parent's branch
        is_dirty=True,
        staged_files=("file1.py",),
        unstaged_files=(),
        untracked_files=(),
        ahead_count=0,
        behind_count=0,
    )

    # Route to get context with generated placeholder branch name
    context = await workspace_router_with_resolution.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Verify context has placeholder branch name (not the resolved parent branch)
    assert "issue-123-" in context.branch_name
    assert context.branch_name != parent_branch

    # Prepare workspace - this will cache the resolved branch name
    prep_result = await workspace_router_with_resolution.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=sample_work_item,
        repository_path=repository_path,
    )
    assert prep_result.success is True
    assert prep_result.metadata["branch_action"] == "reuse_resolved"
    # Verify resolved branch name is in metadata
    assert prep_result.metadata["resolved_branch_name"] == parent_branch

    # Execution result
    execution_result = {
        "agent_id": "developer-agent",
        "summary": "Completed parent task work",
    }

    # Finalize workspace - clears the resolution cache (commit/push now in ExecutionService)
    finalize_result = await workspace_router_with_resolution.finalize_workspace(
        context=context,
        project=sample_project,
        execution_result=execution_result,
        repository_path=repository_path,
    )

    # finalize_workspace is now cleanup-only; commit/push happen in ExecutionService
    assert finalize_result.success is True
    assert finalize_result.commit_sha is None
    mock_repository.commit.assert_not_called()
    mock_repository.push.assert_not_called()

    # prepare_workspace still resolves and surfaces the branch name correctly
    assert prep_result.metadata["resolved_branch_name"] == parent_branch


@pytest.mark.asyncio
async def test_finalize_workspace_with_branch_resolution_create_pushes_resolved_branch(
    workspace_router_with_resolution,
    sample_work_item,
    sample_agent,
    sample_project,
    mock_repository,
    mock_branch_resolution_service,
    repository_path,
):
    """Test finalize_workspace pushes to resolved branch when creating with different name.

    Verifies that when branch resolution decides to create a new branch with
    a different name than the generated placeholder, finalize_workspace correctly
    pushes to the resolved branch name.

    This test ensures:
    - prepare_workspace caches the resolved branch name ("feature/issue-123-auth-flow")
    - finalize_workspace retrieves the cached resolved name for push operation
    - The push uses the resolved name, even though context.branch_name is different
    """
    from codetoreum.domain.value_objects import BranchResolution

    # Configure resolution service to create with different name
    resolved_branch = "feature/issue-123-auth-flow"
    resolution = BranchResolution(
        action="create",
        branch_name=resolved_branch,
        confidence=1.0,
        reason="Creating new branch with optimized name",
        resolution_strategy="new",
        parent_issue_id=None,
    )
    mock_branch_resolution_service.configure_resolution(sample_project.id, sample_work_item.id, resolution)

    # Mock repository status with changes
    mock_repository.status.return_value = RepositoryStatus(
        current_branch=BranchName(resolved_branch),
        is_dirty=True,
        staged_files=("auth.py",),
        unstaged_files=(),
        untracked_files=(),
        ahead_count=0,
        behind_count=0,
    )

    # Mock list_branches to return no existing branches (so create will happen)
    mock_repository.list_branches.return_value = []

    # Route to get context with generated placeholder branch name
    context = await workspace_router_with_resolution.route_workspace(
        work_item=sample_work_item,
        agent=sample_agent,
        project=sample_project,
    )

    # Verify context has different placeholder branch name
    assert context.branch_name != resolved_branch

    # Prepare workspace - this will cache the resolved branch name
    prep_result = await workspace_router_with_resolution.prepare_workspace(
        context=context,
        project=sample_project,
        work_item=sample_work_item,
        repository_path=repository_path,
    )
    assert prep_result.success is True
    assert prep_result.metadata["branch_action"] == "create_resolved"
    # Verify resolved branch name is in metadata
    assert prep_result.metadata["resolved_branch_name"] == resolved_branch

    # Execution result
    execution_result = {
        "agent_id": "developer-agent",
        "summary": "Implemented authentication flow",
    }

    # Finalize workspace - clears the resolution cache (commit/push now in ExecutionService)
    finalize_result = await workspace_router_with_resolution.finalize_workspace(
        context=context,
        project=sample_project,
        execution_result=execution_result,
        repository_path=repository_path,
    )

    # finalize_workspace is now cleanup-only; commit/push happen in ExecutionService
    assert finalize_result.success is True
    assert finalize_result.commit_sha is None
    mock_repository.commit.assert_not_called()
    mock_repository.push.assert_not_called()

    # prepare_workspace still resolves and surfaces the branch name correctly
    assert prep_result.metadata["resolved_branch_name"] == resolved_branch
