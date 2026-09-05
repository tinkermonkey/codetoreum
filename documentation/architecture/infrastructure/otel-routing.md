---
applies_to: "documentation/architecture/infrastructure/otel-routing.md"
---

# Agent-side OTel Routing via Event Bus

> **Status**: Design landed (this document). Implementation: parser + fixtures landed (in `src/codetoreum/adapters/secondary/claude_code/otel_span_parser.py`); strategy wiring + agent image sidecar deferred (tracked as DEF-019). This document is the authoritative answer to **O3** in `~/.claude/plans/coding-agent-port-redesign.md`.

## Problem

`CodingAgentOtlpSpanEvent` is defined (D1) but no adapter emits it. The post-DEF-014 architecture forbids agent containers from reaching `otel-collector` directly — agents now run on Docker's default `bridge` network for outbound internet only, with no path to `codetoreum_default`-attached services like the collector. Claude Code's internal OTel SDK exports to whatever `OTEL_EXPORTER_OTLP_ENDPOINT` it can reach, which by construction is now nothing useful.

The redesign proposal §3f committed to **routing agent OTel spans through the event bus** as `CodingAgentOtlpSpanEvent`, with an `IObservabilityProvider` adapter subscribing and forwarding to whatever collector the deployment configures. That commitment is preserved by this design.

## Constraint summary

| # | Constraint | Source |
|---|------------|--------|
| C1 | Agent containers MUST NOT require attachment to a non-default Docker network. | DEF-014 |
| C2 | Agent execution output flows exclusively through `CodingAgent*` events. Filesystem extraction is forbidden for *output*, allowed for infrastructure telemetry. | INV-16 |
| C3 | The adapter and its strategies stay free of resilience logic (retries / circuit breaker / rate limit). | INV-11 |
| C4 | `CodingAgent*` events MUST be emitted on the event bus. Granular events use 14-day retention. | INV-15 |
| C5 | We cannot patch Claude Code source — it is a closed binary. | proposal §3f |
| C6 | The adapter MUST work without granting the agent container access to the Docker socket. | Agent security model in `CLAUDE.md` |

INV-16 is the load-bearing constraint to interpret. The text reads: *"Agent execution output flows exclusively through CodingAgent* events. Filesystem extraction is forbidden ... A crashed agent + lost filesystem must not equal lost execution data."* OTel spans are **infrastructure telemetry**, not execution output (the work product is the git commit; the OTel span describes the *behaviour* of the LLM and tool stack, not the *decision* the agent made). A file used as a transient inter-process buffer **inside** the container, never persisted past the container's lifetime, and consumed by the adapter before container removal, does not violate the "crashed-agent" clause — if the container crashes, the spans we get are exactly the spans the agent emitted before the crash, no different from any other adapter-collected telemetry. **Routing OTel via files inside the container is INV-16-compliant.** This is documented here so future readers don't second-guess it.

## Approaches considered

Four candidate mechanisms were investigated:

### Approach A — In-container `otelcol` sidecar

**Mechanism**: Bake an `otelcol` (or `otelcol-contrib`) static binary into `codetoreum-agent:latest`. The container's entrypoint launches `otelcol --config /etc/otelcol/config.yaml` in the background listening on `localhost:4318` (HTTP) or `4317` (gRPC). `otelcol` is configured with an OTLP receiver and a **file exporter** (or `debug` exporter) writing newline-delimited JSON spans to a known path like `/var/otel/spans.jsonl`. The container env sets `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` and `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` so Claude Code's internal exporter ships spans to the local collector. After the agent process exits, the strategy reads `spans.jsonl` from the workspace mount (which would need a small dedicated subdirectory carved out for telemetry), parses it line-by-line, and emits `CodingAgentOtlpSpanEvent` per span.

| Attribute | Value |
|-----------|-------|
| C1 compliance | ✅ (everything is `localhost` inside the container) |
| C2 compliance | ✅ (telemetry-only, not output) |
| C3 compliance | ✅ (sidecar is plumbing) |
| C5 compliance | ✅ (no Claude Code changes; just env vars) |
| C6 compliance | ✅ (no Docker socket access needed for sidecar) |
| Streaming | ⚠️ (post-run batch; or follow-mode tail with extra plumbing) |
| Image size | +70MB (`otelcol` static binary) to +250MB (`otelcol-contrib`) |
| Operational complexity | High: wrapper entrypoint script must launch `otelcol`, wait for readiness, exec `claude`, then signal `otelcol` to flush + exit |
| Failure modes | If `otelcol` fails to start, `claude` emits to a black hole; we lose spans silently unless the entrypoint health-checks the receiver first |
| Reusability | Yes — Codex can use the same image |
| Verdict | **Chosen** for the future implementation cycle. Best fit for the constraints. |

### Approach B — `host.docker.internal:host-gateway` to an orchestrator-side receiver

**Mechanism**: The orchestrator's host process runs an OTel HTTP receiver (Python `opentelemetry-proto`-based, or a child `otelcol` process) on `localhost:4318`. Agent containers are created with `--add-host=host.docker.internal:host-gateway` and `OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318`. The receiver decodes OTLP HTTP requests and emits `CodingAgentOtlpSpanEvent` on the event bus directly.

| Attribute | Value |
|-----------|-------|
| C1 compliance | ⚠️ (no extra network attachment, but requires Docker host-gateway feature; Linux Docker 20.10+ supports it but it's opt-in per container) |
| C2 compliance | ✅ |
| C3 compliance | ✅ |
| C5 compliance | ✅ |
| C6 compliance | ✅ |
| Streaming | ✅ (true streaming as spans arrive) |
| Image size | +0 |
| `IContainer` port change required | **Yes** — `IContainer.create` would need a new `extra_hosts: dict[str, str] \| None = None` parameter so `ContainerizedClaudeStrategy` can pass `host.docker.internal=host-gateway`. The Docker adapter would translate to `--add-host`. |
| New long-lived component | **Yes** — an OTLP receiver inside the orchestrator process. Adds a TCP listener and protobuf decode dependency. |
| Host strategy applicability | Awkward — host-mode agents are not in containers, so the receiver becomes a same-host loopback that's strictly a complexity surcharge |
| Verdict | **Rejected** — port change risk + a new long-lived TCP listener inside the orchestrator that didn't exist before. The complexity isn't justified by the streaming benefit since the agent's execution lifetime is bounded (5–60 min typical) and post-exit batch is acceptable. |

### Approach C — OTel SDK file exporter

**Mechanism**: Configure Claude Code to use a file exporter (`OTEL_TRACES_EXPORTER=file` or equivalent). The container writes spans to a known file path; the strategy reads the file post-exit and emits events.

| Attribute | Value |
|-----------|-------|
| C5 compliance | ❌ — **does not exist in the OTel JS SDK and not exposed by Claude Code**. The `OTEL_TRACES_EXPORTER` env var in Claude Code accepts only `console`, `otlp`, `none` per the [monitoring docs](https://code.claude.com/docs/en/monitoring-usage). The third-party `otel-file-exporter` Python package writes JSONL files but is loaded by the *application's* SDK and cannot be injected into a closed Bun-compiled binary. |
| Verdict | **Rejected** — no upstream support; would require Claude Code source changes which C5 forbids. |

### Approach D — Console exporter (`OTEL_TRACES_EXPORTER=console`)

**Mechanism**: Set `CLAUDE_CODE_ENABLE_TELEMETRY=1` + `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` + `OTEL_TRACES_EXPORTER=console` in the container. The OTel JS SDK's `ConsoleSpanExporter` prints each span via `console.dir(span, { depth: 3 })`. The strategy's stream reader splits stdout into (a) Claude Code's `stream-json` lines (which the existing parser consumes) and (b) the console-export span lines (which a new parser converts to `CodingAgentOtlpSpanEvent`).

| Attribute | Value |
|-----------|-------|
| C1 compliance | ✅ |
| C2 compliance | ✅ |
| C3 compliance | ✅ |
| C5 compliance | ✅ |
| C6 compliance | ✅ |
| Streaming | ✅ |
| Image size | +0 |
| Critical blocker | **The output format is not JSON.** `console.dir` uses Node's `util.inspect` which emits JavaScript object-literal syntax (unquoted keys, single quotes, `undefined`, Symbol(), etc.) — see `opentelemetry-js/packages/opentelemetry-sdk-trace-base/src/export/ConsoleSpanExporter.ts`. Parsing this reliably across SDK versions requires either (a) shelling out to Node to re-stringify (heavy), (b) hand-rolling a util.inspect parser (brittle, will break on minor SDK upgrades), or (c) regex-extracting the four or five fields we actually need (loses fidelity for `raw_span`). |
| Stdout collision risk | Claude Code's `stream-json` is on stdout. The Node `console.dir` default also writes to stdout. The two streams interleave at indeterminate line boundaries because `console.dir` outputs multi-line indented blocks. Disambiguating the boundary between a Claude `stream-json` line (single JSON object per line, starting with `{"type":...}`) and a span block (multi-line, starts with `{`, uses unquoted keys) is non-trivial. |
| Verdict | **Rejected as primary path.** Kept as a fallback if Approach A's sidecar binary cannot be cleanly bundled. The util.inspect format problem is the disqualifier — the moment Claude Code or the underlying OTel JS SDK changes `console.dir` options (e.g. to use `depth: null` or `compact: true`), our parser breaks silently. |

## Chosen approach: A (sidecar `otelcol` inside the agent image)

**Mechanism (recap)**:

1. **Image change** (`Dockerfile.agent`): bundle a static `otelcol` (core, ~70MB) at `/usr/local/bin/otelcol` and a config file at `/etc/otelcol/config.yaml` configured with:
   - OTLP receiver on `127.0.0.1:4318` (HTTP/protobuf — Claude Code's default for that endpoint).
   - File exporter writing newline-delimited OTLP/JSON spans to `/var/otel/spans.jsonl`.
   - Single `traces` pipeline.

2. **Entrypoint change** (`scripts/agent-entrypoint.sh`): before `exec`-ing the agent command, launch `otelcol` in the background, poll `:4318` until the receiver is healthy (or `5s` timeout), then run Claude Code. On agent exit, signal `otelcol` `SIGTERM` and wait for it to flush its file output.

3. **Env change** (`ContainerizedClaudeStrategy._build_environment`): inject
   ```
   CLAUDE_CODE_ENABLE_TELEMETRY=1
   CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
   OTEL_TRACES_EXPORTER=otlp
   OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf
   OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces
   ```
   (Metrics / logs deliberately stay off in this first pass; granular metric/log routing is a future increment.)

4. **Workspace mount change**: alongside the existing `workspace_path` → `/workspace/<project>` mount, add a small tmpfs (or bind mount of a per-execution `tmp/otel/` host directory) at `/var/otel`. The strategy reads `spans.jsonl` from this host-side directory **after** `await self._container.wait(...)` and **before** `self._container.remove(...)`.

5. **Strategy change** (`ContainerizedClaudeStrategy.execute`): after the existing `_stream_and_collect(...)` returns, before the `finally:` removal block, call a new helper `_emit_otlp_spans(host_otel_dir, execution_id, work_item_id)` which opens `spans.jsonl`, parses each line via the OTel span parser (see below), and publishes `CodingAgentOtlpSpanEvent` to the event bus per parsed span.

6. **Host strategy**: `HostClaudeStrategy` cannot easily share this mechanism (the agent runs in the orchestrator process's environment). For host mode in this design pass, the orchestrator can already configure its own OTel collector via the existing infrastructure observability stack; spans emitted by a host-mode Claude Code subprocess will export to whatever `OTEL_EXPORTER_OTLP_ENDPOINT` the orchestrator's environment defines. We do not emit `CodingAgentOtlpSpanEvent` for host mode in this iteration — the spans land in the existing collector untouched. This is acceptable because host mode is documented as a development-mode convenience (D7 carryover note), not the production path.

## Parser shape

The parser is **isolated from the strategy** so it can be unit-tested against captured fixtures without needing a live `otelcol`. Module: `src/codetoreum/adapters/secondary/claude_code/otel_span_parser.py`.

Input: an OTLP/JSON span line as emitted by `otelcol`'s file exporter, e.g.

```json
{
  "resourceSpans": [{
    "resource": { "attributes": [...] },
    "scopeSpans": [{
      "scope": { "name": "claude-code" },
      "spans": [{
        "traceId": "5b8aa5a2d2c872e8321cf37308d69df2",
        "spanId": "051581bf3cb55c13",
        "parentSpanId": "",
        "name": "claude_code.interaction",
        "kind": "SPAN_KIND_INTERNAL",
        "startTimeUnixNano": "1748400000000000000",
        "endTimeUnixNano": "1748400003500000000",
        "attributes": [...],
        "status": { "code": "STATUS_CODE_OK" }
      }]
    }]
  }]
}
```

Output: zero or more `CodingAgentOtlpSpanEvent` instances (one per inner `span`), with:

- `trace_id` ← `spans[i].traceId`
- `span_id` ← `spans[i].spanId`
- `parent_span_id` ← `spans[i].parentSpanId` (None if empty string)
- `name` ← `spans[i].name`
- `start_time` ← ISO 8601 conversion of `startTimeUnixNano`
- `end_time` ← ISO 8601 conversion of `endTimeUnixNano`
- `attributes` ← flat `{k: v}` projection of `spans[i].attributes` (OTLP/JSON uses `{"key": ..., "value": {"stringValue": ...}}` shape; the parser flattens)
- `events` ← `spans[i].events` (passed through as tuple of dicts)
- `status` ← `spans[i].status.code` (`"STATUS_CODE_OK"` → `"OK"`, etc.)
- `raw_span` ← the original span dict (for faithful re-export per Q2 Lean)

The parser:
- Is stateless.
- Handles batch lines (one `resourceSpans` envelope per line, multiple `scopeSpans` and `spans` arrays possible per envelope).
- Skips lines that don't parse as JSON (logged at debug level — never silently dropped beyond that).
- Skips spans missing `traceId`/`spanId`/`name` with a debug log and continues.

## Why other approaches were rejected — short form

- **B** introduces a port change (`IContainer.extra_hosts`) and a long-lived TCP receiver inside the orchestrator. Both are increases in surface area for marginal streaming benefit.
- **C** depends on an SDK feature that does not exist in Claude Code (closed binary, no plugin loading).
- **D** depends on parsing `console.dir` output which is JS object-literal syntax, not JSON, and is explicitly documented as unstable by OpenTelemetry. The format will break on minor SDK upgrades silently.

## Implementation phases

| Phase | Deliverable | Tracked as |
|-------|-------------|------------|
| P1 (this commit) | This design doc | — |
| P2 (this commit series) | `otel_span_parser.py` + unit tests against captured OTLP/JSON fixtures | DEF-019 (parser landed; sidecar deferred) |
| P3 (next cycle) | `Dockerfile.agent` adds `otelcol` static binary; `scripts/agent-entrypoint.sh` launches it; tmpfs/host bind for `/var/otel` plumbed through `ContainerizedClaudeStrategy._build_volumes` | DEF-019 (sidecar) |
| P4 (next cycle) | `ContainerizedClaudeStrategy._emit_otlp_spans` calls parser + emits `CodingAgentOtlpSpanEvent` on the event bus before container removal | DEF-019 (wiring) |
| P5 (next cycle) | Integration test: spin up the agent image, run a short Claude execution, assert `CodingAgentOtlpSpanEvent` lands in ES | DEF-019 (e2e) |

P3–P5 are deferred to a future cycle because adding ~70MB to the agent image and a wrapper entrypoint script is a non-trivial change that warrants its own focused review.

## The IObservabilityProvider re-export side

This document covers the **capture** side. The **re-export** side — an `IObservabilityProvider` adapter that subscribes to `CodingAgentOtlpSpanEvent` and forwards spans to the deployment's configured collector — is a separate output port and adapter, designed in `documentation/architecture/ports/output/` (TODO: port spec to be added when the re-export adapter is built). For now: spans land as immutable events in the event store with 14-day retention (per INV-15). Behavioural analysis can query them directly from ES without needing the collector hop at all.

## Cross-references

- **Open question**: O3 in `~/.claude/plans/coding-agent-port-redesign.md`
- **Validation gap**: §"Gap 5: OTel via event bus is still blocked" in [`../adapters/planned/coding-agent-port-validation.md`](../adapters/planned/coding-agent-port-validation.md)
- **Event shape**: `src/codetoreum/domain/events/coding_agent_events.py::CodingAgentOtlpSpanEvent`
- **Strategy entry points**: `src/codetoreum/adapters/secondary/claude_code/strategies/{containerized,host}.py`
- **Invariants**: INV-11, INV-15, INV-16 in `bootstrap/ARCHITECTURE.md` §6
- **DEF that motivated this**: DEF-014 in `bootstrap/ARCHITECTURE.md` §9
- **DEF that tracks this**: DEF-019 in `bootstrap/ARCHITECTURE.md` §9
