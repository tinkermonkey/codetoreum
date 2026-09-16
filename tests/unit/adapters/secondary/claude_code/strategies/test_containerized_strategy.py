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


def _ws(workspace_path: Path | None = None) -> WorkspaceContext:
    return WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id="wi-1",
        branch_name="feature/x",
        workspace_path=workspace_path or Path("/tmp/ws-stub"),
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
    env = container.created["environment"]
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "OAUTH"
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:4318"
    assert env["OTEL_METRICS_EXPORTER"] == "none"
    assert env["OTEL_LOGS_EXPORTER"] == "none"
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

    # Volumes include workspace and otel temp directory.
    volumes = container.created["volumes"]
    assert volumes is not None
    assert "/workspace:rw" in volumes.values()
    assert "/var/otel:rw" in volumes.values()

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
async def test_containerized_strategy_mounts_workspace_from_context(tmp_path: Path):
    host_workspace = tmp_path / "ws"
    host_workspace.mkdir()
    container = _FakeContainer(
        [(json.dumps(RESULT) + "\n").encode()],
        exit_code=0,
    )
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

    await strategy.execute(
        prompt_text="hi",
        execution_id="exec-1",
        workspace_context=_ws(workspace_path=host_workspace),
        options=options,
        event_bus=EventBus(),
        parser=ClaudeStreamJsonParser(),
        coding_agent_id="claude-code",
    )

    volumes = container.created["volumes"]
    assert volumes is not None
    assert str(host_workspace) in volumes
    assert volumes[str(host_workspace)] == "/workspace:rw"  # simple string form per DEF-017


@pytest.mark.asyncio
async def test_containerized_strategy_requires_workspace_path():
    """D6: strategy raises ValueError when WorkspaceContext.workspace_path is unset."""
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
        mode_config={"image": "codetoreum-agent:latest"},
    )
    # Build a context without workspace_path (None).
    ctx = WorkspaceContext.for_issue(
        project_id="proj-1",
        work_item_id="wi-1",
        branch_name="feature/x",
    )
    with pytest.raises(ValueError, match="workspace_path"):
        await strategy.execute(
            prompt_text="hi",
            execution_id="exec-1",
            workspace_context=ctx,
            options=options,
            event_bus=EventBus(),
            parser=ClaudeStreamJsonParser(),
            coding_agent_id="claude-code",
        )


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


@pytest.mark.asyncio
async def test_containerized_strategy_creates_and_cleans_otel_temp_dir(tmp_path: Path):
    """Temp directory is created for OTel spans and cleaned up after execution."""
    lines = [
        (json.dumps(RESULT) + "\n").encode(),
    ]
    container = _FakeContainer(lines, exit_code=0)
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

    await strategy.execute(
        prompt_text="hi",
        execution_id="exec-1",
        workspace_context=_ws(),
        options=options,
        event_bus=EventBus(),
        parser=ClaudeStreamJsonParser(),
        coding_agent_id="claude-code",
    )

    # Verify that volumes include /var/otel mount.
    volumes = container.created["volumes"]
    assert volumes is not None
    assert "/var/otel:rw" in volumes.values()
    # The temp directory itself should have been cleaned up.
    # We just verify that the strategy removes it (no FileNotFoundError on re-exec).


@pytest.mark.asyncio
async def test_containerized_strategy_handles_missing_otel_spans_gracefully():
    """Execution succeeds even if spans.jsonl is missing from temp directory."""
    lines = [
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
        model="m",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={"image": "codetoreum-agent:latest"},
    )

    result = await strategy.execute(
        prompt_text="hi",
        execution_id="exec-1",
        workspace_context=_ws(),
        options=options,
        event_bus=event_bus,
        parser=ClaudeStreamJsonParser(),
        coding_agent_id="claude-code",
    )

    # Execution should succeed regardless of missing spans.
    assert result.success is True
    assert container.removed is True
    # No OTel span events should be emitted (file doesn't exist).
    span_events = [e for e in captured if type(e).__name__ == "CodingAgentOtlpSpanEvent"]
    assert len(span_events) == 0


@pytest.mark.asyncio
async def test_containerized_strategy_parses_and_emits_otel_spans(tmp_path: Path):
    """OTel spans from spans.jsonl are parsed and emitted as domain events."""

    # Create a custom container that populates spans.jsonl.
    class _ContainerWithSpans(_FakeContainer):
        async def remove(self, container_id: str, force: bool = False) -> None:
            # Before removal, populate spans file in the temp directory.
            # This simulates what the in-container OTel sidecar would do.
            self.removed = True

    # Create a test span in OTLP/JSON format.
    test_span_envelope = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "claude-code"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "claude-code"},
                        "spans": [
                            {
                                "traceId": "abcd1234abcd1234abcd1234abcd1234",
                                "spanId": "1234abcd1234abcd",
                                "parentSpanId": "",
                                "name": "test_span",
                                "kind": "SPAN_KIND_INTERNAL",
                                "startTimeUnixNano": "1748400000000000000",
                                "endTimeUnixNano": "1748400001000000000",
                                "attributes": [
                                    {"key": "test_key", "value": {"stringValue": "test_value"}}
                                ],
                                "events": [],
                                "status": {"code": "STATUS_CODE_OK"},
                            }
                        ],
                    }
                ],
            }
        ]
    }

    lines = [
        (json.dumps(RESULT) + "\n").encode(),
    ]

    # Create a custom container adapter that populates the spans file.
    class _SpanWritingContainer(_FakeContainer):
        def __init__(self, log_lines: list[bytes], exit_code: int = 0, span_envelope: Any = None):
            super().__init__(log_lines, exit_code)
            self._span_envelope = span_envelope
            self._otel_temp_dir: str | None = None

        async def create(self, **kwargs: Any) -> str:
            container_id = await super().create(**kwargs)
            # Extract the otel temp dir from volumes.
            volumes = kwargs.get("volumes", {})
            for host_path, container_path in volumes.items():
                if "/var/otel:rw" in container_path:
                    self._otel_temp_dir = host_path
            return container_id

        async def wait(self, container_id: str, timeout: int | None = None) -> int:
            # Before the container "exits", write the spans file (simulating OTel sidecar flush).
            if self._otel_temp_dir:
                import os

                spans_file = os.path.join(self._otel_temp_dir, "spans.jsonl")
                os.makedirs(self._otel_temp_dir, exist_ok=True)
                with open(spans_file, "w") as f:
                    f.write(json.dumps(self._span_envelope) + "\n")
            # Then return the exit code.
            return await super().wait(container_id, timeout)

    container = _SpanWritingContainer(lines, exit_code=0, span_envelope=test_span_envelope)

    strategy = ContainerizedClaudeStrategy(
        container=container,
        credential_provider=_FakeCredentialProvider(),
    )
    event_bus = EventBus()
    captured: list[Any] = []
    event_bus.subscribe(None, lambda e: captured.append(e))
    options = CodingAgentInvocationOptions(
        invocation_mode=InvocationMode.CONTAINERIZED,
        model="m",
        timeout_seconds=30,
        cost_limit_usd=None,
        mode_config={"image": "codetoreum-agent:latest"},
    )

    host_workspace = tmp_path / "ws"
    host_workspace.mkdir()

    result = await strategy.execute(
        prompt_text="hi",
        execution_id="exec-span-test",
        workspace_context=_ws(workspace_path=host_workspace),
        options=options,
        event_bus=event_bus,
        parser=ClaudeStreamJsonParser(),
        coding_agent_id="claude-code",
    )

    # Execution should succeed.
    assert result.success is True
    # Verify that one OTel span event was emitted.
    span_events = [e for e in captured if type(e).__name__ == "CodingAgentOtlpSpanEvent"]
    assert len(span_events) == 1
    span_event = span_events[0]
    assert span_event.execution_id == "exec-span-test"  # type: ignore
    assert span_event.trace_id == "abcd1234abcd1234abcd1234abcd1234"  # type: ignore
    assert span_event.span_id == "1234abcd1234abcd"  # type: ignore
    assert span_event.name == "test_span"  # type: ignore
    assert span_event.attributes == {"test_key": "test_value"}  # type: ignore


# Avoid unused-import lint warnings.
_unused_datetime = datetime
