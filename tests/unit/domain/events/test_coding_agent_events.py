"""Unit tests for the CodingAgent* domain event family (D1).

Covers shape, immutability, validation, dot-notation type strings,
unique auto-generated event ids, and EventSerializer round-tripping
for all 11 events introduced by Phase D1 of the coding-agent port
redesign (see ``~/.claude/plans/coding-agent-port-redesign.md``).

Also exercises the 64KB tool-result truncation factory
(:meth:`CodingAgentToolResultEvent.from_full_content`) per Q4 Lean.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from codetoreum.domain.events import (
    CodingAgentApiRetryEvent,
    CodingAgentCompletedEvent,
    CodingAgentInvokedEvent,
    CodingAgentOtlpSpanEvent,
    CodingAgentRateLimitEvent,
    CodingAgentReadyEvent,
    CodingAgentTextOutputEvent,
    CodingAgentThinkingEvent,
    CodingAgentTokensUsedEvent,
    CodingAgentToolCallEvent,
    CodingAgentToolResultEvent,
    now_iso,
)
from codetoreum.infrastructure.event_serialization import (
    EventSerializer,
    auto_register_event_types,
)


@pytest.fixture(autouse=True)
def _register_event_types() -> None:
    """Ensure all event classes (including CodingAgent*) are registered."""
    auto_register_event_types()


@pytest.fixture
def ts() -> str:
    """A valid ISO 8601 timestamp string."""
    return now_iso()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Coverage matrix — assert each event has the expected dot-notation type and
# survives an EventSerializer round-trip.
# ---------------------------------------------------------------------------


def _round_trip(event):
    json_str = EventSerializer.serialize(event)
    return EventSerializer.deserialize(json_str)


class TestCodingAgentInvokedEvent:
    """CodingAgentInvokedEvent."""

    def _make(self, ts: str, **overrides) -> CodingAgentInvokedEvent:
        defaults = {
            "type": "coding_agent.invoked",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "coding_agent_id": "claude-code",
            "invocation_mode": "containerized",
            "model": "claude-sonnet-4-6",
            "model_options": {"image": "codetoreum-agent:latest"},
        }
        defaults.update(overrides)
        return CodingAgentInvokedEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.execution_id == "exec-123"
        assert e.coding_agent_id == "claude-code"
        assert e.invocation_mode == "containerized"
        assert e.model == "claude-sonnet-4-6"
        assert e.model_options == {"image": "codetoreum-agent:latest"}

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.invoked"

    def test_event_id_auto_generated_and_unique(self, ts: str) -> None:
        a = self._make(ts)
        b = self._make(ts)
        assert a.event_id
        assert b.event_id
        assert a.event_id != b.event_id

    def test_immutable(self, ts: str) -> None:
        e = self._make(ts)
        with pytest.raises(FrozenInstanceError):
            e.execution_id = "other"

    def test_missing_execution_id(self, ts: str) -> None:
        with pytest.raises(ValueError, match="execution_id is required"):
            self._make(ts, execution_id="")

    def test_missing_coding_agent_id(self, ts: str) -> None:
        with pytest.raises(ValueError, match="coding_agent_id is required"):
            self._make(ts, coding_agent_id="")

    def test_missing_invocation_mode(self, ts: str) -> None:
        with pytest.raises(ValueError, match="invocation_mode is required"):
            self._make(ts, invocation_mode="")

    def test_missing_model(self, ts: str) -> None:
        with pytest.raises(ValueError, match="model is required"):
            self._make(ts, model="")

    def test_serialization_round_trip(self, ts: str) -> None:
        e = self._make(ts)
        out = _round_trip(e)
        assert isinstance(out, CodingAgentInvokedEvent)
        assert out.execution_id == e.execution_id
        assert out.coding_agent_id == e.coding_agent_id
        assert out.invocation_mode == e.invocation_mode
        assert out.model == e.model
        assert out.model_options == e.model_options
        assert out.event_id == e.event_id


class TestCodingAgentReadyEvent:
    """CodingAgentReadyEvent."""

    def _make(self, ts: str, **overrides) -> CodingAgentReadyEvent:
        defaults = {
            "type": "coding_agent.ready",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "ready_at": ts,
            "init_metadata": {"session_id": "abc", "version": "2.0"},
        }
        defaults.update(overrides)
        return CodingAgentReadyEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.execution_id == "exec-123"
        assert e.ready_at == ts
        assert e.init_metadata == {"session_id": "abc", "version": "2.0"}

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.ready"

    def test_immutable(self, ts: str) -> None:
        e = self._make(ts)
        with pytest.raises(FrozenInstanceError):
            e.ready_at = "other"

    def test_event_id_unique(self, ts: str) -> None:
        a, b = self._make(ts), self._make(ts)
        assert a.event_id and b.event_id and a.event_id != b.event_id

    def test_missing_execution_id(self, ts: str) -> None:
        with pytest.raises(ValueError, match="execution_id is required"):
            self._make(ts, execution_id="")

    def test_missing_ready_at(self, ts: str) -> None:
        with pytest.raises(ValueError, match="ready_at is required"):
            self._make(ts, ready_at="")

    def test_serialization_round_trip(self, ts: str) -> None:
        e = self._make(ts)
        out = _round_trip(e)
        assert isinstance(out, CodingAgentReadyEvent)
        assert out.ready_at == e.ready_at
        assert out.init_metadata == e.init_metadata


class TestCodingAgentToolCallEvent:
    """CodingAgentToolCallEvent."""

    def _make(self, ts: str, **overrides) -> CodingAgentToolCallEvent:
        defaults = {
            "type": "coding_agent.tool_call",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "tool_use_id": "tu-1",
            "tool_name": "Read",
            "tool_input": {"path": "/tmp/foo"},
            "parent_message_id": "msg-1",
        }
        defaults.update(overrides)
        return CodingAgentToolCallEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.tool_use_id == "tu-1"
        assert e.tool_name == "Read"
        assert e.tool_input == {"path": "/tmp/foo"}
        assert e.parent_message_id == "msg-1"

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.tool_call"

    def test_immutable(self, ts: str) -> None:
        with pytest.raises(FrozenInstanceError):
            self._make(ts).tool_name = "Edit"

    def test_event_id_unique(self, ts: str) -> None:
        a, b = self._make(ts), self._make(ts)
        assert a.event_id != b.event_id

    def test_missing_tool_use_id(self, ts: str) -> None:
        with pytest.raises(ValueError, match="tool_use_id is required"):
            self._make(ts, tool_use_id="")

    def test_missing_tool_name(self, ts: str) -> None:
        with pytest.raises(ValueError, match="tool_name is required"):
            self._make(ts, tool_name="")

    def test_serialization_round_trip(self, ts: str) -> None:
        e = self._make(ts)
        out = _round_trip(e)
        assert isinstance(out, CodingAgentToolCallEvent)
        assert out.tool_use_id == e.tool_use_id
        assert out.tool_name == e.tool_name
        assert out.tool_input == e.tool_input


class TestCodingAgentToolResultEvent:
    """CodingAgentToolResultEvent + from_full_content 64KB truncation."""

    def _make(self, ts: str, **overrides) -> CodingAgentToolResultEvent:
        defaults = {
            "type": "coding_agent.tool_result",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "tool_use_id": "tu-1",
            "result_content": "ok",
            "is_error": False,
            "duration_ms": 12,
            "was_truncated": False,
            "full_content_size": 2,
        }
        defaults.update(overrides)
        return CodingAgentToolResultEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.tool_use_id == "tu-1"
        assert e.result_content == "ok"
        assert e.is_error is False
        assert e.duration_ms == 12
        assert e.was_truncated is False
        assert e.full_content_size == 2

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.tool_result"

    def test_immutable(self, ts: str) -> None:
        with pytest.raises(FrozenInstanceError):
            self._make(ts).result_content = "boom"

    def test_event_id_unique(self, ts: str) -> None:
        a, b = self._make(ts), self._make(ts)
        assert a.event_id != b.event_id

    def test_missing_tool_use_id(self, ts: str) -> None:
        with pytest.raises(ValueError, match="tool_use_id is required"):
            self._make(ts, tool_use_id="")

    def test_negative_duration(self, ts: str) -> None:
        with pytest.raises(ValueError, match="duration_ms must be >= 0"):
            self._make(ts, duration_ms=-1)

    def test_from_full_content_no_truncation_small(self, ts: str) -> None:
        small = "hello world"
        e = CodingAgentToolResultEvent.from_full_content(
            timestamp=ts,
            source="claude-code",
            execution_id="exec-123",
            tool_use_id="tu-1",
            full_content=small,
            duration_ms=5,
        )
        assert e.result_content == small
        assert e.was_truncated is False
        assert e.full_content_size == len(small.encode("utf-8"))

    def test_from_full_content_no_truncation_at_boundary(self, ts: str) -> None:
        # Exactly MAX_RESULT_CONTENT_BYTES: should NOT truncate.
        boundary = "x" * CodingAgentToolResultEvent.MAX_RESULT_CONTENT_BYTES
        e = CodingAgentToolResultEvent.from_full_content(
            timestamp=ts,
            source="claude-code",
            execution_id="exec-123",
            tool_use_id="tu-1",
            full_content=boundary,
        )
        assert e.was_truncated is False
        assert len(e.result_content.encode("utf-8")) == (CodingAgentToolResultEvent.MAX_RESULT_CONTENT_BYTES)
        assert e.full_content_size == CodingAgentToolResultEvent.MAX_RESULT_CONTENT_BYTES

    def test_from_full_content_truncates_above_boundary(self, ts: str) -> None:
        oversize_len = CodingAgentToolResultEvent.MAX_RESULT_CONTENT_BYTES + 1024
        oversize = "y" * oversize_len
        e = CodingAgentToolResultEvent.from_full_content(
            timestamp=ts,
            source="claude-code",
            execution_id="exec-123",
            tool_use_id="tu-1",
            full_content=oversize,
        )
        assert e.was_truncated is True
        assert len(e.result_content.encode("utf-8")) <= (CodingAgentToolResultEvent.MAX_RESULT_CONTENT_BYTES)
        assert e.full_content_size == oversize_len

    def test_from_full_content_preserves_utf8_safely(self, ts: str) -> None:
        # Multi-byte chars exactly at the boundary: encoding should not produce
        # invalid UTF-8 in result_content.
        boundary = CodingAgentToolResultEvent.MAX_RESULT_CONTENT_BYTES
        # Build a string whose UTF-8 length exceeds the boundary by a few bytes,
        # with the cut landing in the middle of a multi-byte char.
        # "é" is 2 bytes in UTF-8.
        prefix_bytes = boundary - 1
        text = ("a" * prefix_bytes) + "é" + "x" * 100
        e = CodingAgentToolResultEvent.from_full_content(
            timestamp=ts,
            source="claude-code",
            execution_id="exec-123",
            tool_use_id="tu-1",
            full_content=text,
        )
        assert e.was_truncated is True
        # Should not raise and should be valid Unicode.
        e.result_content.encode("utf-8")

    def test_serialization_round_trip(self, ts: str) -> None:
        e = CodingAgentToolResultEvent.from_full_content(
            timestamp=ts,
            source="claude-code",
            execution_id="exec-123",
            tool_use_id="tu-1",
            full_content="hello",
            duration_ms=7,
        )
        out = _round_trip(e)
        assert isinstance(out, CodingAgentToolResultEvent)
        assert out.tool_use_id == e.tool_use_id
        assert out.result_content == e.result_content
        assert out.was_truncated == e.was_truncated
        assert out.full_content_size == e.full_content_size


class TestCodingAgentTextOutputEvent:
    """CodingAgentTextOutputEvent."""

    def _make(self, ts: str, **overrides) -> CodingAgentTextOutputEvent:
        defaults = {
            "type": "coding_agent.text_output",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "message_id": "msg-1",
            "content": "Implementing fix...",
            "role": "assistant",
        }
        defaults.update(overrides)
        return CodingAgentTextOutputEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.message_id == "msg-1"
        assert e.content == "Implementing fix..."
        assert e.role == "assistant"

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.text_output"

    def test_immutable(self, ts: str) -> None:
        with pytest.raises(FrozenInstanceError):
            self._make(ts).content = "other"

    def test_event_id_unique(self, ts: str) -> None:
        a, b = self._make(ts), self._make(ts)
        assert a.event_id != b.event_id

    def test_missing_message_id(self, ts: str) -> None:
        with pytest.raises(ValueError, match="message_id is required"):
            self._make(ts, message_id="")

    def test_serialization_round_trip(self, ts: str) -> None:
        e = self._make(ts)
        out = _round_trip(e)
        assert isinstance(out, CodingAgentTextOutputEvent)
        assert out.content == e.content
        assert out.role == e.role


class TestCodingAgentThinkingEvent:
    """CodingAgentThinkingEvent."""

    def _make(self, ts: str, **overrides) -> CodingAgentThinkingEvent:
        defaults = {
            "type": "coding_agent.thinking",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "message_id": "msg-1",
            "content": "Reasoning...",
        }
        defaults.update(overrides)
        return CodingAgentThinkingEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.message_id == "msg-1"
        assert e.content == "Reasoning..."

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.thinking"

    def test_immutable(self, ts: str) -> None:
        with pytest.raises(FrozenInstanceError):
            self._make(ts).content = "other"

    def test_event_id_unique(self, ts: str) -> None:
        a, b = self._make(ts), self._make(ts)
        assert a.event_id != b.event_id

    def test_missing_message_id(self, ts: str) -> None:
        with pytest.raises(ValueError, match="message_id is required"):
            self._make(ts, message_id="")

    def test_serialization_round_trip(self, ts: str) -> None:
        e = self._make(ts)
        out = _round_trip(e)
        assert isinstance(out, CodingAgentThinkingEvent)
        assert out.content == e.content


class TestCodingAgentRateLimitEvent:
    """CodingAgentRateLimitEvent."""

    def _make(self, ts: str, **overrides) -> CodingAgentRateLimitEvent:
        defaults = {
            "type": "coding_agent.rate_limit",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "rate_limit_type": "five_hour",
            "status": "approaching",
            "resets_at": 1717000000,
            "overage_status": "warning",
        }
        defaults.update(overrides)
        return CodingAgentRateLimitEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.rate_limit_type == "five_hour"
        assert e.status == "approaching"
        assert e.resets_at == 1717000000
        assert e.overage_status == "warning"

    def test_overage_status_optional(self, ts: str) -> None:
        e = self._make(ts, overage_status=None)
        assert e.overage_status is None

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.rate_limit"

    def test_immutable(self, ts: str) -> None:
        with pytest.raises(FrozenInstanceError):
            self._make(ts).status = "hit"

    def test_event_id_unique(self, ts: str) -> None:
        a, b = self._make(ts), self._make(ts)
        assert a.event_id != b.event_id

    def test_missing_rate_limit_type(self, ts: str) -> None:
        with pytest.raises(ValueError, match="rate_limit_type is required"):
            self._make(ts, rate_limit_type="")

    def test_missing_status(self, ts: str) -> None:
        with pytest.raises(ValueError, match="status is required"):
            self._make(ts, status="")

    def test_serialization_round_trip(self, ts: str) -> None:
        e = self._make(ts)
        out = _round_trip(e)
        assert isinstance(out, CodingAgentRateLimitEvent)
        assert out.rate_limit_type == e.rate_limit_type
        assert out.status == e.status
        assert out.resets_at == e.resets_at
        assert out.overage_status == e.overage_status


class TestCodingAgentApiRetryEvent:
    """CodingAgentApiRetryEvent."""

    def _make(self, ts: str, **overrides) -> CodingAgentApiRetryEvent:
        defaults = {
            "type": "coding_agent.api_retry",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "attempt": 2,
            "max_retries": 5,
            "error": "ConnectionTimeout",
            "delay_ms": 500,
        }
        defaults.update(overrides)
        return CodingAgentApiRetryEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.attempt == 2
        assert e.max_retries == 5
        assert e.error == "ConnectionTimeout"
        assert e.delay_ms == 500

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.api_retry"

    def test_immutable(self, ts: str) -> None:
        with pytest.raises(FrozenInstanceError):
            self._make(ts).attempt = 99

    def test_event_id_unique(self, ts: str) -> None:
        a, b = self._make(ts), self._make(ts)
        assert a.event_id != b.event_id

    def test_invalid_attempt(self, ts: str) -> None:
        with pytest.raises(ValueError, match="attempt must be >= 1"):
            self._make(ts, attempt=0)

    def test_invalid_max_retries(self, ts: str) -> None:
        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            self._make(ts, max_retries=-1)

    def test_invalid_delay(self, ts: str) -> None:
        with pytest.raises(ValueError, match="delay_ms must be >= 0"):
            self._make(ts, delay_ms=-100)

    def test_serialization_round_trip(self, ts: str) -> None:
        e = self._make(ts)
        out = _round_trip(e)
        assert isinstance(out, CodingAgentApiRetryEvent)
        assert out.attempt == e.attempt
        assert out.max_retries == e.max_retries
        assert out.error == e.error
        assert out.delay_ms == e.delay_ms


class TestCodingAgentOtlpSpanEvent:
    """CodingAgentOtlpSpanEvent — structured fields + raw_span (Q2 Lean)."""

    def _make(self, ts: str, **overrides) -> CodingAgentOtlpSpanEvent:
        defaults = {
            "type": "coding_agent.otlp_span",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "trace_id": "trace-abc",
            "span_id": "span-1",
            "parent_span_id": None,
            "name": "tool.Read",
            "start_time": ts,
            "end_time": ts,
            "attributes": {"file": "/tmp/foo"},
            "events": ({"name": "started"},),
            "status": "OK",
            "raw_span": {"raw": "json"},
        }
        defaults.update(overrides)
        return CodingAgentOtlpSpanEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.trace_id == "trace-abc"
        assert e.span_id == "span-1"
        assert e.parent_span_id is None
        assert e.name == "tool.Read"
        assert e.attributes == {"file": "/tmp/foo"}
        assert e.events == ({"name": "started"},)
        assert e.status == "OK"
        assert e.raw_span == {"raw": "json"}

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.otlp_span"

    def test_immutable(self, ts: str) -> None:
        with pytest.raises(FrozenInstanceError):
            self._make(ts).name = "other"

    def test_event_id_unique(self, ts: str) -> None:
        a, b = self._make(ts), self._make(ts)
        assert a.event_id != b.event_id

    def test_missing_trace_id(self, ts: str) -> None:
        with pytest.raises(ValueError, match="trace_id is required"):
            self._make(ts, trace_id="")

    def test_missing_span_id(self, ts: str) -> None:
        with pytest.raises(ValueError, match="span_id is required"):
            self._make(ts, span_id="")

    def test_missing_name(self, ts: str) -> None:
        with pytest.raises(ValueError, match="name is required"):
            self._make(ts, name="")

    def test_serialization_round_trip(self, ts: str) -> None:
        e = self._make(ts)
        out = _round_trip(e)
        assert isinstance(out, CodingAgentOtlpSpanEvent)
        assert out.trace_id == e.trace_id
        assert out.span_id == e.span_id
        assert out.parent_span_id == e.parent_span_id
        assert out.attributes == e.attributes
        # events round-trip through JSON as list-of-dict; rehydrate to tuple.
        assert tuple(out.events) == e.events
        assert out.raw_span == e.raw_span


class TestCodingAgentTokensUsedEvent:
    """CodingAgentTokensUsedEvent."""

    def _make(self, ts: str, **overrides) -> CodingAgentTokensUsedEvent:
        defaults = {
            "type": "coding_agent.tokens_used",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 5,
            "cost_usd": Decimal("0.01234"),
            "model": "claude-sonnet-4-6",
        }
        defaults.update(overrides)
        return CodingAgentTokensUsedEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.input_tokens == 100
        assert e.output_tokens == 50
        assert e.cache_read_input_tokens == 10
        assert e.cache_creation_input_tokens == 5
        assert e.cost_usd == Decimal("0.01234")
        assert e.model == "claude-sonnet-4-6"

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.tokens_used"

    def test_immutable(self, ts: str) -> None:
        with pytest.raises(FrozenInstanceError):
            self._make(ts).input_tokens = 999

    def test_event_id_unique(self, ts: str) -> None:
        a, b = self._make(ts), self._make(ts)
        assert a.event_id != b.event_id

    def test_negative_tokens(self, ts: str) -> None:
        with pytest.raises(ValueError, match="input_tokens must be >= 0"):
            self._make(ts, input_tokens=-1)

    def test_negative_cost(self, ts: str) -> None:
        with pytest.raises(ValueError, match="cost_usd must be >= 0"):
            self._make(ts, cost_usd=Decimal("-0.01"))

    def test_serialization_round_trip_preserves_decimal(self, ts: str) -> None:
        e = self._make(ts)
        out = _round_trip(e)
        assert isinstance(out, CodingAgentTokensUsedEvent)
        assert out.cost_usd == Decimal("0.01234")
        assert isinstance(out.cost_usd, Decimal)
        assert out.input_tokens == e.input_tokens
        assert out.output_tokens == e.output_tokens
        assert out.model == e.model


class TestCodingAgentCompletedEvent:
    """CodingAgentCompletedEvent."""

    def _make(self, ts: str, **overrides) -> CodingAgentCompletedEvent:
        defaults = {
            "type": "coding_agent.completed",
            "timestamp": ts,
            "source": "claude-code",
            "execution_id": "exec-123",
            "success": True,
            "summary_text": "Done.",
            "total_cost_usd": Decimal("0.50"),
            "total_input_tokens": 1000,
            "total_output_tokens": 500,
            "tool_call_count": 7,
            "duration_ms": 12345,
            "error_summary": None,
        }
        defaults.update(overrides)
        return CodingAgentCompletedEvent(**defaults)

    def test_create_valid(self, ts: str) -> None:
        e = self._make(ts)
        assert e.success is True
        assert e.summary_text == "Done."
        assert e.total_cost_usd == Decimal("0.50")
        assert e.total_input_tokens == 1000
        assert e.total_output_tokens == 500
        assert e.tool_call_count == 7
        assert e.duration_ms == 12345
        assert e.error_summary is None

    def test_type_dot_notation(self, ts: str) -> None:
        assert self._make(ts).type == "coding_agent.completed"

    def test_immutable(self, ts: str) -> None:
        with pytest.raises(FrozenInstanceError):
            self._make(ts).success = False

    def test_event_id_unique(self, ts: str) -> None:
        a, b = self._make(ts), self._make(ts)
        assert a.event_id != b.event_id

    def test_failure_event(self, ts: str) -> None:
        e = self._make(
            ts,
            success=False,
            error_summary="OOM",
            total_cost_usd=Decimal("0.10"),
        )
        assert e.success is False
        assert e.error_summary == "OOM"

    def test_negative_cost(self, ts: str) -> None:
        with pytest.raises(ValueError, match="total_cost_usd must be >= 0"):
            self._make(ts, total_cost_usd=Decimal("-1"))

    def test_negative_tokens(self, ts: str) -> None:
        with pytest.raises(ValueError, match="total_input_tokens must be >= 0"):
            self._make(ts, total_input_tokens=-5)

    def test_negative_tool_call_count(self, ts: str) -> None:
        with pytest.raises(ValueError, match="tool_call_count must be >= 0"):
            self._make(ts, tool_call_count=-1)

    def test_negative_duration(self, ts: str) -> None:
        with pytest.raises(ValueError, match="duration_ms must be >= 0"):
            self._make(ts, duration_ms=-1)

    def test_serialization_round_trip_preserves_decimal(self, ts: str) -> None:
        e = self._make(ts)
        out = _round_trip(e)
        assert isinstance(out, CodingAgentCompletedEvent)
        assert out.success is True
        assert out.total_cost_usd == Decimal("0.50")
        assert isinstance(out.total_cost_usd, Decimal)
        assert out.summary_text == e.summary_text
        assert out.tool_call_count == e.tool_call_count


# ---------------------------------------------------------------------------
# auto_register_event_types picks up all 11 events.
# ---------------------------------------------------------------------------


class TestAutoRegister:
    """Confirms auto_register_event_types() registers all 11 events."""

    def test_all_eleven_events_registered(self) -> None:
        auto_register_event_types()
        registry = EventSerializer._codetoeum_event_registry
        expected = {
            "CodingAgentInvokedEvent",
            "CodingAgentReadyEvent",
            "CodingAgentToolCallEvent",
            "CodingAgentToolResultEvent",
            "CodingAgentTextOutputEvent",
            "CodingAgentThinkingEvent",
            "CodingAgentRateLimitEvent",
            "CodingAgentApiRetryEvent",
            "CodingAgentOtlpSpanEvent",
            "CodingAgentTokensUsedEvent",
            "CodingAgentCompletedEvent",
        }
        missing = expected - set(registry.keys())
        assert not missing, f"Not auto-registered: {sorted(missing)}"
