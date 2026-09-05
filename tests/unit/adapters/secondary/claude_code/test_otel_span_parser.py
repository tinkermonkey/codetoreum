"""Unit tests for :mod:`codetoreum.adapters.secondary.claude_code.otel_span_parser`.

The parser is the vendor boundary between OTLP/JSON file-exporter output
(produced by an in-container ``otelcol`` sidecar) and the
:class:`CodingAgentOtlpSpanEvent` domain event. These tests pin the parser
against a captured-fixture OTLP/JSON stream and a hand-built collection of
edge-case envelopes.

Coverage:

* Happy path: multi-span fixture round-trip; structured fields populated.
* OTLP/JSON typed-attribute unwrapping (string / int / bool / double /
  array / kvlist / bytes).
* Status code mapping (OK / ERROR / UNSET / unknown).
* Root-span parent-id normalisation (empty string / all-zero hex → None).
* Nanosecond timestamp conversion (and graceful degradation when missing).
* Malformed input handling: non-JSON line, non-object line, missing
  required identifiers, malformed inner shapes.
* File-based parsing (``parse_spans_file``) including missing-file case.
* Raw-span faithful preservation for re-export.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from codetoreum.adapters.secondary.claude_code.otel_span_parser import (
    parse_span_lines,
    parse_spans_file,
)
from codetoreum.domain.events.coding_agent_events import CodingAgentOtlpSpanEvent

FIXTURE_DIR = Path(__file__).parent / "fixtures"
OTLP_SAMPLE_PATH = FIXTURE_DIR / "otlp_spans_sample.jsonl"

EXECUTION_ID = "exec-otel-test"
WORK_ITEM_ID = "issue-42"


def _make_envelope(spans: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap a list of span dicts in a minimal resourceSpans envelope."""
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "claude-code"},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "@anthropic-ai/claude-code"},
                        "spans": spans,
                    }
                ],
            }
        ]
    }


def _well_formed_span(**overrides: Any) -> dict[str, Any]:
    """Return a syntactically valid OTLP/JSON span with optional overrides."""
    span: dict[str, Any] = {
        "traceId": "5b8aa5a2d2c872e8321cf37308d69df2",
        "spanId": "051581bf3cb55c13",
        "parentSpanId": "",
        "name": "claude_code.test",
        "kind": "SPAN_KIND_INTERNAL",
        "startTimeUnixNano": "1748400000000000000",
        "endTimeUnixNano": "1748400001000000000",
        "attributes": [],
        "events": [],
        "status": {"code": "STATUS_CODE_OK"},
    }
    span.update(overrides)
    return span


class TestParseSpanLinesFixture:
    """Happy-path tests against the captured multi-line fixture."""

    def test_fixture_yields_four_spans(self) -> None:
        with OTLP_SAMPLE_PATH.open("r", encoding="utf-8") as fh:
            events = list(
                parse_span_lines(
                    fh,
                    execution_id=EXECUTION_ID,
                    correlation_id=WORK_ITEM_ID,
                )
            )
        # 3 lines: 1 root + 2 children (one envelope) + 1 error span.
        assert len(events) == 4

    def test_fixture_root_span_has_no_parent(self) -> None:
        events = list(_parse_fixture_events())
        root = events[0]
        assert root.name == "claude_code.interaction"
        assert root.parent_span_id is None

    def test_fixture_child_spans_link_to_root(self) -> None:
        events = list(_parse_fixture_events())
        root = events[0]
        for child in events[1:]:
            assert child.parent_span_id == root.span_id
            assert child.trace_id == root.trace_id

    def test_fixture_attributes_flattened(self) -> None:
        events = list(_parse_fixture_events())
        root = events[0]
        # String, int, and bool attribute types all decoded.
        assert root.attributes["model"] == "claude-sonnet-4-6"
        assert root.attributes["session_id"] == "sess-abc-123"
        assert root.attributes["prompt_token_count"] == 4521
        assert root.attributes["input.cached"] is True

    def test_fixture_error_span_status(self) -> None:
        events = list(_parse_fixture_events())
        error_span = next(e for e in events if e.attributes.get("tool.name") == "Bash")
        assert error_span.status == "ERROR"
        # Exception event preserved.
        assert len(error_span.events) == 1
        assert error_span.events[0]["name"] == "exception"

    def test_fixture_execution_and_correlation_ids(self) -> None:
        events = list(_parse_fixture_events())
        for ev in events:
            assert ev.execution_id == EXECUTION_ID
            assert ev.correlation_id == WORK_ITEM_ID

    def test_fixture_raw_span_preserved(self) -> None:
        events = list(_parse_fixture_events())
        root = events[0]
        # raw_span keeps the original OTLP/JSON shape verbatim.
        assert root.raw_span["traceId"] == root.trace_id
        assert root.raw_span["spanId"] == root.span_id
        assert isinstance(root.raw_span["attributes"], list)
        # The typed-attribute encoding is preserved in raw_span (not
        # flattened) so a downstream IObservabilityProvider can re-export
        # to a collector without information loss.
        any_string_value_entry = next(
            entry for entry in root.raw_span["attributes"] if "stringValue" in entry.get("value", {})
        )
        assert any_string_value_entry is not None


def _parse_fixture_events() -> Any:
    with OTLP_SAMPLE_PATH.open("r", encoding="utf-8") as fh:
        yield from parse_span_lines(
            fh,
            execution_id=EXECUTION_ID,
            correlation_id=WORK_ITEM_ID,
        )


class TestAttributeUnwrapping:
    """OTLP/JSON typed attribute decoding."""

    @pytest.mark.parametrize(
        ("attr_value", "expected"),
        [
            ({"stringValue": "hi"}, "hi"),
            ({"intValue": "42"}, 42),  # OTLP/JSON encodes int64 as string.
            ({"intValue": 7}, 7),
            ({"doubleValue": 3.14}, 3.14),
            ({"boolValue": True}, True),
            ({"boolValue": False}, False),
            (
                {
                    "arrayValue": {
                        "values": [
                            {"stringValue": "a"},
                            {"stringValue": "b"},
                        ]
                    }
                },
                ["a", "b"],
            ),
            (
                {
                    "kvlistValue": {
                        "values": [
                            {"key": "x", "value": {"intValue": "1"}},
                            {"key": "y", "value": {"stringValue": "z"}},
                        ]
                    }
                },
                {"x": 1, "y": "z"},
            ),
            ({"bytesValue": "aGVsbG8="}, "aGVsbG8="),
        ],
    )
    def test_typed_attribute_unwrap(self, attr_value: dict[str, Any], expected: Any) -> None:
        envelope = _make_envelope([_well_formed_span(attributes=[{"key": "k", "value": attr_value}])])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert len(events) == 1
        assert events[0].attributes["k"] == expected

    def test_unknown_attribute_type_passes_through(self) -> None:
        # An unrecognised wrapper shape is preserved as-is so raw_span
        # re-export stays faithful even if the flattened form is opaque.
        envelope = _make_envelope([_well_formed_span(attributes=[{"key": "weird", "value": {"futureTypeValue": 99}}])])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        # Passes through the dict unchanged.
        assert events[0].attributes["weird"] == {"futureTypeValue": 99}

    def test_attribute_with_missing_key_is_skipped(self) -> None:
        envelope = _make_envelope(
            [
                _well_formed_span(
                    attributes=[
                        {"value": {"stringValue": "no key"}},  # missing "key"
                        {"key": "good", "value": {"stringValue": "ok"}},
                    ]
                )
            ]
        )
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert events[0].attributes == {"good": "ok"}


class TestStatusNormalisation:
    @pytest.mark.parametrize(
        ("raw_status", "expected"),
        [
            ({"code": "STATUS_CODE_OK"}, "OK"),
            ({"code": "STATUS_CODE_ERROR", "message": "boom"}, "ERROR"),
            ({"code": "STATUS_CODE_UNSET"}, "UNSET"),
            ({"code": "OK"}, "OK"),
            ({"code": "ERROR"}, "ERROR"),
            ({"code": 1}, "OK"),  # proto int form
            ({"code": 2}, "ERROR"),
            ({"code": 0}, "UNSET"),
            ({"code": 99}, "UNSET"),  # unknown int → UNSET
            ({}, "UNSET"),
            ({"code": "wat"}, "UNSET"),
        ],
    )
    def test_status_codes(self, raw_status: dict[str, Any], expected: str) -> None:
        envelope = _make_envelope([_well_formed_span(status=raw_status)])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert events[0].status == expected


class TestParentSpanIdNormalisation:
    @pytest.mark.parametrize(
        ("raw_parent", "expected_is_none"),
        [
            ("", True),
            ("0000000000000000", True),  # all-zero hex
            ("0", True),
            (None, True),
            ("abc123", False),
        ],
    )
    def test_parent_normalisation(self, raw_parent: Any, expected_is_none: bool) -> None:
        envelope = _make_envelope([_well_formed_span(parentSpanId=raw_parent)])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        if expected_is_none:
            assert events[0].parent_span_id is None
        else:
            assert events[0].parent_span_id == str(raw_parent)


class TestTimestampConversion:
    def test_unix_nano_to_iso(self) -> None:
        # 1748400000000000000 ns == 2025-05-28T03:00:00 UTC (give or take).
        envelope = _make_envelope(
            [
                _well_formed_span(
                    startTimeUnixNano="1748400000000000000",
                    endTimeUnixNano="1748400001500000000",
                )
            ]
        )
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert events[0].start_time.endswith("+00:00")
        assert events[0].end_time.endswith("+00:00")
        # End is after start.
        assert events[0].end_time > events[0].start_time

    def test_missing_timestamps_yield_empty_string(self) -> None:
        envelope = _make_envelope([_well_formed_span(startTimeUnixNano=None, endTimeUnixNano=None)])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert events[0].start_time == ""
        assert events[0].end_time == ""

    def test_malformed_timestamp_yields_empty(self) -> None:
        envelope = _make_envelope([_well_formed_span(startTimeUnixNano="not a number")])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert events[0].start_time == ""

    def test_negative_timestamp_yields_empty(self) -> None:
        envelope = _make_envelope([_well_formed_span(startTimeUnixNano="-1")])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert events[0].start_time == ""


class TestMalformedInputHandling:
    def test_non_json_line_skipped(self) -> None:
        events = list(
            parse_span_lines(
                ["not json at all", json.dumps(_make_envelope([_well_formed_span()]))],
                execution_id=EXECUTION_ID,
            )
        )
        assert len(events) == 1

    def test_non_object_line_skipped(self) -> None:
        events = list(
            parse_span_lines(
                ["[1, 2, 3]", json.dumps(_make_envelope([_well_formed_span()]))],
                execution_id=EXECUTION_ID,
            )
        )
        assert len(events) == 1

    def test_empty_line_skipped(self) -> None:
        events = list(
            parse_span_lines(
                ["", "   \n", json.dumps(_make_envelope([_well_formed_span()]))],
                execution_id=EXECUTION_ID,
            )
        )
        assert len(events) == 1

    def test_missing_trace_id_span_skipped(self) -> None:
        envelope = _make_envelope(
            [
                _well_formed_span(traceId=""),
                _well_formed_span(spanId="other-span"),
            ]
        )
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        # Only the second (well-formed) span survives.
        assert len(events) == 1
        assert events[0].span_id == "other-span"

    def test_missing_span_id_skipped(self) -> None:
        envelope = _make_envelope([_well_formed_span(spanId="")])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert events == []

    def test_missing_name_skipped(self) -> None:
        envelope = _make_envelope([_well_formed_span(name="")])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert events == []

    def test_envelope_with_non_list_resource_spans(self) -> None:
        envelope = {"resourceSpans": "not a list"}
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert events == []

    def test_envelope_with_missing_inner_shapes(self) -> None:
        # Envelope present but every inner level is missing or wrong type.
        envelope = {
            "resourceSpans": [
                {"resource": {}, "scopeSpans": "wrong"},
                {"scopeSpans": [{"spans": "wrong"}]},
                {"scopeSpans": [{"spans": [None, "not a dict"]}]},
            ]
        }
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert events == []

    def test_bytes_input_decoded(self) -> None:
        envelope = _make_envelope([_well_formed_span()])
        events = list(
            parse_span_lines(
                [json.dumps(envelope).encode("utf-8")],
                execution_id=EXECUTION_ID,
            )
        )
        assert len(events) == 1


class TestParseSpansFile:
    def test_missing_file_yields_no_spans(self, tmp_path: Path) -> None:
        events = list(
            parse_spans_file(
                tmp_path / "does_not_exist.jsonl",
                execution_id=EXECUTION_ID,
            )
        )
        assert events == []

    def test_reads_file_when_present(self, tmp_path: Path) -> None:
        spans_file = tmp_path / "spans.jsonl"
        envelope = _make_envelope([_well_formed_span()])
        spans_file.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
        events = list(
            parse_spans_file(
                spans_file,
                execution_id=EXECUTION_ID,
                correlation_id=WORK_ITEM_ID,
            )
        )
        assert len(events) == 1
        assert events[0].correlation_id == WORK_ITEM_ID

    def test_reads_real_captured_fixture(self) -> None:
        events = list(
            parse_spans_file(
                OTLP_SAMPLE_PATH,
                execution_id=EXECUTION_ID,
            )
        )
        # Same span count as the multi-line iterable test.
        assert len(events) == 4


class TestEventShape:
    """The parser must yield real :class:`CodingAgentOtlpSpanEvent` instances."""

    def test_yields_correct_event_type(self) -> None:
        envelope = _make_envelope([_well_formed_span()])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        assert isinstance(events[0], CodingAgentOtlpSpanEvent)
        assert events[0].type == "coding_agent.otlp_span"
        assert events[0].source == "claude_code"

    def test_event_round_trips_to_dict_and_back(self) -> None:
        envelope = _make_envelope([_well_formed_span()])
        events = list(
            parse_span_lines(
                [json.dumps(envelope)],
                execution_id=EXECUTION_ID,
            )
        )
        original = events[0]
        as_dict = original.to_dict()
        rehydrated = CodingAgentOtlpSpanEvent.from_dict(as_dict)
        assert rehydrated.trace_id == original.trace_id
        assert rehydrated.span_id == original.span_id
        assert rehydrated.name == original.name
        assert rehydrated.attributes == original.attributes
        # Events come back as list when JSON-serialised; the from_dict ctor
        # rebuilds the tuple.
        assert tuple(rehydrated.events) == original.events
        assert rehydrated.raw_span == original.raw_span
