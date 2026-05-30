"""Host-mode invocation strategy: run ``claude`` directly via subprocess.

No container. The subprocess runs in ``WorkspaceContext.workspace_path``,
which the orchestrator populates via
``WorkspaceContext.with_workspace_path()`` after the repository clone.

If ``workspace_path`` is ``None`` at execute time the strategy raises
``ValueError`` — the orchestrator is expected to always provide it.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from codetoreum.adapters.secondary.claude_code.strategies.base import (
    ClaudeInvocationStrategy,
)
from codetoreum.adapters.secondary.claude_code.stream_parser import (
    ClaudeStreamJsonParser,
)
from codetoreum.domain.events.coding_agent_events import (
    CodingAgentCompletedEvent,
    CodingAgentToolCallEvent,
)
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
)

logger = logging.getLogger(__name__)


# Credentials provider protocol (kept structural to avoid an extra import
# dependency on the legacy adapter package, which is removed in D5).
class CredentialProviderProtocol:
    """Minimal contract for credential providers used by the strategies."""

    async def get_credential(self, key: str) -> str | None:  # pragma: no cover - protocol
        raise NotImplementedError


class HostClaudeStrategy(ClaudeInvocationStrategy):
    """Run ``claude --print`` directly on the host as a subprocess."""

    def __init__(
        self,
        *,
        credential_provider: CredentialProviderProtocol,
        claude_cli_path: str = "claude",
        api_key_credential_name: str = "ANTHROPIC_API_KEY",
        oauth_token_credential_name: str = "CLAUDE_CODE_OAUTH_TOKEN",  # noqa: S107
    ) -> None:
        """Construct the host strategy.

        Args:
            credential_provider: Resolves ``ANTHROPIC_API_KEY`` /
                ``CLAUDE_CODE_OAUTH_TOKEN`` at execute time.
            claude_cli_path: Path to the ``claude`` binary. Defaults to
                ``"claude"`` (resolved on ``$PATH``).
            api_key_credential_name: Credential key for the API key
                fallback path.
            oauth_token_credential_name: Credential key for the OAuth
                token (preferred).
        """
        self._credential_provider = credential_provider
        self._claude_cli_path = claude_cli_path
        self._api_key_credential_name = api_key_credential_name
        self._oauth_token_credential_name = oauth_token_credential_name

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
        """Spawn ``claude`` and pump its stdout through the parser."""
        cmd = self._build_command(prompt_text=prompt_text, options=options)
        env = await self._build_environment()
        cwd = self._resolve_cwd(workspace_context)

        start = datetime.now(UTC)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(cwd),
        )
        logger.info(
            "HostClaudeStrategy: spawned PID=%s execution_id=%s cwd=%s",
            process.pid,
            execution_id,
            cwd,
        )

        try:
            return await _stream_and_collect(
                process_stdout=_iter_stdout(process),
                process_stderr_reader=_drain_stderr(process),
                wait_process=process.wait,
                parser=parser,
                event_bus=event_bus,
                execution_id=execution_id,
                coding_agent_id=coding_agent_id,
                workspace_context=workspace_context,
                options=options,
                start=start,
                timeout_seconds=options.timeout_seconds,
                kill=_kill_subprocess_factory(process),
            )
        except BaseException:
            # Best-effort cleanup; never let the parent task die holding the
            # subprocess open.
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            raise

    # ------------------------------------------------------------------
    # Command + env construction
    # ------------------------------------------------------------------

    def _build_command(
        self,
        *,
        prompt_text: str,
        options: CodingAgentInvocationOptions,
    ) -> list[str]:
        cmd = [
            self._claude_cli_path,
            "--print",
            "--output-format",
            "stream-json",
            "--permission-mode",
            "bypassPermissions",
            "--model",
            options.model,
            # --verbose is required by the CLI when --output-format=stream-json
            # is combined with --print.
            "--verbose",
            prompt_text,
        ]
        return cmd

    async def _build_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        api_key = await self._credential_provider.get_credential(
            self._api_key_credential_name,
        )
        oauth_token = await self._credential_provider.get_credential(
            self._oauth_token_credential_name,
        )
        if oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
        elif api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        # No-credentials case: we still launch — the CLI will print a clear
        # auth error which the parser will surface as a CompletedEvent with
        # error_summary. This mirrors the existing adapter's behaviour to
        # avoid double-reporting.
        return env

    def _resolve_cwd(self, workspace_context: WorkspaceContext) -> Path:
        """Return the host directory the subprocess must run in.

        Raises:
            ValueError: If ``workspace_context.workspace_path`` is unset.
                D6 requires the orchestrator to populate this field
                before dispatching execution.
        """
        if workspace_context.workspace_path is None:
            msg = (
                "HostClaudeStrategy requires workspace_context.workspace_path "
                f"(work_item_id={workspace_context.work_item_id!r}); the orchestrator "
                "must call WorkspaceContext.with_workspace_path() before dispatch."
            )
            raise ValueError(msg)
        return workspace_context.workspace_path


# ---------------------------------------------------------------------------
# Shared streaming helpers (also used by containerised strategy)
# ---------------------------------------------------------------------------


async def _iter_stdout(process: asyncio.subprocess.Process) -> AsyncIterator[bytes]:
    """Yield stdout lines from a subprocess; stops when stream closes."""
    if process.stdout is None:
        return
    while True:
        line = await process.stdout.readline()
        if not line:
            return
        yield line


async def _drain_stderr(process: asyncio.subprocess.Process) -> str:
    """Read all stderr; used for error-summary on non-zero exit."""
    if process.stderr is None:
        return ""
    chunks: list[bytes] = []
    while True:
        line = await process.stderr.readline()
        if not line:
            break
        chunks.append(line)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _kill_subprocess_factory(process: asyncio.subprocess.Process):
    """Return a callable that kills *process* idempotently."""

    def kill() -> None:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass

    return kill


async def _stream_and_collect(
    *,
    process_stdout: AsyncIterator[bytes],
    process_stderr_reader,
    wait_process,
    parser: ClaudeStreamJsonParser,
    event_bus: EventBus,
    execution_id: str,
    coding_agent_id: str,
    workspace_context: WorkspaceContext,
    options: CodingAgentInvocationOptions,
    start: datetime,
    timeout_seconds: int,
    kill,
) -> CodingAgentResult:
    """Pump parser output to the event bus and collect the final result.

    This is the shared core used by both host and containerised
    strategies. It owns:

    * publishing every emitted event;
    * extracting outcome data from the final
      :class:`CodingAgentCompletedEvent` (or synthesising one when the
      stream ends without ``result``);
    * counting tool calls (since the parser leaves this field at zero);
    * honouring ``timeout_seconds`` (kills the subprocess on timeout).
    """
    completed_event: CodingAgentCompletedEvent | None = None
    tool_call_count = 0

    # stderr is drained concurrently so we don't deadlock on a full pipe.
    stderr_task = asyncio.create_task(process_stderr_reader)

    async def _pump() -> None:
        nonlocal completed_event, tool_call_count
        async for event in parser.parse_stream(
            process_stdout,
            execution_id=execution_id,
            coding_agent_id=coding_agent_id,
            invocation_mode=options.invocation_mode.value,
            model=options.model,
            model_options=dict(options.mode_config or {}),
            work_item_id=workspace_context.work_item_id,
        ):
            if isinstance(event, CodingAgentToolCallEvent):
                tool_call_count += 1
            if isinstance(event, CodingAgentCompletedEvent):
                completed_event = event
            await event_bus.publish(event)

    try:
        if timeout_seconds and timeout_seconds > 0:
            await asyncio.wait_for(_pump(), timeout=timeout_seconds)
        else:
            await _pump()
    except TimeoutError:
        logger.warning(
            "ClaudeCodeStrategy: timeout after %ds for execution_id=%s; killing process",
            timeout_seconds,
            execution_id,
        )
        kill()
        # Drain stderr (best-effort) so the caller can surface it.
        stderr_text = await _safe_await(stderr_task, default="")
        return _timeout_result(
            execution_id=execution_id,
            start=start,
            stderr=stderr_text,
        )

    exit_code: int | None = None
    try:
        exit_code = await wait_process()
    except Exception:
        logger.exception(
            "ClaudeCodeStrategy: failed to await process exit for execution_id=%s",
            execution_id,
        )

    stderr_text = await _safe_await(stderr_task, default="")

    if completed_event is None:
        # The stream ended without a `result` event. Build a result from
        # the process exit code so the orchestrator still gets a verdict.
        return _synthetic_result_from_exit(
            execution_id=execution_id,
            exit_code=exit_code,
            start=start,
            tool_call_count=tool_call_count,
            stderr=stderr_text,
        )

    # Honour the completed event's outcome and enrich tool_call_count.
    duration_ms = completed_event.duration_ms or int(
        (datetime.now(UTC) - start).total_seconds() * 1000,
    )
    error_summary = completed_event.error_summary
    if exit_code is not None and exit_code != 0 and completed_event.success:
        # Process exited non-zero but the stream said success — trust the
        # process exit (vendor-side errors typically suppress the result
        # event when the wrapper crashes).
        return CodingAgentResult(
            success=False,
            summary_text=completed_event.summary_text,
            total_cost_usd=completed_event.total_cost_usd,
            total_input_tokens=completed_event.total_input_tokens,
            total_output_tokens=completed_event.total_output_tokens,
            tool_call_count=tool_call_count,
            duration_ms=duration_ms,
            error_summary=f"exit_code={exit_code}; {stderr_text[:200]}".strip(),
        )

    return CodingAgentResult(
        success=completed_event.success,
        summary_text=completed_event.summary_text,
        total_cost_usd=completed_event.total_cost_usd,
        total_input_tokens=completed_event.total_input_tokens,
        total_output_tokens=completed_event.total_output_tokens,
        tool_call_count=tool_call_count,
        duration_ms=duration_ms,
        error_summary=error_summary,
    )


async def _safe_await(task, *, default):
    """Await *task*, swallowing exceptions and returning *default* on error."""
    try:
        return await task
    except Exception:
        return default


def _synthetic_result_from_exit(
    *,
    execution_id: str,
    exit_code: int | None,
    start: datetime,
    tool_call_count: int,
    stderr: str,
) -> CodingAgentResult:
    duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
    success = exit_code == 0
    error_summary: str | None
    if success:
        error_summary = None
        summary_text = ""
    else:
        ec_str = "unknown" if exit_code is None else str(exit_code)
        summary_text = ""
        error_summary = f"exit_code={ec_str}; {stderr[:200]}".strip()
    logger.warning(
        "ClaudeCodeStrategy: stream ended without `result` event for execution_id=%s; "
        "synthesised result success=%s exit_code=%s",
        execution_id,
        success,
        exit_code,
    )
    return CodingAgentResult(
        success=success,
        summary_text=summary_text,
        total_cost_usd=Decimal("0"),
        total_input_tokens=0,
        total_output_tokens=0,
        tool_call_count=tool_call_count,
        duration_ms=duration_ms,
        error_summary=error_summary,
    )


def _timeout_result(*, execution_id: str, start: datetime, stderr: str) -> CodingAgentResult:
    duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
    return CodingAgentResult(
        success=False,
        summary_text="",
        total_cost_usd=Decimal("0"),
        total_input_tokens=0,
        total_output_tokens=0,
        tool_call_count=0,
        duration_ms=duration_ms,
        error_summary=f"timeout; {stderr[:200]}".strip(),
    )


__all__ = [
    "CredentialProviderProtocol",
    "HostClaudeStrategy",
]
