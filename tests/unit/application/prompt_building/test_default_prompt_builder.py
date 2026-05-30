"""Unit tests for :class:`DefaultPromptBuilder` (Phase D2).

Covers:

- Each :class:`StructuredPrompt` field is populated from agent + work item +
  workspace + prior outputs.
- ``prior_outputs`` propagate through unchanged.
- The returned ``StructuredPrompt`` is immutable.
- ``instructions`` and ``constraints`` are ``tuple[str, ...]`` (no leaked
  mutable types).
- Varying :attr:`WorkspaceContext.allow_code_changes` and capabilities
  changes the instructions / constraints tuples.
"""

from dataclasses import FrozenInstanceError

import pytest

from codetoreum.application.prompt_building import DefaultPromptBuilder
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.coding_agent_types import AgentInvocationConfig, InvocationMode
from codetoreum.domain.value_objects import CommitPolicy
from codetoreum.domain.work_item import WorkItem
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.ports.output.prompt_builder import (
    ExecutionOutput,
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_agent(
    *,
    capabilities: dict[str, AgentCapability] | None = None,
    makes_code_changes: bool = True,
    filesystem_write_allowed: bool = True,
) -> Agent:
    """Minimal Agent suited to prompt-assembly tests."""
    caps = capabilities or {
        "python": AgentCapability("python", 0.9, "Expert in Python"),
    }
    return Agent.create(
        name="default-agent",
        display_name="Default Agent",
        agent_type=AgentType.MAKER,
        role_description="A senior software engineer.",
        capabilities=caps,
        requires_dev_container=False,
        makes_code_changes=makes_code_changes,
        filesystem_write_allowed=filesystem_write_allowed,
        mcp_servers=[],
        commit_policy=CommitPolicy.ON_SUCCESS,
        invocation=_test_inv(model="claude-opus-4-7", timeout_seconds=300, requires_docker=True),
    )


def _make_work_item() -> WorkItem:
    return WorkItem.create(
        title="Add OAuth2 login",
        description="Implement OAuth2 sign-in with GitHub and Google.",
        project_id="proj-1",
    )


def _make_workspace_context(*, allow_code_changes: bool = True) -> WorkspaceContext:
    ws = WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id="wi-1",
        branch_name="feat/oauth",
    )
    if allow_code_changes is False:
        # for_issue defaults allow_code_changes=True; flip it via dataclass
        # reconstruction (frozen). The contract is "construct with desired
        # values", not "mutate".
        return WorkspaceContext(
            workspace_type=ws.workspace_type,
            project_id=ws.project_id,
            work_item_id=ws.work_item_id,
            branch_name=ws.branch_name,
            create_pr=ws.create_pr,
            discussion_id=ws.discussion_id,
            allow_code_changes=False,
            create_commits=ws.create_commits,
            post_comments=ws.post_comments,
        )
    return ws


def _make_prior_outputs() -> tuple[ExecutionOutput, ...]:
    return (
        ExecutionOutput(
            stage_name="planning",
            output="Plan: 1. Survey existing auth. 2. Add OAuth2.",
            created_at="2026-05-29T00:00:00+00:00",
        ),
        ExecutionOutput(
            stage_name="design",
            output="Design: PKCE flow, callback at /auth/callback.",
            created_at="2026-05-29T01:00:00+00:00",
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDefaultPromptBuilderInherits:
    """DefaultPromptBuilder explicitly inherits IPromptBuilder."""

    def test_inherits_iprompt_builder(self) -> None:
        # Per INV-09 — application services implementing output ports must
        # explicitly inherit the port ABC.
        assert issubclass(DefaultPromptBuilder, IPromptBuilder)

    def test_can_instantiate(self) -> None:
        builder = DefaultPromptBuilder()
        assert isinstance(builder, IPromptBuilder)


class TestDefaultPromptBuilderBasic:
    """Build a StructuredPrompt from a minimal Agent + WorkItem + WorkspaceContext."""

    @pytest.mark.asyncio
    async def test_build_populates_every_field(self) -> None:
        agent = _make_agent()
        work_item = _make_work_item()
        workspace_context = _make_workspace_context()

        builder = DefaultPromptBuilder()
        prompt = await builder.build(agent, work_item, workspace_context)

        assert isinstance(prompt, StructuredPrompt)
        assert prompt.role_description
        assert prompt.task_description
        assert prompt.work_item is work_item
        assert prompt.workspace_context is workspace_context
        assert len(prompt.instructions) > 0
        assert len(prompt.constraints) > 0
        # No prior outputs were provided -> empty tuple by default.
        assert prompt.prior_outputs == ()

    @pytest.mark.asyncio
    async def test_role_description_includes_agent_signal(self) -> None:
        agent = _make_agent()
        builder = DefaultPromptBuilder()
        prompt = await builder.build(agent, _make_work_item(), _make_workspace_context())

        assert agent.display_name in prompt.role_description
        assert agent.agent_type.value in prompt.role_description
        assert agent.role_description in prompt.role_description

    @pytest.mark.asyncio
    async def test_task_description_includes_work_item_signal(self) -> None:
        work_item = _make_work_item()
        builder = DefaultPromptBuilder()
        prompt = await builder.build(_make_agent(), work_item, _make_workspace_context())

        assert work_item.title in prompt.task_description
        assert work_item.description in prompt.task_description


class TestDefaultPromptBuilderWithPriorOutputs:
    """``prior_outputs`` propagate from input to ``StructuredPrompt``."""

    @pytest.mark.asyncio
    async def test_prior_outputs_pass_through(self) -> None:
        prior_outputs = _make_prior_outputs()
        builder = DefaultPromptBuilder()
        prompt = await builder.build(
            _make_agent(),
            _make_work_item(),
            _make_workspace_context(),
            prior_outputs=prior_outputs,
        )

        assert prompt.prior_outputs is prior_outputs
        assert len(prompt.prior_outputs) == 2
        assert prompt.prior_outputs[0].stage_name == "planning"
        assert prompt.prior_outputs[1].stage_name == "design"


class TestDefaultPromptBuilderImmutability:
    """The returned StructuredPrompt is frozen — mutation raises."""

    @pytest.mark.asyncio
    async def test_structured_prompt_is_frozen(self) -> None:
        builder = DefaultPromptBuilder()
        prompt = await builder.build(_make_agent(), _make_work_item(), _make_workspace_context())

        with pytest.raises(FrozenInstanceError):
            prompt.role_description = "tampered"  # type: ignore[misc]


class TestDefaultPromptBuilderCollections:
    """``instructions`` and ``constraints`` are tuples — no leaking mutables."""

    @pytest.mark.asyncio
    async def test_instructions_are_tuple_of_str(self) -> None:
        builder = DefaultPromptBuilder()
        prompt = await builder.build(_make_agent(), _make_work_item(), _make_workspace_context())

        assert isinstance(prompt.instructions, tuple)
        assert all(isinstance(item, str) for item in prompt.instructions)

    @pytest.mark.asyncio
    async def test_constraints_are_tuple_of_str(self) -> None:
        builder = DefaultPromptBuilder()
        prompt = await builder.build(_make_agent(), _make_work_item(), _make_workspace_context())

        assert isinstance(prompt.constraints, tuple)
        assert all(isinstance(item, str) for item in prompt.constraints)

    @pytest.mark.asyncio
    async def test_prior_outputs_are_tuple_of_execution_output(self) -> None:
        builder = DefaultPromptBuilder()
        prompt = await builder.build(
            _make_agent(),
            _make_work_item(),
            _make_workspace_context(),
            prior_outputs=_make_prior_outputs(),
        )

        assert isinstance(prompt.prior_outputs, tuple)
        assert all(isinstance(item, ExecutionOutput) for item in prompt.prior_outputs)


class TestDefaultPromptBuilderWorkspaceVariations:
    """Varying workspace and agent options changes instructions / constraints."""

    @pytest.mark.asyncio
    async def test_allow_code_changes_true_adds_edit_files_instruction(self) -> None:
        builder = DefaultPromptBuilder()
        workspace_context = _make_workspace_context(allow_code_changes=True)
        prompt = await builder.build(_make_agent(), _make_work_item(), workspace_context)

        edit_instruction = "You may edit files in the repository."
        assert edit_instruction in prompt.instructions

    @pytest.mark.asyncio
    async def test_allow_code_changes_false_drops_edit_instruction_and_adds_constraint(
        self,
    ) -> None:
        builder = DefaultPromptBuilder()
        workspace_context = _make_workspace_context(allow_code_changes=False)
        prompt = await builder.build(_make_agent(), _make_work_item(), workspace_context)

        edit_instruction = "You may edit files in the repository."
        assert edit_instruction not in prompt.instructions

        # A "no modifications" constraint should appear.
        assert any("analysis only" in constraint.lower() for constraint in prompt.constraints)

    @pytest.mark.asyncio
    async def test_testing_capability_adds_test_instruction(self) -> None:
        agent = _make_agent(
            capabilities={
                "python": AgentCapability("python", 0.9, ""),
                "testing": AgentCapability("testing", 0.8, ""),
            }
        )
        builder = DefaultPromptBuilder()
        prompt = await builder.build(agent, _make_work_item(), _make_workspace_context())

        assert any("test" in instruction.lower() for instruction in prompt.instructions)

    @pytest.mark.asyncio
    async def test_no_testing_capability_omits_test_instruction(self) -> None:
        agent = _make_agent(capabilities={"python": AgentCapability("python", 0.9, "")})
        builder = DefaultPromptBuilder()
        prompt = await builder.build(agent, _make_work_item(), _make_workspace_context())

        assert not any("run the project's tests" in instruction.lower() for instruction in prompt.instructions)

    @pytest.mark.asyncio
    async def test_filesystem_write_disabled_adds_constraint(self) -> None:
        agent = _make_agent(filesystem_write_allowed=False)
        builder = DefaultPromptBuilder()
        prompt = await builder.build(agent, _make_work_item(), _make_workspace_context())

        assert any("filesystem writes are disabled" in constraint.lower() for constraint in prompt.constraints)

    @pytest.mark.asyncio
    async def test_default_constraints_always_present(self) -> None:
        """The baseline policy constraints always show up."""
        builder = DefaultPromptBuilder()
        prompt = await builder.build(_make_agent(), _make_work_item(), _make_workspace_context())

        joined = " | ".join(prompt.constraints).lower()
        assert ".env" in joined
        assert "binary" in joined
        assert "workspace" in joined

    @pytest.mark.asyncio
    async def test_baseline_instruction_always_present(self) -> None:
        """The minimum "make the changes" instruction is always first."""
        builder = DefaultPromptBuilder()
        prompt = await builder.build(_make_agent(), _make_work_item(), _make_workspace_context())

        assert prompt.instructions[0].lower().startswith("make the changes")
