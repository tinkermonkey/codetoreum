"""Unit tests for :class:`ClaudeCodeAdapter`.

The adapter is exercised against stubbed strategies, repository, and
prompt builder so the tests focus on the adapter's own contract:
mode validation, dispatch, prompt rendering, and result return.
"""

from __future__ import annotations

from collections.abc import Awaitable
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.secondary.claude_code.adapter import (
    ClaudeCodeAdapter,
    UnsupportedInvocationModeError,
)
from codetoreum.adapters.secondary.claude_code.strategies.base import (
    ClaudeInvocationStrategy,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.coding_agent_types import AgentInvocationConfig
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
    InvocationMode,
)
from codetoreum.ports.output.prompt_builder import (
    IPromptBuilder,
    StructuredPrompt,
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


class _RecordingStrategy(ClaudeInvocationStrategy):
    """Strategy stub that records its inputs and returns a canned result."""

    def __init__(self, result: CodingAgentResult | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result or CodingAgentResult(
            success=True,
            summary_text="stub",
            total_cost_usd=Decimal("0"),
            total_input_tokens=0,
            total_output_tokens=0,
            tool_call_count=0,
            duration_ms=1,
            error_summary=None,
        )

    async def execute(
        self,
        *,
        prompt_text: str,
        execution_id: str,
        workspace_context: WorkspaceContext,
        options: CodingAgentInvocationOptions,
        event_bus: EventBus,
        parser: Any,
        coding_agent_id: str,
    ) -> CodingAgentResult:
        self.calls.append(
            {
                "prompt_text": prompt_text,
                "execution_id": execution_id,
                "options": options,
                "coding_agent_id": coding_agent_id,
            },
        )
        return self._result


class _FixedPromptBuilder(IPromptBuilder):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def build(
        self,
        agent: Agent,
        work_item: WorkItem,
        workspace_context: WorkspaceContext,
        prior_outputs: tuple = (),
    ) -> StructuredPrompt:
        self.calls.append({"agent": agent, "work_item": work_item})
        return StructuredPrompt(
            role_description=f"Role: {agent.name}",
            task_description=work_item.title,
            work_item=work_item,
            workspace_context=workspace_context,
            instructions=("Do the thing.",),
            constraints=(),
            prior_outputs=prior_outputs,
        )


def _agent() -> Agent:
    return Agent.create(
        agent_type=AgentType.DEVELOPER,
        display_name="Senior Software Engineer",
        role_description="Implements features",
        name="senior_software_engineer",
        capabilities={"code_generation": AgentCapability(skill="code_generation", proficiency=0.9)},
        invocation=_test_inv(model="claude-sonnet-4-6", timeout_seconds=300, requires_docker=True),
    )


def _work_item() -> WorkItem:
    wi = WorkItem.create(
        title="Implement widget",
        description="Add the widget endpoint per #42.",
        project_id="proj-1",
        priority=WorkItemPriority.MEDIUM,
    )
    object.__setattr__(wi, "id", "wi-1")
    return wi


def _workspace_context() -> WorkspaceContext:
    return WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id="wi-1",
        branch_name="feature/widget",
    )


def _execution(agent_id: str, work_item_id: str) -> AgentExecution:
    return AgentExecution.create(
        agent_id=agent_id,
        work_item_id=work_item_id,
        workflow_id="wf-1",
        stage_name="implement",
        prompt="legacy-prompt-text-ignored",
        model="claude-sonnet-4-6",
    )


class _FakeCredentialProvider:
    async def get_credential(self, _key: str) -> str | None:
        return "secret"


def _build_adapter(
    *,
    container: object | None = None,
    prompt_builder: IPromptBuilder | None = None,
    strategies_override: dict[InvocationMode, ClaudeInvocationStrategy] | None = None,
) -> tuple[ClaudeCodeAdapter, dict[InvocationMode, _RecordingStrategy], _FixedPromptBuilder, AgentExecution, WorkItem]:
    builder = prompt_builder if prompt_builder is not None else _FixedPromptBuilder()
    agent = _agent()
    work_item = _work_item()
    agent_repo = AsyncMock()
    agent_repo.get_by_id.return_value = agent
    wi_service = AsyncMock()
    wi_service.get_work_item.return_value = work_item
    execution = _execution(agent.id, work_item.id)
    bus = EventBus()
    adapter = ClaudeCodeAdapter(
        prompt_builder=builder,
        event_bus=bus,
        credential_provider=_FakeCredentialProvider(),
        agent_repository=agent_repo,
        work_item_service=wi_service,
        container=container,  # type: ignore[arg-type]
    )

    # Replace the strategies the constructor built with recording stubs so
    # we can intercept dispatch.
    recorders: dict[InvocationMode, _RecordingStrategy] = {}
    if strategies_override is not None:
        adapter._strategies.host = strategies_override.get(InvocationMode.HOST)  # type: ignore[attr-defined]
        adapter._strategies.containerised = strategies_override.get(  # type: ignore[attr-defined]
            InvocationMode.CONTAINERIZED,
        )
        for mode, strat in strategies_override.items():
            if isinstance(strat, _RecordingStrategy):
                recorders[mode] = strat
    else:
        host_recorder = _RecordingStrategy()
        adapter._strategies.host = host_recorder  # type: ignore[attr-defined]
        recorders[InvocationMode.HOST] = host_recorder
        if container is not None:
            cont_recorder = _RecordingStrategy()
            adapter._strategies.containerised = cont_recorder  # type: ignore[attr-defined]
            recorders[InvocationMode.CONTAINERIZED] = cont_recorder

    return adapter, recorders, builder, execution, work_item


@pytest.mark.asyncio
async def test_supported_modes_host_only_when_no_container():
    adapter, _recorders, _builder, _exec, _wi = _build_adapter(container=None)
    assert adapter.supported_invocation_modes() == frozenset({InvocationMode.HOST})


@pytest.mark.asyncio
async def test_supported_modes_includes_containerised_when_container_present():
    adapter, _r, _b, _e, _w = _build_adapter(container=object())
    assert adapter.supported_invocation_modes() == frozenset(
        {InvocationMode.HOST, InvocationMode.CONTAINERIZED},
    )


@pytest.mark.asyncio
async def test_execute_unsupported_mode_raises():
    adapter, _r, _b, execution, _wi = _build_adapter(container=None)
    options = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.CONTAINERIZED,
        model="m",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={},
    )
    with pytest.raises(UnsupportedInvocationModeError):
        await adapter.execute(execution, _workspace_context(), options)


@pytest.mark.asyncio
async def test_execute_dispatches_to_host_strategy_with_rendered_prompt():
    adapter, recorders, builder, execution, _wi = _build_adapter(container=None)
    options = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.HOST,
        model="claude-sonnet-4-6",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={},
    )
    result = await adapter.execute(execution, _workspace_context(), options)
    # Builder was called with the resolved agent + work item.
    assert len(builder.calls) == 1
    # Host strategy received a rendered prompt that includes the work item id.
    host_calls = recorders[InvocationMode.HOST].calls
    assert len(host_calls) == 1
    prompt_text = host_calls[0]["prompt_text"]
    assert "# Your Role" in prompt_text
    assert "# Work Item" in prompt_text
    assert "ID: wi-1" in prompt_text
    assert "Title: Implement widget" in prompt_text
    assert host_calls[0]["execution_id"] == execution.id
    assert host_calls[0]["coding_agent_id"] == "claude-code"
    # Adapter returns the strategy's result verbatim.
    assert result.success is True
    assert result.summary_text == "stub"


@pytest.mark.asyncio
async def test_execute_dispatches_to_containerised_when_mode_matches():
    adapter, recorders, _b, execution, _wi = _build_adapter(container=object())
    options = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.CONTAINERIZED,
        model="claude-sonnet-4-6",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={"image": "codetoreum-agent:latest"},
    )
    await adapter.execute(execution, _workspace_context(), options)
    # Containerised strategy fired, host didn't.
    assert len(recorders[InvocationMode.CONTAINERIZED].calls) == 1
    assert len(recorders[InvocationMode.HOST].calls) == 0
