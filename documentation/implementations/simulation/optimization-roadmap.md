# Simulation Footprint Optimization Roadmap

**Status**: Decisions codified (some items superseded — see note)
**Date**: 2026-05-08
**Prerequisite**: [`footprint-optimization.md`](./footprint-optimization.md) — analysis and classification of all 37 simulation adapters

> **Note (2026-05-29)**: The §3 entry "LocalDiskStorageAdapter (replaces `InMemoryStorageAdapter`)" was overtaken by **DEF-015** (Phase D5). The `IStorage` port retired entirely along with `InMemoryStorageAdapter` and `MinioStorageAdapter`; agent output now flows through the `CodingAgent*` event family. The `LocalDiskStorageAdapter` replacement is no longer planned. See `bootstrap/ARCHITECTURE.md` §9 DEF-015 and [`adapters.md`](./adapters.md) for the current shape.

---

## Overview

This document records the resolved decisions for the eight borderline adapters identified in
`footprint-optimization.md`. It is the actionable companion to that analysis: each item
specifies what gets built, what it replaces, and when the simulation adapter is retired.

---

## Shared Infrastructure Dependencies

Two shared containers underpin most of the replacement implementations. They should be
stood up once and reused across all adapters that depend on them.

### Redis Container

**Used by**: Event Store, Queue Service
**Role**: Ephemeral-but-crash-safe storage for event streams and work item queues. A single
Redis container is shared across both adapters; namespaced key prefixes separate the two
concerns.

**Key prefix convention**:
```
codetoreum:events:*       — event store streams
codetoreum:queue:*        — pipeline queue entries and board position state
```

### Elasticsearch Container

**Used by**: Metrics Adapter, Tracer
**Role**: Time-series and structured-log backing for observability data. A single ES
container is shared across both adapters; separate index patterns separate the concerns.

**Index naming convention**:
```
codetoreum-metrics-*      — metrics time-series records
codetoreum-traces-*       — distributed trace spans and events
```

---

## Resolved Decisions

### Borderline adapters — new implementations required

| Adapter | Port Interface | Decision | Replacement | Retire Simulation Adapter? |
|---------|---------------|----------|-------------|----------------------------|
| `InMemoryEventStore` | `IEventStore` | **Replace** | `RedisEventStore` | Yes — once implemented |
| `InMemoryMetricsAdapter` | `IMetrics` | **Replace** | `ElasticsearchMetricsAdapter` | Yes — once implemented |
| `InMemoryStorageAdapter` | `IStorage` | **Replace** | `LocalDiskStorageAdapter` | Yes — once implemented |
| `MockProjectManagerAdapter` | `IProjectManagerService` | **Keep** | N/A — simulation only | No |
| `InMemoryQueueService` | `IPipelineQueueService` | **Replace** | `RedisQueueService` | Yes — once implemented |
| `InMemoryCodeReviewAdapter` | `ICodeReviewService` | **Keep** | N/A — simulation only | No |
| `InMemoryTracer` | `ITracer` | **Replace** | `ElasticsearchTracer` | Yes — once implemented |

### Promoted adapters — file moves and bootstrap wiring only

| Adapter | Current Location | Target Location | Action |
|---------|-----------------|-----------------|--------|
| `InMemoryWorkItemBranchTracker` | `adapters/testing/` | `adapters/secondary/` | Move file, update imports |
| `InMemoryActiveWorkflowRunRegistry` | `adapters/testing/` | `adapters/secondary/` | Move file, update imports |
| `InMemoryAgentRepository` | `adapters/testing/` | `adapters/secondary/` | Move file, update imports |
| `InMemoryCheckpointStore` | `adapters/testing/` | `adapters/secondary/` | Move file, update imports |
| `InMemoryWorkflowConfigService` | `adapters/testing/` | `adapters/secondary/` | Move file, update imports |
| `InMemoryMessageBroker` | `adapters/testing/` | `adapters/secondary/` | Move file, update imports |
| `SimpleEncryptionAdapter` | `adapters/testing/` | `adapters/secondary/` | Move file, rename to `AesGcmEncryptionAdapter` |
| `InMemoryLockService` | `adapters/secondary/` ✓ | Already in place | Wire into production bootstrap |
| `ConfigurableIdentityService` | `adapters/secondary/` ✓ | Already in place | Verify production bootstrap wiring |
| `InMemoryAuditStore` | `infrastructure/audit/stores.py` ✓ | Already in place | Verify production bootstrap wiring |

---

## Replacement Specifications

### 1. RedisEventStore

**Replaces**: `InMemoryEventStore` (`adapters/testing/in_memory_event_store.py`)
**Target location**: `adapters/secondary/redis_event_store.py`
**Shared infra**: Redis container (key prefix `codetoreum:events:`)

**What to preserve from the in-memory implementation**:
- Stream-per-aggregate-id model (key: `codetoreum:events:{aggregate_id}`)
- Optimistic concurrency check on append (compare expected version)
- Snapshot storage alongside event streams
- Correlation index for cross-aggregate queries (`get_events_by_correlation_id`)
- Replay support (`replay_from_beginning`, `replay_from_version`)
- `query_streams_by_latest_event` for board reconciliation queries

**What to drop**:
- `_apply_event_processing_latency` (SimulationClock-aware timing) — simulation-only; does not belong in production
- In-memory dict backing; replace with Redis `RPUSH` / `LRANGE` per stream

**Retirement condition**: `InMemoryEventStore` is removed from `adapters/testing/` and
`SimulationAdapters` once `RedisEventStore` is integrated into both the simulation bootstrap
(pointing at a test Redis instance) and the production bootstrap.

---

### 2. ElasticsearchMetricsAdapter

**Replaces**: `InMemoryMetricsAdapter` (`adapters/testing/in_memory_metrics_adapter.py`)
**Target location**: `adapters/secondary/elasticsearch_metrics_adapter.py`
**Shared infra**: Elasticsearch container (index pattern `codetoreum-metrics-*`)

**What to preserve from the in-memory implementation**:
- `record_timing(operation, duration_ms, tags)` — map to ES document with timestamp
- `increment_counter(metric, labels)` — map to ES counter document
- `record_gauge(metric, value, labels)` — map to ES gauge document
- `query_metrics(name, start, end)` — implement as ES range query on `@timestamp`

**What to drop**:
- In-memory list accumulation and dict-based aggregation
- `get_all_metrics()` (test helper) — not part of the port contract; do not implement in production adapter

**Retirement condition**: `InMemoryMetricsAdapter` is removed once `ElasticsearchMetricsAdapter`
is integrated and the simulation runs cleanly pointing at a test ES instance.

---

### 3. LocalDiskStorageAdapter

**Replaces**: `InMemoryStorageAdapter` (`adapters/testing/in_memory_storage_adapter.py`)
**Target location**: `adapters/secondary/local_disk_storage_adapter.py`
**Shared infra**: None — uses the local filesystem at a configurable base path

**Design notes**:
- Base path configurable via `IConfigStore` key `storage.base_path` (default: `./data/storage/`)
- File layout: `{base_path}/{namespace}/{key}` — direct filesystem hierarchy
- Metadata stored as a sidecar file: `{key}.meta.json` (content-type, size, created-at)
- `list_keys(namespace)` implemented as a directory listing

**What to preserve from the in-memory implementation**:
- `store(namespace, key, content, content_type)` / `retrieve(namespace, key)` / `delete(namespace, key)` / `exists(namespace, key)` / `list_keys(namespace)` — identical contract
- Byte-level storage (no encoding assumptions)

**What to drop**:
- `container` injection (the in-memory adapter delegated to `FakeContainerAdapter` for file retrieval — this is simulation-specific coupling)
- In-memory dict backing

**Retirement condition**: `InMemoryStorageAdapter` is removed once `LocalDiskStorageAdapter`
is integrated and verified in both simulation and production bootstrap. Simulation bootstrap
points at a temp directory (e.g., `tempfile.mkdtemp()`) that is cleaned up in teardown.

---

### 4. MockProjectManagerAdapter — KEEP

**Adapter**: `MockProjectManagerAdapter` (`adapters/testing/mock_project_manager_adapter.py`)
**Port**: `IProjectManagerService`
**Decision**: Retain as a simulation-only component.

**Rationale**: Project management configuration is expected to be database-backed
(PostgreSQL via the config store) in production. Building an in-memory manager as an
interim shared implementation would create a path that dead-ends. The simulation mock is
sufficient to support simulation workflows; the real implementation will be built alongside
the production config store.

**No retirement path in the near term.** Revisit when the database-backed project
configuration service is scoped.

---

### 5. RedisQueueService

**Replaces**: `InMemoryQueueService` (`adapters/testing/in_memory_queue_service.py`)
**Target location**: `adapters/secondary/redis_queue_service.py`
**Shared infra**: Redis container (key prefix `codetoreum:queue:`)

**What to preserve from the in-memory implementation**:
- Board-position-aware ordering (items sorted by board column position, not FIFO)
- `enqueue(work_item_id, board_position)` / `dequeue()` / `peek()` / `get_queue_depth()`
- `WorkItemColumnChangedEvent` subscription for automatic position updates
- Stale entry cleanup (items in queue whose work item no longer exists)
- Audit log entries per enqueue/dequeue operation

**Redis data model**:
```
codetoreum:queue:items       — Sorted set; score = board_position, member = work_item_id
codetoreum:queue:meta:{id}   — Hash; enqueue_time, board_id, column_name, attempt_count
```

**What to drop**:
- In-memory dict and asyncio.Queue backing
- `get_queue_snapshot()` test helper — not part of the port contract

**Retirement condition**: `InMemoryQueueService` is removed once `RedisQueueService` passes
the existing scenario tests pointing at a test Redis instance and is wired into production bootstrap.

---

### 6. InMemoryCodeReviewAdapter — KEEP

**Adapter**: `InMemoryCodeReviewAdapter` (`adapters/testing/in_memory_code_review_adapter.py`)
**Port**: `ICodeReviewService`
**Decision**: Retain as a simulation-only component.

**Rationale**: Keeping this as simulation-specific simplifies the simulation system by
avoiding the complexity of wiring a real GitHub code review integration into scenario tests.
The production implementation will call the GitHub Pull Requests API; that integration
should be built directly without an intermediate shared in-memory adapter.

**No retirement path in the near term.** Revisit when GitHub code review integration is
scoped as a production feature.

---

### 7. ElasticsearchTracer

**Replaces**: `InMemoryTracer` (`adapters/testing/in_memory_tracer.py`)
**Target location**: `adapters/secondary/elasticsearch_tracer.py`
**Shared infra**: Elasticsearch container (index pattern `codetoreum-traces-*`)

**Design notes**:
- Each span maps to one ES document: `{trace_id, span_id, parent_span_id, operation, start_time, duration_ms, tags, status}`
- `start_span(operation, parent=None)` — creates and returns a span context; flushes to ES on span close
- `get_trace(trace_id)` — ES term query on `trace_id` field, sorted by `start_time`
- The `ITracer` port contract (start/close span, get trace) maps cleanly to ES documents

**What to preserve from the in-memory implementation**:
- Span context propagation semantics (parent_span_id threading)
- `get_trace(trace_id)` for test assertions (now queries ES instead of an in-memory list)
- `ITracer` port contract exactly

**What to drop**:
- In-memory span list and dict-based trace assembly
- SimulationClock time source injection (production uses wall clock via `datetime.now(UTC)`)

**Retirement condition**: `InMemoryTracer` is removed from `adapters/testing/` and
`SimulationAdapters` once `ElasticsearchTracer` is integrated. Simulation bootstrap points
at the test ES container; trace assertions in scenario tests use `ElasticsearchTracer.get_trace()`.

---

## Promotion Specifications

These adapters require no new implementation — only a file move (or bootstrap wiring
confirmation for those already in `adapters/secondary/` or `infrastructure/`), plus
updating the production bootstrap to wire the shared class. They can proceed as a parallel
workstream independent of the replacement implementations above.

---

### P1. InMemoryWorkItemBranchTracker

**Current location**: `adapters/testing/in_memory_work_item_branch_tracker.py`
**Target location**: `adapters/secondary/work_item_branch_tracker.py`
**Port**: `IWorkItemBranchTracker`

**Action**: Move file. Update the import in `SimulationAdapters` and `AdapterResolver`.
Wire into production bootstrap.

**What does not change**: The class itself is unchanged. 39 lines: a single dict mapping
`work_item_id → branch_name` with `set`, `get`, `delete`, `get_all` methods.

**Production use**: Tracks which VCS branch each work item's agent is currently working on.
Required to prevent agents from creating duplicate branches across retries.

**Simulation impact**: Zero — the class has no simulation-specific behavior or imports.

---

### P2. InMemoryActiveWorkflowRunRegistry

**Current location**: `adapters/testing/in_memory_active_workflow_run_registry.py`
**Target location**: `adapters/secondary/active_workflow_run_registry.py`
**Port**: `IActiveWorkflowRunRegistry`

**Action**: Move file. Update imports. Wire into production bootstrap.

**What does not change**: 63 lines: a dict mapping `work_item_id → WorkflowRunRecord`,
tracking which workflow run is active for each work item.

**Production use**: Prevents duplicate workflow runs from being created for the same work
item. Read on every `BoardColumnChangedEvent` before dispatching a new run.

**Simulation impact**: Zero — no simulation-specific behavior. `SimulationAdapters` import
path updates automatically once the file moves.

---

### P3. InMemoryAgentRepository

**Current location**: `adapters/testing/in_memory_agent_repository.py`
**Target location**: `adapters/secondary/agent_repository.py`
**Port**: `IAgentRepository`

**Action**: Move file. Update imports. Wire into production bootstrap.

**What does not change**: 128 lines. Dict-based registry keyed by agent ID, with secondary
indexes by name and project. Provides both async (`get_by_id`) and synchronous
(`get_all_sync`, `get_by_name_sync`) accessors. The sync helpers exist because production
initialization code needs them at startup.

**Production use**: Agent catalog — maps agent IDs to capabilities, model configs, and
project assignments. Read during `BoardColumnEventHandler` dispatch to select the
appropriate agent for a stage.

**Simulation impact**: Zero. Note: if a database-backed agent repository is prioritized
within the next two milestones, skip the move and build `PostgresAgentRepository` directly.
The in-memory version then stays simulation-specific until the DB version is ready.

---

### P4. InMemoryCheckpointStore

**Current location**: `adapters/testing/in_memory_checkpoint_store.py`
**Target location**: `adapters/secondary/repair_cycle_checkpoint_store.py`
**Port**: `IRepairCycleCheckpointStore`

**Action**: Move file. Update imports. Wire into production bootstrap.

**What does not change**: 140 lines. TTL-enforced checkpoint storage (24-hour expiry by
default) with `threading.RLock` for thread safety. Accepts an optional `time_source`
callable — defaults to `datetime.now(UTC)` (wall clock), making it production-safe without
any modification. Simulation injects the `SimulationClock` via the `time_source` parameter.

**Production use**: Tracks repair cycle progress across re-entry points within a single
deployment lifetime. Checkpoints are inherently ephemeral (per-run artifacts); no
cross-restart durability is required.

**Simulation impact**: Simulation continues injecting `engine.get_clock_for_testing().now`
as `time_source` — no change to simulation bootstrap beyond the updated import path.

---

### P5. InMemoryWorkflowConfigService

**Current location**: `adapters/testing/in_memory_workflow_config_service.py`
**Target location**: `adapters/secondary/workflow_config_service.py`
**Port**: `IWorkflowConfigService`

**Action**: Move file. Update imports. Wire into production bootstrap.

**What does not change**: 84 lines. Dict-keyed by `board_id`. Implements
`get_workflow_config(board_id)`, `set_workflow_config(board_id, config)`,
`list_board_ids()`. The class docstring already states: *"production code can be written
against this interface without mocks."*

**Production use**: Stores workflow stage definitions (column names, agent types, entry
conditions) per board. Read on every `BoardColumnChangedEvent` to determine the active
stage and which agent to dispatch.

**Simulation impact**: Zero. Simulation scenarios seed config via `set_workflow_config()`
before the scenario runs — this call pattern works identically whether the class lives in
`testing/` or `secondary/`.

---

### P6. InMemoryMessageBroker

**Current location**: `adapters/testing/in_memory_message_broker.py`
**Target location**: `adapters/secondary/message_broker.py`
**Port**: `IMessageBroker`

**Action**: Move file. Update imports. Wire into production bootstrap. Mark test-helper
methods with a `# Test helper — do not call in production code` comment.

**What does not change**: 231 lines. Full in-process pub/sub routing: `publish(topic,
message)`, `subscribe(topic, handler)`, `unsubscribe(topic, handler)`. Tracks message
history and subscriber counts via `get_published_messages()` and `get_subscriber_count()`.

**Production use**: In-process message routing for a single-process deployment. When
multi-process deployment is required, a `RedisPubSubBroker` implementing the same
`IMessageBroker` interface replaces this — the in-memory version then reverts to
simulation-only use.

**Simulation impact**: `get_published_messages()` and `clear_published_messages()` are used
in simulation test assertions. These remain on the class; add the "test helper" comment but
do not remove them.

---

### P7. SimpleEncryptionAdapter → AesGcmEncryptionAdapter

**Current location**: `adapters/testing/simple_encryption_adapter.py`
**Target location**: `adapters/secondary/aes_gcm_encryption_adapter.py`
**Port**: `IEncryptionService`

**Action**: Move file. Rename class from `SimpleEncryptionAdapter` to
`AesGcmEncryptionAdapter`. Update all imports and references. Wire into production
bootstrap.

**What does not change**: 275 lines. Genuine AES-256-GCM implementation using the
`cryptography` library — not a mock. Supports key rotation, named keys, and in-memory key
storage.

**Critical production requirement**: The default random key is regenerated on every process
start, making cross-restart decryption impossible. Production bootstrap **must** inject a
stable `default_key` loaded from an environment variable or secrets manager (Vault, AWS
Secrets Manager). Add a startup assertion that fails loudly if no stable key is provided:

```python
if not config.encryption_key:
    raise RuntimeError("ENCRYPTION_KEY must be set in production environment")
adapter = AesGcmEncryptionAdapter(default_key=config.encryption_key)
```

**Simulation impact**: Simulation bootstrap can continue using a randomly generated key (or
a fixed test key for determinism). No scenario assertions depend on cross-restart decryption.

---

### P8. InMemoryLockService — Already in secondary

**Current location**: `adapters/secondary/in_memory_queue_lock_service.py` ✓
**Port**: `IPipelineLockService` / `IQueuedPipelineLockService`

**Action**: No file move required. Wire into production bootstrap (`create_app()`) if not
already done. Remove any "simulation-only" or "testing" caveats from comments and docs.

**What to verify**:
1. `create_app()` receives an `InMemoryLockService` instance — confirm this is wired, not
   left as a simulation-only path.
2. The stale lock threshold (`stale_threshold_seconds`, default 7200) is read from the
   production config store rather than relying on the constructor default.
3. The test helper `set_lock_acquired_at()` has a comment marking it as a test helper; it
   need not be removed since simulation tests depend on it.
4. The watchdog that detects stale locks is started in the production bootstrap (not only
   in the simulation bootstrap).

**Simulation impact**: None — `SimulationAdapters` already uses this class.

---

### P9. ConfigurableIdentityService — Already in secondary

**Current location**: `adapters/secondary/configurable_identity_service.py` ✓
**Port**: `IIdentityService`

**Action**: No file move required. Verify production bootstrap calls `configure()` with a
populated `BotIdentityConfig` at startup.

**What to verify**:
1. Production bootstrap calls `service.configure(BotIdentityConfig(bot_usernames=[...],
   bot_patterns=[...]))` during startup — not only in the simulation bootstrap.
2. `configure()` raises `ValueError` if called with empty bot lists; add a startup assertion
   or provide a non-empty default config so the error surfaces immediately on misconfiguration
   rather than silently misclassifying all users as human.
3. The bot username list is populated from the config store (not hardcoded in the bootstrap).

**Simulation impact**: None — simulation already configures this service.

---

### P10. InMemoryAuditStore — Already in infrastructure

**Current location**: `infrastructure/audit/stores.py` ✓
**Port**: `IAuditStore`

**Action**: No file move required. Confirm that the production bootstrap imports from
`infrastructure/audit/stores.py` (not from `adapters/testing/`) and wires this instance
into all paths that require audit logging.

**What to verify**:
1. Production bootstrap (`create_app()`) constructs an `InMemoryAuditStore` and passes it
   to all services and adapters that accept `IAuditStore`.
2. The TTL cleanup (entries older than the configured window are purged) is running — the
   store has a `cleanup_expired()` method that should be called periodically (e.g., via a
   background task or watchdog).
3. If audit records must survive process restarts for compliance reasons, a
   `PostgresAuditStore` must be built before production launch. Document this constraint
   explicitly in the class docstring.

**Simulation impact**: None — simulation already uses this class via `SimulationAdapters.audit_store`.

---

## Implementation Sequencing

All work divides into two parallel tracks. The promotion track (file moves and bootstrap
wiring) has zero infrastructure dependency and can start immediately. The replacement track
(new implementations) requires infrastructure containers to be stood up first.

### Track 1 — Promotions (no new implementation, parallel to Track 2)

```
Wave 1 — Trivial moves (1–2 hours each, no dependencies between them)
  ├── P1. InMemoryWorkItemBranchTracker  → adapters/secondary/
  ├── P2. InMemoryActiveWorkflowRunRegistry → adapters/secondary/
  ├── P3. InMemoryAgentRepository        → adapters/secondary/
  ├── P4. InMemoryCheckpointStore        → adapters/secondary/
  └── P5. InMemoryWorkflowConfigService  → adapters/secondary/

Wave 2 — Moves with minor notes (half-day each)
  ├── P6. InMemoryMessageBroker          → adapters/secondary/ (add test-helper comments)
  └── P7. SimpleEncryptionAdapter        → adapters/secondary/ (rename + stable key requirement)

Wave 3 — Bootstrap wiring verification only (no file move)
  ├── P8. InMemoryLockService            — verify production bootstrap wiring + watchdog
  ├── P9. ConfigurableIdentityService    — verify configure() called at startup
  └── P10. InMemoryAuditStore            — verify production bootstrap wiring + TTL cleanup
```

### Track 2 — Replacements (new implementations, grouped by shared infrastructure)

```
Phase C — No shared infra (start here — lowest risk)
  └── R3. LocalDiskStorageAdapter

Phase A — Redis container (shared; stand up once for both)
  ├── R1. RedisEventStore
  └── R5. RedisQueueService

Phase B — Elasticsearch container (shared; stand up once for both)
  ├── R2. ElasticsearchMetricsAdapter
  └── R7. ElasticsearchTracer

Phase D — No action (keep as simulation-only)
  ├── R4. MockProjectManagerAdapter
  └── R6. InMemoryCodeReviewAdapter
```

**Recommended order within Track 2**: Phase C first (filesystem only, no container
standup), then Phase A (Redis is operationally simpler than ES), then Phase B.

Within each phase, both adapters share the same container standup and Docker Compose
service entry — implement them together to avoid redundant infrastructure work.

---

## Completion Checklists

### Promotion checklist (Track 1 — file moves)

For each promotion (P1–P7), before closing the work:

- [ ] File moved to `adapters/secondary/` (or renamed, for P7)
- [ ] All imports in `adapters/testing/`, `SimulationAdapters`, and `AdapterResolver` updated to the new path
- [ ] Class wired into production bootstrap (`create_app()`) with the correct port interface
- [ ] Any test-helper methods commented with `# Test helper — do not call in production code`
- [ ] Class docstring updated to remove any "simulation-only" or "testing" language and note durability limits where applicable
- [ ] `adapters.md` table row updated (Location column changes from `adapters/testing/` to `adapters/secondary/`)
- [ ] `bootstrap-wiring.md` adapter list updated

For P8–P10 (already in the right location, bootstrap wiring verification only):

- [ ] Production bootstrap confirmed to wire the adapter (not simulation-only path)
- [ ] Any specific startup requirements verified (P7 stable key, P8 watchdog, P9 configure() call, P10 TTL cleanup)
- [ ] Docs updated to remove simulation-only caveats

### Replacement checklist (Track 2 — new implementations)

For each replacement (R1, R2, R3, R5, R7), before retiring the simulation adapter:

- [ ] New adapter fully implements the port interface (`IEventStore`, `IMetrics`, etc.)
- [ ] New adapter wired into production bootstrap
- [ ] Simulation bootstrap updated to use the new adapter pointing at a test container instance (test Redis, test ES, or temp directory)
- [ ] All existing simulation scenarios pass with the new adapter in place of the in-memory version
- [ ] `SimulationAdapters` dataclass field type annotation updated if the concrete type changes (port interface annotation stays the same)
- [ ] Old in-memory adapter file deleted from `adapters/testing/`
- [ ] `adapters.md` table row updated (old row replaced with new adapter row)
- [ ] `bootstrap-wiring.md` adapter list updated

---
