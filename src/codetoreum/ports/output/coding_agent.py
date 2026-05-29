"""``ICodingAgent`` output port — coding agent abstraction.

Replaces the historical ``ILLMProvider`` / ``IAgentLauncher`` pair (to be
deleted in Phase D5 of the coding-agent port redesign — see
``~/.claude/plans/coding-agent-port-redesign.md`` and DEF-015 in
``bootstrap/ARCHITECTURE.md`` §9).

This port expresses the role — "do coding work, produce a structured
result, emit rich telemetry while you work" — rather than any single
invocation mechanism. Three concrete adapters are planned against this
shape:

- ``ClaudeCodeAdapter`` (next): ``{CONTAINERIZED, HOST}`` modes via
  subprocess + ``IContainer``.
- ``GitHubCopilotAdapter`` (planned): ``{API}`` only — pure HTTP, no
  subprocess.
- ``CodexAdapter`` (planned): ``{CONTAINERIZED, HOST}`` like Claude
  Code.

**Invariants** (see ``bootstrap/ARCHITECTURE.md`` §6):

- **INV-15** — adapters MUST emit the full ``CodingAgent*`` event family
  (see :mod:`codetoreum.domain.events.coding_agent_events`) during
  execution. Lifecycle bookends + tool calls / results / text /
  thinking / rate limits / API retries / OTel spans / tokens.
- **INV-16** — agent output flows exclusively through events.
  Filesystem extraction from agent execution environments is
  forbidden.
- **INV-17** — the coding agent adapter, not the orchestrator, owns the
  choice of invocation mode. The orchestrator validates the configured
  mode is in the adapter's :meth:`ICodingAgent.supported_invocation_modes`
  at config-load time.
- **INV-18** — prompt-building business logic lives in
  :class:`~codetoreum.ports.output.prompt_builder.IPromptBuilder`
  implementations, not inside coding agent adapters. Adapters render
  the structured prompt to their vendor's expected format
  (presentation), but do not own *what context to include* (business).

Resilience patterns (INV-11) apply via decorator at the adapter
boundary; this port itself carries no resilience concerns.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.workspace_context import WorkspaceContext


class InvocationMode(StrEnum):
    """Where the coding agent's execution happens.

    Orthogonal to *how* the agent communicates (subprocess
    ``stream-json``, HTTP streaming response, etc.) — that's an
    adapter-internal implementation choice.

    Members:
        CONTAINERIZED: adapter uses ``IContainer`` to run the agent
            inside a sandboxed container.
        HOST: adapter runs the agent process directly on the host.
        API: adapter makes HTTP calls (Copilot, future direct APIs).
    """

    CONTAINERIZED = "containerized"
    HOST = "host"
    API = "api"


@dataclass(frozen=True)
class CodingAgentInvocationOptions:
    """Per-execution configuration for a coding agent invocation.

    Immutable value object (frozen dataclass). The adapter validates
    ``invocation_mode`` is in its
    :meth:`ICodingAgent.supported_invocation_modes` at construction time
    of the upstream agent config (load time), not at first invocation.

    Attributes:
        invocation_mode: One of :class:`InvocationMode` — where the
            agent execution happens.
        model: Model name. The adapter validates this against its
            supported model list.
        timeout_seconds: Hard timeout for the execution.
        cost_limit_usd: Optional per-execution USD cost ceiling.
            ``None`` means no enforced limit.
        mode_config: Mode-specific configuration — e.g. for
            ``CONTAINERIZED``: ``{"image": ..., "cpu_limit": ...,
            "memory_limit": ...}``; for ``API``: ``{"endpoint": ...,
            "auth_token_ref": ...}``. Carried as a generic ``Mapping``
            so each mode's strategy can interpret it.
    """

    invocation_mode: InvocationMode
    model: str
    timeout_seconds: int
    cost_limit_usd: Decimal | None
    mode_config: Mapping[str, Any]


@dataclass(frozen=True)
class CodingAgentResult:
    """Final summary returned by a coding agent execution.

    Granular per-execution behaviour (tool calls, tool results, text,
    thinking, rate limits, API retries, OTel spans, token usage) flows
    through ``CodingAgent*`` domain events on the event bus while the
    agent runs. This value object is the **outcome summary** returned
    once execution completes; ``ExecutionService`` consumes it to
    decide whether to emit ``ExecutionCompletedEvent`` or
    ``ExecutionFailedEvent`` at the workflow level.

    Attributes:
        success: True if execution completed without unrecoverable error.
        summary_text: Final agent summary / response text.
        total_cost_usd: Total cost across the execution.
        total_input_tokens: Total input tokens consumed
            (including cache traffic).
        total_output_tokens: Total output tokens generated.
        tool_call_count: Number of tool invocations made by the agent.
        duration_ms: End-to-end duration of the execution.
        error_summary: Error description when ``success`` is False;
            ``None`` otherwise.
    """

    success: bool
    summary_text: str
    total_cost_usd: Decimal
    total_input_tokens: int
    total_output_tokens: int
    tool_call_count: int
    duration_ms: int
    error_summary: str | None


class ICodingAgent(ABC):
    """Coding agent abstraction (Claude Code, GitHub Copilot, Codex, ...).

    Replaces the historical ``ILLMProvider`` / ``IAgentLauncher`` pair.
    The port expresses the **role** — "do coding work, produce a
    structured result, emit rich telemetry while you work" — not the
    invocation mechanism.

    Adapters own the choice of invocation mode (containerized via
    ``IContainer``, host via subprocess, or HTTP API for adapters like
    Copilot that don't shell out). Prompt assembly is delegated to an
    :class:`~codetoreum.ports.output.prompt_builder.IPromptBuilder`
    injected via DI; the adapter renders the resulting
    :class:`~codetoreum.ports.output.prompt_builder.StructuredPrompt`
    to its vendor's expected format (text for Claude Code, message
    array for Copilot, etc.).

    Per INV-15, adapters MUST emit the full ``CodingAgent*`` event
    family on the event bus while the agent runs.
    """

    @abstractmethod
    def supported_invocation_modes(self) -> frozenset[InvocationMode]:
        """Declare which invocation modes this adapter implements.

        For example, ``frozenset({InvocationMode.CONTAINERIZED,
        InvocationMode.HOST})`` for a CLI-shaped adapter, or
        ``frozenset({InvocationMode.API})`` for an HTTP-only vendor.

        Validated against agent config at load time, not at first
        invocation — bad configuration fails fast.

        Returns:
            The set of invocation modes the adapter implements.
        """

    @abstractmethod
    async def execute(
        self,
        execution: AgentExecution,
        workspace_context: WorkspaceContext,
        options: CodingAgentInvocationOptions,
    ) -> CodingAgentResult:
        """Execute the coding agent.

        The adapter:

        1. Validates ``options.invocation_mode`` is in
           :meth:`supported_invocation_modes`.
        2. Picks the corresponding internal strategy
           (containerized / host / API).
        3. Calls its injected ``IPromptBuilder.build(...)`` to assemble
           the :class:`StructuredPrompt`.
        4. Renders the structured prompt to its vendor's format and
           drives the agent.
        5. Emits ``CodingAgent*`` events on the event bus while the
           agent runs (per INV-15).
        6. Returns a :class:`CodingAgentResult` summarising the outcome.

        Per INV-16, the adapter MUST NOT extract output from the agent
        filesystem. All telemetry flows through events.

        Args:
            execution: The :class:`~codetoreum.domain.agent_execution.AgentExecution`
                tracking this run. Carries ``execution_id`` (aggregate
                ID for the event stream), agent reference, etc.
            workspace_context: Logical workspace description from
                ``WorkspaceRouter`` — workspace path, branch, git
                identity, project env vars. Replaces the prior
                ``prepare_container_environment`` env dict.
            options: Per-execution configuration (mode, model, limits).

        Returns:
            :class:`CodingAgentResult` summarising the run.
        """


__all__ = [
    "CodingAgentInvocationOptions",
    "CodingAgentResult",
    "ICodingAgent",
    "InvocationMode",
]
