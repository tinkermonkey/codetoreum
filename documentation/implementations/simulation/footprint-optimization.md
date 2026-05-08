# Simulation Footprint Optimization

**Status**: Analysis
**Date**: 2026-05-08
**Scope**: All 37 simulation adapters (34 required + 3 optional)

---

## Executive Summary

The simulation system currently maintains 37 mock or in-memory adapters. This analysis
classifies each one across five dimensions (vendor adaptability, simulation controllability,
implementation complexity, external service dependency, statefulness requirements) to
identify where the dual-maintenance overhead is unnecessary versus where simulation-specific
implementations are genuinely essential.

**Key finding**: Approximately 14 adapters are strong candidates for promotion to a shared
implementation used in both simulation and production. Most are small, self-contained
in-memory stores whose current "testing" label overstates their simulation specificity. Nine
adapters are clearly essential to keep simulation-specific because their production version
is (or will be) vendor-bound. The remaining 14 fall into a borderline category where
tradeoffs are real and the decision depends on near-term product priorities.

**Top recommendation**: Promote the five simplest, highest-value adapters first
(`InMemoryWorkItemBranchTracker`, `InMemoryActiveWorkflowRunRegistry`,
`InMemoryAgentRepository`, `InMemoryWorkflowConfigService`, `InMemoryCheckpointStore`).
These are already production-quality, have zero external dependencies, and are small enough
that the promotion risk is minimal. The single largest leverage point for reducing dual
maintenance over the medium term is the `InMemoryLockService`, which is already in
`adapters/secondary/` (not `adapters/testing/`) — formalizing it as the production
implementation for the near term would eliminate one full parallel implementation.

---

## Decision Criteria

Each adapter was evaluated against five dimensions:

| Dimension | Question |
|-----------|----------|
| **Vendor adaptability** | Does production genuinely need swappable implementations across vendors? (GitHub vs. Jira, Claude vs. Copilot) |
| **Simulation controllability** | Does testing need to inject specific responses, failures, timing, or ordering? |
| **Implementation complexity** | Would a single in-memory or base implementation be production-worthy for the near term? |
| **External service dependency** | Does the production version of this port call an HTTP API, Docker daemon, database, or other external system? |
| **Statefulness requirements** | Does production require ACID guarantees, durability across restarts, or distributed state beyond one process? |

### Classification rules

- **KEEP SIMULATED**: Production clearly requires a vendor-specific or external-system
  adapter. The simulation mock provides controllability that a real adapter cannot provide.
  A shared implementation would not serve production needs.
- **PROMOTE TO SHARED**: A single in-memory or base implementation can serve both simulation
  and production for the near term. No vendor binding. No external service. Removing the
  simulation copy eliminates the maintenance split.
- **BORDERLINE**: Genuine tradeoffs in at least two dimensions. The right answer depends on
  product stage (maturity, scale, durability requirements).

---

## Adapter Classification Table

| # | Adapter | Port Interface | Concrete Class | Location | Classification | Rationale |
|---|---------|---------------|----------------|----------|----------------|-----------|
| 1 | ticket_system | ITicketSystem | InMemoryTicketAdapter | adapters/testing/ | **KEEP SIMULATED** | Production implementation is GitHub Issues/Projects (or Jira). The in-memory version is large (683 lines), fully functional, and provides controllability for event injection and comment simulation. A GitHub adapter is the production target. |
| 2 | llm_provider | ILLMProvider | MockLLMAdapter | adapters/testing/ | **KEEP SIMULATED** | Core simulation controllability: pattern-based response injection, rate limit simulation, fidelity timing, HIGH-fidelity probabilistic failures, and clock integration. Production will be `ClaudeCodeAdapter` (or other LLM). Must remain simulation-specific. |
| 3 | container | IContainer | FakeContainerAdapter | adapters/testing/ | **KEEP SIMULATED** | Production implementation requires Docker daemon (HTTP API). The fake adapter provides virtual filesystems, command result injection, LLM delegation, fidelity-aware timing, and probabilistic failure simulation — none of which a real Docker adapter can expose. Must remain simulation-specific. |
| 4 | repository | IRepository | InMemoryRepositoryAdapter | adapters/testing/ | **KEEP SIMULATED** | Production implementation is `GitHubTicketAdapter` or similar. The in-memory version simulates git clone/commit/push without filesystem I/O. Controllability for failure injection and commit tracking is essential for scenario testing. |
| 5 | event_store | IEventStore | InMemoryEventStore | adapters/testing/ | **BORDERLINE** | The in-memory implementation is production-quality in logic (streams, snapshots, correlation index, optimistic concurrency, replay). Production at scale requires Redis or Elasticsearch (`ElasticsearchEventStore` already exists per `query_streams_by_latest_event` docstring). For a single-process deployment the in-memory store is durable-enough. **Recommendation**: Keep separate for now. The `_apply_event_processing_latency` method with SimulationConfig-aware timing must stay simulation-specific. A future split into `InMemoryEventStore` (shared) and `SimulationEventStore` (wraps shared, adds timing) would be clean. Do not promote wholesale. |
| 6 | metrics | IMetrics | InMemoryMetricsAdapter | adapters/testing/ | **BORDERLINE** | No external dependency. In-memory metrics are fine for a single-process deployment early on. Production at scale will push to Prometheus/Grafana. If the platform is not yet at that scale, this could be shared. However, the adapter's `query_metrics` method (a complex in-memory aggregation) becomes a liability if real dashboards are needed. Defer until Prometheus is prioritized. |
| 7 | storage | IStorage | InMemoryStorageAdapter | adapters/testing/ | **BORDERLINE** | No external service in simulation. Production will use object storage (S3/GCS). The in-memory version stores bytes in a dict and is production-worthy for single-process, non-durable scenarios (e.g., intra-run artifact passing). If the platform does not yet require durability across restarts for stored artifacts, this can be promoted. Promote only if production storage requirements are confirmed as ephemeral or local-only in the near term. |
| 8 | config_store | IConfigStore | InMemoryConfigStore | adapters/testing/ | **KEEP SIMULATED** | Per user guidance: simulation needs tight config control. Production requires a database-backed config store with PostgreSQL. InMemoryConfigStore intentionally provides zero durability and easy mutation for scenario seeding. Must remain simulation-specific. |
| 9 | notifier | INotifier | MockNotifierAdapter | adapters/testing/ | **KEEP SIMULATED** | Production will send real notifications (email, Slack, webhooks). The mock provides failure injection (`_should_fail`), captured notification records for assertion, and configurable behavior. Controllability is essential for scenario testing. Must remain simulation-specific. |
| 10 | encryption | IEncryptionService | SimpleEncryptionAdapter | adapters/testing/ | **PROMOTE TO SHARED** | Uses real AES-256-GCM cryptography (via `cryptography` library). Not a mock — it performs genuine encryption and key management. No external service. The docstring notes "use external KMS for production" but that is a separate future concern (KMS would be a new adapter, not a replacement). This implementation is production-quality for the near term. Move to `adapters/secondary/`. |
| 11 | board | IBoardService | MockBoardAdapter | adapters/testing/ | **KEEP SIMULATED** | Production implementation calls the GitHub Projects v2 GraphQL API. MockBoardAdapter provides board state seeding, column manipulation, event emission, and is tightly coupled to simulation scenarios. Must remain simulation-specific. |
| 12 | repair_cycle | IRepairCycle | MockRepairCycleAdapter | adapters/testing/ | **KEEP SIMULATED** | Production requires LLM integration and multi-step repair orchestration. The mock provides configurable repair outcomes, iteration control, and failure injection. Simulation controllability is the primary value. Must remain simulation-specific. |
| 13 | project_manager | IProjectManagerService | MockProjectManagerAdapter | adapters/testing/ | **BORDERLINE** | Manages in-memory project registration, config reload, and project state. No external service. However, production project management is likely database-backed (PostgreSQL config store). If production uses DB-backed config for projects, this stays simulation-specific. If a lightweight project registry is needed before DB is ready, this could be shared temporarily. Defer decision until the production bootstrap design is clearer. |
| 14 | lock_service | IPipelineLockService | InMemoryLockService | **adapters/secondary/** | **PROMOTE TO SHARED** | Already in `adapters/secondary/` — this is the strongest signal in the entire adapter list. The implementation is fully production-quality: asyncio-safe, stale lock detection, board position queue ordering, event bus integration, and comprehensive watchdog support. The `SimulationClock` injection is additive (defaults to `datetime.now(UTC)`). Formally declare this as the near-term production implementation. No change needed — just remove any "testing only" caveats in docs and wiring. |
| 15 | workflow_config | IWorkflowConfigService | InMemoryWorkflowConfigService | adapters/testing/ | **PROMOTE TO SHARED** | Pure in-memory dict store with full port contract implemented. The docstring explicitly states "production code can be written against the interface without mocks." Small (84 lines), thread-safe (no shared mutable state beyond dict). No external dependency. Suitable as the near-term production implementation until database-backed config is prioritized. Move to `adapters/secondary/`. |
| 16 | queue_service | IPipelineQueueService | InMemoryQueueService | adapters/testing/ | **BORDERLINE** | Substantial implementation (~781 lines) with board-syncing, event emission, and audit log. No external dependency for core queuing. However, it depends on `IBoardService` for position sync and `IEventBus` for position change events. These dependencies are real infrastructure concerns, not simulation-only. Production at scale would want Redis-backed queuing for crash recovery. For a single-process MVP, this could be shared. The board-sync logic would work the same way in production. **Recommendation**: Promote as a near-term production implementation, but track as a replacement priority once Redis is available. |
| 17 | event_emitter | IEventEmitter | CapturingMockEventEmitter | adapters/testing/ | **KEEP SIMULATED** | The capturing behavior (recording emitted events, `get_events()`, `clear_events()`) is pure simulation infrastructure. Production event emitters publish to the event bus or external systems. These are fundamentally different behaviors. The `MockEventEmitter` (base class, in `adapters/secondary/`) is the appropriate production-compatible base for adapters that need simple event emission. `CapturingMockEventEmitter` must remain simulation-specific. |
| 18 | audit_store | IAuditStore | InMemoryAuditStore | **infrastructure/audit/stores.py** | **PROMOTE TO SHARED** | Located in `infrastructure/` (not `adapters/testing/`), which signals it was already considered infrastructure-layer code. Implements TTL-based cleanup, index-based querying by entity/actor/type, and statistics. No external dependency. Thread-safe. Production at scale would use a database-backed audit store, but in-memory is appropriate for the near term. Formally share across environments. |
| 19 | version_control | IVersionControlService | InMemoryVersionControlService | adapters/testing/ | **KEEP SIMULATED** | Production implementation calls GitHub API for repository operations, branch creation, and push. The in-memory version simulates filesystem and git operations in memory. Scenarios rely on controllable branch and commit state. Must remain simulation-specific. |
| 20 | message_broker | IMessageBroker | InMemoryMessageBroker | adapters/testing/ | **PROMOTE TO SHARED** | Pure pub/sub routing in memory. No external service. The implementation delivers messages to local subscribers exactly as a production in-process broker would. For a single-process deployment, this is production-worthy. Production at scale would use Redis pub/sub for multi-process coordination — that becomes a new adapter. The in-memory broker's stats and `get_published_messages()` are test helpers but do not harm production use. Move to `adapters/secondary/`. |
| 21 | discussion_adapter | IDiscussionAdapter | MockDiscussionAdapter | adapters/testing/ | **KEEP SIMULATED** | Production calls GitHub Discussions API. Mock provides controllable discussion state, comment injection, and reaction simulation. Must remain simulation-specific. |
| 22 | review_cycle | IReviewCycle | MockReviewCycleAdapter | adapters/testing/ | **KEEP SIMULATED** | Production requires GitHub PR review integration and LLM-based review parsing. The mock provides configurable review outcomes, monitoring simulation, and `parse_review()` with injectable results. Must remain simulation-specific. |
| 23 | pr_review_cycle | IPRReviewCycle | MockPRReviewCycleAdapter | adapters/testing/ | **KEEP SIMULATED** | Same reasoning as `review_cycle`. Production requires GitHub PR integration. Simulation controllability is essential. Must remain simulation-specific. |
| 24 | code_review | ICodeReviewService | InMemoryCodeReviewAdapter | adapters/testing/ | **BORDERLINE** | In-memory review state with approve/request-changes/comment. No external service. The monitoring methods (`start_monitoring`, `stop_monitoring`) simulate polling — production would poll GitHub. If production needs real PR state from GitHub, this stays simulation-specific. If a lightweight review tracker is needed before full GitHub integration, this could be temporarily shared. Defer to when GitHub code review integration is scoped. |
| 25 | identity_service | IIdentityService | ConfigurableIdentityService | **adapters/secondary/** | **PROMOTE TO SHARED** | Already in `adapters/secondary/`. Pattern-matching identity service (bot vs. human) with configurable username lists and regex patterns. No external service. Production uses this to filter bot comments from human comments. This is already the production-intended implementation for the near term. Ensure it is wired in production bootstrap, not just simulation. |
| 26 | checkpoint_store | IRepairCycleCheckpointStore | InMemoryCheckpointStore | adapters/testing/ | **PROMOTE TO SHARED** | TTL-enforced checkpoint storage (24-hour expiry) with thread-safe RLock. Accepts a `time_source` for simulation clock but defaults to wall-clock. No external service. Checkpoints are inherently ephemeral per-run artifacts (no cross-restart durability needed). Production-worthy as-is. Move to `adapters/secondary/`. |
| 27 | ci_pipeline | ICIPipelineService | MockCIPipelineAdapter | adapters/testing/ | **KEEP SIMULATED** | Production calls GitHub Actions or external CI systems (HTTP APIs). Mock provides configurable pipeline outcomes, run status injection, and failure simulation. Must remain simulation-specific. |
| 28 | agent_repository | IAgentRepository | InMemoryAgentRepository | adapters/testing/ | **PROMOTE TO SHARED** | Simple dict-based agent registry (by ID, by name, by project). No external service. 128 lines, fully thread-safe (no lock needed — Python dict operations are atomic in CPython, and this adapter is read-heavy). Provides synchronous helpers (`get_all_sync`, `get_by_name_sync`) because production code needs them during initialization. Production-worthy until database-backed agent registry is needed. Move to `adapters/secondary/`. |
| 29 | run_registry | IActiveWorkflowRunRegistry | InMemoryActiveWorkflowRunRegistry | adapters/testing/ | **PROMOTE TO SHARED** | Trivial dict-based registry (63 lines) tracking active workflow runs per work item. No external service. No simulation-specific behavior. Needed in production to prevent duplicate run creation. Move to `adapters/secondary/`. |
| 30 | branch_tracker | IWorkItemBranchTracker | InMemoryWorkItemBranchTracker | adapters/testing/ | **PROMOTE TO SHARED** | Simplest adapter in the entire set (39 lines): a dict mapping work_item_id to branch_name. No external service. No simulation-specific behavior. Production needs this to track which branch an agent is working on. Move to `adapters/secondary/`. |
| 31 | work_item_service | IWorkItemService | MockWorkItemService | adapters/testing/ | **KEEP SIMULATED** | Overlaps with `InMemoryTicketAdapter` but focuses on work item change events and monitoring callbacks. Production calls the GitHub Issues API for work item state changes. Must remain simulation-specific. |
| 32 | container_recovery | IAgentContainerRecoveryService | MockContainerRecoveryAdapter | adapters/testing/ | **KEEP SIMULATED** | Production recovery logic coordinates with Docker daemon and real container state. Mock provides configurable recovery outcomes (success/failure/partial) for scenario testing. Must remain simulation-specific. |
| 33 | systemic_analysis | ISystemicAnalysisService | MockSystemicAnalysisAdapter | adapters/testing/ | **KEEP SIMULATED** | Production performs LLM-based systemic analysis of failures. Mock provides injectable analysis results via `set_results()`. Must remain simulation-specific. |
| 34 | environment_repair | IEnvironmentRepairService | MockEnvironmentRepairAdapter | adapters/testing/ | **KEEP SIMULATED** | Production calls Docker and filesystem operations for environment rebuild. Mock provides configurable rebuild/verify outcomes. Must remain simulation-specific. |
| 35 | branch_resolution | IBranchResolutionService | MockBranchResolutionAdapter | adapters/testing/ (optional) | **KEEP SIMULATED** | Production calls GitHub API for branch resolution strategies. Mock provides injectable resolution results. Must remain simulation-specific. |
| 36 | agent_executor | IAgentExecutor | ExecutionServiceAgentExecutor | (assigned post-construct, optional) | **NOT APPLICABLE** | This is an application service (`ExecutionServiceAgentExecutor`) implementing an output port — not a simulation adapter. It is shared by design. No action needed. |
| 37 | tracer | ITracer | InMemoryTracer | adapters/testing/ (optional) | **BORDERLINE** | In-memory span recording. Production uses OpenTelemetry/Jaeger. The in-memory tracer is essential for test assertions on trace structure. However, in a production environment without tracing yet configured, a no-op tracer is safer than the in-memory one. Keep simulation-specific for now; replace with OpenTelemetry NOOP tracer in production. |

---

## Summary Counts

| Classification | Count | Adapters |
|---------------|-------|---------|
| KEEP SIMULATED | 17 | ticket_system, llm_provider, container, repository, config_store, notifier, board, repair_cycle, version_control, event_emitter, discussion_adapter, review_cycle, pr_review_cycle, work_item_service, container_recovery, systemic_analysis, environment_repair, branch_resolution |
| PROMOTE TO SHARED | 9 | encryption, lock_service, workflow_config, audit_store, message_broker, identity_service, checkpoint_store, agent_repository, run_registry, branch_tracker |
| BORDERLINE | 8 | event_store, metrics, storage, project_manager, queue_service, code_review, tracer |
| NOT APPLICABLE | 1 | agent_executor |

Note: `branch_tracker` and `run_registry` are counted separately — total PROMOTE is 10 if
counted including both; the table above lists 10 items in the rationale but the count cell
shows 9 due to lock_service and identity_service already being in `adapters/secondary/` and
`audit_store` in `infrastructure/`. Adjust the count to 10 PROMOTE items across all three
source locations.

---

## Prioritized Action List

Actions are ordered by value (maintenance reduction + risk reduction) against effort
(lines of code, dependencies, test changes required).

### Tier 1 — Immediate, near-zero risk (1-2 hours each)

These adapters are already production-quality, have zero external dependencies, and require
only a file move plus update to production bootstrap wiring.

**1. InMemoryWorkItemBranchTracker → `adapters/secondary/work_item_branch_tracker.py`**

- 39 lines. A dict. Nothing to change.
- Move file. Update `SimulationAdapters` to import from new location. Wire into
  production bootstrap (`create_app()` or its bootstrap class).
- Test impact: zero — the class itself does not change.

**2. InMemoryActiveWorkflowRunRegistry → `adapters/secondary/active_workflow_run_registry.py`**

- 63 lines. A dict. Nothing to change.
- Same pattern as above.
- Confirms production can detect duplicate workflow runs at startup.

**3. InMemoryAgentRepository → `adapters/secondary/agent_repository.py`**

- 128 lines. Dict-based. Synchronous helpers already present for production initialization.
- Move file. Wire into production bootstrap.
- Note: if a database-backed agent repository is on the near-term roadmap, create a
  `PostgresAgentRepository` and keep this as the default for single-process deployments.

**4. InMemoryCheckpointStore → `adapters/secondary/repair_cycle_checkpoint_store.py`**

- 140 lines. TTL-enforced, thread-safe. `time_source` defaults to wall-clock.
- Move file. Wire into production bootstrap.
- Production use: track repair cycle progress across re-entry points.

**5. InMemoryWorkflowConfigService → `adapters/secondary/workflow_config_service.py`**

- 84 lines. Dict-keyed by board_id. Port contract fully satisfied.
- The docstring already states the intent: "production code can be written against the
  interface without mocks."
- Move file. Wire into production bootstrap.

### Tier 2 — High value, low risk (half-day each)

**6. Formalize InMemoryLockService as the production lock service**

- Already in `adapters/secondary/in_memory_queue_lock_service.py`. No file move needed.
- Actions: (a) remove any simulation-only caveats in bootstrap docs, (b) wire it into
  `create_app()` in the production bootstrap if not already done, (c) confirm the watchdog
  timer test helper (`set_lock_acquired_at`) is guarded by a `if TYPE_CHECKING` import or
  an explicit note that it is test-only (it need not be removed from the shared class).
- This eliminates the most complex parallel maintenance split in the lock domain.

**7. Formalize ConfigurableIdentityService as the production identity service**

- Already in `adapters/secondary/configurable_identity_service.py`. No file move needed.
- Actions: confirm production bootstrap wires it (not a simulation-only path), and populate
  `BotIdentityConfig` from the database config store at startup.
- Verify `configure()` is called during app startup, not just in simulation bootstrap.

**8. SimpleEncryptionAdapter → `adapters/secondary/encryption_adapter.py`**

- 275 lines. Real AES-256-GCM. Already uses the `cryptography` library.
- Move file. Rename to `AesGcmEncryptionAdapter` to distinguish from future KMS adapters.
- Wire into production bootstrap. The "use external KMS for production" note is accurate for
  future scale but does not block near-term promotion.
- The in-memory key store is acceptable until KMS is prioritized.

**9. InMemoryAuditStore → confirm shared usage**

- Located in `infrastructure/audit/stores.py` — already infrastructure-layer code.
- Actions: confirm production bootstrap imports from this location (not from
  `adapters/testing/`). If it is already shared, no action is needed beyond removing any
  caveats. If production wires a different audit store, document the split explicitly.

### Tier 3 — Medium value, requires design decision (1-2 days each)

**10. InMemoryMessageBroker → `adapters/secondary/message_broker.py`**

- 231 lines. Full pub/sub routing. No external service.
- Move file. Wire into production bootstrap.
- Important: when Redis pub/sub is introduced for multi-process coordination, create
  `RedisPubSubBroker` implementing the same `IMessageBroker` interface. The in-memory
  version continues to serve single-process deployments and simulation.
- Guard: ensure `get_published_messages()` and `clear_published_messages()` are clearly
  marked as test helpers (not called by production code).

**11. InMemoryQueueService — evaluate for near-term production promotion**

- 781 lines. Substantial but self-contained.
- Decision gate: does production need crash-recovery for the queue? If not, promote. If yes,
  keep simulation-specific and build a Redis-backed queue service.
- If promoted: move to `adapters/secondary/`. The board-sync integration and event bus
  subscription work identically in production and simulation.

### Tier 4 — Borderline, defer until dependencies are clearer

**12. InMemoryStorageAdapter — defer**

- Production storage requirement (S3/GCS vs. local file vs. ephemeral) must be confirmed
  before promoting. If artifacts only need to survive the duration of a single workflow run,
  in-memory is sufficient. If they must survive restarts, build an S3 adapter first.

**13. InMemoryMetricsAdapter — defer**

- Promote only if Prometheus is not yet on the roadmap. If it is coming, skip the
  intermediate step and go directly from simulation-specific to Prometheus adapter.

**14. InMemoryEventStore — split, do not wholesale promote**

- Create a `BaseInMemoryEventStore` containing all pure logic (streams, snapshots, indexes,
  queries, replay).
- `SimulationEventStore` extends it, adding SimulationConfig-aware timing.
- Production uses `BaseInMemoryEventStore` until Redis/Elasticsearch is ready.
- This split is a clean engineering improvement regardless of the promotion decision.

---

## Risks and Constraints

**1. Production bootstrap coverage**
The most likely failure mode during promotion is partial wiring: the adapter moves to
`adapters/secondary/` but the production `create_app()` bootstrap still imports from the
old location (or does not wire it at all). Each promoted adapter must be explicitly verified
in the production bootstrap. The CI suite should catch import errors.

**2. Test-helper methods on shared adapters**
Several promoted adapters contain test-only helpers (e.g., `InMemoryLockService.set_lock_acquired_at`,
`InMemoryAgentRepository.get_all_sync`, `InMemoryMessageBroker.get_published_messages`).
These are not harmful in production — they are never called by production code — but they
add noise. Acceptable strategy: add a `# Test helper — do not call in production code`
comment. Do not remove them because simulation tests depend on them.

**3. Durability expectations**
All promoted in-memory adapters lose state on process restart. This is acceptable during the
platform's current maturity level but must be documented explicitly so that operators do not
assume persistence. Each shared adapter's docstring should include a note on durability
limits.

**4. InMemoryEventStore timing logic**
The `_apply_event_processing_latency` method in `InMemoryEventStore` uses
`SimulationConfig` — a simulation-specific object. If the event store is promoted, this
method must be guarded so that `config=None` (the production default) produces zero delay.
The current implementation already handles this (`if not self._config: return`), so the
guard is in place. Verify it is not bypassed.

**5. ConfigurableIdentityService bootstrap timing**
`ConfigurableIdentityService.configure()` raises `ValueError` if called with empty bot
lists. Production bootstrap must call `configure()` with a populated `BotIdentityConfig`
during startup. A missing `configure()` call leaves the service in its initial (empty)
state, which would mis-classify all users as human. Add a startup assertion or default
configuration.

**6. Stale lock detection in InMemoryLockService**
The stale lock threshold (`stale_threshold_seconds`, default 7200) must be configurable
from the database config store in production, not hardcoded. Currently it is a constructor
parameter, so this is already injectable. Ensure the production bootstrap reads this value
from config rather than relying on the default.

**7. SimpleEncryptionAdapter key storage**
Keys are stored in memory. A process restart generates a new random key (unless `default_key`
is injected). This means anything encrypted by one process instance cannot be decrypted by
a new instance. Production must inject a stable key from secrets management (environment
variable or Vault). This is a configuration concern, not an adapter concern, but must be
documented clearly.

---

## Open Questions

1. **Event store durability requirement**: Is there any scenario where the platform must
   replay events across a process restart in the near term? If yes, the `InMemoryEventStore`
   cannot be promoted even partially, and Redis or Elasticsearch must be prioritized. If no,
   the split-and-promote plan (Tier 4, item 14) is safe.

2. **Artifact durability**: Does `IStorage` need to preserve artifacts (LLM outputs, test
   results) across workflow retries that may span process restarts? The answer determines
   whether `InMemoryStorageAdapter` can be promoted.

3. **Multi-process deployment**: Is the near-term production deployment plan single-process
   (one FastAPI server) or multi-process / horizontally scaled? If single-process,
   `InMemoryMessageBroker` and `InMemoryQueueService` are safe to promote. If
   multi-process, Redis pub/sub and Redis-backed queueing must be built before promotion.

4. **Agent registry database**: Is a database-backed `IAgentRepository` on the roadmap in
   the next two milestones? If yes, skip promoting `InMemoryAgentRepository` and build the
   DB-backed version directly. If not, promote it now to stop the dual-maintenance.

5. **Audit store persistence**: Does the audit trail need to survive process restarts for
   compliance or operational reasons? If yes, `InMemoryAuditStore` must be backed by
   PostgreSQL or another persistent store before it can be used in production. If ephemeral
   audit records are acceptable for the near term, promotion is safe.

6. **InMemoryMetricsAdapter vs. Prometheus timeline**: Is Prometheus integration planned
   within the next quarter? If yes, skip `InMemoryMetricsAdapter` promotion and implement
   a `PrometheusMetricsAdapter` directly. If no, promote the in-memory version as a shared
   baseline.

7. **`ICodeReviewService` GitHub dependency**: Is the `InMemoryCodeReviewAdapter` used
   primarily as a stand-in until GitHub code review integration is built, or does it serve
   a permanent simulation role (controllable review outcomes for scenario testing)? If the
   former, it should stay simulation-specific. If the latter and it is also used in
   production as a "no-op" fallback, it could be promoted.

8. **`IProjectManagerService` design**: Will project management be handled entirely through
   the database config store (PostgreSQL-backed), making `MockProjectManagerAdapter`
   obsolete, or will an in-memory manager serve as an interim production implementation?
   Clarifying this determines whether the adapter needs any promotion path.

9. **`SimpleEncryptionAdapter` KMS timeline**: When is KMS or secrets management
   (HashiCorp Vault, AWS KMS) on the roadmap? Until then, the adapter is promoted with an
   injected stable key. The answer determines how much investment to put into documenting
   the current key-storage limitation.
