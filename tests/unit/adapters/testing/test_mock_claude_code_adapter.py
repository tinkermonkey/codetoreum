"""Unit tests for :class:`MockClaudeCodeAdapter`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from codetoreum.adapters.testing.mock_claude_code_adapter import (
    MockClaudeCodeAdapter,
)
from codetoreum.domain.agent_execution import AgentExecution
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
    InvocationMode,
)


def _execution() -> AgentExecution:
    return AgentExecution.create(
        agent_id="agent-1",
        work_item_id="wi-1",
        workflow_id="wf-1",
        stage_name="stage",
        prompt="prompt",
        model="m",
    )


def _options(mode: InvocationMode = InvocationMode.HOST) -> CodingAgentInvocationOptions:
    return CodingAgentInvocationOptions(
        invocation_mode=mode,
        model="claude-sonnet-4-6",
        timeout_seconds=10,
        cost_limit_usd=None,
        mode_config={},
    )


def _ws() -> WorkspaceContext:
    return WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id="wi-1",
        branch_name="feature/x",
    )


@pytest.mark.asyncio
async def test_default_event_stream_and_result():
    bus = EventBus()
    captured: list[Any] = []
    bus.subscribe(None, lambda e: captured.append(e))
    adapter = MockClaudeCodeAdapter(event_bus=bus)

    result = await adapter.execute(_execution(), _ws(), _options())

    assert result.success is True
    assert result.summary_text == "mock execution completed"
    assert result.total_cost_usd == Decimal("0")

    types = [type(e).__name__ for e in captured]
    assert types == [
        "CodingAgentInvokedEvent",
        "CodingAgentReadyEvent",
        "CodingAgentTextOutputEvent",
        "CodingAgentTokensUsedEvent",
        "CodingAgentCompletedEvent",
    ]
    invoked = next(e for e in captured if isinstance(e, CodingAgentInvokedEvent))
    assert invoked.invocation_mode == "host"
    assert invoked.model == "claude-sonnet-4-6"
    ready = next(e for e in captured if isinstance(e, CodingAgentReadyEvent))
    assert ready.init_metadata.get("session_id") is not None
    text = next(e for e in captured if isinstance(e, CodingAgentTextOutputEvent))
    assert text.content == "mock execution completed"
    tokens = next(e for e in captured if isinstance(e, CodingAgentTokensUsedEvent))
    assert tokens.model == "claude-sonnet-4-6"
    completed = next(e for e in captured if isinstance(e, CodingAgentCompletedEvent))
    assert completed.success is True


@pytest.mark.asyncio
async def test_supported_modes_default():
    adapter = MockClaudeCodeAdapter(event_bus=EventBus())
    assert adapter.supported_invocation_modes() == frozenset(
        {InvocationMode.HOST, InvocationMode.CONTAINERIZED},
    )


@pytest.mark.asyncio
async def test_records_invocations():
    adapter = MockClaudeCodeAdapter(event_bus=EventBus())
    await adapter.execute(_execution(), _ws(), _options())
    await adapter.execute(_execution(), _ws(), _options(InvocationMode.CONTAINERIZED))
    assert len(adapter.invocations) == 2
    assert adapter.invocations[0].invocation_mode == InvocationMode.HOST
    assert adapter.invocations[1].invocation_mode == InvocationMode.CONTAINERIZED


@pytest.mark.asyncio
async def test_custom_default_result_propagates():
    custom = CodingAgentResult(
        success=False,
        summary_text="boom",
        total_cost_usd=Decimal("1.5"),
        total_input_tokens=10,
        total_output_tokens=20,
        tool_call_count=3,
        duration_ms=1000,
        error_summary="something failed",
    )
    bus = EventBus()
    captured: list[Any] = []
    bus.subscribe(None, lambda e: captured.append(e))
    adapter = MockClaudeCodeAdapter(event_bus=bus, default_result=custom)

    result = await adapter.execute(_execution(), _ws(), _options())
    assert result == custom

    completed = next(e for e in captured if isinstance(e, CodingAgentCompletedEvent))
    assert completed.success is False
    assert completed.error_summary == "something failed"
    assert completed.tool_call_count == 3
    assert completed.total_cost_usd == Decimal("1.5")


@pytest.mark.asyncio
async def test_script_overrides_events_and_result():
    custom_events: list[Any] = []  # Will be populated by the script.

    async def script(execution, workspace_context, options):
        events = [
            CodingAgentInvokedEvent(
                type="coding_agent.invoked",
                timestamp="2026-01-01T00:00:00+00:00",
                source="mock_claude_code",
                execution_id=execution.id,
                coding_agent_id="claude-code",
                invocation_mode=options.invocation_mode.value,
                model=options.model,
            ),
        ]
        custom_events.extend(events)
        result = CodingAgentResult(
            success=True,
            summary_text="scripted",
            total_cost_usd=Decimal("0"),
            total_input_tokens=0,
            total_output_tokens=0,
            tool_call_count=0,
            duration_ms=0,
            error_summary=None,
        )
        return events, result

    bus = EventBus()
    captured: list[Any] = []
    bus.subscribe(None, lambda e: captured.append(e))
    adapter = MockClaudeCodeAdapter(event_bus=bus, script=script)

    result = await adapter.execute(_execution(), _ws(), _options())
    assert result.summary_text == "scripted"
    # Only the scripted single event was published.
    assert len(captured) == 1
    assert isinstance(captured[0], CodingAgentInvokedEvent)
