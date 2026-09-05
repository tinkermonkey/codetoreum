"""Coding agent domain events — granular per-execution telemetry.

This module defines 11 ``CodingAgent*`` events emitted by ``ICodingAgent``
adapters (e.g. ``ClaudeCodeAdapter``) as they drive an autonomous coding
agent through one execution. The events are **agent-level**, distinct from
the workflow-level ``ExecutionStartedEvent`` / ``ExecutionCompletedEvent``
emitted by ``ExecutionService``.

Event family (in emission order during a typical run):

1. ``CodingAgentInvokedEvent`` — lifecycle bookend; agent has been started.
2. ``CodingAgentReadyEvent`` — agent has initialised and awaits a prompt.
3. ``CodingAgentToolCallEvent`` — agent invoked a tool (Read, Edit, Bash, ...).
4. ``CodingAgentToolResultEvent`` — tool result returned to the agent.
5. ``CodingAgentTextOutputEvent`` — agent emitted assistant text.
6. ``CodingAgentThinkingEvent`` — extended-thinking / reasoning block.
7. ``CodingAgentRateLimitEvent`` — rate-limit notice from the upstream API.
8. ``CodingAgentApiRetryEvent`` — API request retry.
9. ``CodingAgentOtlpSpanEvent`` — OTel span routed through the event bus.
10. ``CodingAgentTokensUsedEvent`` — token / cost accounting checkpoint.
11. ``CodingAgentCompletedEvent`` — agent's final summary (written *before*
    the workflow-level ``ExecutionCompletedEvent`` produced by
    ``ExecutionService`` from the synchronous ``CodingAgentResult``).

**Aggregate ID**: every event in this family uses ``execution_id`` as the
aggregate — one execution forms one event stream. ``work_item_id`` is not
carried on these events; the ``execution_id`` → ``work_item_id`` join is
maintained by the event store's index. See open question O1 in
``~/.claude/plans/coding-agent-port-redesign.md``.

**Retention** (per the design proposal, Q1 Lean): granular behavioural
events (tool calls, tool results, text outputs, thinking, rate limits,
API retries, OTel spans) carry a **14-day default retention** distinct
from lifecycle events; they are high-volume telemetry optimised for
analysis (timings, decisions, input/output dimensions), not replay.

**Purpose** (per Q2 Lean): the event shape favours **behavioural
analysis** over reconstruction — average tool-call counts, rate-limit
frequencies, token-usage distributions. Granular events such as
``CodingAgentOtlpSpanEvent`` carry both structured fields *and* the raw
OTel JSON for re-export to downstream collectors.

**Tool-result truncation** (per Q4 Lean): ``CodingAgentToolResultEvent``
caps ``result_content`` at 64KB via the
``CodingAgentToolResultEvent.from_full_content`` factory, recording
``was_truncated`` and ``full_content_size`` so analysis pipelines can
identify and re-fetch large bodies when needed.

See INV-15, INV-16, INV-17, INV-18 in ``bootstrap/ARCHITECTURE.md`` §6
and DEF-015 in §9 for architectural context.

All events are frozen dataclasses inheriting :class:`CodetoreumEvent`,
which supplies ``type`` / ``timestamp`` / ``source`` / ``correlation_id``
/ ``causation_id`` / ``event_id``.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import uuid4

from .adapter_events import CodetoreumEvent

# ---------------------------------------------------------------------------
# Type strings — single source of truth for the 11 events' dot-notation type.
# ---------------------------------------------------------------------------

_TYPE_INVOKED = "coding_agent.invoked"
_TYPE_READY = "coding_agent.ready"
_TYPE_TOOL_CALL = "coding_agent.tool_call"
_TYPE_TOOL_RESULT = "coding_agent.tool_result"
_TYPE_TEXT_OUTPUT = "coding_agent.text_output"
_TYPE_THINKING = "coding_agent.thinking"
_TYPE_RATE_LIMIT = "coding_agent.rate_limit"
_TYPE_API_RETRY = "coding_agent.api_retry"
_TYPE_OTLP_SPAN = "coding_agent.otlp_span"
_TYPE_TOKENS_USED = "coding_agent.tokens_used"
_TYPE_COMPLETED = "coding_agent.completed"


# ---------------------------------------------------------------------------
# 1. CodingAgentInvokedEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentInvokedEvent(CodetoreumEvent):
    """Emitted when a coding agent adapter starts the agent.

    Lifecycle bookend. Fired by :class:`ICodingAgent` adapters
    (e.g. ``ClaudeCodeAdapter``) once the underlying agent process /
    API session has been launched but before it is ready for input.

    Type: ``coding_agent.invoked``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        coding_agent_id: Adapter identifier (e.g. ``"claude-code"``,
            ``"github-copilot"``, ``"codex"``).
        invocation_mode: One of ``"containerized"`` / ``"host"`` / ``"api"``.
        model: Model name configured for this execution.
        model_options: Vendor-specific options (image, cpu_limit,
            memory_limit, etc.).
    """

    execution_id: str = ""
    coding_agent_id: str = ""
    invocation_mode: str = ""
    model: str = ""
    model_options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.coding_agent_id:
            msg = "coding_agent_id is required"
            raise ValueError(msg)
        if not self.invocation_mode:
            msg = "invocation_mode is required"
            raise ValueError(msg)
        if not self.model:
            msg = "model is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "coding_agent_id": self.coding_agent_id,
                "invocation_mode": self.invocation_mode,
                "model": self.model,
                "model_options": dict(self.model_options),
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentInvokedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", _TYPE_INVOKED),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            coding_agent_id=data["coding_agent_id"],
            invocation_mode=data["invocation_mode"],
            model=data["model"],
            model_options=dict(data.get("model_options") or {}),
        )


# ---------------------------------------------------------------------------
# 2. CodingAgentReadyEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentReadyEvent(CodetoreumEvent):
    """Emitted when the coding agent has finished initialisation.

    The agent has signalled readiness (session id received, version
    handshake complete, etc.) and is awaiting its first prompt.

    Type: ``coding_agent.ready``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        ready_at: ISO 8601 timestamp when the agent reached ready state.
        init_metadata: Vendor-specific init payload (session id, version,
            available tools, etc.).
    """

    execution_id: str = ""
    ready_at: str = ""
    init_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.ready_at:
            msg = "ready_at is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "ready_at": self.ready_at,
                "init_metadata": dict(self.init_metadata),
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentReadyEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", _TYPE_READY),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            ready_at=data["ready_at"],
            init_metadata=dict(data.get("init_metadata") or {}),
        )


# ---------------------------------------------------------------------------
# 3. CodingAgentToolCallEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentToolCallEvent(CodetoreumEvent):
    """Emitted when the coding agent invokes a tool.

    High-volume behavioural event — analysis-oriented, **14-day default
    retention**.

    Type: ``coding_agent.tool_call``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        tool_use_id: Vendor-supplied tool invocation id (correlates to
            the matching ``CodingAgentToolResultEvent``).
        tool_name: Tool invoked (e.g. ``"Read"``, ``"Edit"``, ``"Bash"``).
        tool_input: Tool arguments. May be truncated for very large
            payloads (open question O4 in the design doc).
        parent_message_id: Vendor message id the tool call originated from.
    """

    execution_id: str = ""
    tool_use_id: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    parent_message_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.tool_use_id:
            msg = "tool_use_id is required"
            raise ValueError(msg)
        if not self.tool_name:
            msg = "tool_name is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "tool_use_id": self.tool_use_id,
                "tool_name": self.tool_name,
                "tool_input": dict(self.tool_input),
                "parent_message_id": self.parent_message_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentToolCallEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", _TYPE_TOOL_CALL),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            tool_use_id=data["tool_use_id"],
            tool_name=data["tool_name"],
            tool_input=dict(data.get("tool_input") or {}),
            parent_message_id=data.get("parent_message_id", ""),
        )


# ---------------------------------------------------------------------------
# 4. CodingAgentToolResultEvent (with 64KB truncation per Q4 Lean)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentToolResultEvent(CodetoreumEvent):
    """Emitted when a tool returns a result to the coding agent.

    High-volume behavioural event — analysis-oriented, **14-day default
    retention**. ``result_content`` is capped at
    :data:`MAX_RESULT_CONTENT_BYTES` (64 KiB UTF-8); use
    :meth:`from_full_content` for deterministic truncation.

    Type: ``coding_agent.tool_result``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        tool_use_id: Correlates to the originating
            :class:`CodingAgentToolCallEvent`.
        result_content: Tool output. May be truncated; see
            ``was_truncated`` and ``full_content_size``.
        is_error: True if the tool returned an error.
        duration_ms: How long the tool execution took.
        was_truncated: True if ``result_content`` was truncated below
            ``full_content_size`` (per Q4 Lean).
        full_content_size: Size in bytes (UTF-8) of the *original*
            result content, regardless of truncation.
    """

    MAX_RESULT_CONTENT_BYTES = 65536  # 64 KiB cap (Q4 Lean)

    execution_id: str = ""
    tool_use_id: str = ""
    result_content: str = ""
    is_error: bool = False
    duration_ms: int = 0
    was_truncated: bool = False
    full_content_size: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.tool_use_id:
            msg = "tool_use_id is required"
            raise ValueError(msg)
        if self.duration_ms < 0:
            msg = "duration_ms must be >= 0"
            raise ValueError(msg)
        if self.full_content_size < 0:
            msg = "full_content_size must be >= 0"
            raise ValueError(msg)

    @classmethod
    def from_full_content(
        cls,
        *,
        type: str = _TYPE_TOOL_RESULT,
        timestamp: str,
        source: str,
        execution_id: str,
        tool_use_id: str,
        full_content: str,
        is_error: bool = False,
        duration_ms: int = 0,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        event_id: str | None = None,
    ) -> "CodingAgentToolResultEvent":
        """Construct a tool-result event with deterministic 64KB truncation.

        The full content is measured in UTF-8 bytes; if it exceeds
        :data:`MAX_RESULT_CONTENT_BYTES` the content is truncated at the
        byte boundary (decoded back to a string with errors ignored) and
        ``was_truncated`` / ``full_content_size`` are set accordingly.

        Args:
            type: Event type (defaults to ``"coding_agent.tool_result"``).
            timestamp: ISO 8601 timestamp.
            source: Adapter identifier.
            execution_id: Aggregate ID.
            tool_use_id: Matching tool-call id.
            full_content: Untruncated tool output.
            is_error: True if the tool errored.
            duration_ms: Tool execution duration.
            correlation_id: Optional correlation id.
            causation_id: Optional causation id.
            event_id: Optional event id (auto-generated if absent).

        Returns:
            A :class:`CodingAgentToolResultEvent` with content truncated
            (if needed) and ``was_truncated`` / ``full_content_size`` set.
        """
        encoded = full_content.encode("utf-8")
        full_size = len(encoded)
        if full_size > cls.MAX_RESULT_CONTENT_BYTES:
            truncated_bytes = encoded[: cls.MAX_RESULT_CONTENT_BYTES]
            # Decode tolerating split multi-byte sequences at the boundary.
            result_content = truncated_bytes.decode("utf-8", errors="ignore")
            was_truncated = True
        else:
            result_content = full_content
            was_truncated = False

        return cls(
            type=type,
            timestamp=timestamp,
            source=source,
            correlation_id=correlation_id,
            causation_id=causation_id,
            event_id=event_id or str(uuid4()),
            execution_id=execution_id,
            tool_use_id=tool_use_id,
            result_content=result_content,
            is_error=is_error,
            duration_ms=duration_ms,
            was_truncated=was_truncated,
            full_content_size=full_size,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "tool_use_id": self.tool_use_id,
                "result_content": self.result_content,
                "is_error": self.is_error,
                "duration_ms": self.duration_ms,
                "was_truncated": self.was_truncated,
                "full_content_size": self.full_content_size,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentToolResultEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", _TYPE_TOOL_RESULT),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            tool_use_id=data["tool_use_id"],
            result_content=data.get("result_content", ""),
            is_error=bool(data.get("is_error", False)),
            duration_ms=int(data.get("duration_ms", 0)),
            was_truncated=bool(data.get("was_truncated", False)),
            full_content_size=int(data.get("full_content_size", 0)),
        )


# ---------------------------------------------------------------------------
# 5. CodingAgentTextOutputEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentTextOutputEvent(CodetoreumEvent):
    """Emitted when the coding agent produces assistant text.

    High-volume behavioural event — analysis-oriented, **14-day default
    retention**.

    Type: ``coding_agent.text_output``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        message_id: Vendor-supplied message id.
        content: Assistant text content.
        role: Normalised role string (``"assistant"`` by default; some
            vendors may surface other roles within a single execution).
    """

    execution_id: str = ""
    message_id: str = ""
    content: str = ""
    role: str = "assistant"

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.message_id:
            msg = "message_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "message_id": self.message_id,
                "content": self.content,
                "role": self.role,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentTextOutputEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", _TYPE_TEXT_OUTPUT),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            message_id=data["message_id"],
            content=data.get("content", ""),
            role=data.get("role", "assistant"),
        )


# ---------------------------------------------------------------------------
# 6. CodingAgentThinkingEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentThinkingEvent(CodetoreumEvent):
    """Emitted when the coding agent surfaces an extended-thinking block.

    High-volume behavioural event — analysis-oriented, **14-day default
    retention**.

    Type: ``coding_agent.thinking``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        message_id: Vendor-supplied message id.
        content: Thinking / reasoning content text.
    """

    execution_id: str = ""
    message_id: str = ""
    content: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.message_id:
            msg = "message_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "message_id": self.message_id,
                "content": self.content,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentThinkingEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", _TYPE_THINKING),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            message_id=data["message_id"],
            content=data.get("content", ""),
        )


# ---------------------------------------------------------------------------
# 7. CodingAgentRateLimitEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentRateLimitEvent(CodetoreumEvent):
    """Emitted when the vendor reports a rate-limit condition.

    High-volume behavioural event — analysis-oriented, **14-day default
    retention**.

    Type: ``coding_agent.rate_limit``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        rate_limit_type: Vendor-supplied limit category
            (e.g. ``"five_hour"``, ``"tokens_per_minute"``).
        status: Vendor status string (e.g. ``"approaching"``, ``"hit"``).
        resets_at: Epoch-seconds timestamp at which the limit resets.
        overage_status: Vendor overage classification
            (e.g. ``"warning"`` / ``"hard"``); ``None`` when not provided.
    """

    execution_id: str = ""
    rate_limit_type: str = ""
    status: str = ""
    resets_at: int = 0
    overage_status: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.rate_limit_type:
            msg = "rate_limit_type is required"
            raise ValueError(msg)
        if not self.status:
            msg = "status is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "rate_limit_type": self.rate_limit_type,
                "status": self.status,
                "resets_at": self.resets_at,
                "overage_status": self.overage_status,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentRateLimitEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", _TYPE_RATE_LIMIT),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            rate_limit_type=data["rate_limit_type"],
            status=data["status"],
            resets_at=int(data.get("resets_at", 0)),
            overage_status=data.get("overage_status"),
        )


# ---------------------------------------------------------------------------
# 8. CodingAgentApiRetryEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentApiRetryEvent(CodetoreumEvent):
    """Emitted when the adapter retries a vendor API call.

    High-volume behavioural event — analysis-oriented, **14-day default
    retention**.

    Type: ``coding_agent.api_retry``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        attempt: Current retry attempt number (1-indexed).
        max_retries: Configured retry ceiling.
        error: Short error identifier for what triggered the retry.
        delay_ms: Backoff delay applied before this attempt.
    """

    execution_id: str = ""
    attempt: int = 0
    max_retries: int = 0
    error: str = ""
    delay_ms: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if self.attempt <= 0:
            msg = "attempt must be >= 1"
            raise ValueError(msg)
        if self.max_retries < 0:
            msg = "max_retries must be >= 0"
            raise ValueError(msg)
        if self.delay_ms < 0:
            msg = "delay_ms must be >= 0"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "attempt": self.attempt,
                "max_retries": self.max_retries,
                "error": self.error,
                "delay_ms": self.delay_ms,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentApiRetryEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", _TYPE_API_RETRY),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            attempt=int(data["attempt"]),
            max_retries=int(data.get("max_retries", 0)),
            error=data.get("error", ""),
            delay_ms=int(data.get("delay_ms", 0)),
        )


# ---------------------------------------------------------------------------
# 9. CodingAgentOtlpSpanEvent (structured + raw_span per Q2 Lean)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentOtlpSpanEvent(CodetoreumEvent):
    """Emitted when the coding agent surfaces an OpenTelemetry span.

    High-volume behavioural event — analysis-oriented, **14-day default
    retention**. Replaces the prior approach of agent containers
    exporting OTel directly to a collector (DEF-014). An
    ``IObservabilityProvider`` adapter subscribes to this event and
    forwards spans to whatever collector is configured for the
    deployment.

    Per Q2 Lean: span data is captured as **structured fields**
    (queryable) **and** as a raw span dict (faithful re-export).

    Type: ``coding_agent.otlp_span``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        trace_id: OTel trace id.
        span_id: OTel span id.
        parent_span_id: OTel parent span id; ``None`` for root spans.
        name: Span name.
        start_time: ISO 8601 span start time.
        end_time: ISO 8601 span end time.
        attributes: Structured span attributes.
        events: Tuple of OTel span events (each event a dict).
        status: Span status code (e.g. ``"OK"``, ``"ERROR"``,
            ``"UNSET"``).
        raw_span: Original OTel span JSON, preserved for faithful
            re-export by downstream observability adapters.
    """

    execution_id: str = ""
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str | None = None
    name: str = ""
    start_time: str = ""
    end_time: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    events: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    status: str = ""
    raw_span: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if not self.trace_id:
            msg = "trace_id is required"
            raise ValueError(msg)
        if not self.span_id:
            msg = "span_id is required"
            raise ValueError(msg)
        if not self.name:
            msg = "name is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "trace_id": self.trace_id,
                "span_id": self.span_id,
                "parent_span_id": self.parent_span_id,
                "name": self.name,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "attributes": dict(self.attributes),
                "events": list(self.events),
                "status": self.status,
                "raw_span": dict(self.raw_span),
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentOtlpSpanEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", _TYPE_OTLP_SPAN),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            trace_id=data["trace_id"],
            span_id=data["span_id"],
            parent_span_id=data.get("parent_span_id"),
            name=data["name"],
            start_time=data.get("start_time", ""),
            end_time=data.get("end_time", ""),
            attributes=dict(data.get("attributes") or {}),
            events=tuple(data.get("events") or ()),
            status=data.get("status", ""),
            raw_span=dict(data.get("raw_span") or {}),
        )


# ---------------------------------------------------------------------------
# 10. CodingAgentTokensUsedEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentTokensUsedEvent(CodetoreumEvent):
    """Emitted with token-usage / cost accounting summary.

    May be emitted multiple times during a long execution (per-message,
    per-round-trip) or once at completion, depending on adapter
    granularity. Lifecycle-class event — standard retention.

    Type: ``coding_agent.tokens_used``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        input_tokens: Tokens sent to the model.
        output_tokens: Tokens produced by the model.
        cache_read_input_tokens: Cached input tokens read
            (cost-discounted).
        cache_creation_input_tokens: Cache-writing input tokens
            (premium-priced).
        cost_usd: Estimated cost for this measurement window. Stored as
            :class:`~decimal.Decimal` for accurate accounting.
        model: Model name (in case multiple models are used in one
            execution).
    """

    execution_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    model: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if self.input_tokens < 0:
            msg = "input_tokens must be >= 0"
            raise ValueError(msg)
        if self.output_tokens < 0:
            msg = "output_tokens must be >= 0"
            raise ValueError(msg)
        if self.cache_read_input_tokens < 0:
            msg = "cache_read_input_tokens must be >= 0"
            raise ValueError(msg)
        if self.cache_creation_input_tokens < 0:
            msg = "cache_creation_input_tokens must be >= 0"
            raise ValueError(msg)
        if self.cost_usd < Decimal("0"):
            msg = "cost_usd must be >= 0"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (Decimal rendered as string)."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cache_read_input_tokens": self.cache_read_input_tokens,
                "cache_creation_input_tokens": self.cache_creation_input_tokens,
                "cost_usd": str(self.cost_usd),
                "model": self.model,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentTokensUsedEvent":
        """Deserialize from dictionary."""
        cost_raw = data.get("cost_usd", "0")
        cost = cost_raw if isinstance(cost_raw, Decimal) else Decimal(str(cost_raw))
        return cls(
            type=data.get("type", _TYPE_TOKENS_USED),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            cache_read_input_tokens=int(data.get("cache_read_input_tokens", 0)),
            cache_creation_input_tokens=int(data.get("cache_creation_input_tokens", 0)),
            cost_usd=cost,
            model=data.get("model", ""),
        )


# ---------------------------------------------------------------------------
# 11. CodingAgentCompletedEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodingAgentCompletedEvent(CodetoreumEvent):
    """Emitted when the coding agent finishes execution.

    Agent-level completion bookend. ``ExecutionService`` reads this (or
    the synchronously returned ``CodingAgentResult``) and then emits the
    workflow-level ``ExecutionCompletedEvent`` / ``ExecutionFailedEvent``.

    Type: ``coding_agent.completed``

    Attributes:
        execution_id: Aggregate ID for this execution stream.
        success: Whether execution completed successfully.
        summary_text: Final agent summary / response text.
        total_cost_usd: Total cost across the execution
            (:class:`~decimal.Decimal` for accurate accounting).
        total_input_tokens: Total input tokens (incl. cache traffic).
        total_output_tokens: Total output tokens.
        tool_call_count: Number of tool invocations made.
        duration_ms: End-to-end duration.
        error_summary: Error description if ``not success``, else
            ``None``.
    """

    execution_id: str = ""
    success: bool = False
    summary_text: str = ""
    total_cost_usd: Decimal = Decimal("0")
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    tool_call_count: int = 0
    duration_ms: int = 0
    error_summary: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.execution_id:
            msg = "execution_id is required"
            raise ValueError(msg)
        if self.total_cost_usd < Decimal("0"):
            msg = "total_cost_usd must be >= 0"
            raise ValueError(msg)
        if self.total_input_tokens < 0:
            msg = "total_input_tokens must be >= 0"
            raise ValueError(msg)
        if self.total_output_tokens < 0:
            msg = "total_output_tokens must be >= 0"
            raise ValueError(msg)
        if self.tool_call_count < 0:
            msg = "tool_call_count must be >= 0"
            raise ValueError(msg)
        if self.duration_ms < 0:
            msg = "duration_ms must be >= 0"
            raise ValueError(msg)
        if not self.success and not self.error_summary:
            # When success is False, callers should provide an error_summary.
            # We allow None to keep construction flexible (some failure paths
            # produce no error string) but flag negative durations / costs.
            pass

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (Decimal rendered as string)."""
        d = super().to_dict()
        d.update(
            {
                "execution_id": self.execution_id,
                "success": self.success,
                "summary_text": self.summary_text,
                "total_cost_usd": str(self.total_cost_usd),
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "tool_call_count": self.tool_call_count,
                "duration_ms": self.duration_ms,
                "error_summary": self.error_summary,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingAgentCompletedEvent":
        """Deserialize from dictionary."""
        cost_raw = data.get("total_cost_usd", "0")
        cost = cost_raw if isinstance(cost_raw, Decimal) else Decimal(str(cost_raw))
        return cls(
            type=data.get("type", _TYPE_COMPLETED),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "coding_agent"),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            execution_id=data["execution_id"],
            success=bool(data.get("success", False)),
            summary_text=data.get("summary_text", ""),
            total_cost_usd=cost,
            total_input_tokens=int(data.get("total_input_tokens", 0)),
            total_output_tokens=int(data.get("total_output_tokens", 0)),
            tool_call_count=int(data.get("tool_call_count", 0)),
            duration_ms=int(data.get("duration_ms", 0)),
            error_summary=data.get("error_summary"),
        )


__all__ = [
    "CodingAgentApiRetryEvent",
    "CodingAgentCompletedEvent",
    "CodingAgentInvokedEvent",
    "CodingAgentOtlpSpanEvent",
    "CodingAgentRateLimitEvent",
    "CodingAgentReadyEvent",
    "CodingAgentTextOutputEvent",
    "CodingAgentThinkingEvent",
    "CodingAgentTokensUsedEvent",
    "CodingAgentToolCallEvent",
    "CodingAgentToolResultEvent",
]
