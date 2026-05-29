"""Deterministic mock of :class:`ClaudeCodeAdapter` for simulation tests.

Implements :class:`~codetoreum.ports.output.coding_agent.ICodingAgent` so
scenario tests can wire the same port that production wires, without
spinning subprocesses or containers.

The mock:

* Records every invocation for assertion.
* Returns a configurable :class:`CodingAgentResult` (defaults to a happy
  success).
* Emits a minimal but complete ``CodingAgent*`` event stream to the
  injected event bus on each ``execute()`` call:
  invoked → ready → text_output → tokens_used → completed.

Scenarios that need richer event sequences (tool calls, rate limits,
api retries) can pass a custom ``script`` callable returning the events
to emit.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.domain.events.coding_agent_events import (
    CodingAgentCompletedEvent,
    CodingAgentInvokedEvent,
    CodingAgentReadyEvent,
    CodingAgentTextOutputEvent,
    CodingAgentTokensUsedEvent,
)
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
    ICodingAgent,
    InvocationMode,
)


@dataclass
class _Invocation:
    execution_id: str
    work_item_id: str
    agent_id: str
    invocation_mode: InvocationMode
    model: str


ScriptCallable = Callable[
    [AgentExecution, WorkspaceContext, CodingAgentInvocationOptions],
    Awaitable[tuple[list[CodetoreumEvent], CodingAgentResult]],
]


class MockClaudeCodeAdapter(ICodingAgent):
    """Deterministic :class:`ICodingAgent` test double."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        supported_modes: frozenset[InvocationMode] = frozenset(
            {InvocationMode.CONTAINERIZED, InvocationMode.HOST},
        ),
        default_result: CodingAgentResult | None = None,
        script: ScriptCallable | None = None,
    ) -> None:
        """Construct the mock.

        Args:
            event_bus: Bus to publish synthetic events on.
            supported_modes: Modes to report from
                :meth:`supported_invocation_modes`. Defaults to the same
                pair the production adapter supports.
            default_result: Result returned when ``script`` is ``None``.
                Defaults to a success summary with zero cost / tokens.
            script: Optional callable that returns ``(events, result)``
                per invocation. Use this for richer test scenarios (tool
                calls, rate limits, errors).
        """
        self._event_bus = event_bus
        self._supported_modes = supported_modes
        self._default_result = default_result or _default_success_result()
        self._script = script
        self.invocations: list[_Invocation] = field(default_factory=list)  # type: ignore[assignment]
        # field(default_factory=...) doesn't work outside a dataclass; do it
        # explicitly:
        self.invocations = []

    def supported_invocation_modes(self) -> frozenset[InvocationMode]:
        return self._supported_modes

    async def execute(
        self,
        execution: AgentExecution,
        workspace_context: WorkspaceContext,
        options: CodingAgentInvocationOptions,
    ) -> CodingAgentResult:
        self.invocations.append(
            _Invocation(
                execution_id=execution.id,
                work_item_id=execution.work_item_id,
                agent_id=execution.agent_id,
                invocation_mode=options.invocation_mode,
                model=options.model,
            ),
        )

        if self._script is not None:
            events, result = await self._script(execution, workspace_context, options)
        else:
            events, result = self._build_default_event_stream(execution, options), self._default_result

        for event in events:
            await self._event_bus.publish(event)

        return result

    def _build_default_event_stream(
        self,
        execution: AgentExecution,
        options: CodingAgentInvocationOptions,
    ) -> list[CodetoreumEvent]:
        ts = datetime.now(UTC).isoformat()
        return [
            CodingAgentInvokedEvent(
                type="coding_agent.invoked",
                timestamp=ts,
                source="mock_claude_code",
                correlation_id=execution.work_item_id,
                execution_id=execution.id,
                coding_agent_id="claude-code",
                invocation_mode=options.invocation_mode.value,
                model=options.model,
                model_options={},
            ),
            CodingAgentReadyEvent(
                type="coding_agent.ready",
                timestamp=ts,
                source="mock_claude_code",
                correlation_id=execution.work_item_id,
                execution_id=execution.id,
                ready_at=ts,
                init_metadata={"session_id": f"mock-{execution.id[:8]}"},
            ),
            CodingAgentTextOutputEvent(
                type="coding_agent.text_output",
                timestamp=ts,
                source="mock_claude_code",
                correlation_id=execution.work_item_id,
                execution_id=execution.id,
                message_id=f"mock-msg-{execution.id[:8]}",
                content=self._default_result.summary_text,
                role="assistant",
            ),
            CodingAgentTokensUsedEvent(
                type="coding_agent.tokens_used",
                timestamp=ts,
                source="mock_claude_code",
                correlation_id=execution.work_item_id,
                execution_id=execution.id,
                input_tokens=self._default_result.total_input_tokens,
                output_tokens=self._default_result.total_output_tokens,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                cost_usd=self._default_result.total_cost_usd,
                model=options.model,
            ),
            CodingAgentCompletedEvent(
                type="coding_agent.completed",
                timestamp=ts,
                source="mock_claude_code",
                correlation_id=execution.work_item_id,
                execution_id=execution.id,
                success=self._default_result.success,
                summary_text=self._default_result.summary_text,
                total_cost_usd=self._default_result.total_cost_usd,
                total_input_tokens=self._default_result.total_input_tokens,
                total_output_tokens=self._default_result.total_output_tokens,
                tool_call_count=self._default_result.tool_call_count,
                duration_ms=self._default_result.duration_ms,
                error_summary=self._default_result.error_summary,
            ),
        ]


def _default_success_result() -> CodingAgentResult:
    return CodingAgentResult(
        success=True,
        summary_text="mock execution completed",
        total_cost_usd=Decimal("0"),
        total_input_tokens=0,
        total_output_tokens=0,
        tool_call_count=0,
        duration_ms=1,
        error_summary=None,
    )


__all__ = ["MockClaudeCodeAdapter"]
