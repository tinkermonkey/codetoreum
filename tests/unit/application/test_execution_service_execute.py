"""Unit tests for the new ``ExecutionService.execute()`` dispatch path (Phase D4).

Covers the keystone of the coding-agent port redesign: a single entry
point that delegates to :class:`ICodingAgent`, captures the
:class:`CodingAgentResult`, commits the workspace on success, and
emits the appropriate domain events via the AgentExecution lifecycle
methods.

The legacy ``execute_with_container`` / ``execute_with_llm`` methods
remain on ``ExecutionService`` for the D4 bridge state but D5 deletes
them; this file exercises only the new path.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.application.execution_service import (
    ExecutionFailureReason,
    ExecutionService,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType, CommitPolicy
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.domain.events.execution_events import (
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
)
from codetoreum.domain.value_objects import ExecutionContext
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def event_store() -> InMemoryEventStore:
    return InMemoryEventStore()


@pytest.fixture
def coding_agent_mock() -> AsyncMock:
    """A :class:`ICodingAgent`-shaped AsyncMock.

    Default ``execute`` returns a success :class:`CodingAgentResult`.
    Tests override ``return_value`` / ``side_effect`` as needed.
    """
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
) -> ExecutionService:
    return ExecutionService(
        coding_agent=coding_agent_mock,
        event_store=event_store,
    )


@pytest.fixture
def sample_agent() -> Agent:
    return Agent.create(
        name="test-agent",
        display_name="Test Agent",
        agent_type=AgentType.DEVELOPER,
        role_description="Test role",
        capabilities={"python": AgentCapability(skill="python", proficiency=0.9, description="Python")},
        makes_code_changes=True,
        invocation=_test_inv(model="claude-sonnet-4-5-20250929", timeout_seconds=300, requires_docker=True),
    )


@pytest.fixture
def sample_work_item() -> WorkItem:
    return WorkItem.create(
        title="Test",
        description="Test description",
        project_id="proj-1",
        priority=WorkItemPriority.MEDIUM,
    )


@pytest.fixture
def sample_workspace_context(sample_work_item: WorkItem) -> WorkspaceContext:
    return WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id=sample_work_item.id,
        branch_name="feature/test",
        create_pr=False,
    )


@pytest.fixture
def sample_execution_context(sample_agent: Agent, sample_work_item: WorkItem) -> ExecutionContext:
    return ExecutionContext(
        work_item_id=sample_work_item.id,
        workflow_id="wf-1",
        stage_name="stage-1",
        agent_id=sample_agent.id,
        model=sample_agent.invocation.model,
        timeout_seconds=300,
        workspace_type="issue",
        branch_name="feature/test",
        discussion_id=None,
        project_id="proj-1",
        repository_url="https://github.com/test/repo",
        tech_stack=("python",),
        filesystem_write_allowed=True,
        can_make_commits=False,  # default: skip commit in this fixture
        requires_docker=False,
        mcp_servers=(),
        commit_policy=CommitPolicy.NONE,
        repository_path=None,
        metadata={},
    )


@pytest.fixture
def sample_execution(sample_agent: Agent, sample_work_item: WorkItem) -> AgentExecution:
    """Real :class:`AgentExecution` advanced to RUNNING.

    The new path mutates the execution via ``complete()`` / ``fail()``
    which require the RUNNING state, so we use a real domain object
    rather than a MagicMock.
    """
    exec_ = AgentExecution.create(
        agent_id=sample_agent.id,
        work_item_id=sample_work_item.id,
        workflow_id="wf-1",
        stage_name="stage-1",
        prompt="prompt",
        model=sample_agent.invocation.model,
    )
    exec_.clear_events()
    exec_.start(container_name=None)
    exec_.clear_events()
    return exec_


@pytest.fixture
def default_options() -> CodingAgentInvocationOptions:
    return CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.HOST,
        model="claude-sonnet-4-5-20250929",
        timeout_seconds=300,
        cost_limit_usd=None,
        mode_config={},
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_happy_path_delegates_to_coding_agent_and_completes(
    execution_service: ExecutionService,
    coding_agent_mock: AsyncMock,
    sample_execution: AgentExecution,
    sample_execution_context: ExecutionContext,
    sample_workspace_context: WorkspaceContext,
    default_options: CodingAgentInvocationOptions,
    event_store: InMemoryEventStore,
) -> None:
    """Success path: coding_agent.execute() is called with the right args,
    AgentExecution moves to COMPLETED, ExecutionCompletedEvent persisted."""
    result = await execution_service.execute(
        sample_execution,
        sample_execution_context,
        sample_workspace_context,
        default_options,
    )

    # Coding agent received the right inputs
    coding_agent_mock.execute.assert_awaited_once()
    args, kwargs = coding_agent_mock.execute.await_args
    # Positional-only call shape per ExecutionService.execute() implementation
    assert args[0] is sample_execution
    assert args[1] is sample_workspace_context
    assert args[2] is default_options
    assert kwargs == {}

    # Result reports success
    assert result.success is True
    assert result.execution is sample_execution
    assert result.commit_sha is None  # commit policy NONE
    assert result.branch is None
    assert result.failure_reason is None

    # Execution lifecycle advanced to COMPLETED
    assert sample_execution.status == ExecutionStatus.COMPLETED
    assert sample_execution.input_tokens == 123
    assert sample_execution.output_tokens == 456
    assert sample_execution.output == "agent finished"

    # ExecutionCompletedEvent persisted to event store
    events = await event_store.get_events(sample_execution.id)
    completion_events = [e for e in events if isinstance(e, ExecutionCompletedEvent)]
    assert len(completion_events) == 1
    completed = completion_events[0]
    assert completed.execution_id == sample_execution.id
    assert completed.input_tokens == 123
    assert completed.output_tokens == 456


# ---------------------------------------------------------------------------
# Failure path: coding_agent reports failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_failure_result_emits_failed_event_and_skips_commit(
    execution_service: ExecutionService,
    coding_agent_mock: AsyncMock,
    sample_execution: AgentExecution,
    sample_execution_context: ExecutionContext,
    sample_workspace_context: WorkspaceContext,
    default_options: CodingAgentInvocationOptions,
    event_store: InMemoryEventStore,
) -> None:
    """Failure path: success=False — ExecutionFailedEvent persisted; no commit."""
    coding_agent_mock.execute.return_value = CodingAgentResult(
        success=False,
        summary_text="",
        total_cost_usd=Decimal("0.05"),
        total_input_tokens=10,
        total_output_tokens=0,
        tool_call_count=0,
        duration_ms=500,
        error_summary="agent encountered a rate limit",
    )

    result = await execution_service.execute(
        sample_execution,
        sample_execution_context,
        sample_workspace_context,
        default_options,
    )

    assert result.success is False
    assert result.failure_reason == ExecutionFailureReason.RATE_LIMIT
    assert "rate limit" in (result.error or "").lower()
    assert sample_execution.status == ExecutionStatus.FAILED

    events = await event_store.get_events(sample_execution.id)
    failed_events = [e for e in events if isinstance(e, ExecutionFailedEvent)]
    assert len(failed_events) == 1
    completion_events = [e for e in events if isinstance(e, ExecutionCompletedEvent)]
    assert completion_events == []


# ---------------------------------------------------------------------------
# Failure path: coding_agent raises
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_coding_agent_exception_is_translated_to_failed_result(
    execution_service: ExecutionService,
    coding_agent_mock: AsyncMock,
    sample_execution: AgentExecution,
    sample_execution_context: ExecutionContext,
    sample_workspace_context: WorkspaceContext,
    default_options: CodingAgentInvocationOptions,
    event_store: InMemoryEventStore,
) -> None:
    """When the coding agent raises, the service translates to a failure
    result so the workflow doesn't strand in RUNNING."""
    coding_agent_mock.execute.side_effect = RuntimeError("adapter exploded")

    result = await execution_service.execute(
        sample_execution,
        sample_execution_context,
        sample_workspace_context,
        default_options,
    )

    assert result.success is False
    assert "adapter exploded" in (result.error or "")
    assert sample_execution.status == ExecutionStatus.FAILED

    events = await event_store.get_events(sample_execution.id)
    assert any(isinstance(e, ExecutionFailedEvent) for e in events)


# ---------------------------------------------------------------------------
# Regression: untracked (new) files must be staged + committed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_workspace_stages_untracked_files(
    coding_agent_mock: AsyncMock,
    sample_execution: AgentExecution,
    sample_execution_context: ExecutionContext,
    event_store: InMemoryEventStore,
    tmp_path,
) -> None:
    """Agent-created NEW (untracked) files must be staged and committed.

    Claude Code creates new files; _commit_workspace previously staged only
    ``unstaged_files`` (modified-tracked), so a new-file-only run staged
    nothing and ``git commit`` failed with "nothing to commit". The fix adds
    ``untracked_files`` to VCSStatus and stages unstaged + untracked together.
    """
    from dataclasses import replace

    from codetoreum.ports.output.version_control_service import VCSStatus

    new_file = "rounds/tests/core/test_fingerprint.py"
    vcs = AsyncMock()
    vcs.status = AsyncMock(
        return_value=VCSStatus(
            is_dirty=True,
            staged_files=(),
            unstaged_files=(),
            untracked_files=(new_file,),
        )
    )
    vcs.commit = AsyncMock(return_value="abc123")
    vcs.push = AsyncMock()

    service = ExecutionService(
        coding_agent=coding_agent_mock,
        event_store=event_store,
        vcs=vcs,
    )

    ctx = replace(
        sample_execution_context,
        commit_policy=CommitPolicy.ON_SUCCESS,
        can_make_commits=True,
        repository_path=str(tmp_path),
        branch_name="feature/test",
    )

    commit_sha, branch = await service._commit_workspace(ctx, sample_execution)

    vcs.commit.assert_awaited_once()
    _, kwargs = vcs.commit.await_args
    assert new_file in kwargs["files"], f"untracked file not staged for commit; files={kwargs.get('files')!r}"
    assert commit_sha == "abc123"
    assert branch == "feature/test"
    vcs.push.assert_awaited_once()
