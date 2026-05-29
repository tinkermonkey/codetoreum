"""Unit tests for :class:`ClaudeStreamJsonParser`.

Fixtures are synthetic, modelled after the captured ``stream-json`` sample
at ``/tmp/stream_sample.jsonl`` (Claude Code 2.1.156). The captured shape
is documented in the parser's module docstring.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest

from codetoreum.adapters.secondary.claude_code.stream_parser import (
    ClaudeStreamJsonParser,
)
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


async def _bytes_iter(lines: list[dict | str]) -> AsyncIterator[bytes]:
    for line in lines:
        if isinstance(line, str):
            yield line.encode("utf-8")
        else:
            yield (json.dumps(line) + "\n").encode("utf-8")


async def _collect(parser, stream, **kwargs):
    return [event async for event in parser.parse_stream(stream, **kwargs)]


# ---------------------------------------------------------------------------
# Fixtures resembling the real wire shape
# ---------------------------------------------------------------------------

INIT_EVENT: dict = {
    "type": "system",
    "subtype": "init",
    "session_id": "sess-1",
    "cwd": "/workspace",
    "tools": ["Read", "Edit", "Bash"],
    "mcp_servers": [{"name": "x", "status": "connected"}],
    "model": "claude-haiku-4-5",
    "permissionMode": "bypassPermissions",
    "apiKeySource": "none",
    "claude_code_version": "2.1.156",
}

THINKING_ASSISTANT: dict = {
    "type": "assistant",
    "message": {
        "id": "msg-1",
        "content": [
            {"type": "thinking", "thinking": "Let me consider the request."},
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 3,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 100,
        },
    },
}

TOOL_USE_ASSISTANT: dict = {
    "type": "assistant",
    "message": {
        "id": "msg-1",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "Bash",
                "input": {"command": "ls", "description": "list files"},
            },
        ],
    },
}

TOOL_RESULT_USER: dict = {
    "type": "user",
    "message": {
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_1",
                "content": "file1\nfile2\n",
                "is_error": False,
            }
        ]
    },
}

TEXT_ASSISTANT: dict = {
    "type": "assistant",
    "message": {
        "id": "msg-2",
        "content": [
            {"type": "text", "text": "Here is a summary."},
        ],
    },
}

RATE_LIMIT: dict = {
    "type": "rate_limit_event",
    "rate_limit_info": {
        "status": "allowed",
        "resetsAt": 1780103400,
        "rateLimitType": "five_hour",
        "overageStatus": "rejected",
        "isUsingOverage": False,
    },
}

RESULT_SUCCESS: dict = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "duration_ms": 1234,
    "num_turns": 2,
    "result": "Done.",
    "stop_reason": "end_turn",
    "session_id": "sess-1",
    "total_cost_usd": 0.025,
    "usage": {
        "input_tokens": 15,
        "output_tokens": 156,
        "cache_read_input_tokens": 36422,
        "cache_creation_input_tokens": 49375,
    },
    "modelUsage": {
        "claude-haiku-4-5": {
            "inputTokens": 15,
            "outputTokens": 156,
            "cacheReadInputTokens": 36422,
            "cacheCreationInputTokens": 49375,
            "costUSD": 0.025,
        }
    },
}

RESULT_ERROR: dict = {
    "type": "result",
    "subtype": "error_max_turns",
    "is_error": True,
    "duration_ms": 4000,
    "result": "",
    "stop_reason": "max_turns",
    "total_cost_usd": 0.05,
    "usage": {"input_tokens": 1, "output_tokens": 2},
}


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestClaudeStreamJsonParser:
    """Behavioural tests for the stream parser."""

    @pytest.mark.asyncio
    async def test_init_emits_invoked_and_ready(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter([INIT_EVENT]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="containerized",
            model="claude-haiku-4-5",
            model_options={"image": "x:latest"},
            work_item_id="wi-1",
        )
        assert len(events) == 2
        invoked, ready = events
        assert isinstance(invoked, CodingAgentInvokedEvent)
        assert invoked.execution_id == "exec-1"
        assert invoked.coding_agent_id == "claude-code"
        assert invoked.invocation_mode == "containerized"
        assert invoked.model == "claude-haiku-4-5"
        assert invoked.model_options == {"image": "x:latest"}
        assert invoked.correlation_id == "wi-1"
        assert isinstance(ready, CodingAgentReadyEvent)
        assert ready.execution_id == "exec-1"
        assert "session_id" in ready.init_metadata
        assert ready.init_metadata["model"] == "claude-haiku-4-5"
        assert ready.correlation_id == "wi-1"

    @pytest.mark.asyncio
    async def test_init_only_emitted_once(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter([INIT_EVENT, INIT_EVENT]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        invoked = [e for e in events if isinstance(e, CodingAgentInvokedEvent)]
        ready = [e for e in events if isinstance(e, CodingAgentReadyEvent)]
        assert len(invoked) == 1
        assert len(ready) == 1

    @pytest.mark.asyncio
    async def test_thinking_block(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter([THINKING_ASSISTANT]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, CodingAgentThinkingEvent)
        assert evt.message_id == "msg-1"
        assert "consider" in evt.content

    @pytest.mark.asyncio
    async def test_text_block(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter([TEXT_ASSISTANT]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, CodingAgentTextOutputEvent)
        assert evt.message_id == "msg-2"
        assert evt.content == "Here is a summary."
        assert evt.role == "assistant"

    @pytest.mark.asyncio
    async def test_tool_use_block(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter([TOOL_USE_ASSISTANT]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, CodingAgentToolCallEvent)
        assert evt.tool_use_id == "toolu_1"
        assert evt.tool_name == "Bash"
        assert evt.tool_input == {"command": "ls", "description": "list files"}
        assert evt.parent_message_id == "msg-1"

    @pytest.mark.asyncio
    async def test_tool_result_block(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter([TOOL_RESULT_USER]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, CodingAgentToolResultEvent)
        assert evt.tool_use_id == "toolu_1"
        assert evt.result_content == "file1\nfile2\n"
        assert evt.is_error is False
        assert evt.was_truncated is False
        assert evt.full_content_size == len(b"file1\nfile2\n")

    @pytest.mark.asyncio
    async def test_tool_result_truncates_above_64kb(self):
        parser = ClaudeStreamJsonParser()
        big = "x" * 100_000
        block = {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_big",
                        "content": big,
                        "is_error": False,
                    }
                ]
            },
        }
        events = await _collect(
            parser,
            _bytes_iter([block]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        evt = events[0]
        assert isinstance(evt, CodingAgentToolResultEvent)
        assert evt.was_truncated is True
        assert evt.full_content_size == 100_000
        assert len(evt.result_content.encode("utf-8")) <= 65536

    @pytest.mark.asyncio
    async def test_tool_result_content_list_with_text_and_image(self):
        parser = ClaudeStreamJsonParser()
        block = {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_img",
                        "content": [
                            {"type": "text", "text": "alpha"},
                            {"type": "image", "source": {"data": "..."}},
                            {"type": "text", "text": "beta"},
                        ],
                        "is_error": True,
                    }
                ]
            },
        }
        events = await _collect(
            parser,
            _bytes_iter([block]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        evt = events[0]
        assert isinstance(evt, CodingAgentToolResultEvent)
        assert evt.is_error is True
        assert "alpha" in evt.result_content
        assert "beta" in evt.result_content
        assert "[image]" in evt.result_content

    @pytest.mark.asyncio
    async def test_rate_limit_event(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter([RATE_LIMIT]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, CodingAgentRateLimitEvent)
        assert evt.rate_limit_type == "five_hour"
        assert evt.status == "allowed"
        assert evt.resets_at == 1780103400
        assert evt.overage_status == "rejected"

    @pytest.mark.asyncio
    async def test_api_retry_event(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter(
                [
                    {
                        "type": "system",
                        "subtype": "api_retry",
                        "attempt": 2,
                        "max_retries": 5,
                        "error": "ETIMEDOUT",
                        "delay_ms": 750,
                    }
                ]
            ),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, CodingAgentApiRetryEvent)
        assert evt.attempt == 2
        assert evt.max_retries == 5
        assert evt.error == "ETIMEDOUT"
        assert evt.delay_ms == 750

    @pytest.mark.asyncio
    async def test_result_success_emits_tokens_then_completed(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter([RESULT_SUCCESS]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="claude-haiku-4-5",
        )
        assert len(events) == 2
        tokens, completed = events
        assert isinstance(tokens, CodingAgentTokensUsedEvent)
        assert tokens.input_tokens == 15
        assert tokens.output_tokens == 156
        assert tokens.cache_read_input_tokens == 36422
        assert tokens.cache_creation_input_tokens == 49375
        assert tokens.cost_usd == Decimal("0.025")
        assert tokens.model == "claude-haiku-4-5"
        assert isinstance(completed, CodingAgentCompletedEvent)
        assert completed.success is True
        assert completed.summary_text == "Done."
        assert completed.duration_ms == 1234
        assert completed.total_input_tokens == 15
        assert completed.total_output_tokens == 156
        assert completed.total_cost_usd == Decimal("0.025")
        assert completed.error_summary is None

    @pytest.mark.asyncio
    async def test_result_error_sets_summary(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter([RESULT_ERROR]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        completed = [e for e in events if isinstance(e, CodingAgentCompletedEvent)][0]
        assert completed.success is False
        assert completed.error_summary == "max_turns"

    @pytest.mark.asyncio
    async def test_skips_non_json_and_blank_lines(self):
        parser = ClaudeStreamJsonParser()
        lines = [
            "",
            "   ",
            "this is not json\n",
            json.dumps(TEXT_ASSISTANT) + "\n",
        ]
        events = await _collect(
            parser,
            _bytes_iter(lines),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        assert len(events) == 1
        assert isinstance(events[0], CodingAgentTextOutputEvent)

    @pytest.mark.asyncio
    async def test_unknown_event_types_logged_and_skipped(self):
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter([{"type": "made_up_type"}]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        assert events == []

    @pytest.mark.asyncio
    async def test_full_pipeline_in_order(self):
        """End-to-end fixture mirroring the captured sample event order."""
        parser = ClaudeStreamJsonParser()
        events = await _collect(
            parser,
            _bytes_iter(
                [
                    INIT_EVENT,
                    THINKING_ASSISTANT,
                    TOOL_USE_ASSISTANT,
                    TOOL_RESULT_USER,
                    RATE_LIMIT,
                    TEXT_ASSISTANT,
                    RESULT_SUCCESS,
                ]
            ),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="claude-haiku-4-5",
            work_item_id="wi-99",
        )
        # Expected order: invoked, ready, thinking, tool_call, tool_result,
        # rate_limit, text, tokens_used, completed.
        assert [type(e).__name__ for e in events] == [
            "CodingAgentInvokedEvent",
            "CodingAgentReadyEvent",
            "CodingAgentThinkingEvent",
            "CodingAgentToolCallEvent",
            "CodingAgentToolResultEvent",
            "CodingAgentRateLimitEvent",
            "CodingAgentTextOutputEvent",
            "CodingAgentTokensUsedEvent",
            "CodingAgentCompletedEvent",
        ]
        # Correlation id (work_item_id) carried throughout.
        assert all(e.correlation_id == "wi-99" for e in events)
        # All execution ids match.
        assert all(getattr(e, "execution_id", "exec-1") == "exec-1" for e in events)

    @pytest.mark.asyncio
    async def test_malformed_event_does_not_crash_parser(self):
        """A single bad event (e.g. missing tool_use_id) must not abort the stream."""
        parser = ClaudeStreamJsonParser()
        bad_tool_result = {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "no id here", "is_error": False}]},
        }
        events = await _collect(
            parser,
            _bytes_iter([bad_tool_result, TEXT_ASSISTANT]),
            execution_id="exec-1",
            coding_agent_id="claude-code",
            invocation_mode="host",
            model="m",
        )
        # The bad event is logged + skipped; the subsequent text event survives.
        assert len(events) == 1
        assert isinstance(events[0], CodingAgentTextOutputEvent)
