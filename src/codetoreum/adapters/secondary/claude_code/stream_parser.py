"""Claude Code ``stream-json`` parser → ``CodingAgent*`` domain events.

The parser is the **vendor boundary** between Claude Code's ``--output-format
stream-json`` wire format and Codetoreum's vendor-agnostic event vocabulary.
No vendor-specific shape leaks above this module (per INV-15).

Wire schema (confirmed against ``claude --version 2.1.156``, captured at
``/tmp/stream_sample.jsonl`` during D3 implementation):

- ``{"type": "system", "subtype": "init", ...}``
  Emitted once at session start. Carries ``session_id``, ``cwd``, ``tools``,
  ``mcp_servers``, ``model``, ``permissionMode``, ``apiKeySource``,
  ``claude_code_version``, ``output_style``, ``slash_commands``, ``agents``,
  ``skills``, ``plugins``. The parser maps this single event to a
  :class:`CodingAgentInvokedEvent` (lifecycle bookend) **and** a
  :class:`CodingAgentReadyEvent` (init complete, awaiting prompt).

- ``{"type": "system", "subtype": "hook_started" | "hook_response" | ...}``
  Hook lifecycle. Currently no domain event mapping; logged at debug level.

- ``{"type": "system", "subtype": "api_retry", ...}``
  Documented but not observed in the captured sample. Maps to
  :class:`CodingAgentApiRetryEvent`. Defensive: parser checks for the field
  names ``attempt`` / ``max_retries`` / ``error`` / ``delay_ms`` and falls
  back to safe defaults.

- ``{"type": "assistant", "message": {...}}``
  Assistant message chunk. ``message.id`` is the (vendor) message id.
  ``message.content`` is a list of blocks; each block carries a ``type``:

    * ``"thinking"`` → :class:`CodingAgentThinkingEvent`
    * ``"text"``     → :class:`CodingAgentTextOutputEvent`
    * ``"tool_use"`` → :class:`CodingAgentToolCallEvent`
      (uses ``parent_message_id = message.id``)

  ``message.usage`` carries per-chunk token accounting. We do **not** emit
  a per-chunk ``CodingAgentTokensUsedEvent`` (would be noisy); the final
  ``result`` event carries the authoritative totals.

- ``{"type": "user", "message": {"content": [{"type": "tool_result", ...}]}}``
  Tool result returned to the agent. ``content`` is a string (or list of
  items); ``is_error`` flags failures. Maps to
  :class:`CodingAgentToolResultEvent`. Tool-result content is run through
  :meth:`CodingAgentToolResultEvent.from_full_content` for deterministic
  64 KiB truncation (Q4 Lean).

- ``{"type": "rate_limit_event", "rate_limit_info": {...}}``
  Rate-limit notice. The inner dict uses **camelCase** keys
  (``rateLimitType``, ``resetsAt``, ``overageStatus``, ``isUsingOverage``,
  ``status``). Maps to :class:`CodingAgentRateLimitEvent`.

- ``{"type": "result", "subtype": "success" | "error_max_turns" | ...}``
  Terminal event. Carries ``total_cost_usd``, ``duration_ms``, ``usage`` and
  ``modelUsage`` totals, ``is_error``, ``stop_reason``, ``result`` (final
  summary text). Maps to **two** events emitted in order:
    1. :class:`CodingAgentTokensUsedEvent` — final/total counters.
    2. :class:`CodingAgentCompletedEvent` — outcome bookend.

**OpenTelemetry spans** (open question O3 in
``~/.claude/plans/coding-agent-port-redesign.md``): Claude Code currently
emits OTel spans via the OpenTelemetry SDK to ``OTEL_EXPORTER_OTLP_ENDPOINT``
— *not* through ``stream-json``. The CLI offers no ``--otel-output-mode``
switch (as of 2.1.156). The :class:`CodingAgentOtlpSpanEvent` shape is
defined and exercised by serializer tests, but this parser will not emit it
until either (a) the CLI exposes spans on stdout/stderr, or (b) a sidecar
collector inside the container streams them. Tracked as DEF-014 follow-up;
likely surfaces in D7 bootstrap validation.

**Aggregate ID**: every event uses ``execution_id`` as the aggregate.
``correlation_id`` is set to the optional ``work_item_id`` passed via
:meth:`ClaudeStreamJsonParser.parse_stream` so cross-stream queries
(work item → all executions) work without rebuilding indexes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.domain.events.coding_agent_events import (
    CodingAgentApiRetryEvent,
    CodingAgentCompletedEvent,
    CodingAgentInvokedEvent,
    CodingAgentRateLimitEvent,
    CodingAgentReadyEvent,
    CodingAgentTextOutputEvent,
    CodingAgentThinkingEvent,
    CodingAgentTokensUsedEvent,
    CodingAgentToolCallEvent,
    CodingAgentToolResultEvent,
)

logger = logging.getLogger(__name__)

_SOURCE = "claude_code"


class ClaudeStreamJsonParser:
    """Parse Claude Code ``stream-json`` output to ``CodingAgent*`` events.

    Stateless across :meth:`parse_stream` invocations; one parser instance can
    be reused for multiple executions.
    """

    async def parse_stream(
        self,
        stream: AsyncIterator[bytes],
        *,
        execution_id: str,
        coding_agent_id: str,
        invocation_mode: str,
        model: str,
        model_options: dict[str, Any] | None = None,
        work_item_id: str | None = None,
    ) -> AsyncIterator[CodetoreumEvent]:
        """Parse a Claude Code stream into domain events.

        Args:
            stream: Async iterator of raw stdout lines (one JSON event per
                line, possibly with non-JSON noise between them).
            execution_id: Aggregate id for the resulting event stream.
            coding_agent_id: Adapter identifier (e.g. ``"claude-code"``).
            invocation_mode: One of ``"containerized"`` / ``"host"`` / ``"api"``.
            model: Model name configured for the execution.
            model_options: Vendor-specific options (image, cpu, etc.) to
                attach to :class:`CodingAgentInvokedEvent`.
            work_item_id: Optional work item id; carried on every event as
                ``correlation_id`` so the event store can index by work item.

        Yields:
            ``CodingAgent*`` events in the order Claude Code surfaces them.
            On end-of-stream without a ``result`` event, the parser does
            **not** synthesise a :class:`CodingAgentCompletedEvent` — the
            calling strategy is responsible for that (the process exit code
            is the authoritative outcome in that case).
        """
        opts = dict(model_options) if model_options else {}
        # Track whether the parser saw an init event so we know whether to
        # emit the invoked/ready bookends.
        invoked_emitted = False

        async for raw in stream:
            line = self._normalise_line(raw)
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                # Progress output, stderr leakage, or truncated lines — skip.
                logger.debug(
                    "Skipping non-JSON stream line: %s; line=%r",
                    exc,
                    line[:200],
                )
                continue

            if not isinstance(event, dict):
                logger.debug("Skipping non-object stream line: %r", line[:200])
                continue

            event_type = event.get("type")

            try:
                if event_type == "system":
                    subtype = event.get("subtype")
                    if subtype == "init" and not invoked_emitted:
                        invoked_emitted = True
                        yield self._build_invoked_event(
                            execution_id=execution_id,
                            coding_agent_id=coding_agent_id,
                            invocation_mode=invocation_mode,
                            model=model,
                            model_options=opts,
                            correlation_id=work_item_id,
                        )
                        yield self._build_ready_event(
                            event=event,
                            execution_id=execution_id,
                            correlation_id=work_item_id,
                        )
                    elif subtype == "api_retry":
                        yield self._build_api_retry_event(
                            event=event,
                            execution_id=execution_id,
                            correlation_id=work_item_id,
                        )
                    # Other system subtypes (hook_started, hook_response, etc.)
                    # are logged at debug level — no domain mapping today.
                    else:
                        logger.debug(
                            "Unmapped system subtype=%s for execution_id=%s",
                            subtype,
                            execution_id,
                        )

                elif event_type == "assistant":
                    message = event.get("message") or {}
                    message_id = str(message.get("id") or "")

                    for block in message.get("content") or []:
                        if not isinstance(block, dict):
                            continue
                        block_event = self._build_assistant_block_event(
                            block=block,
                            message_id=message_id,
                            execution_id=execution_id,
                            correlation_id=work_item_id,
                        )
                        if block_event is not None:
                            yield block_event

                elif event_type == "user":
                    message = event.get("message") or {}
                    for block in message.get("content") or []:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") != "tool_result":
                            continue
                        yield self._build_tool_result_event(
                            block=block,
                            execution_id=execution_id,
                            correlation_id=work_item_id,
                        )

                elif event_type == "rate_limit_event":
                    yield self._build_rate_limit_event(
                        event=event,
                        execution_id=execution_id,
                        correlation_id=work_item_id,
                    )

                elif event_type == "result":
                    # Emit final TokensUsed first, then Completed.
                    tokens_event = self._build_tokens_used_from_result(
                        event=event,
                        execution_id=execution_id,
                        model=model,
                        correlation_id=work_item_id,
                    )
                    if tokens_event is not None:
                        yield tokens_event
                    yield self._build_completed_event(
                        event=event,
                        execution_id=execution_id,
                        correlation_id=work_item_id,
                    )

                else:
                    logger.debug(
                        "Unmapped stream event type=%s for execution_id=%s",
                        event_type,
                        execution_id,
                    )

            except Exception as exc:
                # A single malformed event should never crash the parser;
                # log with exc_info=True (no silent failures per ARCH rules)
                # and continue.
                logger.exception(
                    "Failed to map stream event type=%s for execution_id=%s: %s",
                    event_type,
                    execution_id,
                    exc,
                )
                # Avoid mention here suppressing legitimate runtime errors —
                # we continue but the warning surfaces the breakage.

    # ------------------------------------------------------------------
    # Block / event builders
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_line(raw: bytes | str) -> str:
        """Decode and strip a stream line; return empty string for blanks."""
        if isinstance(raw, (bytes, bytearray)):
            try:
                decoded = raw.decode("utf-8")
            except UnicodeDecodeError:
                decoded = raw.decode("utf-8", errors="replace")
        else:
            decoded = raw
        return decoded.strip()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def _build_invoked_event(
        self,
        *,
        execution_id: str,
        coding_agent_id: str,
        invocation_mode: str,
        model: str,
        model_options: dict[str, Any],
        correlation_id: str | None,
    ) -> CodingAgentInvokedEvent:
        return CodingAgentInvokedEvent(
            type="coding_agent.invoked",
            timestamp=self._now_iso(),
            source=_SOURCE,
            correlation_id=correlation_id,
            execution_id=execution_id,
            coding_agent_id=coding_agent_id,
            invocation_mode=invocation_mode,
            model=model,
            model_options=model_options,
        )

    def _build_ready_event(
        self,
        *,
        event: dict[str, Any],
        execution_id: str,
        correlation_id: str | None,
    ) -> CodingAgentReadyEvent:
        # Capture the init payload as metadata for downstream analysis.
        init_meta: dict[str, Any] = {}
        for key in (
            "session_id",
            "cwd",
            "tools",
            "mcp_servers",
            "model",
            "permissionMode",
            "apiKeySource",
            "claude_code_version",
            "output_style",
            "slash_commands",
            "agents",
            "skills",
        ):
            if key in event:
                init_meta[key] = event[key]

        return CodingAgentReadyEvent(
            type="coding_agent.ready",
            timestamp=self._now_iso(),
            source=_SOURCE,
            correlation_id=correlation_id,
            execution_id=execution_id,
            ready_at=self._now_iso(),
            init_metadata=init_meta,
        )

    def _build_api_retry_event(
        self,
        *,
        event: dict[str, Any],
        execution_id: str,
        correlation_id: str | None,
    ) -> CodingAgentApiRetryEvent:
        attempt = int(event.get("attempt", 1)) or 1
        return CodingAgentApiRetryEvent(
            type="coding_agent.api_retry",
            timestamp=self._now_iso(),
            source=_SOURCE,
            correlation_id=correlation_id,
            execution_id=execution_id,
            attempt=max(attempt, 1),
            max_retries=int(event.get("max_retries", 0)),
            error=str(event.get("error", "")),
            delay_ms=int(event.get("delay_ms", 0)),
        )

    def _build_assistant_block_event(
        self,
        *,
        block: dict[str, Any],
        message_id: str,
        execution_id: str,
        correlation_id: str | None,
    ) -> CodetoreumEvent | None:
        block_type = block.get("type")
        # Some block types (e.g. server_tool_use, redacted_thinking) are not
        # surfaced today; the parser silently skips them.
        if block_type == "thinking":
            return CodingAgentThinkingEvent(
                type="coding_agent.thinking",
                timestamp=self._now_iso(),
                source=_SOURCE,
                correlation_id=correlation_id,
                execution_id=execution_id,
                message_id=message_id or "unknown",
                content=str(block.get("thinking") or ""),
            )
        if block_type == "text":
            return CodingAgentTextOutputEvent(
                type="coding_agent.text_output",
                timestamp=self._now_iso(),
                source=_SOURCE,
                correlation_id=correlation_id,
                execution_id=execution_id,
                message_id=message_id or "unknown",
                content=str(block.get("text") or ""),
                role="assistant",
            )
        if block_type == "tool_use":
            tool_use_id = str(block.get("id") or "")
            tool_name = str(block.get("name") or "")
            if not tool_use_id or not tool_name:
                logger.debug(
                    "Skipping tool_use block missing id/name: %r",
                    block,
                )
                return None
            tool_input = block.get("input")
            if not isinstance(tool_input, dict):
                tool_input = {"value": tool_input} if tool_input is not None else {}
            return CodingAgentToolCallEvent(
                type="coding_agent.tool_call",
                timestamp=self._now_iso(),
                source=_SOURCE,
                correlation_id=correlation_id,
                execution_id=execution_id,
                tool_use_id=tool_use_id,
                tool_name=tool_name,
                tool_input=tool_input,
                parent_message_id=message_id,
            )
        logger.debug("Unmapped assistant block type=%s", block_type)
        return None

    def _build_tool_result_event(
        self,
        *,
        block: dict[str, Any],
        execution_id: str,
        correlation_id: str | None,
    ) -> CodingAgentToolResultEvent:
        tool_use_id = str(block.get("tool_use_id") or "")
        if not tool_use_id:
            # The event ctor will reject this; raise here with context
            # so the parser's outer except logs the offending payload.
            msg = f"tool_result missing tool_use_id; block={block!r}"
            raise ValueError(msg)

        is_error = bool(block.get("is_error", False))
        raw_content = block.get("content")
        full_content = self._flatten_tool_result_content(raw_content)
        return CodingAgentToolResultEvent.from_full_content(
            timestamp=self._now_iso(),
            source=_SOURCE,
            correlation_id=correlation_id,
            execution_id=execution_id,
            tool_use_id=tool_use_id,
            full_content=full_content,
            is_error=is_error,
            duration_ms=int(block.get("duration_ms", 0)),
        )

    @staticmethod
    def _flatten_tool_result_content(content: Any) -> str:
        """Reduce Claude's heterogeneous tool_result content to a single string.

        ``content`` may be:

        - ``None`` → ``""``
        - a string → returned as-is
        - a list of items, each either a string or ``{"type": "text", "text": ...}``
          or ``{"type": "image", ...}`` → concatenated with single newlines.

        Image references are recorded as a short marker so downstream analysis
        can detect their presence without parsing nested binary payloads.
        """
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type == "text":
                        parts.append(str(item.get("text") or ""))
                    elif item_type == "image":
                        parts.append("[image]")
                    else:
                        parts.append(json.dumps(item, ensure_ascii=False))
            return "\n".join(parts)
        # Fall back: stringify whatever was passed.
        return str(content)

    def _build_rate_limit_event(
        self,
        *,
        event: dict[str, Any],
        execution_id: str,
        correlation_id: str | None,
    ) -> CodingAgentRateLimitEvent:
        info = event.get("rate_limit_info") or {}
        # rate_limit_info uses camelCase: rateLimitType, resetsAt, overageStatus,
        # isUsingOverage, status. (Confirmed via captured fixture.)
        rate_limit_type = str(info.get("rateLimitType") or info.get("rate_limit_type") or "unknown")
        status = str(info.get("status") or "unknown")
        resets_at_raw = info.get("resetsAt") or info.get("resets_at") or 0
        try:
            resets_at = int(resets_at_raw)
        except (TypeError, ValueError):
            resets_at = 0
        overage_status = info.get("overageStatus") or info.get("overage_status")
        if overage_status is not None:
            overage_status = str(overage_status)
        return CodingAgentRateLimitEvent(
            type="coding_agent.rate_limit",
            timestamp=self._now_iso(),
            source=_SOURCE,
            correlation_id=correlation_id,
            execution_id=execution_id,
            rate_limit_type=rate_limit_type,
            status=status,
            resets_at=resets_at,
            overage_status=overage_status,
        )

    def _build_tokens_used_from_result(
        self,
        *,
        event: dict[str, Any],
        execution_id: str,
        model: str,
        correlation_id: str | None,
    ) -> CodingAgentTokensUsedEvent | None:
        usage = event.get("usage") or {}
        if not isinstance(usage, dict):
            return None
        # Prefer the per-model figures (modelUsage[<model>].costUSD) when
        # available; fall back to the top-level total_cost_usd.
        model_usage = event.get("modelUsage") or {}
        cost: Decimal = Decimal("0")
        # modelUsage keys can be the model alias (e.g. claude-haiku-4-5) or a
        # fully-qualified id; take the only entry if there's one model.
        if isinstance(model_usage, dict) and model_usage:
            for entry in model_usage.values():
                if isinstance(entry, dict) and "costUSD" in entry:
                    try:
                        cost += Decimal(str(entry["costUSD"]))
                    except (TypeError, ValueError, ArithmeticError):
                        continue
        if cost == Decimal("0"):
            total_cost = event.get("total_cost_usd", 0)
            try:
                cost = Decimal(str(total_cost))
            except (TypeError, ValueError, ArithmeticError):
                cost = Decimal("0")
        cost = max(cost, Decimal("0"))

        return CodingAgentTokensUsedEvent(
            type="coding_agent.tokens_used",
            timestamp=self._now_iso(),
            source=_SOURCE,
            correlation_id=correlation_id,
            execution_id=execution_id,
            input_tokens=max(int(usage.get("input_tokens", 0)), 0),
            output_tokens=max(int(usage.get("output_tokens", 0)), 0),
            cache_read_input_tokens=max(int(usage.get("cache_read_input_tokens", 0)), 0),
            cache_creation_input_tokens=max(int(usage.get("cache_creation_input_tokens", 0)), 0),
            cost_usd=cost,
            model=model,
        )

    def _build_completed_event(
        self,
        *,
        event: dict[str, Any],
        execution_id: str,
        correlation_id: str | None,
    ) -> CodingAgentCompletedEvent:
        is_error = bool(event.get("is_error", False))
        success = not is_error
        summary_text = str(event.get("result") or "")
        try:
            total_cost = Decimal(str(event.get("total_cost_usd", 0)))
        except (TypeError, ValueError, ArithmeticError):
            total_cost = Decimal("0")
        total_cost = max(total_cost, Decimal("0"))

        usage = event.get("usage") or {}
        input_tokens = max(int(usage.get("input_tokens", 0)), 0) if isinstance(usage, dict) else 0
        output_tokens = max(int(usage.get("output_tokens", 0)), 0) if isinstance(usage, dict) else 0
        duration_ms = max(int(event.get("duration_ms", 0)), 0)
        # tool_call_count is not surfaced by the result event today;
        # the strategy that owns the parser may wrap us and inject it after
        # the fact, but at parse-time we leave it at zero.
        error_summary = None
        if is_error:
            # Stop_reason can serve as a quick label when the result text is
            # absent (e.g. error_max_turns).
            stop_reason = event.get("stop_reason") or event.get("subtype") or "unknown"
            error_summary = str(stop_reason)

        return CodingAgentCompletedEvent(
            type="coding_agent.completed",
            timestamp=self._now_iso(),
            source=_SOURCE,
            correlation_id=correlation_id,
            execution_id=execution_id,
            success=success,
            summary_text=summary_text,
            total_cost_usd=total_cost,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            tool_call_count=0,
            duration_ms=duration_ms,
            error_summary=error_summary,
        )


__all__ = ["ClaudeStreamJsonParser"]
