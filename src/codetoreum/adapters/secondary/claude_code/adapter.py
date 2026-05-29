"""Claude Code coding-agent adapter (D3 redesign).

Implements :class:`~codetoreum.ports.output.coding_agent.ICodingAgent` for
Claude Code via two internal strategies (containerised and host). The
adapter:

1. Validates the requested invocation mode is in
   :meth:`supported_invocation_modes`.
2. Resolves the :class:`Agent` and :class:`WorkItem` for the execution
   from the injected :class:`IAgentRepository` and
   :class:`IWorkItemService`.
3. Builds a :class:`StructuredPrompt` via the injected
   :class:`IPromptBuilder`.
4. Renders the structured prompt to text via
   :func:`render_structured_prompt_to_text`.
5. Dispatches to the chosen strategy, which streams stream-json and
   publishes ``CodingAgent*`` events to the event bus.
6. Returns the strategy's :class:`CodingAgentResult`.

Per INV-15, the adapter emits the full ``CodingAgent*`` event family.
Per INV-16, the adapter never reads from the agent's filesystem to
recover output.
Per INV-17, the adapter (not the orchestrator) owns the choice of
invocation mode.
Per INV-18, prompt-building business logic lives in
:class:`IPromptBuilder`; the adapter only renders.

Resilience patterns (INV-11) wrap the adapter via
:class:`~codetoreum.infrastructure.resilience.decorators.ResilientCodingAgentDecorator`,
which is registered separately by the adapter resolver. The adapter
itself carries no resilience logic.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from codetoreum.adapters.secondary.claude_code.prompt_renderer import (
    render_structured_prompt_to_text,
)
from codetoreum.adapters.secondary.claude_code.strategies.base import (
    ClaudeInvocationStrategy,
)
from codetoreum.adapters.secondary.claude_code.strategies.containerized import (
    ContainerizedClaudeStrategy,
)
from codetoreum.adapters.secondary.claude_code.strategies.host import (
    CredentialProviderProtocol,
    HostClaudeStrategy,
)
from codetoreum.adapters.secondary.claude_code.stream_parser import (
    ClaudeStreamJsonParser,
)
from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.agent_repository import IAgentRepository
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
    ICodingAgent,
    InvocationMode,
)
from codetoreum.ports.output.container import IContainer
from codetoreum.ports.output.prompt_builder import IPromptBuilder
from codetoreum.ports.output.work_item_service import IWorkItemService

logger = logging.getLogger(__name__)

_CODING_AGENT_ID = "claude-code"


@dataclass(frozen=True)
class ClaudeCodeAdapterConfig:
    """Adapter-level configuration (model-agnostic, mode-agnostic).

    Per-execution settings (model, mode, timeout, mode_config) live on
    :class:`CodingAgentInvocationOptions`, not here.

    Attributes:
        claude_cli_path: Path to the ``claude`` binary. Defaults to
            ``"claude"`` (resolved on PATH at execute time).
        api_key_credential_name: Credential key for the API key.
        oauth_token_credential_name: Credential key for the OAuth token.
    """

    claude_cli_path: str = "claude"
    api_key_credential_name: str = "ANTHROPIC_API_KEY"
    oauth_token_credential_name: str = "CLAUDE_CODE_OAUTH_TOKEN"


@dataclass
class _StrategyBundle:
    containerised: ClaudeInvocationStrategy | None = None
    host: ClaudeInvocationStrategy | None = None
    extra: dict[InvocationMode, ClaudeInvocationStrategy] = field(default_factory=dict)

    def get(self, mode: InvocationMode) -> ClaudeInvocationStrategy | None:
        if mode == InvocationMode.CONTAINERIZED:
            return self.containerised
        if mode == InvocationMode.HOST:
            return self.host
        return self.extra.get(mode)

    def supported_modes(self) -> frozenset[InvocationMode]:
        modes: set[InvocationMode] = set()
        if self.containerised is not None:
            modes.add(InvocationMode.CONTAINERIZED)
        if self.host is not None:
            modes.add(InvocationMode.HOST)
        modes.update(self.extra.keys())
        return frozenset(modes)


class ClaudeCodeAdapter(ICodingAgent):
    """Coding agent adapter for Claude Code.

    Supports :class:`InvocationMode.CONTAINERIZED` (via :class:`IContainer`)
    and :class:`InvocationMode.HOST` (via :mod:`asyncio.subprocess`),
    selected per-execution by ``options.invocation_mode``.

    Construction wires both strategies if an :class:`IContainer` is
    supplied; otherwise only :class:`InvocationMode.HOST` is supported and
    :meth:`supported_invocation_modes` reports as much.
    """

    def __init__(
        self,
        *,
        prompt_builder: IPromptBuilder,
        event_bus: EventBus,
        credential_provider: CredentialProviderProtocol,
        agent_repository: IAgentRepository,
        work_item_service: IWorkItemService,
        container: IContainer | None = None,
        workspace_path_resolver: Callable[[WorkspaceContext], Path] | None = None,
        config: ClaudeCodeAdapterConfig | None = None,
    ) -> None:
        """Construct the adapter.

        Args:
            prompt_builder: Vendor-agnostic prompt builder (INV-18).
            event_bus: Event bus to publish ``CodingAgent*`` events to.
            credential_provider: Resolves vendor credentials at execute
                time.
            agent_repository: Used to fetch the :class:`Agent` for an
                :class:`AgentExecution`.
            work_item_service: Used to fetch the :class:`WorkItem` for an
                :class:`AgentExecution`.
            container: :class:`IContainer` adapter. When ``None`` the
                adapter cannot run containerised executions and
                :meth:`supported_invocation_modes` reflects that.
            workspace_path_resolver: Maps a :class:`WorkspaceContext` to
                the host directory either mounted into the container
                (containerised mode) or used as the subprocess cwd (host
                mode). When ``None``, the host strategy uses ``cwd=None``
                (process default) and the containerised strategy skips
                the workspace mount.
            config: Adapter-level configuration. Defaults to
                :class:`ClaudeCodeAdapterConfig` defaults.
        """
        self._prompt_builder = prompt_builder
        self._event_bus = event_bus
        self._agent_repository = agent_repository
        self._work_item_service = work_item_service
        self._config = config or ClaudeCodeAdapterConfig()
        self._parser = ClaudeStreamJsonParser()

        host_strategy = HostClaudeStrategy(
            credential_provider=credential_provider,
            claude_cli_path=self._config.claude_cli_path,
            api_key_credential_name=self._config.api_key_credential_name,
            oauth_token_credential_name=self._config.oauth_token_credential_name,
            workspace_path_resolver=workspace_path_resolver,
        )
        containerised_strategy: ClaudeInvocationStrategy | None = None
        if container is not None:
            containerised_strategy = ContainerizedClaudeStrategy(
                container=container,
                credential_provider=credential_provider,
                claude_cli_path=self._config.claude_cli_path,
                api_key_credential_name=self._config.api_key_credential_name,
                oauth_token_credential_name=self._config.oauth_token_credential_name,
                workspace_path_resolver=workspace_path_resolver,
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

        Raises:
            UnsupportedInvocationModeError: When ``options.invocation_mode``
                is not in :meth:`supported_invocation_modes`.
        """
        strategy = self._strategies.get(options.invocation_mode)
        if strategy is None:
            supported = sorted(m.value for m in self._strategies.supported_modes())
            msg = (
                f"ClaudeCodeAdapter does not support invocation_mode="
                f"{options.invocation_mode.value!r}; supported={supported}"
            )
            raise UnsupportedInvocationModeError(msg)

        agent = await self._agent_repository.get_by_id(execution.agent_id)
        work_item = await self._work_item_service.get_work_item(execution.work_item_id)

        structured = await self._prompt_builder.build(
            agent=agent,
            work_item=work_item,
            workspace_context=workspace_context,
            prior_outputs=(),
        )
        prompt_text = render_structured_prompt_to_text(structured)

        logger.info(
            "ClaudeCodeAdapter.execute: execution_id=%s mode=%s model=%s",
            execution.id,
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
            coding_agent_id=_CODING_AGENT_ID,
        )


class UnsupportedInvocationModeError(ValueError):
    """Raised when an unsupported :class:`InvocationMode` is requested."""


__all__ = [
    "ClaudeCodeAdapter",
    "ClaudeCodeAdapterConfig",
    "UnsupportedInvocationModeError",
]
