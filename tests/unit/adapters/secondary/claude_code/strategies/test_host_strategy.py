"""Unit tests for :class:`HostClaudeStrategy`.

The strategy is exercised against a mocked ``asyncio.subprocess`` so we
can drive the parser without spawning a real process.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from codetoreum.adapters.secondary.claude_code.strategies.host import (
    HostClaudeStrategy,
)
from codetoreum.adapters.secondary.claude_code.stream_parser import (
    ClaudeStreamJsonParser,
)
from codetoreum.domain.events.coding_agent_events import (
    CodingAgentCompletedEvent,
    CodingAgentInvokedEvent,
    CodingAgentReadyEvent,
    CodingAgentToolCallEvent,
)
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    InvocationMode,
)


class _FakeCredentialProvider:
    def __init__(self, oauth: str | None = "oauth-tok", api_key: str | None = None):
        self._oauth = oauth
        self._api_key = api_key

    async def get_credential(self, key: str) -> str | None:
        if key == "CLAUDE_CODE_OAUTH_TOKEN":
            return self._oauth
        if key == "ANTHROPIC_API_KEY":
            return self._api_key
        return None


def _ws(workspace_path: Path | None = None) -> WorkspaceContext:
    return WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id="wi-1",
        branch_name="feature/x",
        workspace_path=workspace_path or Path("/tmp/ws-stub"),
    )


def _opts() -> CodingAgentInvocationOptions:
    return CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.HOST,
        model="claude-haiku-4-5",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={},
    )


# Canned stream-json frames (subset; full coverage lives in
# tests/unit/adapters/secondary/claude_code/test_stream_parser.py).
INIT = {
    "type": "system",
    "subtype": "init",
    "session_id": "s",
    "model": "claude-haiku-4-5",
}
TOOL_USE = {
    "type": "assistant",
    "message": {
        "id": "msg1",
        "content": [
            {"type": "tool_use", "id": "tu1", "name": "Bash", "input": {"command": "ls"}},
        ],
    },
}
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "duration_ms": 500,
    "result": "ok",
    "stop_reason": "end_turn",
    "total_cost_usd": 0.01,
    "usage": {"input_tokens": 5, "output_tokens": 7},
}


class _FakeProcessStdout:
    """Async readline reader that yields canned bytes lines."""

    def __init__(self, lines: list[bytes]):
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _FakeProcess:
    def __init__(self, stdout_lines: list[bytes], exit_code: int = 0):
        self.stdout = _FakeProcessStdout(stdout_lines)
        self.stderr = _FakeProcessStdout([])
        self.pid = 12345
        self.returncode: int | None = None
        self._exit_code = exit_code
        self.kill_called = False

    async def wait(self) -> int:
        self.returncode = self._exit_code
        return self._exit_code

    def kill(self) -> None:
        self.kill_called = True
        self.returncode = -9


@pytest.mark.asyncio
async def test_host_strategy_emits_events_and_returns_result(monkeypatch):
    lines = [
        (json.dumps(INIT) + "\n").encode(),
        (json.dumps(TOOL_USE) + "\n").encode(),
        (json.dumps(RESULT) + "\n").encode(),
    ]
    fake_proc = _FakeProcess(lines, exit_code=0)

    async def fake_create(*args: Any, **kwargs: Any) -> Any:
        return fake_proc

    strategy = HostClaudeStrategy(credential_provider=_FakeCredentialProvider())
    event_bus = EventBus()
    parser = ClaudeStreamJsonParser()

    captured: list[Any] = []

    async def capture(event: Any) -> None:
        captured.append(event)

    event_bus.subscribe(None, capture)

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=fake_create)):
        result = await strategy.execute(
            prompt_text="hi",
            execution_id="exec-1",
            workspace_context=_ws(),
            options=_opts(),
            event_bus=event_bus,
            parser=parser,
            coding_agent_id="claude-code",
        )

    assert result.success is True
    assert result.tool_call_count == 1
    assert result.summary_text == "ok"
    assert result.total_cost_usd == Decimal("0.01")

    # Event ordering and presence:
    types = [type(e).__name__ for e in captured]
    assert "CodingAgentInvokedEvent" in types
    assert "CodingAgentReadyEvent" in types
    assert "CodingAgentToolCallEvent" in types
    assert "CodingAgentCompletedEvent" in types
    # The invoked event carries the correct invocation_mode.
    invoked = next(e for e in captured if isinstance(e, CodingAgentInvokedEvent))
    assert invoked.invocation_mode == "host"
    assert invoked.model == "claude-haiku-4-5"
    # Correlation id = work_item_id.
    assert all(getattr(e, "correlation_id", "wi-1") == "wi-1" for e in captured)


@pytest.mark.asyncio
async def test_host_strategy_synthesises_result_when_stream_lacks_result():
    """If the stream ends without a `result` event, build a result from exit code."""
    lines = [(json.dumps(INIT) + "\n").encode()]
    fake_proc = _FakeProcess(lines, exit_code=2)

    async def fake_create(*args: Any, **kwargs: Any) -> Any:
        return fake_proc

    strategy = HostClaudeStrategy(credential_provider=_FakeCredentialProvider())
    event_bus = EventBus()
    parser = ClaudeStreamJsonParser()

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=fake_create)):
        result = await strategy.execute(
            prompt_text="hi",
            execution_id="exec-1",
            workspace_context=_ws(),
            options=_opts(),
            event_bus=event_bus,
            parser=parser,
            coding_agent_id="claude-code",
        )

    assert result.success is False
    assert "exit_code=2" in (result.error_summary or "")


@pytest.mark.asyncio
async def test_host_strategy_oauth_preferred_over_api_key(monkeypatch):
    """OAuth wins when both credentials are available — only OAuth env is set."""
    # Clear both credential env vars on the *parent* process so the strategy's
    # env-copy doesn't smuggle real-world values into the assertion.
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    captured_env: dict[str, str] = {}

    async def fake_create(*args: Any, **kwargs: Any) -> Any:
        captured_env.update(kwargs.get("env", {}))
        return _FakeProcess([(json.dumps(RESULT) + "\n").encode()], exit_code=0)

    strategy = HostClaudeStrategy(
        credential_provider=_FakeCredentialProvider(oauth="OAUTH", api_key="APIK"),
    )

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=fake_create)):
        await strategy.execute(
            prompt_text="hi",
            execution_id="exec-1",
            workspace_context=_ws(),
            options=_opts(),
            event_bus=EventBus(),
            parser=ClaudeStreamJsonParser(),
            coding_agent_id="claude-code",
        )

    assert captured_env.get("CLAUDE_CODE_OAUTH_TOKEN") == "OAUTH"
    assert "ANTHROPIC_API_KEY" not in captured_env


@pytest.mark.asyncio
async def test_host_strategy_api_key_fallback_when_no_oauth(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    captured_env: dict[str, str] = {}

    async def fake_create(*args: Any, **kwargs: Any) -> Any:
        captured_env.update(kwargs.get("env", {}))
        return _FakeProcess([(json.dumps(RESULT) + "\n").encode()], exit_code=0)

    strategy = HostClaudeStrategy(
        credential_provider=_FakeCredentialProvider(oauth=None, api_key="APIK"),
    )

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=fake_create)):
        await strategy.execute(
            prompt_text="hi",
            execution_id="exec-1",
            workspace_context=_ws(),
            options=_opts(),
            event_bus=EventBus(),
            parser=ClaudeStreamJsonParser(),
            coding_agent_id="claude-code",
        )

    assert captured_env.get("ANTHROPIC_API_KEY") == "APIK"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in captured_env


@pytest.mark.asyncio
async def test_host_strategy_builds_expected_command():
    captured_argv: list[Any] = []

    async def fake_create(*args: Any, **kwargs: Any) -> Any:
        captured_argv.extend(args)
        return _FakeProcess([(json.dumps(RESULT) + "\n").encode()], exit_code=0)

    strategy = HostClaudeStrategy(
        credential_provider=_FakeCredentialProvider(),
        claude_cli_path="/usr/bin/claude",
    )

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=fake_create)):
        await strategy.execute(
            prompt_text="prompt-body",
            execution_id="exec-1",
            workspace_context=_ws(),
            options=CodingAgentInvocationOptions(
                invocation_mode=InvocationMode.HOST,
                model="claude-sonnet-4-6",
                timeout_seconds=60,
                cost_limit_usd=None,
                mode_config={},
            ),
            event_bus=EventBus(),
            parser=ClaudeStreamJsonParser(),
            coding_agent_id="claude-code",
        )

    assert captured_argv[0] == "/usr/bin/claude"
    assert "--print" in captured_argv
    assert "--output-format" in captured_argv
    assert "stream-json" in captured_argv
    assert "--permission-mode" in captured_argv
    assert "bypassPermissions" in captured_argv
    assert "--verbose" in captured_argv
    assert "--model" in captured_argv
    assert "claude-sonnet-4-6" in captured_argv
    # Prompt is the final positional argument.
    assert captured_argv[-1] == "prompt-body"
