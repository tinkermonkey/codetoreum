# Architectural Invariants

This document records cross-cutting invariants that hold across the Codetoreum platform — rules that apply globally and that, when violated, produce architectural defects rather than feature bugs.

Bootstrap-phase-specific invariants (those that govern ordering or wiring inside `ProductionApplicationBootstrap.setup()`) live in [`bootstrap/ARCHITECTURE.md §6`](../../bootstrap/ARCHITECTURE.md). The invariants here apply regardless of bootstrap mode (production, simulation, CLI).

Numbering matches `bootstrap/ARCHITECTURE.md`'s INV-NN scheme; gaps in the sequence here correspond to bootstrap-only invariants that remain in that document.

---

## Layer purity

### INV-12 — Domain layer has zero external dependencies

The domain layer (`src/codetoreum/domain/`) imports only from within the domain package and the Python standard library. `Agent`, `WorkItem`, `AgentExecution`, and all domain events comply.

**Violation cost**: domain logic becomes untestable without mocks, the audit trail leaks framework-specific types, and migrating to a different runtime (CLI vs FastAPI vs worker process) requires editing the core.

### INV-11 — Resilience logic lives in infrastructure decorators

Retry loops, circuit breaker checks, rate-limit backoff, timeout enforcement: all of these belong in `src/codetoreum/infrastructure/resilience/` decorator classes that wrap adapters. **Adapter bodies do not embed resilience logic.**

Example: `GitHubTicketAdapter._make_request()` documents that it does not retry; `ResilientTicketSystemDecorator` handles it.

**Violation cost**: resilience strategy fragments across adapters, becomes inconsistent, and can't be swapped per environment.

---

## Event discipline

### INV-10 — All state changes emit a domain event

Any mutation that affects observable state MUST produce a frozen-dataclass domain event. The executor emits via `event_store.append()`; event handlers emit via `event_bus.publish()`.

Silent mutations — code that changes state without emitting an event — are architectural violations.

**Violation cost**: the event store loses its audit-trail guarantee; replay-based debugging breaks; downstream subscribers (metrics, dashboards, derived projections) can't observe the change.

### Domain event handler invariant (referenced by GitHub issue #904 Work item 1)

Every `EventHandler` subclass in `application/event_handlers/` MUST either be:
- Registered with the event bus in `ProductionApplicationBootstrap.setup()`, or
- Explicitly marked as dead code in source (annotated `@dead_code` or scheduled for deletion).

The 2026-05-31 bootstrap run discovered four handlers (`WorkflowEventHandler`, `ExecutionEventHandler`, `BranchResolutionEventHandler`, `RepairCycleEventHandler`) that exist in source but were never wired. Per architect decision (review doc §7.1), all four will be wired; the placeholder stubs in three of them remain as scaffolding for future capabilities. CI should enforce the "registered-or-marked" rule going forward.

---

## Port discipline

### INV-09 — Explicit port inheritance

Application services and adapters that implement an output port MUST inherit from the port ABC explicitly. Duck typing is forbidden.

Example: `ExecutionServiceAgentExecutor(IAgentExecutor)`, `MultiProjectOrchestrator(IMultiProjectOrchestrator)`, `WorkflowOrchestrator(IWorkflowOrchestrator)`.

**Violation cost**: mypy can't verify the implementation; refactors that change a port signature don't catch out-of-date implementations.

### INV-08 — Critical adapter slots must be non-mock in production

```python
CRITICAL_ADAPTER_SLOTS = {"board", "ticket", "coding_agent", "version_control", "container", "code_review"}
```

No adapter in these slots may be `Mock`, `InMemory`, `Fake`, or `Null` in a production bootstrap. Production bootstrap raises `RuntimeError` at startup if any of these slots resolves to a non-production implementation.

**Violation cost**: production bootstrap silently runs on stub adapters, producing meaningless results.

### INV-19 — Board adapter is authoritative for current column state

The board adapter (`IBoardService`, and via it GitHub Projects v2 / Jira / etc.) is the **single source of truth for which column a given work item is currently in**. Reads of current column go through `IBoardService.get_item_position()`. Writes go through `IBoardService.move_item_to_column()`, which projects the change to the external system and emits `WorkItemColumnChangedEvent`.

Project config remains authoritative for workflow *structure* (which columns exist and how they're configured). The board adapter reconciles the external board to project config on startup and on demand.

`WorkItem.current_column` is being deleted from the domain (breaking REST change per GitHub issue #904 Work item 3). Reads always go to the board adapter; subscribers update derived projections via `WorkItemColumnChangedEvent`.

**Violation cost**: silent column drift between internal state and the external board (D-S from the 2026-05-31 bootstrap retrospective).

---

## Adapter design rules

### INV-15 — Coding agent adapters emit lifecycle and granular events

`ICodingAgent` adapters MUST emit `CodingAgent*` events on the event bus for every tool call, tool result, text output, thinking block, rate-limit notice, API retry, OTel span, and tokens-used summary they observe — plus `CodingAgentInvokedEvent` / `CodingAgentReadyEvent` / `CodingAgentCompletedEvent` lifecycle bookends.

Granular events (`CodingAgentToolCallEvent`, `CodingAgentToolResultEvent`, `CodingAgentTextOutputEvent`, `CodingAgentThinkingEvent`, `CodingAgentRateLimitEvent`, `CodingAgentApiRetryEvent`, `CodingAgentOtlpSpanEvent`) follow a 14-day default retention policy. See [domain/events.md → Coding Agent Context](./domain/events.md).

**Violation cost**: agent execution becomes a black box; behavioural analysis (prompt optimisation, tool selection, context strategy) becomes impossible; OTel routing via the event bus breaks.

### INV-16 — No filesystem extraction from agent execution environments

Agent execution output flows exclusively through `CodingAgent*` events. **Filesystem extraction from agent execution environments is forbidden.** The filesystem may be used to *pass context into* agents (read-only source mounts) but never to *retrieve context out*.

A crashed agent + lost filesystem must not equal lost execution data.

**Violation cost**: introduces a Schrödinger source of truth (some data in events, some on disk); resurrects the `/output` antipattern; breaks event-store-as-audit-trail guarantees.

### INV-17 — Coding agent adapter owns invocation mode

The coding agent adapter, not the orchestrator, owns the choice of invocation mode (containerized / host / API). The orchestrator validates that the configured mode is in the adapter's `supported_invocation_modes()` at config-load time.

`ExecutionService` does not branch on container details — mode comes from `AgentConfig.invocation.mode`.

**Violation cost**: container concepts leak back into the application layer; supporting a new vendor with a different invocation shape (e.g. an HTTP-only API) requires application-layer changes instead of being a pure adapter concern.

### INV-18 — Prompt building separated from coding agent adapters

Prompt-building business logic (assembling work-item + agent role + workspace context + prior outputs into a `StructuredPrompt`) lives in `IPromptBuilder` implementations, not inside coding agent adapters. Adapters render the structured prompt to their vendor's expected format (text for Claude Code, message array for Copilot, etc.) but do not own *what context to include*.

**Violation cost**: prompt logic forks across adapters; a Copilot adapter and a Claude Code adapter use divergent context strategies for the same agent role; the same prompt-building improvement has to be made in N places.

---

## Production isolation

### INV-07 — Simulation-only routes never appear in production

Simulation-only REST routes mount exclusively in `SimulationApplicationBootstrap._create_fastapi_app()`. They MUST NEVER appear in `ProductionApplicationBootstrap._create_fastapi_app()`.

The two bootstrap classes produce fundamentally different `FastAPI` instances. Merging routes is a production security boundary violation.

**Violation cost**: simulation seeding / reset endpoints accidentally exposed in production.

### INV-14 — Production REST API requires bearer auth

All production REST API calls MUST include `Authorization: Bearer <token>`. The token is generated by `SimpleTokenAuthManager` on startup and printed to the console as `Authentication token: <jwt>`.

Exceptions:
- The `/health` endpoint is unauthenticated.
- GitHub webhook endpoints use HMAC-SHA256 signature verification instead of bearer tokens.

**Violation cost**: production endpoints exposed without auth.

### INV-20 — Critical adapters must declare a failure route (GitHub issue #904 Work item 5)

Adapters in the critical slots (INV-08), plus the event store, MUST take an `IFailedEventStore` parameter and route final failures to it. `ProductionApplicationBootstrap.setup()` fails to start if a critical-path adapter has no failure route.

**Violation cost**: dropped data has no recovery surface. The 2026-05-31 bootstrap run lost 8 coding-agent telemetry events because the ES event store dropped after 2 retries with no DLQ wiring (D-P).

### INV-21 — Production bootstrap requires exclusive infrastructure (GitHub issue #904 Work item 7)

The production bootstrap harness MUST refuse to start if any of the following are shared with another service:

- The Elasticsearch cluster at `ELASTICSEARCH_URL` (or its index prefix is contended).
- The Redis instance at `REDIS_URL` (or its key prefix is contended).
- The Docker daemon's running container count + headroom does not accommodate `agent_count × max_parallel_work_items`.
- `GITHUB_TOKEN` rate-limit headroom is below 1000 requests, or the configured `github_org/github_repo` is inaccessible.

There is no "opt out and run anyway" flag.

**Violation cost**: the 2026-05-31 run shared ES with switchyard, producing 51-second cycles, 9.7-second work-item GETs, dropped telemetry, and masked errors. Running bootstrap on shared infra is worse than not running it — it hides real problems behind contention noise.

---

## Cross-references

- [`bootstrap/ARCHITECTURE.md §6`](../../bootstrap/ARCHITECTURE.md) — bootstrap-phase-specific invariants (INV-01 through INV-06, INV-13).
- [`bootstrap/implementation-review-2026-05-31.md §7`](../../bootstrap/implementation-review-2026-05-31.md) — architect decisions that shaped INV-19, INV-20, INV-21.
- GitHub issue #904 — roadmap for the work that establishes INV-19 / 20 / 21 in code.
- [`overview.md`](./overview.md) — architectural model these invariants apply to.
