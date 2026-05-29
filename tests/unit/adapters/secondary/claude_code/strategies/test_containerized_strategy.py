"""Unit tests for :class:`ContainerizedClaudeStrategy`.

The strategy is exercised against a hand-rolled fake :class:`IContainer`
so the test asserts container-config, mount, and log-stream pumping
without spinning up Docker.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from codetoreum.adapters.secondary.claude_code.strategies.containerized import (
    ContainerizedClaudeStrategy,
)
from codetoreum.adapters.secondary.claude_code.stream_parser import (
    ClaudeStreamJsonParser,
)
from codetoreum.domain.events.coding_agent_events import (
    CodingAgentCompletedEvent,
    CodingAgentInvokedEvent,
)
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    InvocationMode,
)


class _FakeCredentialProvider:
    async def get_credential(self, key: str) -> str | None:
        if key == "CLAUDE_CODE_OAUTH_TOKEN":
            return "OAUTH"
        return None


def _ws() -> WorkspaceContext:
    return WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id="wi-1",
        branch_name="feature/x",
    )


INIT = {
    "type": "system",
    "subtype": "init",
    "session_id": "s",
    "model": "claude-haiku-4-5",
}
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "duration_ms": 800,
    "result": "ok",
    "stop_reason": "end_turn",
    "total_cost_usd": 0.02,
    "usage": {"input_tokens": 1, "output_tokens": 2},
}


class _FakeContainer:
    """In-memory IContainer-compatible fake for strategy tests."""

    def __init__(self, log_lines: list[bytes], exit_code: int = 0):
        self._log_lines = log_lines
        self._exit_code = exit_code
        self.created: dict[str, Any] = {}
        self.started = False
        self.removed = False
        self.killed = False

    async def create(
        self,
        *,
        image: str,
        name: str | None = None,
        command: Any = None,
        volumes: Any = None,
        environment: Any = None,
        working_dir: str | None = None,
        user: str | None = None,
        network: str | None = None,
        labels: dict[str, str] | None = None,
    ) -> str:
        self.created = {
            "image": image,
            "name": name,
            "command": command,
            "volumes": volumes,
            "environment": environment,
            "working_dir": working_dir,
            "network": network,
            "labels": labels,
        }
        return "container-1"

    async def start(self, container_id: str) -> None:
        self.started = True

    async def logs(self, container_id: str, *, stream: bool = False, follow: bool = False, **_) -> Any:
        async def _gen() -> AsyncIterator[str]:
            for line in self._log_lines:
                if isinstance(line, bytes):
                    yield line.decode("utf-8")
                else:
                    yield line

        return _gen()

    async def wait(self, container_id: str, timeout: int | None = None) -> int:
        return self._exit_code

    async def remove(self, container_id: str, force: bool = False) -> None:
        self.removed = True

    async def kill(self, container_id: str, signal: str = "SIGKILL") -> None:
        self.killed = True


@pytest.mark.asyncio
async def test_containerized_strategy_full_pipeline():
    lines = [
        (json.dumps(INIT) + "\n").encode(),
        (json.dumps(RESULT) + "\n").encode(),
    ]
    container = _FakeContainer(lines, exit_code=0)
    strategy = ContainerizedClaudeStrategy(
        container=container,
        credential_provider=_FakeCredentialProvider(),
    )
    event_bus = EventBus()
    captured: list[Any] = []
    event_bus.subscribe(None, lambda e: captured.append(e))

    options = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.CONTAINERIZED,
        model="claude-haiku-4-5",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={
            "image": "codetoreum-agent:latest",
            "network": "bridge",
        },
    )

    result = await strategy.execute(
        prompt_text="prompt body",
        execution_id="exec-1",
        workspace_context=_ws(),
        options=options,
        event_bus=event_bus,
        parser=ClaudeStreamJsonParser(),
        coding_agent_id="claude-code",
    )

    # Container lifecycle:
    assert container.created["image"] == "codetoreum-agent:latest"
    assert container.created["network"] == "bridge"
    assert container.created["working_dir"] == "/workspace"
    assert container.created["environment"] == {"CLAUDE_CODE_OAUTH_TOKEN": "OAUTH"}
    cmd = container.created["command"]
    assert "--print" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--model" in cmd
    assert "claude-haiku-4-5" in cmd
    assert cmd[-1] == "prompt body"
    labels = container.created["labels"]
    assert labels["codetoreum.execution_id"] == "exec-1"
    assert labels["codetoreum.work_item_id"] == "wi-1"
    assert labels["codetoreum.adapter"] == "claude-code"

    assert container.started is True
    assert container.removed is True

    # Result:
    assert result.success is True
    assert result.summary_text == "ok"
    assert result.total_cost_usd == Decimal("0.02")

    # Events:
    types = [type(e).__name__ for e in captured]
    assert "CodingAgentInvokedEvent" in types
    assert "CodingAgentCompletedEvent" in types
    invoked = next(e for e in captured if isinstance(e, CodingAgentInvokedEvent))
    assert invoked.invocation_mode == "containerized"
    completed = next(e for e in captured if isinstance(e, CodingAgentCompletedEvent))
    assert completed.success is True


@pytest.mark.asyncio
async def test_containerized_strategy_requires_image():
    container = _FakeContainer([], exit_code=0)
    strategy = ContainerizedClaudeStrategy(
        container=container,
        credential_provider=_FakeCredentialProvider(),
    )
    options = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.CONTAINERIZED,
        model="m",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={},  # missing image
    )
    with pytest.raises(ValueError, match="image"):
        await strategy.execute(
            prompt_text="hi",
            execution_id="exec-1",
            workspace_context=_ws(),
            options=options,
            event_bus=EventBus(),
            parser=ClaudeStreamJsonParser(),
            coding_agent_id="claude-code",
        )
    assert container.removed is False  # never created — nothing to remove


@pytest.mark.asyncio
async def test_containerized_strategy_mounts_workspace_when_resolver_provided(tmp_path: Path):
    host_workspace = tmp_path / "ws"
    host_workspace.mkdir()
    container = _FakeContainer(
        [(json.dumps(RESULT) + "\n").encode()],
        exit_code=0,
    )
    strategy = ContainerizedClaudeStrategy(
        container=container,
        credential_provider=_FakeCredentialProvider(),
        workspace_path_resolver=lambda _ctx: host_workspace,
    )
    options = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.CONTAINERIZED,
        model="m",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={"image": "codetoreum-agent:latest"},
    )

    await strategy.execute(
        prompt_text="hi",
        execution_id="exec-1",
        workspace_context=_ws(),
        options=options,
        event_bus=EventBus(),
        parser=ClaudeStreamJsonParser(),
        coding_agent_id="claude-code",
    )

    volumes = container.created["volumes"]
    assert volumes is not None
    assert str(host_workspace) in volumes
    assert volumes[str(host_workspace)] == {"bind": "/workspace", "mode": "rw"}


@pytest.mark.asyncio
async def test_containerized_strategy_removes_container_on_failure():
    """Container is removed even if the stream raises."""

    class _BrokenContainer(_FakeContainer):
        async def logs(self, container_id: str, *, stream: bool = False, follow: bool = False, **_) -> Any:
            raise RuntimeError("kaboom")

    container = _BrokenContainer([], exit_code=0)
    strategy = ContainerizedClaudeStrategy(
        container=container,
        credential_provider=_FakeCredentialProvider(),
    )
    options = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.CONTAINERIZED,
        model="m",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={"image": "codetoreum-agent:latest"},
    )
    with pytest.raises(RuntimeError, match="kaboom"):
        await strategy.execute(
            prompt_text="hi",
            execution_id="exec-1",
            workspace_context=_ws(),
            options=options,
            event_bus=EventBus(),
            parser=ClaudeStreamJsonParser(),
            coding_agent_id="claude-code",
        )
    assert container.removed is True


# Avoid unused-import lint warnings.
_unused_datetime = datetime
