---
applies_to: "documentation/architecture/adapters/planned/coding-agent-port-validation.md"
---

# `ICodingAgent` Port Validation Across Three Target Adapters

> **Status**: D9 of the coding-agent port redesign (DEF-015). **Design-only.** This document is the cross-adapter validation summary for `ICodingAgent` — does the port shape proven against Claude Code (D1–D7) hold for `GitHubCopilotAdapter` and `CodexAdapter` without modification?

## Scope and Method

Three target adapters were specified by §Q6 of the proposal:

1. **`ClaudeCodeAdapter`** — landed and validated in D3 / D7. Reference at [`../production/claude-code-adapter.md`](../production/claude-code-adapter.md).
2. **`GitHubCopilotAdapter`** — designed in D9. Spec at [`github-copilot-adapter.md`](./github-copilot-adapter.md).
3. **`CodexAdapter`** — designed in D9. Spec at [`codex-adapter.md`](./codex-adapter.md).

For each adapter, the D9 design walked through:
- `supported_invocation_modes()` — which modes apply
- `execute()` shape — how the single-method contract is implemented
- Internal structure (strategies / parser / renderer split)
- Event mapping — which of the 11 `CodingAgent*` events are emittable
- Configuration — `mode_config` consumption
- Resilience — which `ResilientCodingAgentDecorator` behaviours apply
- Port-shape critique — what fits cleanly, what fits with strain, what doesn't fit

This document consolidates findings into a verdict.

## Headline Verdict

**The `ICodingAgent` port shape holds across all three target adapters without changes that would break existing code.** Two **additive, non-breaking enhancements** are recommended to clean up vendor-accounting and tool-categorisation differences surfaced by `GitHubCopilotAdapter` and `CodexAdapter`; both can land in a focused D10 phase before the Copilot adapter implementation cycle. Three **documentation-only changes** are recommended for the event catalog. **No breaking port changes are required.**

| Aspect | Verdict | Notes |
|---|---|---|
| `ICodingAgent` interface (two methods) | **Holds unchanged** | Both methods make sense for all three adapters. |
| `InvocationMode.{CONTAINERIZED, HOST, API}` enum | **Holds unchanged** | The three values cover all three adapters. Copilot is the sole API consumer; Codex is the second CONTAINERIZED+HOST adapter. No fourth mode surfaced. |
| `CodingAgentInvocationOptions` value object | **Holds with one recommended additive change** | `cost_limit_usd` is not enforceable by Copilot; recommend adding a non-breaking advisory mechanism (see §Recommended Changes). |
| `WorkspaceContext` value object | **Holds unchanged** | `workspace_path` is unused by Copilot but present-and-ignored is the right contract; downgrading to optional creates friction for the majority. |
| `CodingAgentResult` value object | **Holds with one recommended additive change** | `total_input_tokens` / `total_output_tokens` are token-shaped; Copilot reports requests. Recommend a `resource_usage` discriminated union (additive). |
| `IPromptBuilder` / `StructuredPrompt` | **Holds unchanged** | The vendor-agnostic prompt assembly worked for all three adapters; each renderer translates cleanly to its vendor's input format. |
| `CodingAgent*` event family (11 events) | **Holds with documentation tiering recommended** | Not every adapter can emit every event; recommend tiering the catalog. |
| Strategy split (containerized vs host) | **Holds and validates as a template** | Codex's strategy split is one-for-one with Claude Code's. Confirms it's not Claude-specific. |
| 14-day retention policy on granular events | **Holds, with one nuance** | Copilot has fewer events per execution; 14 days is fine, but cost analysis may want longer retention on `Completed` for Copilot specifically. See §Retention Adequacy. |

## Per-Adapter Fit

### `ClaudeCodeAdapter` (reference)
- All 11 `CodingAgent*` events emittable in principle (10 of 11 today; `CodingAgentOtlpSpanEvent` blocked by O3 — same OTel sidecar gap that Codex shares).
- Both modes (`CONTAINERIZED`, `HOST`) implemented.
- Strategy pattern, stream parser, prompt renderer all clean.
- D7 validated 67+ events landed in ES across 9 distinct types per execution.

### `GitHubCopilotAdapter`
- 8 of 11 `CodingAgent*` events emittable (assuming the session-data API surfaces tool calls — **needs verification**; worst-case is 5 of 11 covering only lifecycle bookends + rate limits + retries + final summary).
- 1 mode (`API`) — adds no new mode to the enum.
- No strategy split (single mode); validates that the strategies are an **internal** detail, not a port-level concept.
- Three structural gaps: no `Thinking`, no `OtlpSpan`, no `TokensUsed` (Copilot is request-priced, not token-priced).

### `CodexAdapter`
- 10 of 11 `CodingAgent*` events emittable (only `CodingAgentOtlpSpanEvent` blocked — same O3 OTel gap as Claude Code).
- Both modes (`CONTAINERIZED`, `HOST`) implemented; strategies one-for-one with Claude Code (template reuse confirmed).
- Confirmed JSONL stream provides messages, reasoning, command executions, file changes, MCP tool calls, web searches, plan updates — full granular telemetry.
- One field-semantics drift: Codex tool-call categories are finer-grained than Claude Code's flat `tool_name`.

## Surfaced Gaps

### Gap 1: Copilot lacks token-based cost accounting

**Symptom**: `CodingAgentResult.total_input_tokens: int` and `total_output_tokens: int` are non-optional ints. Copilot has no token concept — it bills per request. The Copilot adapter would have to lie (return 0) or violate the contract (return `None`).

**Cross-adapter impact**: cross-vendor cost analysis ("which agent costs more per execution?") cannot use these fields uniformly. Each vendor reports a different denominator.

**Recommendation**: introduce a `CodingAgentResourceUsage` discriminated union and add `CodingAgentResult.resource_usage: CodingAgentResourceUsage` as an **additive field**. The existing `total_input_tokens` / `total_output_tokens` fields stay (so no breaking change), but they become specifically meaningful only when `resource_usage.kind == "tokens"`. Sketch:

```python
@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0

@dataclass(frozen=True)
class RequestUsage:
    request_count: int           # for request-priced vendors (Copilot)
    premium_request_count: int = 0  # if vendor distinguishes

# Discriminated union
CodingAgentResourceUsage = TokenUsage | RequestUsage
```

The existing fields become projections from `TokenUsage`; when `resource_usage` is `RequestUsage`, the existing fields are `0` with a documented meaning of "n/a for this vendor". Analysis pipelines that need cross-vendor cost compare on `total_cost_usd` (still meaningful) and on `resource_usage` discriminant.

**Phase**: Land before D1 of the Copilot adapter cycle. Additive change to ports + events; one new field in `CodingAgentResult`.

### Gap 2: `cost_limit_usd` is not enforceable by Copilot

**Symptom**: `CodingAgentInvocationOptions.cost_limit_usd: Decimal | None` is enforceable by Claude Code and Codex (they emit per-step token counts adapter-internally and can short-circuit). Copilot's API does not expose per-request cost back to the caller during execution; the adapter cannot enforce a budget.

**Cross-adapter impact**: callers configuring a `cost_limit_usd` get silent best-effort enforcement (works for some adapters, not others) with no signal.

**Recommendation**: two complementary additions:

(a) Document `cost_limit_usd` as **best-effort**, with the adapter raising a warning event (new: `CodingAgentCostLimitNotEnforceableEvent`) at execution start when a non-`None` limit is set against an adapter that cannot enforce it. This event subscribes to the same 14-day retention as other granular events.

(b) On `ICodingAgent`, add a query method `def cost_limit_enforcement(self) -> CostLimitEnforcement` returning an enum `{HARD, SOFT, NONE}` so config validation can flag mismatches at load time rather than runtime.

**Phase**: (a) before D1 of Copilot. (b) optional — could defer indefinitely.

### Gap 3: Tool-call category drift between adapters

**Symptom**: Claude Code emits `CodingAgentToolCallEvent(tool_name="Read")` / `tool_name="Bash"`; Codex emits with `tool_name="command_execution"` / `tool_name="file_change"` / `tool_name="web_search"`. Both use the same field, but cross-adapter analysis ("which executions invoked any kind of file edit?") needs per-adapter taxonomies.

**Cross-adapter impact**: behavioural-analysis queries become adapter-specific or require a translation table maintained outside the events.

**Recommendation**: add an **optional** `tool_category: str | None = None` field on `CodingAgentToolCallEvent` populated by the parser. Defined values: `"file_read"`, `"file_write"`, `"command_execution"`, `"web_search"`, `"mcp_tool"`, `"other"`. The parser maps the vendor's tool name to a category at the boundary; queries can filter on `tool_category` for cross-adapter analysis or on `tool_name` for vendor-specific drill-down.

**Phase**: Additive field with a default; can land before D1 of either Copilot or Codex without affecting Claude Code's existing parser (which gets a no-op category mapping).

### Gap 4: `CodingAgent*` event family is not uniformly emittable

**Symptom**: The catalog lists 11 events as if every adapter would emit all 11. In practice:
- Claude Code: 10 of 11 (`OtlpSpan` blocked by O3).
- Codex: 10 of 11 (`OtlpSpan` blocked by O3 — same gap).
- Copilot: 5–8 of 11 (no `Thinking`, no `OtlpSpan`, no `TokensUsed`; granular tool events depend on session-data API).

**Cross-adapter impact**: consumers of the event stream cannot assume every event type is present. Today this is implicit (no invariant says every adapter must emit every event); the lack of explicit tiering invites bugs.

**Recommendation** (documentation-only): tier the events in `documentation/architecture/domain/events.md`:

- **Tier 1 — Lifecycle (every adapter MUST emit)**: `CodingAgentInvokedEvent`, `CodingAgentReadyEvent`, `CodingAgentCompletedEvent`.
- **Tier 2 — Operational (every adapter SHOULD emit if the vendor surfaces the data)**: `CodingAgentToolCallEvent`, `CodingAgentToolResultEvent`, `CodingAgentTextOutputEvent`, `CodingAgentRateLimitEvent`, `CodingAgentApiRetryEvent`.
- **Tier 3 — Vendor-dependent (emit if vendor exposes)**: `CodingAgentThinkingEvent`, `CodingAgentOtlpSpanEvent`, `CodingAgentTokensUsedEvent`.

Each `ICodingAgent` adapter's spec must declare which Tier 2 and Tier 3 events it emits. A new invariant in `bootstrap/ARCHITECTURE.md` §6 (e.g. INV-19) codifies the tiering.

**Phase**: Doc-only change. Can land in D9 or D10.

### Gap 5: OTel via event bus is still blocked

**Symptom**: `CodingAgentOtlpSpanEvent` is not emitted by `ClaudeCodeAdapter` today (D7 carryover, tracked as O3 in the proposal). Codex inherits the same blockage — no documented `--otel` flag. Copilot does not expose OTel at all.

**Cross-adapter impact**: distributed-tracing-based behavioural analysis is unavailable across all three target adapters until O3 is resolved.

**Recommendation**: track separately — this is not an `ICodingAgent` port-shape problem; the port already accepts `CodingAgentOtlpSpanEvent` as a valid event. The blockage is upstream (vendor surfaces) and downstream (sidecar collector design). **No port changes needed; keep tracking as O3 in the proposal.**

**Status update (2026-05-30)**: O3 partially resolved by DEF-019 — see [`../../infrastructure/otel-routing.md`](../../infrastructure/otel-routing.md). Approach chosen: in-container `otelcol` sidecar emitting OTLP/JSON via the collector's file exporter; the adapter reads `/var/otel/spans.jsonl` after the agent exits and emits `CodingAgentOtlpSpanEvent` to the event bus. **Parser landed** (`src/codetoreum/adapters/secondary/claude_code/otel_span_parser.py`, 52 unit tests). **Strategy wiring + agent image sidecar deferred** to the next implementation cycle. Codex (Approach A is mode-agnostic enough that the same image + parser apply) gets it for free once strategy wiring lands; Copilot remains uncovered (no OTel from that vendor at all).

## Retention Adequacy

The 14-day default retention on granular `CodingAgent*` events (Q1 Lean, INV-15) was sized against the expected high volume from `ClaudeCodeAdapter` (D7 measured 67+ events per execution). Adequacy across the three adapters:

| Adapter | Events per execution (estimate) | 14-day adequacy |
|---|---|---|
| Claude Code | 67+ (measured in D7) | Sized for this. Adequate. |
| Codex | ~50–100 (similar profile; finer tool taxonomy may bump slightly) | Adequate. |
| Copilot | ~5–20 (mostly lifecycle + a few session updates) | More than adequate; could keep longer at minimal cost. |

**Recommendation**: leave the 14-day default as the global granular-event retention. **Do not** introduce per-adapter retention — adds infrastructure complexity for marginal storage savings. If Copilot data turns out to be analysis-valuable beyond 14 days, lift the global default rather than fragment per adapter.

## `InvocationMode` Enum Adequacy

The enum is `{CONTAINERIZED, HOST, API}`. Validation across the three adapters:

| Adapter | Modes used | Notes |
|---|---|---|
| Claude Code | `CONTAINERIZED`, `HOST` | Both used; ratio depends on project config. |
| Codex | `CONTAINERIZED`, `HOST` | Same as Claude Code. |
| Copilot | `API` | Sole consumer of this mode. |

**No fourth mode surfaced.** Modes considered and rejected:
- `REMOTE_PROCESS` (e.g. SSH to a build host) — not in scope for any target adapter; YAGNI.
- `WEBHOOK_DRIVEN` (vendor pushes results to a webhook we host) — covered by API mode internally (the adapter's polling could be replaced with webhook callbacks without changing the port shape).
- `IDE_EXTENSION` (e.g. Copilot in-IDE) — orthogonal to Codetoreum's autonomous-workflow model; not a coding agent in the role the port describes.

**Verdict**: enum is right-sized. Hold at three values.

## Recommended Changes (Summary)

In **priority order**, before the Copilot adapter implementation cycle begins:

| # | Change | Type | Phase | Justification |
|---|---|---|---|---|
| 1 | Add `CodingAgentResourceUsage` discriminated union + `CodingAgentResult.resource_usage` field | Additive port + event change | Before Copilot D1 | Token vs request accounting mismatch. Gap 1. |
| 2 | Add `CodingAgentToolCallEvent.tool_category: str | None = None` optional field | Additive event change | Before Copilot or Codex D1 | Cross-adapter tool-category analysis. Gap 3. |
| 3 | Tier the `CodingAgent*` event catalog in `events.md`; add INV-19 documenting the tiering | Doc-only | Anytime (could land in D9) | Clarify emission expectations. Gap 4. |
| 4 | Document `cost_limit_usd` as best-effort; emit `CodingAgentCostLimitNotEnforceableEvent` from adapters that cannot enforce it | Additive event change | Before Copilot D1 | Cost-limit silent-ignore is a footgun. Gap 2. |
| 5 | Add `ICodingAgent.cost_limit_enforcement() -> CostLimitEnforcement` query method | Additive port change | Optional / deferrable | Stronger version of #4; nice-to-have, not required. |

**No breaking changes** are recommended. The existing `ICodingAgent` adapters (Claude Code today, Codex tomorrow) continue working with current shapes; the additive fields default to backward-compatible values.

## What Was Confirmed (Positive Findings)

1. **The two-method `ICodingAgent` interface holds.** Every target adapter implements `supported_invocation_modes()` and `execute()` without strain. The interface is genuinely minimal — adding nothing it doesn't need.

2. **The prompt-builder separation is genuinely vendor-agnostic.** `StructuredPrompt` rendered cleanly to (a) text for Claude Code, (b) Markdown for Copilot issue body, (c) text for Codex. The `IPromptBuilder` injection model worked unchanged.

3. **The strategy pattern is a true template, not Claude-specific.** Codex's strategies mirror Claude Code's one-for-one. The pattern is reusable.

4. **The `API` mode was the right addition.** Copilot fits cleanly under `API`; no further mode innovation was needed.

5. **No filesystem-extraction temptation surfaced.** All three adapters comply with INV-16 without architectural pressure. The agent-output-through-events principle holds.

6. **The 14-day granular-event retention is right-sized.** Adequate for the most event-dense adapter (Claude Code, 67+ events) without being wasteful for the sparsest (Copilot).

7. **Resilience as infrastructure concern (INV-11) holds.** `ResilientCodingAgentDecorator` wraps all three adapters identically; per-adapter resilience tuning is configuration, not adapter modification.

## Forward Sequencing Recommendation

1. **D10 (proposed, additive)** — land the four pre-Copilot port enhancements (changes 1–4 above). Single commit series; no breaking changes; Claude Code adapter gets the additive fields populated naturally. Tier the event catalog. Add INV-19.

2. **D11 (proposed)** — `CodexAdapter` implementation. Lower-risk than Copilot since it mirrors Claude Code's shape; serves as a second proof of the strategy template before tackling the API mode.

3. **D12 (proposed)** — `GitHubCopilotAdapter` implementation. Highest-risk because of the unverified session-data surface; would benefit from D10's `tool_category` and `resource_usage` fields being in place.

4. **O3 (open question, parallel)** — resolve the OTel-via-event-bus sidecar design; benefits both Claude Code and Codex.

If user prefers to ship Copilot first (per §Q6's ordering), the recommended pre-D1 work shrinks to:
- Change 1 (`CodingAgentResourceUsage`) — must land.
- Change 4 (`cost_limit_usd` advisory event) — should land.
- Change 3 (event-catalog tiering) — should land.
- Change 2 (`tool_category`) — can defer to Codex cycle.

## Cross-References

- **Reference adapter**: [`../production/claude-code-adapter.md`](../production/claude-code-adapter.md)
- **Planned adapters**: [`github-copilot-adapter.md`](./github-copilot-adapter.md), [`codex-adapter.md`](./codex-adapter.md)
- **Port specs**: [`../../ports/output/core-system.md`](../../ports/output/core-system.md) (`ICodingAgent`), [`../../ports/output/domain-services.md`](../../ports/output/domain-services.md) (`IPromptBuilder`)
- **Event catalog**: [`../../domain/events.md`](../../domain/events.md) (`CodingAgent*` events)
- **Source code**: `src/codetoreum/ports/output/coding_agent.py`, `src/codetoreum/ports/output/prompt_builder.py`, `src/codetoreum/domain/events/coding_agent_events.py`
- **Design proposal**: `~/.claude/plans/coding-agent-port-redesign.md`
- **Deficiency log**: `bootstrap/ARCHITECTURE.md` §9, DEF-015
