# ADR-0001 — Durable delivery for must-not-lose events: consumer-group vs transactional outbox

- **Status**: Proposed
- **Date**: 2026-06-07
- **Deciders**: Architecture (codetoreum-architect), platform owners
- **Related**: INV-13 (fully event-driven), INV-19 (board authoritative for column), INV-20 (critical adapters declare a failure route), `infrastructure/event-bus.md §6` (Completion-Event Delivery Semantics)
- **Supersedes/depends-on**: Step 1 (central `EventBus.drain()` + unified `publish_detached`) is already implemented; this ADR decides Step 2.

---

## Context

`EventBus` is an **in-process** pub/sub. Handlers run inline inside `publish()` via
`asyncio.gather`. When a Redis client is configured, `publish()` also does an
`xadd` to a per-event-type stream — but that stream is an **audit/replay trail,
not a work queue**: it has no consumer group, no pending-entries-list (PEL), and
no reader that re-drives unprocessed events on restart.

Some publishes are detached (fire-and-forget) on purpose. The canonical case is
`ExecutionServiceAgentExecutor._publish_completion`: awaiting the completion
publish inline would keep the work item "executing" across the auto-progression
handler chain and risk a re-trigger loop, so the publish is detached. The
handler chain it drives is network-bound (GitHub GraphQL move + ES round-trips),
so the **lock release / board advance lands ~3–4s after the container exits**.

This makes **at-most-once-across-restart a property of the bus**, shared by every
state-mutating handler — not a quirk of completion. A crash or redeploy in the
~3–4s window loses the side effect:

- The pipeline lock is **Redis-backed** (`RedisDistributedLock`, 2-hour safety
  TTL), so it survives the crash. The board stays in the trigger column; the
  advance event is gone.
- Result: the board is **serialized for up to 2 hours** (other items queue behind
  the orphaned lock), then the TTL expires, the board adapter's internal poll
  re-detects the item in a trigger column, and the agent **re-runs** — recovery by
  *redoing the work*, not *replaying the advance*. Duplicate commit/PR risk,
  gated entirely on agent/handler idempotency.

Step 1 (already landed) closes the **graceful-shutdown** window: `EventBus`
now owns `publish_detached(event, on_error=…)` and `drain(timeout)`, and
`ProductionApplicationBootstrap.teardown()` drains in-flight publishes before
closing the stores. Step 1 does **not** help a hard crash — nothing replays.

> Note on MPO: `MultiProjectOrchestrator` has **no poll loop** (it is admin-query
> only; see INV-13). A "reconciliation sweep on MPO" is therefore not a cheap
> bolt-on — it would mean reviving application-layer polling the architecture
> deliberately removed. This ADR does not pursue that path.

### The conceptual split this ADR rests on

"Make every event full-weight and replayable" conflates two **orthogonal**
properties:

1. **Persistence of the record** — every event written to an ordered, queryable,
   replayable log. Serves debugging, traceability, monitoring, audit.
2. **Delivery guarantee to the handler** — the bus retries and won't consider the
   event done until the handler *acks* (at-least-once, PEL, redelivery-on-restart).

Our observability goals ride entirely on (1). The crash-recovery gap is entirely
about (2). They are separable: **persist everything (uniform), guarantee delivery
selectively.** Forcing (2) on all events is not free — it imposes idempotency as a
global handler obligation (at-least-once **double-counts metrics**), and replaying
timestamped observability events on restart **re-emits stale spans**, degrading the
very traceability it claims to improve. And replay-safety is **not uniform across
handlers** — even a naïve "replay the whole log on restart" is forced to mark which
handlers are safe to re-run, which *is* the second class. The selectivity is
intrinsic to the problem, not an artifact of design.

**Therefore: one log (uniform persistence), two delivery modes (selective
guarantee), the mode declared in one line at handler registration. The modes
differ ONLY in delivery guarantee, never in persistence — observability stays
uniform.**

This ADR decides *how* to implement the durable delivery mode for the
must-not-lose class.

### The must-not-lose class (initial membership)

State-transition-driving handlers whose loss strands work or corrupts the board:

- `AgentExecutionCompletedEvent` → auto-progression (lock release + board advance)
- `WorkItemColumnChangedEvent` → pipeline trigger
- review/repair-cycle progression events

Everything else (the `CodingAgent*` telemetry family — dozens of events per
execution, 14-day retention, loss-tolerant by nature; metrics; tracing) stays on
the in-process gather path. This is the **high-volume / low-criticality** majority;
routing it through ack/redelivery is the most cost for the least benefit.

## Decision drivers

- **Crash/redeploy must not strand work** or silently lose a state transition.
- **Idempotency tax must be localized** to the small must-not-lose set, not imposed
  globally.
- **Observability must stay uniform** — same log, same trace, regardless of mode.
- **Operational surface proportional to the gain** — "a lot of events" is a stated
  forward requirement; the critical set is tiny. Don't build a broker for 151
  event types to protect ~5 handlers.
- **No application-layer polling** (INV-13).
- **Respect existing sources of truth** — board adapter (INV-19), failure routes
  (INV-20).

## Considered options

### Option A — Redis Streams **consumer group** on the EventBus

Promote the existing `xadd` stream(s) for must-not-lose event types to a real
delivery substrate. A bus-owned consumer-group reader drives the durable handlers
with **XACK after success**; unacked entries sit in the PEL and are re-claimed
(`XAUTOCLAIM`) on restart. The in-process gather path remains for loss-tolerant
handlers.

- **Pros**
  - Reuses infrastructure already present (Redis, the streams we already write).
  - At-least-once + restart redelivery falls out of the PEL — minimal new storage.
  - "Strengthen the bus" — robustness becomes a property of the *channel*; future
    critical handlers inherit it by registering in durable mode.
  - Natural multi-instance story (consumer-group load-balances; one delivery
    across instances).
- **Cons**
  - Handlers must move off inline `publish()` dispatch onto a consumer-group reader
    loop — a real structural change to how durable handlers are invoked.
  - Handlers must be **runnable from the serialized event alone** (no reliance on
    in-memory `run_registry`/closures). This is the gating refactor.
  - Per-stream consumer / ordering / poison-message handling to design (a stuck
    entry grows the PEL; needs a max-deliveries → DLQ path, dovetailing with INV-20).
  - Two delivery code paths to operate and reason about (mitigated: one log, the
    mode is one registration flag, the durable set is ~5 handlers).

### Option B — Transactional **outbox / inbox**

Before the detached publish, write a durable `pending_completion`-style row
(`event_id, work_item_id, board_id, payload, status=PENDING`) in the same store
that holds work state; the handler chain flips it `DONE` on success. A startup (and
periodic) sweep re-drives `PENDING` rows.

- **Pros**
  - Strongest guarantee; delivery becomes independent of process liveness and of
    Redis stream semantics.
  - The outbox table is trivially inspectable/queryable ("what's un-acked right
    now?") — good operability.
  - Doesn't require restructuring handler *invocation* (still goes through the bus);
    the durability is a write-ahead record around it.
- **Cons**
  - New persistent table + schema + migration + a sweeper component (which, to obey
    INV-13, must live as bootstrap/infra lifecycle, not an app poll loop).
  - Most moving parts of the three options; another store to keep consistent.
  - The sweep reintroduces a periodic component (bounded, infra-level) — acceptable
    but more than Option A's event-driven redelivery.

### Option C — Status quo + Step 1 drain only (do nothing further)

Keep at-most-once; rely on the Step 1 drain for graceful shutdown and the
2-hour lock TTL + board re-poll as the crash backstop.

- **Pros**: zero additional work; the system already self-heals (slowly, lossily).
- **Cons**: up to 2h board serialization + duplicate agent runs after any crash in
  the window; recovery is *redo*, not *replay*; no path to the stated "robust,
  standardized, lots of events" future. Leaves INV-20's spirit (no dropped data
  without a recovery surface) only partially met for detached delivery.

## Decision (proposed)

Adopt **Option A (consumer-group-on-EventBus)** as the durable delivery mode for
the must-not-lose class, behind a one-line registration flag
(`register_handler(handler, durable=True)` / a `durable=True` marker on the event),
with the **explicit, gating prerequisite** that every durable-mode handler is made
**idempotent and reconstructable from the serialized event alone**.

Rationale for A over B:

- It strengthens the *channel* (the user's stated goal: "all this pub/sub needs to
  be robust and standardized"), so robustness is inherited, not re-implemented per
  handler.
- It reuses streams we already write — least new persistent state.
- Restart redelivery via the PEL is event-driven, honoring INV-13 (no app polling)
  more cleanly than B's sweeper.

Option B remains the fallback if, during the idempotency refactor, we find handlers
that genuinely cannot be reconstructed from the event payload, or if we need an
exactly-once-ish SLA tighter than consumer-group at-least-once comfortably gives.

Option C is rejected as a destination but **is the correct interim state**: Step 1
(drain) is shipped; Option A is sequenced behind the idempotency work.

## Prerequisites (gating — do before any durable-mode handler ships)

1. **Handler idempotency**: each must-not-lose handler is safe to run ≥2× for the
   same `event_id` / `(work_item_id, transition)`. Add a test asserting this per
   handler. At-least-once is meaningless — actively harmful — without it.
2. **Self-contained events**: durable-mode handlers take everything they need from
   the event payload; no reliance on in-memory `run_registry`, closures, or
   adapter caches that don't survive a restart.
3. **Poison/redelivery policy**: max-deliveries → route to `IFailedEventStore`
   (INV-20), so a permanently failing entry can't block the PEL forever.

## Consequences

- **Positive**: crash/redeploy no longer strands work; the board-serialization +
  duplicate-run failure mode is eliminated for the critical set; robustness becomes
  a channel property; observability stays uniform (one log).
- **Negative / cost**: two delivery paths to operate; a structural change to how
  durable handlers are invoked; the idempotency refactor is mandatory up-front
  (though it is required anyway once event volume grows).
- **Neutral**: persistence is unchanged and remains universal; `publish_detached` /
  `drain` (Step 1) stay as the graceful-shutdown mechanism and as the path for
  loss-tolerant detached publishes.

## Implementation sketch (post-decision)

1. Make the must-not-lose handlers idempotent + event-reconstructable (+ tests).
2. Add a durable registration mode to `EventBus`; route those event types through a
   consumer-group reader (`XREADGROUP` / `XACK` / `XAUTOCLAIM`) instead of inline
   gather; keep gather for the rest.
3. Wire max-deliveries → `IFailedEventStore`; surface PEL depth in bus statistics.
4. Update `infrastructure/event-bus.md` (§6) and `invariants.md` (a new INV for
   "must-not-lose events are delivered at-least-once") once code lands.
