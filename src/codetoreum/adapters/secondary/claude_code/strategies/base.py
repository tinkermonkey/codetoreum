"""Strategy ABC for :class:`ClaudeCodeAdapter` invocation modes.

A strategy owns *where* the agent's execution happens for one
:class:`~codetoreum.ports.output.coding_agent.InvocationMode`. The
adapter selects a strategy at the start of each ``execute()`` call and
delegates the entire run to it.

Strategies are *internal* to the Claude Code adapter. They don't appear
in any port surface; substituting one strategy for another is an
adapter-internal concern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from codetoreum.adapters.secondary.claude_code.stream_parser import (
    ClaudeStreamJsonParser,
)
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
)


class ClaudeInvocationStrategy(ABC):
    """How :class:`ClaudeCodeAdapter` invokes Claude Code for one execution.

    A strategy:

    1. Launches the Claude Code CLI for the configured invocation mode
       (containerised, host, ...).
    2. Streams its ``stream-json`` output through the supplied
       :class:`ClaudeStreamJsonParser`.
    3. Publishes every emitted :class:`CodetoreumEvent` to the supplied
       :class:`EventBus` while the agent runs (per INV-15).
    4. Returns a final :class:`CodingAgentResult` once the run completes.

    Strategies must remain free of resilience concerns (INV-11) —
    retries, timeouts and circuit breakers wrap the *adapter* via
    :class:`~codetoreum.infrastructure.resilience.decorators.ResilientCodingAgentDecorator`.
    """

    @abstractmethod
    async def execute(
        self,
        *,
        prompt_text: str,
        execution_id: str,
        workspace_context: WorkspaceContext,
        options: CodingAgentInvocationOptions,
        event_bus: EventBus,
        parser: ClaudeStreamJsonParser,
        coding_agent_id: str,
    ) -> CodingAgentResult:
        """Run the Claude Code CLI in this strategy's invocation mode.

        Args:
            prompt_text: Final, rendered prompt suitable for
                ``claude --print TEXT``.
            execution_id: Aggregate id for the resulting event stream.
            workspace_context: Logical workspace description. Strategies
                consume this differently — containerised mounts the
                workspace, host uses it as the subprocess cwd.
            options: Per-execution configuration (mode, model, timeout,
                ``mode_config``).
            event_bus: Event bus to publish ``CodingAgent*`` events to.
            parser: Shared stream parser to map vendor frames to events.
            coding_agent_id: Adapter identifier carried on emitted events
                (e.g. ``"claude-code"``).

        Returns:
            Final :class:`CodingAgentResult` summarising the run.
        """


__all__ = ["ClaudeInvocationStrategy"]
