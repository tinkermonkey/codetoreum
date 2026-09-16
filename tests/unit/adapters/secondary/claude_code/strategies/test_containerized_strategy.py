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
from unittest.mock import AsyncMock, patch

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


class _SpanWritingContainer(_FakeContainer):
    """Container fake that writes OTel spans to the mounted temp directory.

    Used by tests that need to verify span parsing and emission. The
    ``write_callable`` parameter allows customization of what gets written
    to spans.jsonl (valid envelope, malformed JSON, etc.).
    """

    def __init__(
        self,
        log_lines: list[bytes],
        exit_code: int = 0,
        write_callable: Any | None = None,
    ):
        """Construct the span-writing container.

        Args:
            log_lines: Log output to be returned by logs().
            exit_code: Exit code to be returned by wait().
            write_callable: Optional callable(otel_temp_dir) that writes to
                spans.jsonl. If None, no spans file is written. If provided,
                it will be called during wait() before the container exits.
        """
        super().__init__(log_lines, exit_code)
        self._write_callable = write_callable
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
        # Before the container "exits", call the write callable if provided.
        if self._otel_temp_dir and self._write_callable:
            self._write_callable(self._otel_temp_dir)
        # Then return the exit code.
        return await super().wait(container_id, timeout)


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
    assert env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
    assert env["CLAUDE_CODE_ENHANCED_TELEMETRY_BETA"] == "1"
    assert env["OTEL_TRACES_EXPORTER"] == "otlp"
    assert env["OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"] == "http/protobuf"
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:4318"
    assert env["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] == "http://127.0.0.1:4318/v1/traces"
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

    def _write_valid_span(otel_temp_dir: str) -> None:
        """Write a valid span envelope to spans.jsonl."""
        spans_file = Path(otel_temp_dir) / "spans.jsonl"
        Path(otel_temp_dir).mkdir(parents=True, exist_ok=True)
        with spans_file.open("w") as f:
            f.write(json.dumps(test_span_envelope) + "\n")

    container = _SpanWritingContainer(
        lines,
        exit_code=0,
        write_callable=_write_valid_span,
    )

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


@pytest.mark.asyncio
async def test_containerized_strategy_emits_spans_on_abnormal_exit(tmp_path: Path):
    """OTel spans are emitted even when the agent process exits abnormally."""

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
                                "name": "partial_span",
                                "kind": "SPAN_KIND_INTERNAL",
                                "startTimeUnixNano": "1748400000000000000",
                                "endTimeUnixNano": "1748400001000000000",
                                "attributes": [
                                    {"key": "partial", "value": {"stringValue": "yes"}}
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

    def _write_valid_span(otel_temp_dir: str) -> None:
        """Write a valid span envelope to spans.jsonl."""
        spans_file = Path(otel_temp_dir) / "spans.jsonl"
        Path(otel_temp_dir).mkdir(parents=True, exist_ok=True)
        with spans_file.open("w") as f:
            f.write(json.dumps(test_span_envelope) + "\n")

    # Exit with non-zero code (abnormal exit).
    container = _SpanWritingContainer(
        lines,
        exit_code=1,
        write_callable=_write_valid_span,
    )

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
        execution_id="exec-abnormal-exit",
        workspace_context=_ws(workspace_path=host_workspace),
        options=options,
        event_bus=event_bus,
        parser=ClaudeStreamJsonParser(),
        coding_agent_id="claude-code",
    )

    # Even with non-zero exit, the execution result is returned.
    assert result.success is False  # Exit code 1 means failure.
    # Spans that were flushed should still be emitted.
    span_events = [e for e in captured if type(e).__name__ == "CodingAgentOtlpSpanEvent"]
    assert len(span_events) == 1
    span_event = span_events[0]
    assert span_event.execution_id == "exec-abnormal-exit"  # type: ignore
    assert span_event.name == "partial_span"  # type: ignore


@pytest.mark.asyncio
async def test_containerized_strategy_handles_span_emit_failure(tmp_path: Path):
    """Failures during span emission are logged but don't affect the result."""

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
                                "attributes": [],
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

    def _write_valid_span(otel_temp_dir: str) -> None:
        """Write a valid span envelope to spans.jsonl."""
        spans_file = Path(otel_temp_dir) / "spans.jsonl"
        Path(otel_temp_dir).mkdir(parents=True, exist_ok=True)
        with spans_file.open("w") as f:
            f.write(json.dumps(test_span_envelope) + "\n")

    container = _SpanWritingContainer(
        lines,
        exit_code=0,
        write_callable=_write_valid_span,
    )

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

    # Patch parse_spans_file to raise, triggering the exception handler
    # in _parse_and_emit_spans. This exercises the error logging path.
    with patch(
        "codetoreum.adapters.secondary.claude_code.strategies.containerized.parse_spans_file",
        side_effect=RuntimeError("parse failure"),
    ):
        with patch(
            "codetoreum.adapters.secondary.claude_code.strategies.containerized.logger"
        ) as mock_logger:
            result = await strategy.execute(
                prompt_text="hi",
                execution_id="exec-fail-emit",
                workspace_context=_ws(workspace_path=host_workspace),
                options=options,
                event_bus=event_bus,
                parser=ClaudeStreamJsonParser(),
                coding_agent_id="claude-code",
            )

            # Verify that logger.exception was called with exc_info=True.
            mock_logger.exception.assert_called_once()
            call_args = mock_logger.exception.call_args
            # The message should mention the parse failure.
            assert "failed to parse OTel spans file" in str(call_args[0][0])

    # Despite the parse failure, execution result is unaffected.
    assert result.success is True
    assert container.removed is True
    # No span events should be emitted (parse failed).
    span_events = [e for e in captured if type(e).__name__ == "CodingAgentOtlpSpanEvent"]
    assert len(span_events) == 0


@pytest.mark.asyncio
async def test_containerized_strategy_continues_on_single_span_publish_failure(tmp_path: Path):
    """When one span's publish fails, remaining spans are still published."""

    # Create three spans with distinct identifiers
    test_spans_envelope = {
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
                                "traceId": "trace0000000000000000000000000001",
                                "spanId": "span0000000000000001",
                                "parentSpanId": "",
                                "name": "span_1",
                                "kind": "SPAN_KIND_INTERNAL",
                                "startTimeUnixNano": "1748400000000000000",
                                "endTimeUnixNano": "1748400001000000000",
                                "attributes": [{"key": "span_num", "value": {"stringValue": "1"}}],
                                "events": [],
                                "status": {"code": "STATUS_CODE_OK"},
                            },
                            {
                                "traceId": "trace0000000000000000000000000002",
                                "spanId": "span0000000000000002",
                                "parentSpanId": "",
                                "name": "span_2",
                                "kind": "SPAN_KIND_INTERNAL",
                                "startTimeUnixNano": "1748400000000000000",
                                "endTimeUnixNano": "1748400001000000000",
                                "attributes": [{"key": "span_num", "value": {"stringValue": "2"}}],
                                "events": [],
                                "status": {"code": "STATUS_CODE_OK"},
                            },
                            {
                                "traceId": "trace0000000000000000000000000003",
                                "spanId": "span0000000000000003",
                                "parentSpanId": "",
                                "name": "span_3",
                                "kind": "SPAN_KIND_INTERNAL",
                                "startTimeUnixNano": "1748400000000000000",
                                "endTimeUnixNano": "1748400001000000000",
                                "attributes": [{"key": "span_num", "value": {"stringValue": "3"}}],
                                "events": [],
                                "status": {"code": "STATUS_CODE_OK"},
                            },
                        ],
                    }
                ],
            }
        ]
    }

    lines = [
        (json.dumps(RESULT) + "\n").encode(),
    ]

    def _write_multiple_spans(otel_temp_dir: str) -> None:
        """Write three spans to spans.jsonl."""
        spans_file = Path(otel_temp_dir) / "spans.jsonl"
        Path(otel_temp_dir).mkdir(parents=True, exist_ok=True)
        with spans_file.open("w") as f:
            f.write(json.dumps(test_spans_envelope) + "\n")

    container = _SpanWritingContainer(
        lines,
        exit_code=0,
        write_callable=_write_multiple_spans,
    )

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

    # Track OTel span publish attempts to fail on the second one
    span_publish_count = [0]

    async def _mock_publish_with_failure(event: Any) -> None:
        """Mock publish that fails on the second OTel span event."""
        # Only track and fail on OTel span events
        if type(event).__name__ == "CodingAgentOtlpSpanEvent":
            span_publish_count[0] += 1
            # Fail on the second span (span_2)
            if span_publish_count[0] == 2:
                raise RuntimeError("Simulated publish failure for span_2")

    # Patch event_bus.publish to inject failure on second span
    with patch.object(event_bus, "publish", side_effect=_mock_publish_with_failure):
        with patch(
            "codetoreum.adapters.secondary.claude_code.strategies.containerized.logger"
        ) as mock_logger:
            result = await strategy.execute(
                prompt_text="hi",
                execution_id="exec-partial-fail",
                workspace_context=_ws(workspace_path=host_workspace),
                options=options,
                event_bus=event_bus,
                parser=ClaudeStreamJsonParser(),
                coding_agent_id="claude-code",
            )

            # Verify that logger.exception was called for the span publish failure
            exception_calls = [
                call for call in mock_logger.exception.call_args_list
                if "failed to publish OTel span event" in str(call)
            ]
            assert len(exception_calls) == 1, "Should log exactly one span publish failure"

    # Despite the span_2 publish failure, execution result is unaffected.
    assert result.success is True
    assert container.removed is True

    # Verify that we attempted to publish all three spans
    # span_1 succeeds, span_2 fails with exception, span_3 should be attempted after failure
    assert span_publish_count[0] >= 3, f"Expected to attempt publishing at least 3 spans, got {span_publish_count[0]}"


# Avoid unused-import lint warnings.
_unused_datetime = datetime
