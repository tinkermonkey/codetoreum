"""Containerised invocation strategy: run ``claude`` inside an IContainer.

The strategy:

1. Builds a :class:`ContainerConfig` from
   :class:`CodingAgentInvocationOptions.mode_config` (image, cpu, mem,
   network) and the credentials provider.
2. Mounts the workspace from the host into the container at
   ``/workspace`` (read-write so the agent can edit files).
3. Creates and starts the container running ``claude --print ...
   --output-format stream-json`` as the entrypoint.
4. Follows the container's log stream and pumps it through the shared
   :class:`ClaudeStreamJsonParser` → events → ``EventBus``.
5. Waits for the container to exit, captures the exit code, and removes
   the container.

Per Q7 (no ``/output`` extraction) the strategy never reads files from
the container post-exit. All telemetry lives in events.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codetoreum.adapters.secondary.claude_code.strategies.base import (
    ClaudeInvocationStrategy,
)
from codetoreum.adapters.secondary.claude_code.strategies.host import (
    CredentialProviderProtocol,
    _stream_and_collect,
)
from codetoreum.adapters.secondary.claude_code.stream_parser import (
    ClaudeStreamJsonParser,
)
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
)
from codetoreum.ports.output.container import IContainer

logger = logging.getLogger(__name__)

_DEFAULT_WORKDIR = "/workspace"


class ContainerizedClaudeStrategy(ClaudeInvocationStrategy):
    """Run Claude Code inside a sandboxed container via :class:`IContainer`."""

    def __init__(
        self,
        *,
        container: IContainer,
        credential_provider: CredentialProviderProtocol,
        claude_cli_path: str = "claude",
        api_key_credential_name: str = "ANTHROPIC_API_KEY",
        oauth_token_credential_name: str = "CLAUDE_CODE_OAUTH_TOKEN",  # noqa: S107
        workspace_path_resolver: Callable[[WorkspaceContext], Path] | None = None,
    ) -> None:
        """Construct the containerised strategy.

        Args:
            container: :class:`IContainer` adapter used to manage the
                sandbox.
            credential_provider: Resolves vendor credentials at execute
                time. Credentials are injected into the container env,
                **not** baked into the image.
            claude_cli_path: Path to ``claude`` inside the container.
                Defaults to ``"claude"`` (resolved on the container's
                PATH).
            api_key_credential_name: Credential key for the API key
                fallback.
            oauth_token_credential_name: Credential key for the OAuth
                token (preferred).
            workspace_path_resolver: Maps a :class:`WorkspaceContext` to
                the host directory mounted into the container at
                ``/workspace``. When ``None``, no workspace mount is
                added (the container can still run, but won't see source
                files — useful for tests).
        """
        self._container = container
        self._credential_provider = credential_provider
        self._claude_cli_path = claude_cli_path
        self._api_key_credential_name = api_key_credential_name
        self._oauth_token_credential_name = oauth_token_credential_name
        self._workspace_path_resolver = workspace_path_resolver

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
        """Create, start, stream, and remove the container."""
        mode_config = dict(options.mode_config or {})
        image = str(mode_config.get("image") or "")
        if not image:
            msg = "ContainerizedClaudeStrategy requires mode_config['image']"
            raise ValueError(msg)

        command = self._build_command(prompt_text=prompt_text, options=options)
        env = await self._build_environment()
        volumes = self._build_volumes(workspace_context)
        labels = {
            "codetoreum.execution_id": execution_id,
            "codetoreum.work_item_id": workspace_context.work_item_id,
            "codetoreum.adapter": "claude-code",
        }

        container_id = await self._container.create(
            image=image,
            name=f"claude-{execution_id[:12]}",
            command=command,
            environment=env,
            volumes=volumes,
            working_dir=_DEFAULT_WORKDIR,
            network=mode_config.get("network"),
            labels=labels,
        )
        logger.info(
            "ContainerizedClaudeStrategy: created container_id=%s image=%s execution_id=%s",
            container_id,
            image,
            execution_id,
        )

        start = datetime.now(UTC)
        try:
            await self._container.start(container_id)
            stdout = await self._open_log_stream(container_id)
            stderr_reader = _drain_nothing()

            async def _wait_exit() -> int:
                return await self._container.wait(container_id, timeout=None)

            def _kill_container() -> None:
                # Use asyncio.create_task on a fire-and-forget kill since
                # this is called from sync code on timeout paths.
                try:
                    asyncio.create_task(self._container.kill(container_id))
                except RuntimeError:
                    # No running loop — best-effort, just log.
                    logger.warning(
                        "Could not schedule container kill (no event loop) for %s",
                        container_id,
                    )

            return await _stream_and_collect(
                process_stdout=stdout,
                process_stderr_reader=stderr_reader,
                wait_process=_wait_exit,
                parser=parser,
                event_bus=event_bus,
                execution_id=execution_id,
                coding_agent_id=coding_agent_id,
                workspace_context=workspace_context,
                options=options,
                start=start,
                timeout_seconds=options.timeout_seconds,
                kill=_kill_container,
            )
        finally:
            # Always remove the container.
            try:
                await self._container.remove(container_id, force=True)
            except Exception:
                logger.exception(
                    "ContainerizedClaudeStrategy: failed to remove container_id=%s",
                    container_id,
                )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def _build_command(
        self,
        *,
        prompt_text: str,
        options: CodingAgentInvocationOptions,
    ) -> list[str]:
        return [
            self._claude_cli_path,
            "--print",
            "--output-format",
            "stream-json",
            "--permission-mode",
            "bypassPermissions",
            "--model",
            options.model,
            "--verbose",
            prompt_text,
        ]

    async def _build_environment(self) -> dict[str, str]:
        env: dict[str, str] = {}
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
        return env

    def _build_volumes(
        self,
        workspace_context: WorkspaceContext,
    ) -> dict[str, dict[str, str]] | None:
        if self._workspace_path_resolver is None:
            return None
        try:
            host_path = self._workspace_path_resolver(workspace_context)
        except Exception:
            logger.exception(
                "workspace_path_resolver failed for work_item_id=%s; skipping mount",
                workspace_context.work_item_id,
            )
            return None
        return {
            str(host_path): {"bind": _DEFAULT_WORKDIR, "mode": "rw"},
        }

    async def _open_log_stream(self, container_id: str) -> AsyncIterator[bytes]:
        """Open the container's follow-mode log stream as a byte iterator.

        :meth:`IContainer.logs` (Docker adapter) returns an async generator
        of decoded ``str`` chunks when called with ``stream=True``. The
        parser expects ``bytes`` per line, so we re-encode and split.
        """
        raw_stream: Any = await self._container.logs(
            container_id,
            stream=True,
            follow=True,
        )
        return _normalise_log_stream(raw_stream)


async def _normalise_log_stream(stream: Any) -> AsyncIterator[bytes]:
    """Adapt :meth:`IContainer.logs` output to per-line ``bytes``.

    Docker chunks may contain multiple newline-separated frames; the
    parser is line-oriented, so we split here.
    """
    buf = b""
    if hasattr(stream, "__aiter__"):
        async for chunk in stream:
            buf += _coerce_to_bytes(chunk)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line:
                    yield line + b"\n"
        if buf:
            yield buf
        return
    # Iterable (sync) fallback.
    for chunk in stream:
        buf += _coerce_to_bytes(chunk)
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if line:
                yield line + b"\n"
    if buf:
        yield buf


def _coerce_to_bytes(chunk: Any) -> bytes:
    if isinstance(chunk, bytes):
        return chunk
    if isinstance(chunk, str):
        return chunk.encode("utf-8")
    return str(chunk).encode("utf-8")


async def _drain_nothing() -> str:
    """Containerised stderr is part of the log stream; return empty."""
    return ""


__all__ = ["ContainerizedClaudeStrategy"]
