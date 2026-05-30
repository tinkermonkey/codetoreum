"""Free-form ``ICodingAgent`` for adapter-local prompt use cases.

Background
----------

The repair / systemic-analysis adapters
(:class:`~codetoreum.adapters.secondary.production_repair_cycle_adapter.ProductionRepairCycleAdapter`,
:class:`~codetoreum.adapters.secondary.production_environment_repair_adapter.ProductionEnvironmentRepairAdapter`,
:class:`~codetoreum.adapters.secondary.llm_systemic_analysis_adapter.LLMSystemicAnalysisAdapter`)
each issue *free-form* prompts that have no backing :class:`Agent` or
:class:`WorkItem` — systemic-analysis wants JSON-shaped classifications
for a batch of failures, environment-repair wants rebuild plans,
repair-cycle wants file-fix instructions.

The standard :class:`~codetoreum.adapters.secondary.claude_code.ClaudeCodeAdapter`
loads an :class:`Agent` from its injected
:class:`~codetoreum.ports.output.agent_repository.IAgentRepository` and a
:class:`WorkItem` from its injected
:class:`~codetoreum.ports.input.work_item_service.IWorkItemService` before
calling its injected :class:`~codetoreum.ports.output.prompt_builder.IPromptBuilder`.
That contract is task-shaped — perfect for the workflow-pipeline path,
wrong for these free-form callers.

This module provides:

- :class:`FreeFormCodingAgent` — a thin :class:`ICodingAgent` that drives
  the same Claude strategies (:mod:`codetoreum.adapters.secondary.claude_code.strategies`)
  used by :class:`ClaudeCodeAdapter`, but **bypasses the agent / work-item
  lookup**. The adapter passes the per-call
  :class:`~codetoreum.ports.output.prompt_builder.IPromptBuilder` it
  was constructed with synthetic agent / work-item arguments which the
  builder is free to ignore.
- :func:`synthetic_agent_execution`,
  :func:`synthetic_work_item`,
  :func:`synthetic_workspace_context` — helpers that build the minimal
  domain stand-ins needed so the strategies can run.

The "synthetic" objects are an intentional smell: the repair adapters
*could* be migrated more invasively (e.g. teach the strategies to accept
a :class:`StructuredPrompt` directly), but the cost would be churning
production paths that have already been migrated. The synthetics are
*local* to free-form invocations and never escape into the
work-item / workflow path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from codetoreum.adapters.secondary.claude_code.adapter import _StrategyBundle
from codetoreum.adapters.secondary.claude_code.prompt_renderer import (
    render_structured_prompt_to_text,
)
from codetoreum.adapters.secondary.claude_code.strategies.containerized import (
    ContainerizedClaudeStrategy,
)
from codetoreum.adapters.secondary.claude_code.strategies.host import (
    HostClaudeStrategy,
)
from codetoreum.adapters.secondary.claude_code.stream_parser import (
    ClaudeStreamJsonParser,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.agent_execution import AgentExecution, ExecutionStatus
from codetoreum.domain.coding_agent_types import (
    AgentInvocationConfig,
    InvocationMode,
)
from codetoreum.domain.work_item import (
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
)
from codetoreum.domain.workspace_context import WorkspaceContext, WorkspaceType
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
    ICodingAgent,
)

if TYPE_CHECKING:
    from codetoreum.adapters.secondary.claude_code.adapter import (
        ClaudeCodeAdapterConfig,
    )
    from codetoreum.adapters.secondary.claude_code.strategies.host import (
        CredentialProviderProtocol,
    )
    from codetoreum.infrastructure.event_bus import EventBus
    from codetoreum.ports.output.container import IContainer
    from codetoreum.ports.output.prompt_builder import IPromptBuilder

logger = logging.getLogger(__name__)


_FREE_FORM_CODING_AGENT_ID = "claude-code-free-form"


# ---------------------------------------------------------------------------
# Synthetic domain stand-ins
# ---------------------------------------------------------------------------


def synthetic_work_item(purpose: str) -> WorkItem:
    """Build a minimal :class:`WorkItem` for a free-form prompt.

    The prompt renderer reads ``id``, ``title``, and ``external_url`` from
    the WorkItem on the rendered :class:`StructuredPrompt`. For free-form
    prompts we set ``id=""`` (so the renderer skips the ID line), supply
    ``purpose`` as the title (descriptive), and leave ``external_url``
    blank.

    Args:
        purpose: Short label describing the free-form call (e.g.
            ``"systemic_analysis"``, ``"repair_cycle.file_fix"``). Surfaces
            as the rendered work-item title only.

    Returns:
        A :class:`WorkItem` satisfying the domain invariants with no
        cross-references into the real persistence layer.
    """
    now = datetime.now(UTC)
    return WorkItem(
        id="",
        project_id="free-form",
        title=purpose,
        description="",
        status=WorkItemStatus.IN_PROGRESS,
        priority=WorkItemPriority.MEDIUM,
        labels=[],
        external_id=None,
        external_url=None,
        assigned_agent_id=None,
        assigned_at=None,
        current_workflow_id=None,
        current_stage=None,
        current_column=None,
        entered_column_at=None,
        created_at=now,
        updated_at=now,
    )


def synthetic_agent(purpose: str) -> Agent:
    """Build a minimal :class:`Agent` for a free-form prompt.

    The :class:`Agent` is passed to the adapter-local
    :class:`IPromptBuilder.build`; adapter-local builders for free-form
    prompts ignore the agent entirely. The synthetic instance therefore
    only has to satisfy the :class:`Agent` constructor invariants.

    Args:
        purpose: Short label describing the free-form call. Surfaces as
            the agent's display name / role description so any logs that
            leak through point back to the correct call site.

    Returns:
        An :class:`Agent` satisfying the domain invariants.
    """
    return Agent.create(
        name=f"free-form-{purpose}",
        display_name=f"Free-form ({purpose})",
        agent_type=AgentType.SPECIALIZED,
        role_description=f"Synthetic agent for free-form prompt: {purpose}",
        capabilities={
            "free_form": AgentCapability(
                skill="free_form",
                proficiency=1.0,
                description="Synthetic capability for free-form prompts.",
            ),
        },
        invocation=AgentInvocationConfig(
            mode=InvocationMode.HOST,
            model="claude-sonnet-4-6",
            timeout_seconds=300,
        ),
        filesystem_write_allowed=True,
    )


def synthetic_workspace_context(
    *,
    purpose: str,
    workspace_path: Path | None,
) -> WorkspaceContext:
    """Build a minimal :class:`WorkspaceContext` for a free-form prompt.

    ``HostClaudeStrategy`` and ``ContainerizedClaudeStrategy`` read
    ``workspace_context.workspace_path`` to set the subprocess cwd /
    container mount. For systemic-analysis there is no workspace; the
    caller should pass a temp directory (or the orchestrator's working
    dir) here. For repair-cycle / env-repair there is a real workspace
    and the caller passes it through.

    Args:
        purpose: Short label describing the free-form call; folded into
            the synthetic ``work_item_id`` for log traceability.
        workspace_path: Host-side absolute path the agent should run
            in. ``None`` means the strategies will raise — only suitable
            for tests that mock the strategy.

    Returns:
        A :class:`WorkspaceContext` flagged as
        :class:`WorkspaceType.ISSUE` with a synthetic branch name.
    """
    return WorkspaceContext(
        workspace_type=WorkspaceType.ISSUE,
        project_id="free-form",
        work_item_id=f"free-form-{purpose}",
        branch_name=f"free-form-{purpose}",
        create_pr=False,
        discussion_id=None,
        allow_code_changes=True,
        create_commits=False,
        post_comments=False,
        workspace_path=workspace_path,
    )


def synthetic_agent_execution(
    *,
    purpose: str,
    agent_id: str | None = None,
    model: str = "claude-sonnet-4-6",
) -> AgentExecution:
    """Build a minimal :class:`AgentExecution` for a free-form prompt.

    The :class:`AgentExecution` is the aggregate carrying ``execution_id``
    (the event-stream key) into the strategies' event emission. For
    free-form calls we generate a fresh UUID and tag the rest of the
    fields with the ``purpose`` for traceability.

    Args:
        purpose: Short label describing the free-form call (e.g.
            ``"systemic_analysis"``).
        agent_id: Optional explicit agent_id; defaults to
            ``f"free-form-{purpose}"``.
        model: Model name recorded on the execution. The strategies
            consume the model from ``CodingAgentInvocationOptions``, not
            this field — it is informational only.

    Returns:
        An :class:`AgentExecution` in :class:`ExecutionStatus.INITIALIZED`
        state.
    """
    now = datetime.now(UTC)
    return AgentExecution(
        id=str(uuid4()),
        agent_id=agent_id or f"free-form-{purpose}",
        work_item_id=f"free-form-{purpose}",
        workflow_id=f"free-form-{purpose}",
        stage_name="free-form",
        status=ExecutionStatus.INITIALIZED,
        prompt="",  # populated by the strategies via the rendered text
        model=model,
        session_id=None,
        container_name=None,
        container_id=None,
        output=None,
        error_message=None,
        exit_code=None,
        input_tokens=0,
        output_tokens=0,
        duration_seconds=None,
        initialized_at=now,
        started_at=None,
        completed_at=None,
        metadata={"free_form_purpose": purpose},
    )


# ---------------------------------------------------------------------------
# Free-form coding agent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreeFormCodingAgentConfig:
    """Configuration for :class:`FreeFormCodingAgent`.

    Mirrors :class:`~codetoreum.adapters.secondary.claude_code.adapter.ClaudeCodeAdapterConfig`
    — the Claude strategies need the same CLI path and credential keys.

    Attributes:
        claude_cli_path: Path to the ``claude`` binary. Defaults to
            ``"claude"`` (resolved on PATH at execute time).
        api_key_credential_name: Credential key for the API key.
        oauth_token_credential_name: Credential key for the OAuth token.
    """

    claude_cli_path: str = "claude"
    api_key_credential_name: str = "ANTHROPIC_API_KEY"
    oauth_token_credential_name: str = "CLAUDE_CODE_OAUTH_TOKEN"


class FreeFormCodingAgent(ICodingAgent):
    """:class:`ICodingAgent` for free-form prompts (no Agent / WorkItem).

    Drives the same Claude strategies as
    :class:`~codetoreum.adapters.secondary.claude_code.ClaudeCodeAdapter`
    — the only difference is that this adapter does NOT load an
    :class:`Agent` or :class:`WorkItem` from a repository before calling
    its injected :class:`IPromptBuilder`. The repair / systemic-analysis
    adapters supply a private ``IPromptBuilder`` that closure-captures
    whatever call-specific data is needed and ignores the synthetic
    agent / work-item arguments.

    Construction
    ------------

    A bootstrap-wired ``coding_agent_factory: Callable[[IPromptBuilder], ICodingAgent]``
    constructs one of these per free-form call. The repair adapters do
    not hold a long-lived :class:`FreeFormCodingAgent`; each call builds
    a fresh adapter-local prompt-builder, asks the factory for a fresh
    coding agent for that builder, and discards both after the call
    completes.

    Per INV-15, the underlying strategies emit the full
    ``CodingAgent*`` event family on the event bus while the agent runs.
    """

    def __init__(
        self,
        *,
        prompt_builder: IPromptBuilder,
        event_bus: EventBus,
        credential_provider: CredentialProviderProtocol,
        container: IContainer | None = None,
        config: ClaudeCodeAdapterConfig | FreeFormCodingAgentConfig | None = None,
    ) -> None:
        """Construct the free-form coding agent.

        Args:
            prompt_builder: Adapter-local
                :class:`~codetoreum.ports.output.prompt_builder.IPromptBuilder`
                supplied by the per-call factory. The builder closure-
                captures the call-specific data (failure list, repair
                context, etc.) and produces the
                :class:`~codetoreum.ports.output.prompt_builder.StructuredPrompt`
                the call needs. The builder is invoked with synthetic
                :class:`Agent` and :class:`WorkItem` arguments which the
                builder is free to ignore.
            event_bus: Event bus the underlying strategies publish
                ``CodingAgent*`` events to.
            credential_provider: Resolves ``ANTHROPIC_API_KEY`` /
                ``CLAUDE_CODE_OAUTH_TOKEN`` at execute time.
            container: Optional :class:`IContainer`. When ``None`` only
                :class:`InvocationMode.HOST` is supported.
            config: Optional adapter-level configuration. Accepts either
                a :class:`FreeFormCodingAgentConfig` or a
                :class:`ClaudeCodeAdapterConfig` for parity with the
                main adapter.
        """
        self._prompt_builder = prompt_builder
        self._event_bus = event_bus
        self._config = config or FreeFormCodingAgentConfig()
        self._parser = ClaudeStreamJsonParser()

        host_strategy = HostClaudeStrategy(
            credential_provider=credential_provider,
            claude_cli_path=self._config.claude_cli_path,
            api_key_credential_name=self._config.api_key_credential_name,
            oauth_token_credential_name=self._config.oauth_token_credential_name,
        )
        containerised_strategy = None
        if container is not None:
            containerised_strategy = ContainerizedClaudeStrategy(
                container=container,
                credential_provider=credential_provider,
                claude_cli_path=self._config.claude_cli_path,
                api_key_credential_name=self._config.api_key_credential_name,
                oauth_token_credential_name=self._config.oauth_token_credential_name,
            )
        self._strategies = _StrategyBundle(
            host=host_strategy,
            containerised=containerised_strategy,
        )

    # ------------------------------------------------------------------
    # ICodingAgent
    # ------------------------------------------------------------------

    def supported_invocation_modes(self) -> frozenset[InvocationMode]:
        """Modes this adapter supports.

        Always includes :class:`InvocationMode.HOST`. Includes
        :class:`InvocationMode.CONTAINERIZED` iff an :class:`IContainer`
        adapter was injected at construction.
        """
        return self._strategies.supported_modes()

    async def execute(
        self,
        execution: AgentExecution,
        workspace_context: WorkspaceContext,
        options: CodingAgentInvocationOptions,
    ) -> CodingAgentResult:
        """Render the prompt and dispatch to the chosen strategy.

        Calls the injected :class:`IPromptBuilder` with synthetic
        :class:`Agent` and :class:`WorkItem` arguments. The free-form
        adapter-local builder is expected to ignore both and build the
        :class:`StructuredPrompt` from its closure-captured state.

        Raises:
            UnsupportedInvocationModeError: When ``options.invocation_mode``
                is not in :meth:`supported_invocation_modes`.
        """
        from codetoreum.adapters.secondary.claude_code.adapter import (
            UnsupportedInvocationModeError,
        )

        strategy = self._strategies.get(options.invocation_mode)
        if strategy is None:
            supported = sorted(m.value for m in self._strategies.supported_modes())
            msg = (
                f"FreeFormCodingAgent does not support invocation_mode="
                f"{options.invocation_mode.value!r}; supported={supported}"
            )
            raise UnsupportedInvocationModeError(msg)

        # Pass synthetic Agent / WorkItem to the builder; the free-form
        # builder is expected to ignore them and use its closure-
        # captured state instead.
        purpose = execution.metadata.get("free_form_purpose", "free-form")
        syn_agent = synthetic_agent(purpose)
        syn_work_item = synthetic_work_item(purpose)

        structured = await self._prompt_builder.build(
            agent=syn_agent,
            work_item=syn_work_item,
            workspace_context=workspace_context,
            prior_outputs=(),
        )
        prompt_text = render_structured_prompt_to_text(structured)

        logger.info(
            "FreeFormCodingAgent.execute: execution_id=%s purpose=%s mode=%s model=%s",
            execution.id,
            purpose,
            options.invocation_mode.value,
            options.model,
        )

        return await strategy.execute(
            prompt_text=prompt_text,
            execution_id=execution.id,
            workspace_context=workspace_context,
            options=options,
            event_bus=self._event_bus,
            parser=self._parser,
            coding_agent_id=_FREE_FORM_CODING_AGENT_ID,
        )


# ---------------------------------------------------------------------------
# Re-exports for typing convenience
# ---------------------------------------------------------------------------

__all__ = [
    "FreeFormCodingAgent",
    "FreeFormCodingAgentConfig",
    "synthetic_agent",
    "synthetic_agent_execution",
    "synthetic_work_item",
    "synthetic_workspace_context",
]
