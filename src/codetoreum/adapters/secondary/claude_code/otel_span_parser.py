"""OTLP/JSON span parser → :class:`CodingAgentOtlpSpanEvent`.

This module is the vendor boundary between the OpenTelemetry Collector's
**file exporter** output (newline-delimited OTLP/JSON) and Codetoreum's
domain event vocabulary. It is paired with the in-container ``otelcol``
sidecar pattern documented in
``documentation/architecture/infrastructure/otel-routing.md``.

The parser is **isolated from the strategy** so it can be unit-tested
against captured OTel fixtures without needing a live ``otelcol`` running.
The strategy (``ContainerizedClaudeStrategy``) is the consumer; it reads
``/var/otel/spans.jsonl`` from the per-execution telemetry mount after the
agent process exits, hands the lines to :func:`parse_spans_file` or
:func:`parse_span_lines`, and publishes each returned event to the event
bus before removing the container.

Wire format
-----------

The OTel Collector's file exporter (and ``debug`` exporter at
``verbosity: detailed``) emits one JSON object per line, in OTLP/JSON
encoding. Each line contains a ``resourceSpans`` envelope with one or
more ``resource`` blocks, each with one or more ``scopeSpans`` blocks,
each carrying one or more ``spans``. A single line therefore expands
to **N spans** rather than one. Example::

    {
      "resourceSpans": [{
        "resource": {"attributes": [{"key": "service.name",
                                     "value": {"stringValue": "claude-code"}}]},
        "scopeSpans": [{
          "scope": {"name": "claude-code"},
          "spans": [{
            "traceId": "5b8aa5a2d2c872e8321cf37308d69df2",
            "spanId": "051581bf3cb55c13",
            "parentSpanId": "",
            "name": "claude_code.interaction",
            "kind": "SPAN_KIND_INTERNAL",
            "startTimeUnixNano": "1748400000000000000",
            "endTimeUnixNano": "1748400003500000000",
            "attributes": [{"key": "model",
                            "value": {"stringValue": "claude-sonnet-4-6"}}],
            "events": [],
            "status": {"code": "STATUS_CODE_OK"}
          }]
        }]
      }]
    }

The parser **flattens** OTLP/JSON's typed attribute encoding
(``{"key": k, "value": {"stringValue": v}}``) to a flat ``{k: v}`` dict
in the resulting event's ``attributes`` field. The original span dict
is preserved verbatim in ``raw_span`` so a downstream
``IObservabilityProvider`` adapter can re-export the spans without loss
to whichever collector the deployment configures.

INV invariants honoured
-----------------------

* **INV-11** — no resilience logic here; this is pure parsing.
* **INV-15** — the parser yields :class:`CodingAgentOtlpSpanEvent` which
  is part of the granular ``CodingAgent*`` family. Granular events use
  14-day retention.
* **INV-16** — OTel spans are **infrastructure telemetry** (describe the
  agent's behaviour) rather than execution output (the work product is
  the git commit). The OTel sidecar's transient ``spans.jsonl`` file is
  an inter-process buffer and is read before the container is removed.
  See ``otel-routing.md`` for the long-form INV-16 rationale.

Resilience
----------

The parser logs and skips malformed lines / spans rather than raising,
so a single corrupt line does not poison an entire batch. Each skip is
logged at debug level with ``exc_info=True`` when relevant (no silent
failures per ARCH rules).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codetoreum.domain.events.coding_agent_events import CodingAgentOtlpSpanEvent

logger = logging.getLogger(__name__)

_SOURCE = "claude_code"
_TYPE_OTLP_SPAN = "coding_agent.otlp_span"


def parse_span_lines(
    lines: Iterable[str | bytes],
    *,
    execution_id: str,
    correlation_id: str | None = None,
) -> Iterator[CodingAgentOtlpSpanEvent]:
    """Yield :class:`CodingAgentOtlpSpanEvent` per inner span in each line.

    Args:
        lines: Iterable of raw OTLP/JSON envelope lines. Each line is one
            ``resourceSpans``-rooted object. Bytes are decoded as UTF-8.
        execution_id: Aggregate id for the resulting event stream.
        correlation_id: Optional work-item id carried on every event as
            ``correlation_id`` so the event store can index by work item.

    Yields:
        One :class:`CodingAgentOtlpSpanEvent` per inner span. Malformed
        envelopes are skipped (debug-logged). Spans missing required
        identifiers (``traceId`` / ``spanId`` / ``name``) are skipped
        (debug-logged).
    """
    for raw in lines:
        decoded = _decode_line(raw)
        if not decoded:
            continue

        try:
            envelope = json.loads(decoded)
        except json.JSONDecodeError as exc:
            logger.debug(
                "Skipping non-JSON OTLP line: %s; line=%r",
                exc,
                decoded[:200],
            )
            continue

        if not isinstance(envelope, dict):
            logger.debug(
                "Skipping non-object OTLP line: %r",
                decoded[:200],
            )
            continue

        yield from _extract_events_from_envelope(
            envelope=envelope,
            execution_id=execution_id,
            correlation_id=correlation_id,
        )


def parse_spans_file(
    path: str | Path,
    *,
    execution_id: str,
    correlation_id: str | None = None,
) -> Iterator[CodingAgentOtlpSpanEvent]:
    """Parse ``spans.jsonl`` at ``path`` and yield events.

    Convenience wrapper over :func:`parse_span_lines` that opens the file
    line-by-line. Missing-file is treated as "no spans" (debug-logged);
    the caller decides whether that's an error.

    Args:
        path: Path to the OTel-collector-emitted ``spans.jsonl``.
        execution_id: Aggregate id for the resulting event stream.
        correlation_id: Optional work-item id carried on every event.

    Yields:
        One :class:`CodingAgentOtlpSpanEvent` per parsed inner span.
    """
    p = Path(path)
    if not p.is_file():
        logger.debug("OTel spans file not found: %s — yielding no spans.", p)
        return

    try:
        with p.open("r", encoding="utf-8") as fh:
            yield from parse_span_lines(
                fh,
                execution_id=execution_id,
                correlation_id=correlation_id,
            )
    except OSError:
        # Caller handles persistence-level failures; we log and stop.
        logger.exception("Failed reading OTel spans file: %s", p)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _decode_line(raw: str | bytes) -> str:
    """Decode bytes / strip, return empty string on blank input."""
    if isinstance(raw, (bytes, bytearray)):
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw.decode("utf-8", errors="replace")
    else:
        decoded = raw
    return decoded.strip()


def _extract_events_from_envelope(
    *,
    envelope: dict[str, Any],
    execution_id: str,
    correlation_id: str | None,
) -> Iterator[CodingAgentOtlpSpanEvent]:
    """Walk one OTLP/JSON envelope and yield one event per inner span."""
    resource_spans = envelope.get("resourceSpans") or []
    if not isinstance(resource_spans, list):
        logger.debug("Skipping envelope with non-list resourceSpans")
        return

    for rs in resource_spans:
        if not isinstance(rs, dict):
            continue
        scope_spans = rs.get("scopeSpans") or []
        if not isinstance(scope_spans, list):
            continue
        for ss in scope_spans:
            if not isinstance(ss, dict):
                continue
            spans = ss.get("spans") or []
            if not isinstance(spans, list):
                continue
            for span in spans:
                if not isinstance(span, dict):
                    continue
                event = _build_event(
                    span=span,
                    execution_id=execution_id,
                    correlation_id=correlation_id,
                )
                if event is not None:
                    yield event


def _build_event(
    *,
    span: dict[str, Any],
    execution_id: str,
    correlation_id: str | None,
) -> CodingAgentOtlpSpanEvent | None:
    """Map one OTLP/JSON span dict to a domain event.

    Returns ``None`` (with a debug log) if required identifiers are
    missing — never raises. The strategy publishes whatever the parser
    produces, so dropping malformed spans is preferable to crashing the
    post-run cleanup path.
    """
    trace_id = str(span.get("traceId") or "")
    span_id = str(span.get("spanId") or "")
    name = str(span.get("name") or "")
    if not trace_id or not span_id or not name:
        logger.debug(
            "Skipping OTLP span missing required fields: " "traceId=%r span_id=%r name=%r",
            trace_id,
            span_id,
            name,
        )
        return None

    parent_span_id_raw = span.get("parentSpanId")
    parent_span_id: str | None
    if parent_span_id_raw in (None, "", "0", "0" * 16):
        # OTLP/JSON serialises a root span's parent as empty string or
        # all-zero hex; normalise both to None.
        parent_span_id = None
    else:
        parent_span_id = str(parent_span_id_raw)

    start_time = _unix_nano_to_iso(span.get("startTimeUnixNano"))
    end_time = _unix_nano_to_iso(span.get("endTimeUnixNano"))
    attributes = _flatten_otlp_attributes(span.get("attributes"))
    events = _normalise_span_events(span.get("events"))
    status = _normalise_status(span.get("status"))

    try:
        return CodingAgentOtlpSpanEvent(
            type=_TYPE_OTLP_SPAN,
            timestamp=_now_iso(),
            source=_SOURCE,
            correlation_id=correlation_id,
            execution_id=execution_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=name,
            start_time=start_time,
            end_time=end_time,
            attributes=attributes,
            events=events,
            status=status,
            raw_span=dict(span),
        )
    except ValueError:
        # The event ctor enforces non-empty trace_id/span_id/name; we
        # already filtered above, so this should be unreachable, but
        # log defensively rather than crash the loop.
        logger.exception(
            "OTLP span passed pre-check but event ctor rejected it; " "span=%r",
            span,
        )
        return None


def _flatten_otlp_attributes(raw: Any) -> dict[str, Any]:
    """Flatten OTLP/JSON's typed attribute list to a flat ``{k: v}`` dict.

    OTLP/JSON encodes attributes as a list of ``{"key": k, "value":
    {"<type>Value": v}}``. The ``<type>`` is one of ``string``, ``bool``,
    ``int``, ``double``, ``array``, ``kvlist``, ``bytes``. This helper
    unwraps the typed value to a plain Python value.

    Returns an empty dict for missing / malformed input rather than
    raising — a partially-broken attribute list should not poison the
    whole span.
    """
    if not isinstance(raw, list):
        return {}
    out: dict[str, Any] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            continue
        value = _unwrap_otlp_value(entry.get("value"))
        out[key] = value
    return out


def _unwrap_otlp_value(value: Any) -> Any:
    """Unwrap an OTLP/JSON typed value to a Python primitive / container.

    Recognised wrappers:

    * ``{"stringValue": s}`` → ``s``
    * ``{"intValue": "123"}`` → ``123`` (OTLP/JSON encodes int64 as string)
    * ``{"doubleValue": 1.5}`` → ``1.5``
    * ``{"boolValue": True}`` → ``True``
    * ``{"arrayValue": {"values": [...]}}`` → ``[..., ...]`` (recursive)
    * ``{"kvlistValue": {"values": [...]}}`` → ``{k: v}`` (recursive)
    * ``{"bytesValue": "<base64>"}`` → the base64 string as-is (caller's
      responsibility to decode if needed; we don't auto-decode binary)

    Unrecognised shapes are passed through unchanged so the ``raw_span``
    re-export stays faithful.
    """
    if not isinstance(value, dict):
        return value
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        iv = value["intValue"]
        try:
            return int(iv)
        except (TypeError, ValueError):
            return iv
    if "doubleValue" in value:
        return value["doubleValue"]
    if "boolValue" in value:
        return bool(value["boolValue"])
    if "arrayValue" in value:
        inner = value["arrayValue"]
        if isinstance(inner, dict):
            values = inner.get("values") or []
            if isinstance(values, list):
                return [_unwrap_otlp_value(v) for v in values]
        return []
    if "kvlistValue" in value:
        inner = value["kvlistValue"]
        if isinstance(inner, dict):
            values = inner.get("values") or []
            if isinstance(values, list):
                out: dict[str, Any] = {}
                for entry in values:
                    if not isinstance(entry, dict):
                        continue
                    k = entry.get("key")
                    if not isinstance(k, str):
                        continue
                    out[k] = _unwrap_otlp_value(entry.get("value"))
                return out
        return {}
    if "bytesValue" in value:
        return value["bytesValue"]
    return value


def _normalise_span_events(raw: Any) -> tuple[dict[str, Any], ...]:
    """Normalise the inner ``events`` array to a tuple of plain dicts.

    Each OTel span can carry events (e.g. exceptions, retries). We keep
    them as a tuple of raw dicts — they're consumer-of-the-event's
    problem to interpret. Empty / missing → empty tuple.
    """
    if not isinstance(raw, list):
        return ()
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(dict(item))
    return tuple(out)


def _normalise_status(raw: Any) -> str:
    """Map OTLP/JSON status code to a short string.

    OTLP/JSON encodes status as ``{"code": "STATUS_CODE_OK", ...}`` or
    ``{"code": 1, "message": "..."}``. We accept both string and int
    encodings and reduce to ``"OK"`` / ``"ERROR"`` / ``"UNSET"``.
    Unknown codes become ``"UNSET"`` to match the event's default.
    """
    if not isinstance(raw, dict):
        return "UNSET"
    code = raw.get("code")
    if isinstance(code, int):
        # OTel proto: 0 UNSET, 1 OK, 2 ERROR.
        return {0: "UNSET", 1: "OK", 2: "ERROR"}.get(code, "UNSET")
    if isinstance(code, str):
        if code in {"STATUS_CODE_OK", "OK"}:
            return "OK"
        if code in {"STATUS_CODE_ERROR", "ERROR"}:
            return "ERROR"
        if code in {"STATUS_CODE_UNSET", "UNSET"}:
            return "UNSET"
        return "UNSET"
    return "UNSET"


def _unix_nano_to_iso(raw: Any) -> str:
    """Convert OTLP's nanoseconds-since-epoch to an ISO-8601 UTC string.

    OTLP/JSON encodes nanosecond timestamps as **strings** (because JS
    integers cannot represent 64-bit nanos safely) or occasionally as
    plain ints. Missing / malformed → empty string so the event keeps
    its default-empty value (the ctor only requires the *id* fields).
    """
    if raw is None:
        return ""
    try:
        nanos = int(raw)
    except (TypeError, ValueError):
        return ""
    if nanos <= 0:
        return ""
    seconds, remainder = divmod(nanos, 1_000_000_000)
    # Build with microsecond precision (Python datetime caps at us).
    micros = remainder // 1_000
    try:
        dt = datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=micros)
    except (OverflowError, OSError, ValueError):
        return ""
    return dt.isoformat()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
