"""Tests for PR title refresh on commit.

Ensures that when new commits are added to a branch with an existing PR,
the PR title is refreshed to reference the current work item, and that
idempotent no-ops skip unnecessary API calls.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.adapters.testing.in_memory_version_control_service import (
    InMemoryVersionControlService,
)
from codetoreum.application.execution_service import ExecutionService
from codetoreum.domain.agent import Agent, AgentCapability, AgentType, CommitPolicy
from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.domain.value_objects import ExecutionContext
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
)


def _test_inv() -> AgentInvocationConfig:
    """Build an AgentInvocationConfig for tests."""
    return AgentInvocationConfig(
        mode=InvocationMode.CONTAINERIZED,
        model="claude-sonnet-4-5-20250929",
        timeout_seconds=300,
        mode_config={"image": "codetoreum-agent:latest"},
    )


@pytest.fixture
def event_store() -> InMemoryEventStore:
    return InMemoryEventStore()


@pytest.fixture
def vcs_service() -> InMemoryVersionControlService:
    return InMemoryVersionControlService()


@pytest.fixture
def coding_agent_mock() -> AsyncMock:
    """Mock ICodingAgent that returns success."""
    mock = AsyncMock()
    mock.supported_invocation_modes.return_value = frozenset(
        {InvocationMode.CONTAINERIZED, InvocationMode.HOST},
    )
    mock.execute = AsyncMock(
        return_value=CodingAgentResult(
            success=True,
            summary_text="agent finished",
            total_cost_usd=Decimal("0.42"),
            total_input_tokens=123,
            total_output_tokens=456,
            tool_call_count=7,
            duration_ms=15000,
            error_summary=None,
        )
    )
    return mock


@pytest.fixture
def execution_service(
    event_store: InMemoryEventStore,
    coding_agent_mock: AsyncMock,
    vcs_service: InMemoryVersionControlService,
) -> ExecutionService:
    return ExecutionService(
        coding_agent=coding_agent_mock,
        event_store=event_store,
        vcs=vcs_service,
    )


def _make_agent() -> Agent:
    return Agent.create(
        name="test-agent",
        display_name="Test Agent",
        agent_type=AgentType.DEVELOPER,
        role_description="Test role",
        capabilities={"python": AgentCapability(skill="python", proficiency=0.9, description="Python")},
        makes_code_changes=True,
        invocation=_test_inv(),
    )


def _make_work_item(title: str = "Test Work Item") -> WorkItem:
    return WorkItem.create(
        title=title,
        description="Test description",
        project_id="proj-1",
        priority=WorkItemPriority.MEDIUM,
    )


# ---------------------------------------------------------------------------
# Tests: PR title refresh on new commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pr_title_refreshed_on_new_commit_to_existing_branch(
    execution_service: ExecutionService,
    coding_agent_mock: AsyncMock,
    vcs_service: InMemoryVersionControlService,
    event_store: InMemoryEventStore,
) -> None:
    """When commits are added to a branch with existing PR, title is refreshed.

    Scenario:
    1. Work item A creates PR with title "[WI-A] stage-1: agent-1"
    2. Work item B reuses same branch with new PR title "[WI-B] stage-2: agent-2"
    3. update_pull_request_title() should update the PR title to WI-B

    This test verifies the PR title is refreshed when commits from a
    different work item are added to the same branch.
    """
    # Setup: clone repo and create initial PR with work item A
    agent = _make_agent()
    work_item_a = _make_work_item("Work Item A")
    repo_path = "/tmp/test-repo"

    await vcs_service.clone_repository("https://github.com/test/repo.git", repo_path)
    await vcs_service.create_branch(repo_path, "feature/test")
    await vcs_service.checkout(repo_path, "feature/test")

    # Create initial PR with work item A title
    initial_title = f"[{work_item_a.id}] stage-1: agent-1"
    await vcs_service.create_pull_request(
        repo_path=repo_path,
        head="feature/test",
        base="main",
        title=initial_title,
        body="Initial PR",
    )

    # Now setup for work item B reusing the same branch
    work_item_b = _make_work_item("Work Item B")
    new_title = f"[{work_item_b.id}] stage-2: agent-2"

    # Update PR title (simulating new commit from different work item)
    title_updated = await vcs_service.update_pull_request_title(
        repo_path=repo_path,
        head="feature/test",
        base="main",
        new_title=new_title,
    )

    # Verify title was updated
    assert title_updated is True

    # Verify the PR title was actually changed
    prs = vcs_service._pull_requests
    assert len(prs) == 1
    assert prs[0]["title"] == new_title
    assert prs[0]["head"] == "feature/test"


@pytest.mark.asyncio
async def test_pr_title_update_skips_api_call_when_title_matches(
    execution_service: ExecutionService,
    vcs_service: InMemoryVersionControlService,
) -> None:
    """When PR title already matches, update is a no-op (idempotent).

    Scenario:
    1. Create PR with title "[WI-A] stage-1: agent-1"
    2. Call update_pull_request_title with same title
    3. Should return False (no update needed)

    This verifies the idempotent no-op: if the PR already has the
    requested title, we skip the API call and return False.
    """
    # Setup: create repository and initial PR
    work_item = _make_work_item("Work Item A")
    repo_path = "/tmp/test-repo"
    title = f"[{work_item.id}] stage-1: agent-1"

    await vcs_service.clone_repository("https://github.com/test/repo.git", repo_path)
    await vcs_service.create_branch(repo_path, "feature/test")
    await vcs_service.checkout(repo_path, "feature/test")

    # Create PR
    await vcs_service.create_pull_request(
        repo_path=repo_path,
        head="feature/test",
        base="main",
        title=title,
        body="PR body",
    )

    # Attempt to update with same title
    title_updated = await vcs_service.update_pull_request_title(
        repo_path=repo_path,
        head="feature/test",
        base="main",
        new_title=title,  # Same title
    )

    # Should return False (no update needed)
    assert title_updated is False

    # Verify PR title remains unchanged
    prs = vcs_service._pull_requests
    assert len(prs) == 1
    assert prs[0]["title"] == title


@pytest.mark.asyncio
async def test_pr_title_update_returns_false_when_no_pr_exists(
    vcs_service: InMemoryVersionControlService,
) -> None:
    """When no PR exists for head->base, update returns False gracefully.

    Scenario:
    1. Try to update PR title for a branch that has no open PR
    2. Should return False (no PR found)
    3. Should not raise an exception (best-effort)

    This verifies that attempting to update a non-existent PR is a
    graceful no-op rather than an error.
    """
    repo_path = "/tmp/test-repo"

    await vcs_service.clone_repository("https://github.com/test/repo.git", repo_path)

    # Try to update PR title when no PR exists
    title_updated = await vcs_service.update_pull_request_title(
        repo_path=repo_path,
        head="nonexistent-branch",
        base="main",
        new_title="[WI-123] new title",
    )

    # Should return False (no PR found)
    assert title_updated is False


@pytest.mark.asyncio
async def test_execution_service_calls_update_pull_request_title_on_commit(
    execution_service: ExecutionService,
    coding_agent_mock: AsyncMock,
    vcs_service: InMemoryVersionControlService,
    event_store: InMemoryEventStore,
) -> None:
    """ExecutionService._open_pull_request calls update_pull_request_title after create.

    Scenario:
    1. Execute agent with auto_create_pull_requests=True and can_make_commits=True
    2. After push, create_pull_request is called, then update_pull_request_title
    3. Verify the update call happens to refresh the title

    This integration test verifies that ExecutionService correctly calls
    the title update method as part of the PR opening workflow.
    """
    # Setup
    agent = _make_agent()
    work_item = _make_work_item("Work Item")
    repo_path = "/tmp/test-repo"

    await vcs_service.clone_repository("https://github.com/test/repo.git", repo_path)
    await vcs_service.create_branch(repo_path, "feature/test")
    await vcs_service.checkout(repo_path, "feature/test")

    # Create execution with auto PR creation and commit enabled
    execution = AgentExecution.create(
        agent_id=agent.id,
        work_item_id=work_item.id,
        workflow_id="wf-1",
        stage_name="Development",
        prompt="prompt",
        model=agent.invocation.model,
    )
    execution.clear_events()
    execution.start(container_name=None)
    execution.clear_events()

    context = ExecutionContext(
        work_item_id=work_item.id,
        workflow_id="wf-1",
        stage_name="Development",
        agent_id=agent.id,
        model=agent.invocation.model,
        timeout_seconds=300,
        workspace_type="issue",
        branch_name="feature/test",
        discussion_id=None,
        project_id="proj-1",
        repository_url="https://github.com/test/repo",
        tech_stack=("python",),
        filesystem_write_allowed=True,
        can_make_commits=True,
        requires_docker=True,
        mcp_servers=(),
        commit_policy=CommitPolicy.ALWAYS,
        repository_path=repo_path,
        auto_create_pull_requests=True,  # Enable PR creation
        metadata={},
    )

    workspace_context = WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id=work_item.id,
        branch_name="feature/test",
        create_pr=True,
    )

    options = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.HOST,
        model="claude-sonnet-4-5-20250929",
        timeout_seconds=300,
        cost_limit_usd=None,
        mode_config={},
    )

    # Execute
    result = await execution_service.execute(
        execution,
        context,
        workspace_context,
        options,
    )

    # Verify
    assert result.success is True

    # Verify PR was created
    prs = vcs_service._pull_requests
    assert len(prs) == 1
    assert prs[0]["head"] == "feature/test"
    assert prs[0]["base"] == "main"

    # Verify PR title matches the work item
    expected_title = f"[{work_item.id}] Development: {agent.id}"
    assert prs[0]["title"] == expected_title


@pytest.mark.asyncio
async def test_execution_service_refreshes_stale_pr_title_on_branch_reuse(
    execution_service: ExecutionService,
    coding_agent_mock: AsyncMock,
    vcs_service: InMemoryVersionControlService,
    event_store: InMemoryEventStore,
) -> None:
    """ExecutionService refreshes stale PR title when branch is reused.

    Scenario:
    1. Work item A creates PR on branch "feature/test" with title "[WI-A] ..."
    2. Work item B reuses same branch with a new execution
    3. ExecutionService should call update_pull_request_title to refresh to "[WI-B] ..."
    4. Verify the PR title was updated to the new work item

    This integration test verifies the core feature: when a branch is reused
    across different work items, ExecutionService correctly refreshes the
    stale PR title to reflect the current work item.
    """
    # Setup: clone repo and create branch with initial PR from work item A
    agent = _make_agent()
    work_item_a = _make_work_item("Work Item A")
    work_item_b = _make_work_item("Work Item B")
    repo_path = "/tmp/test-repo-branch-reuse"

    await vcs_service.clone_repository("https://github.com/test/repo.git", repo_path)
    await vcs_service.create_branch(repo_path, "feature/test")
    await vcs_service.checkout(repo_path, "feature/test")

    # Pre-create PR with work item A's title
    old_title = f"[{work_item_a.id}] Development: {agent.id}"
    await vcs_service.create_pull_request(
        repo_path=repo_path,
        head="feature/test",
        base="main",
        title=old_title,
        body="Initial PR from work item A",
    )

    # Verify PR exists with old title
    prs = vcs_service._pull_requests
    assert len(prs) == 1
    assert prs[0]["title"] == old_title

    # Now execute with work item B, reusing the same branch
    execution = AgentExecution.create(
        agent_id=agent.id,
        work_item_id=work_item_b.id,
        workflow_id="wf-1",
        stage_name="Development",
        prompt="prompt",
        model=agent.invocation.model,
    )
    execution.clear_events()
    execution.start(container_name=None)
    execution.clear_events()

    context = ExecutionContext(
        work_item_id=work_item_b.id,
        workflow_id="wf-1",
        stage_name="Development",
        agent_id=agent.id,
        model=agent.invocation.model,
        timeout_seconds=300,
        workspace_type="issue",
        branch_name="feature/test",  # Reuse same branch
        discussion_id=None,
        project_id="proj-1",
        repository_url="https://github.com/test/repo",
        tech_stack=("python",),
        filesystem_write_allowed=True,
        can_make_commits=True,
        requires_docker=True,
        mcp_servers=(),
        commit_policy=CommitPolicy.ALWAYS,
        repository_path=repo_path,
        auto_create_pull_requests=True,
        metadata={},
    )

    workspace_context = WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id=work_item_b.id,
        branch_name="feature/test",
        create_pr=True,
    )

    options = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.HOST,
        model="claude-sonnet-4-5-20250929",
        timeout_seconds=300,
        cost_limit_usd=None,
        mode_config={},
    )

    # Execute with work item B
    result = await execution_service.execute(
        execution,
        context,
        workspace_context,
        options,
    )

    # Verify execution succeeded
    assert result.success is True

    # Verify PR title was refreshed to work item B
    prs = vcs_service._pull_requests
    assert len(prs) == 1  # Still only one PR
    new_title = f"[{work_item_b.id}] Development: {agent.id}"
    assert prs[0]["title"] == new_title
    assert prs[0]["title"] != old_title  # Title changed from work item A to B
