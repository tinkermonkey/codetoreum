# Implementation Review — Bootstrap Run 2026-05-31 (post-D-N…D-S sweep)

**Scope**: Codetoreum production path, exercised on rounds#65, that drove one work item through a real Docker-hosted Claude Code agent. Six runtime deficiencies (D-N through D-S) surfaced and were fixed; this document is the architectural retrospective on what those defects *expose* about the implementation, separate from the individual patches.

**Audience**: codetoreum-architect, anyone planning the next refactor cycle.

**Frame**: Gen 2 hexagonal architecture, the invariants in `bootstrap/ARCHITECTURE.md §6`, and the production-bootstrap phasing in `bootstrap/ARCHITECTURE.md §3` are the reference. The Deficiency Log (§9) is the running record of confirmed gaps.

---

## 1. Executive Summary

The Gen 2 design separates concerns cleanly *on paper* — domain, application, ports, adapters, infrastructure. The bootstrap run shows that the design holds at the structural level (file layout, imports, port definitions) but **breaks down at the seams between subsystems that the architecture doesn't fully name**:

1. **Lifecycle events are emitted without subscribers.** Some domain events (`WorkflowOrphanedEvent`, queue-handoff `LockAcquiredEvent`) are produced as if they signal something meaningful, but no handler completes the recovery they were designed to trigger. The event-driven model is half-wired.

2. **The pipeline lock service is a triune.** `IPipelineLockService` is simultaneously a distributed lock primitive, a FIFO queue, and an emitter of events that *imply* downstream work. The contract doesn't name the third responsibility, so callers either know to follow up manually (the `_handle_exit_column` path does) or they don't (Phase 4e doesn't, our external recovery script didn't, the legacy in-memory queue handoff doesn't survive restart).

3. **Two sources of truth for column state coexist with no authority rule.** Internal `WorkItem.current_column` and external GitHub Projects v2 column position diverge silently. `handle_agent_completion` queries the *external* board first and uses it as the basis for auto-progression — the opposite of what the rest of the codebase treats as authoritative. D-S exposed this; D-E (in the existing log) acknowledged the problem at the exit path but never propagated the fix to entry paths.

4. **Polling and event-driven orchestration are parallel universes.** `MultiProjectOrchestrator` (poll loop) and `BoardColumnEventHandler` (event-driven) coexist per INV-13, but their *observability* surfaces don't intersect — the poll loop's cycle log can't see in-flight work driven by events, and the event path doesn't surface to the poll loop's `OrchestrationCycleCompletedEvent`. D-Q exposed this.

5. **Failure paths are systematically under-architected.** The DLQ infrastructure exists and `IFailedEventStore` is a defined port, but the ES event store's "after 2 attempts, log CRITICAL, drop" code path predates the DLQ wiring and was never updated. Error constructors (`ExternalServiceError`) drift from their signatures because nothing forces call-site validation. The orchestration cycle has its *own* error handler crash (D-R).

6. **In-memory state inside application services creates restart-fragile dependencies.** `BoardColumnEventHandler._active_runs` is the authoritative source of "do I need to start a workflow run" — but it's wiped on restart, with the persistent registry treated as a fallback rather than the primary. The polarity is inverted from what the architecture would imply.

The fixes shipped this cycle (D-N through D-S) are *correct point fixes* but several of them paper over deeper structural smells. Section 5 catalogues those smells with recommendations. The architect's resolutions to the six open questions are in §7 and supersede §5's recommendations where they conflict — notably, **the board adapter is authoritative for column state, not the internal domain field** (reversing §4.5 / R2), and the pipeline lock + queue + orchestrator design replaces the original "atomic coordinator" proposal (§7.2).

---

## 2. What we observed during the run

Chronological — each item is a *fact from logs*, not interpretation.

1. **Server start (12:41:16)**: bootstrap phases 5c, 5e completed; rounds registered; agent loaded; MPO poll loop started; Phase 4e detected one orphaned workflow run from a previous crashed instance and emitted `WorkflowOrphanedEvent` for it.

2. **Trigger #1 (12:42:14)**: `POST /api/v2/trigger/column-change` → 202. `BoardColumnEventHandler` ran `try_acquire_lock`. The lock was already held by the orphaned WI from the previous run — `Lock held, 40c20302-… queued at position 0`. Work was now stuck behind a phantom holder. **D-N**.

3. **Manual recovery (12:50:02)**: External Python script imported `RedisPipelineLockService`, called `release_lock` on the orphaned WI. Redis correctly popped the queued WI (40c20302) and granted it the lock. `LockAcquiredEvent` was published, but nobody listened. The next-WI workflow run was not started.

4. **Trigger #2 (12:50:34)**: re-trigger via REST → `BoardColumnEventHandler` saw `ALREADY_HELD` (40c20302 now holds the lock) → triggered the agent → `ExecutionServiceAgentExecutor` looked for an active run → "No active run found for work item '40c20302-…'. Cannot execute." **D-O**.

5. **Manual recovery #2 (12:50:39)**: `redis-cli DEL` the lock + clear queue meta; re-trigger.

6. **Clean run (12:51:54)**: `Lock acquired for 40c20302` (fresh ACQUIRED, not ALREADY_HELD) → `_start_workflow_run` registered the run → `ContainerizedClaudeStrategy` created container `e67e5e4f1d68` → agent ran for 5.5 minutes.

7. **During the run**: ES timeouts surfaced — 6+ `Background event-store append failed` lines for `coding-agent-…` events; one terminal `Dropping 8 events for stream coding-agent-… after 2 attempts` (CRITICAL, no DLQ). **D-P**. Polling cycles took 51s (during ES contention) and reported `0 actions, 0 errors` while the agent executed. **D-Q**. One cycle's error handler raised `ExternalServiceError.__init__() missing 1 required positional argument: 'message'`. **D-R**.

8. **Agent completion (12:57:29)**: Commit `809c5d9` pushed to `feature/issue-65-…`; PR #78 already existed (idempotent); execution stats: 14675 output tokens, 54 tool calls, 326962ms. `BoardColumnEventHandler.handle_agent_completion` then queried the *external* board for the WI's current column → got `Backlog` → looked up Backlog's column config → `auto_progress_on_completion=False` → "Auto-progression disabled for Backlog". Work item remained in `Development / in_progress` despite the agent succeeding. **D-S**.

9. **Final state**: PR open and mergeable. Internal `WorkItem.current_column == "Development"`. External board column == "Backlog". No further auto-progression possible.

---

## 3. Architectural deviations from the documented Gen 2 design

Mapping observed behaviour to the documented architecture (CLAUDE.md, `bootstrap/ARCHITECTURE.md`, `documentation/architecture/`):

### 3.1 Domain events with no subscribers (`WorkflowOrphanedEvent`)

> Architecture: "Domain Events: Immutable records of state changes... Event Bus: Pub/sub infrastructure for event distribution... Event Emission: Adapters emit events for external system changes."

`WorkflowOrphanedEvent` is emitted by Phase 4e in `production_bootstrap._detect_orphaned_workflow_runs`. Grep across `src/` confirms **zero subscribers**. The event is purely write-only — it lands in the ES event stream for audit purposes but does not drive recovery.

This is a clean architectural smell: a `domain event` that announces *something requiring action* with no handler that takes action. The orphan-recovery responsibility (release the lock, surface the WI for re-trigger) is ad-hoc — Phase 4e does part of it (clears registry), our D-N fix does another part (releases lock), and nothing handles "the queued WI now holds the lock but has no active run".

**Pattern violated**: events should drive behaviour; otherwise they are status messages and should be named accordingly. INV-10 ("All state changes MUST emit a domain event") covers emission but not handling.

### 3.2 The pipeline lock service is three concerns in one port

> Architecture: "Ports: Clean interfaces between core and external systems."

`IPipelineLockService` is documented as "Pipeline lock management with event emission" and inherits `IEventEmitter`. In practice the `RedisPipelineLockService` adapter does three jobs:

1. **Distributed lock primitive** — `try_acquire_lock` / `release_lock` over a Redis key.
2. **FIFO queue with stage_name persistence** — ZADD/ZPOPMIN with sibling hash for `next_stage_name`.
3. **Side-effect emitter that *implies* downstream orchestration** — `_publish_lock_acquired` on queue handoff.

The third responsibility is the leaky one. Callers of `release_lock` get back a `LockReleaseResult` with `next_work_item_id` and `next_stage_name` — and are expected to do something with them. `BoardColumnEventHandler._handle_exit_column` does (it runs `_start_workflow_run` + `_trigger_agent`); every other caller doesn't. The contract doesn't say "you must follow up"; the code in one specific handler is the only place this is correct.

D-O was the runtime symptom: external recovery code (and, by implication, Phase 4e) didn't know to follow up.

**Deviation**: the port defines an interface, but the *semantics* of correct usage live in one handler's body. Adapters can't help — they emit the event, but the queue-handoff lifecycle isn't formalised.

### 3.3 Authority for "current column" is undefined

> Architecture: domain layer has `WorkItem.current_column`; adapter layer has `GitHubBoardAdapter.get_item_position` which queries the external board.

Both exist. The documentation doesn't say which one is authoritative. The behaviour:

- `POST /api/v2/trigger/column-change` updates internal state only — external board untouched.
- `handle_agent_completion` queries the external board (`_find_item_position`) and only falls back to internal `_active_runs` if the board service returns nothing.
- `_handle_exit_column` (release path) calls `move_item_to_column` after lock release — external is updated on the way out.
- D-S fix adds: ACQUIRED path now also calls `move_item_to_column` on the way in.

The asymmetry is the smell: entry, exit, and completion all sync the external board differently. D-E (in the prior log) acknowledged the problem and emitted `BoardSyncFailedEvent` on exit-path failures — but the entry-path equivalent didn't exist until D-S.

**Deviation**: hexagonal architecture wants the domain (`WorkItem.current_column`) to be authoritative and the adapter to project to the external system. The current code uses the external board as the primary read source in at least one place (`handle_agent_completion`), reversing the polarity.

### 3.4 In-memory caches inside application services

> Architecture: state lives in adapters (repositories, registries). Application services orchestrate but don't hold state.

`BoardColumnEventHandler._active_runs: dict[str, _WorkflowRunMetadata]` is an in-process dict that mirrors the (persistent) `IActiveWorkflowRunRegistry`. The handler:

- Writes to it in `_start_workflow_run` (alongside the registry).
- Reads from it in `handle_agent_completion`'s fallback path.
- Reads from it in `_handle_exit_column` to gate `_start_workflow_run` calls.

D-O's fix relies on `if work_item_id not in self._active_runs` to decide whether to start a workflow run on queue handoff. That guard is reliable in a fresh process but completely useless after a restart — `_active_runs` is empty, so every column-change event would re-start a workflow run for items that already have one in the registry.

**Deviation**: the registry is the authoritative source; the in-memory dict is a caching convenience that *also* serves as the de-dup guard. After restart the de-dup guard collapses to nothing.

### 3.5 Failure paths drop instead of route

> Architecture: dead letter queue (`infrastructure/dead_letter_queue.py`), `IFailedEventStore` port, `DeadLetterQueueFailedEventStoreAdapter` adapter — all defined.

The ES event store had a "drop after 2 attempts, log CRITICAL" path that bypassed the DLQ entirely. The infrastructure for failure routing existed but wasn't connected. D-P fixed the wiring.

**Deviation**: the architecture documents the DLQ as a first-class infrastructure component but the adapters that produce failures aren't required to use it. The port doesn't enforce it; the bootstrap doesn't enforce it.

### 3.6 Two orchestration paths with no shared observability

> Architecture (INV-13): "`MultiProjectOrchestrator` is the sole orchestration entry point... `BoardColumnEventHandler` is the event-driven complement — they are cooperative, not competing."

Cooperative on paper, blind to each other in observability. The poll cycle's `OrchestrationCycleCompletedEvent` had four fields (projects_processed, boards_processed, total_actions, cycle_duration_ms) — none of which reflect work driven by the event handler. The poll cycle log line says "0 actions" even when an agent is running on a 5-minute job because that work was triggered via a different path.

D-Q's fix added `active_workflow_runs` to the event and the log line. But the broader issue: **the two orchestration paths share no aggregation point**. A single "what is the orchestrator doing right now" answer doesn't exist; consumers must query the registry, the lock service, the queue, and the event stream independently.

**Deviation**: INV-13's "cooperative" framing is correct in intent but unrealised — there's no observation API that joins the two paths.

### 3.7 Bootstrap phase ordering forces duplication

> Architecture (§3 of `bootstrap/ARCHITECTURE.md`): phases 1 → 5e, each described with its purpose.

Phase 4e (orphan recovery) runs *before* Phase 5 (handler registration). When Phase 4e needs to perform recovery actions that are exactly what `BoardColumnEventHandler._handle_exit_column` does (release lock, start workflow run for popped WI, trigger agent), it can't — the handler doesn't exist yet.

D-N's fix duplicates the lock-release call. D-O's fix puts the workflow-run start in the handler's ALREADY_HELD path so a *subsequent* column-change event re-syncs. The two-step dance is correct but brittle: the recovery is incomplete until something else happens.

**Deviation**: phase ordering enforces an asymmetry. Either recovery runs late enough to use the normal code paths (cleaner) or recovery is a first-class subsystem with its own utilities (more honest but more code).

### 3.8 Trigger endpoint is fire-and-forget with no traceability

> Architecture: REST inbound primary adapter; events to event bus.

`POST /api/v2/trigger/column-change` returns 202 with an `event_id` but offers no follow-up endpoint. A trigger that lands in the bus and then gets queued (because the lock is held) is invisible to the client — no `GET /api/v2/triggers/$event_id` exists. Combined with `BoardColumnEventHandler` running asynchronously, debugging "did my trigger fire?" requires log inspection.

**Deviation**: the architecture has an audit trail (the event store) but no query surface over it for trigger lifecycle.

### 3.9 Production isolation is incidental

> Architecture: production adapters use real external services.

`localhost:9200` was shared with switchyard (`switchyard-elasticsearch-1`) during this run. Switchyard's ingestion caused ES timeouts in codetoreum, which:

- Dropped 8 coding-agent telemetry events (pre-D-P fix).
- Made work-item GETs take 9.7s.
- Made one MPO cycle take 51s.
- Crashed the MPO error handler (D-R, ExternalServiceError constructor bug exposed by the timeout).

The architecture doesn't say anything about ES isolation. The harness `bootstrap/register_project.py` uses whatever's at `ELASTICSEARCH_URL` (default `http://localhost:9200`), which means production code shares fate with whatever other service is bound there.

**Deviation**: production resource isolation is not an architectural concept. Should it be?

---

## 4. Boundaries and interfaces that are violated or undermined

This section is narrower than §3 — strict violations of named architectural rules, port contracts, or hexagonal layering.

### 4.1 `RedisPipelineLockService` emits `LockAcquiredEvent` for two distinct semantic conditions

The same event type is published in two situations:

1. **Initial acquisition** by `try_acquire_lock` — caller wants the lock, gets it, and now has work to do.
2. **Queue handoff** in `release_lock` — caller was a different work item; we're picking the next from the queue and granting it the lock. The new lock holder has *not* run any orchestration setup.

Callers downstream can't distinguish these from the event payload alone. The architecture says events are immutable records of state changes; here we have one event type carrying two different state-change semantics. A subscriber that wanted to handle "lock granted via queue handoff" specifically would have no signal.

**Recommendation**: split into `PipelineLockAcquiredEvent` + `PipelineLockGrantedFromQueueEvent` (or add a discriminator field on the existing event).

### 4.2 Application services holding state that should be derived from adapters

`_active_runs` on `BoardColumnEventHandler` violates the hexagonal principle that application services should be functions over adapter state. The dict serves as both:

- A read-side cache (fine if invalidated correctly).
- A *de-dup guard* (not fine — the registry is the persistent source of that guard).

INV-12 ("domain layer has zero external dependencies") doesn't cover application-layer in-memory caches, but the spirit applies. After restart, the cache is empty, the de-dup guard is gone, and the system behaves differently from a fresh process. That's a restart-fragility surface.

**Recommendation**: query `IActiveWorkflowRunRegistry.get_active_run(work_item_id)` instead of `work_item_id in self._active_runs`. The registry is persistent and authoritative.

### 4.3 `ExternalServiceError` calls violate the type contract silently

The class signature is `ExternalServiceError(service: str, message: str)`. Six production call sites (five in `elasticsearch_project_manager_adapter.py`, one in `github_version_control_adapter.py`) called it with only `(message,)`. Mypy did not catch this — the calls type-check because both args are `str`.

This is symptomatic of a broader issue: the existing tests don't exercise these error paths often enough to catch constructor drift. INV-11 ("Resilience logic... MUST remain in infrastructure decorator classes") is enforced; INV-10 ("All state changes MUST emit a domain event") is enforced. There's no equivalent invariant for "all exception raises must use validated constructor signatures."

**Recommendation**: stricter mypy on adapter error paths, or a custom exception factory that requires keyword arguments (`ExternalServiceError.for_service("project_manager", msg)`).

### 4.4 The DLQ port (`IFailedEventStore`) is not required by any adapter

A failure path that loses durable data should — by hexagonal layering — write to a persistence port before logging-and-dropping. The ES event store had no `failed_event_store: IFailedEventStore` constructor parameter, no DLQ wiring, no contract that said "you must route final failures here." It was a documented infrastructure component with one consumer pattern (used by some application services) and no enforcement.

This contrasts with INV-08 (`CRITICAL_ADAPTER_SLOTS` enforced at bootstrap), which actually fails fast at startup if violated. Failure routing has no equivalent.

**Recommendation**: add a `CRITICAL_FAILURE_ROUTES = {"event_store_drop": "failed_event_store", ...}` enforcement at bootstrap. Adapters that can lose data must declare a route or fail to construct.

### 4.5 External board column read as the basis for internal workflow decisions

`handle_agent_completion._find_item_position` queries the external GitHub board for the WI's current column, then uses that column's config to decide auto-progression. This inverts the domain-as-authority polarity.

The fallback path (`if not current_position and work_item_id in self._active_runs`) tries to recover by using the in-memory dict, but only kicks in when the board service returns nothing — not when it returns the *wrong* column (which is exactly what happens when the external board lags).

**Recommendation**: invert. Internal state is authoritative; external board sync is best-effort projection; reconciliation runs separately (the existing `BoardSyncFailedEvent` audit + dashboard).

### 4.6 Phase 4e duplicates handler-level orchestration logic

To complete orphan recovery, Phase 4e now (post-D-N) calls `release_lock` directly. But the proper completion of that operation — start workflow run for the popped WI, trigger the agent — lives in `BoardColumnEventHandler._handle_exit_column`. Phase 4e can't call into the handler (it doesn't exist yet) and the handler's helpers aren't extracted, so the recovery is incomplete on the Phase 4e side and depends on a later column-change event to finish.

This is a phase-ordering boundary that the architecture doesn't account for. Bootstrap phases 1–4 run before phases 5+. Anything that needs to *act* on data has to wait for phase 5, or duplicate handler logic, or use a recovery indirection (emit an event that the handler picks up once registered).

**Recommendation**: move orphan recovery to a post-5 phase (call it 5f), so handlers exist and the recovery can use the same code paths as live execution. Or: extract handler logic into static helpers / a dedicated `OrphanRecoveryService` that both 4e and the handler call.

### 4.7 The `redis_pipeline_lock_service.release_lock` constructor needs `redis_client=`, not `redis=`

Minor but real: our `release_orphan_lock.py` recovery script initially failed with `TypeError: __init__() got an unexpected keyword argument 'redis'`. The naming is fine in isolation but inconsistent with typical Python conventions (parameters named after types are common). Not a violation, just a friction point — and a sign that adapters expect to be constructed only by the factory, never by ad-hoc scripts. Recovery tooling is a real use case the architecture doesn't acknowledge.

---

## 5. What the architecture needs to evolve

Recommendations, prioritised. Each is independently actionable.

### Priority 1 (correctness gaps that will recur)

**R1. Formalise the queue-handoff lifecycle.** When `release_lock` pops a queued WI and grants the lock, *some* application-level orchestration must complete the handoff (start workflow run, trigger agent). Options:

- **R1a**: split `LockAcquiredEvent` into `PipelineLockAcquiredEvent` (initial) + `PipelineLockGrantedFromQueueEvent` (handoff). `BoardColumnEventHandler` subscribes to the new event and runs the start-workflow-run + trigger-agent dance. Then *every* release_lock call works correctly, including Phase 4e, external recovery, and any future caller.
- **R1b**: alternatively, expose `BoardColumnEventHandler.complete_queue_handoff(work_item_id, next_stage_name, project_id, board_id)` as a public method. Phase 4e calls it; external recovery scripts call it. Less change but exposes the handler as a service.

R1a is cleaner architecturally; R1b is smaller surface change.

**R2. Decide and document column-state authority.** A single source-of-truth rule: "internal `WorkItem.current_column` is authoritative; the external GitHub Project board is a best-effort projection." Then:

- All read paths (including `handle_agent_completion._find_item_position`) check internal state first.
- All write paths (trigger, completion, exit) update internal first, sync external second.
- A reconciliation job periodically detects drift and emits `BoardSyncFailedEvent` for any divergence.

INV-19 candidate: "Internal `WorkItem.current_column` is the authoritative source for workflow decisions. External board state is a projection synced via `IBoardService.move_item_to_column` and reconciled via the board adapter's reconcile job."

**R3. Adapters must declare failure routes.** Any adapter that can drop durable data declares a `failed_event_store: IFailedEventStore` constructor parameter. Bootstrap enforces at construction time. The DLQ becomes a required collaborator, not an optional add-on.

INV-20 candidate: "Adapters that can permanently drop events MUST take an `IFailedEventStore` parameter and route final failures to it. Bootstrap fails to start if a critical-path adapter has no route."

### Priority 2 (architectural smells that will keep producing bugs)

**R4. Move runtime caches out of application services.** `_active_runs` should be replaced with on-demand reads from `IActiveWorkflowRunRegistry`. If the registry's call frequency becomes a hot spot, add a read-through cache *in the adapter* (e.g. Redis), not in the handler. The handler should be functional over the registry.

**R5. Reorganise bootstrap phases to enable consistent recovery.** Move orphan detection (current 4e) to run after handlers are wired (call it 5f or 6a). Orphan recovery then uses the normal code paths — `BoardColumnEventHandler.complete_queue_handoff` or the equivalent event-driven mechanism — rather than duplicating logic.

**R6. Distinguish "events that audit" from "events that drive."** The codebase emits both kinds in one event bus. `WorkflowOrphanedEvent` was clearly intended to drive recovery; the absence of a subscriber means it functions only as audit. Audit-only events should be named and stored differently from action-triggering events, or every action-triggering event should have a documented handler list.

INV-21 candidate: "Every action-triggering domain event MUST have at least one subscribed handler. Audit-only events MUST be tagged `audit_only=True` (or live in a different naming/event hierarchy)."

### Priority 3 (operability)

**R7. Make orchestration state queryable.** A single endpoint — say `GET /api/v2/diagnostics/state` — that returns:

- Active workflow runs (count + per-run info from `IActiveWorkflowRunRegistry`).
- Active pipeline locks + queues (from `IPipelineLockService.get_all_lock_states` + queue introspection).
- Pending trigger events (from the event bus's dead-letter or from a trigger-tracking table).
- Failed events count (from `IFailedEventStore.get_stats()`).

This is the unified observability that INV-13's "cooperative" framing implies but the code doesn't realise. The bootstrap harness should consume it; future watchdogs should consume it; humans should consume it.

**R8. Trigger lifecycle traceability.** Add `GET /api/v2/triggers/$event_id` returning the event's processing status (received, queued, in-progress, completed, failed). Backed by either the event store or a small dedicated trigger-state Redis structure. Removes the "did my trigger fire?" debugging friction.

**R9. Production resource isolation as architecture, not coincidence.** Document that the production bootstrap requires:

- An ES cluster not shared with other services (or at least non-conflicting index prefixes + sufficient connection pool isolation).
- A Redis instance not shared with other services.
- A Docker daemon with sufficient capacity for the configured agent count × max parallel work items.

The harness should health-check these at startup and refuse to run with shared infra unless explicitly opted in.

**R10. PR/branch metadata refresh on commit add.** When `ExecutionService` adds a commit to an existing branch with an open PR, refresh the PR title from the *current* work item — not from whatever was there when the PR was first opened. Avoids the "PR #78 title carries an old work_item_id" surprise.

### Priority 4 (longer-horizon)

**R11. The pipeline lock service contract should decompose.** Long term: separate `IDistributedLock` (just the lock primitive — try_acquire, release, get holder) from `IFairQueueService` (FIFO with metadata) from `IPipelineCoordinator` (the application service that composes the two and emits the right events). This makes each port testable in isolation and makes the queue-handoff lifecycle a first-class concern of the coordinator, not a side-effect of the lock.

**R12. Replace fire-and-forget event publish with awaited publish + recovery.** INV-05 explicitly notes that the executor publishes `AgentExecutionCompletedEvent` via `asyncio.create_task` to avoid re-entry loops. That's a workaround for a deeper issue: there's no architectural answer for "publish failed, what now?" — the current `AgentExecutionRecoveryService` is a partial answer. A formal recovery model (DLQ for events, replay, idempotent handlers) would let publishes be awaited safely.

**R13. Consider whether INV-13's two-path orchestration is the right long-term shape.** Polling (`MultiProjectOrchestrator`) and event-driven (`BoardColumnEventHandler`) cover different cases — initial pickup vs. real-time reaction. But they're parallel implementations of overlapping concerns. A future cycle could fold them into a single orchestrator that listens for both wall-clock ticks (for polling-style sweeps) and event bus messages (for reactions), with one shared state model and one observability surface.

---

## 6. Open questions for the architect

1. **Is `WorkItem.current_column` or the external Project v2 column authoritative?** §3.3 and §4.5 frame the question; R2 proposes an answer. Confirm.

2. **Should `LockAcquiredEvent` split into two events?** R1a vs R1b. Pick a direction so future cycles don't keep stepping on the same line.

3. **Should orphan recovery be a Phase ≥5 concern instead of Phase 4e?** R5 proposes moving it. Confirm or document why current placement is necessary.

4. **Is in-memory `_active_runs` deliberate caching, or unintentional duplication of registry state?** R4 assumes the latter. If the former, document the invalidation contract.

5. **How should the system express "this event drives action" vs "this event records state"?** R6 proposes a tagging convention. Is there a better mechanism (separate event types, different bus topics)?

6. **Should the bootstrap harness fail to start when infra is shared with other services?** R9 says yes. Confirm scope: does this apply to ES only, or also Redis, Docker, GitHub credentials, etc.?

---

## 7. Architect decisions on the open questions

Following the 2026-05-31 review, the architect closed the six open questions from §6. These resolutions supersede the recommendations in §5 wherever they conflict, and drive the roadmap in GitHub issue #904.

### 8.1 The board adapter is authoritative for column state

**Reverses the recommendation in §4.5 and R2.** Internal `WorkItem.current_column` is *not* the authoritative source; the external GitHub Project v2 board, mediated through `IBoardService` (the board adapter), is. The board adapter owns the "what column is this WI in right now" question. The implementation review's intuition that domain-as-authority should win was incorrect for this domain.

Implications:

- `handle_agent_completion._find_item_position` querying the board first is *correct* and stays.
- `POST /api/v2/trigger/column-change` is the bug: it bypasses the board adapter and updates internal state directly. The trigger endpoint must call `IBoardService.move_item_to_column` and let the board adapter project the change to GitHub. The board adapter then emits `WorkItemColumnChangedEvent`. Internal projections (if any) are updated by event handlers, not by the trigger endpoint.
- `WorkItem.current_column` becomes a cache of the board adapter's authoritative answer. Reads should prefer the board adapter; the domain field exists only for serialization and historical record.
- Project config (workflow + column definitions) remains the source of truth for *structure*. The board adapter is responsible for reconciling GitHub's board structure with project config (creating missing columns, renaming mismatched ones).

### 8.2 Split `LockAcquiredEvent` and let an orchestrator manage the queue

**Replaces R1 with a simpler decoupled design.** `PipelineLockAcquiredEvent` signals only that a lock was acquired — by any path. The lock service and the queue service do not know about each other.

A new orchestrator subscribes to `PipelineLockAcquiredEvent` and runs:
```
on PipelineLockAcquiredEvent(work_item_id):
    if queue.contains(work_item_id):
        queue.remove(work_item_id)        # they're no longer waiting; they have the lock
    # …and then drive whatever the lock holder needs (start workflow run, trigger agent)
```

And subscribes to `PipelineLockReleasedEvent` to start the next queued item:
```
on PipelineLockReleasedEvent:
    next = queue.peek()
    if next: lock.try_acquire(next)   # fires PipelineLockAcquiredEvent if successful
```

This decouples the lock service and queue service entirely. The lock service is just a lock primitive; the queue service is just a FIFO. The orchestrator subscriber maintains the invariant "the lock holder is not in the queue." No atomic Redis transactions across both subsystems are required; the consistency is event-driven and eventual.

This supersedes the `PipelineCoordinator` design in the original GitHub issue #904 Work item 2.

### 8.3 Move orphan recovery to the right place; use normal code paths

**Confirms R5.** Phase 4e is deleted. Orphan detection runs after handlers are wired (or starts as part of the lock-service startup behaviour). When it detects a stale lock, it releases via the normal `IDistributedLock.release` path. That emits `PipelineLockReleasedEvent`, which the orchestrator subscriber processes the same way it processes any release: peek the queue, try-acquire for the next candidate, etc.

No special recovery code path. No duplicated logic. Orphan recovery is the same as the steady-state path, just driven by a startup scan rather than a user action.

### 8.4 Eliminate the local cache

**Confirms R4.** `BoardColumnEventHandler._active_runs` is deleted. All reads of "is there an active run for this WI" go to `IActiveWorkflowRunRegistry`. If performance becomes an issue, the cache lives in the adapter (e.g. Redis-backed), not in the handler. The handler must be functional over the registry.

### 8.5 Audit vs drive is not a real distinction

**Reverses R6.** An event is an event. The same event can have a subscriber that audits (writes to event store, dashboards, OTel) and a subscriber that drives (acts on the state change). The fact that `WorkflowOrphanedEvent` has no driving subscriber is not a design choice — it's an incomplete implementation. Document the fact, fix the gap.

The proposed INV-21 (tagging events as `audit_only`) is withdrawn. Events are just events.

### 8.6 Production infra isolation is a hard requirement

**Confirms R9.** The bootstrap harness must refuse to run if its infrastructure is shared with other services. Specifically:

- Elasticsearch at `ELASTICSEARCH_URL` must be exclusive to codetoreum (or use a namespaced cluster with no concurrent writers from other services).
- Redis must be exclusive.
- Docker daemon must have capacity for configured agent count × max parallel work items.
- GitHub credentials must have sufficient scopes and rate-limit headroom.

The harness performs these checks at startup and exits with a clear error if any check fails. "Run the bootstrap anyway and hope for the best" is not an option — the failure modes we saw (9.7s ES reads, 51s cycles, dropped telemetry, masked errors) make the run worse than not running it.

---

## 8. Closing — what this run actually validated

Despite the six deficiencies, this run *did* prove the production code path end-to-end:

- Real GitHub issue → real work item → real Docker container → real Claude Code agent → real commit → real PR push → real auto-progression attempt.
- The `ICodingAgent` contract works against the real Claude Code subprocess (INV-15 events all emitted; INV-16 no filesystem extraction; INV-17 mode owned by adapter).
- Production adapters in critical slots (board, ticket, coding_agent, version_control, container, code_review) are non-mock as INV-08 requires.
- The event bus, event store (with new DLQ wiring), lock service, and persistent run registry all participate correctly when their preconditions are met.

The deficiencies are at the **seams** — orphan recovery, queue handoff, board sync direction, observability aggregation — not at the **core mechanism**. The Gen 2 hexagonal model is sound; the failure modes are about *what happens when state crosses subsystem boundaries* and what guarantees those boundaries make.

That's the work the next refactor cycle should target.
