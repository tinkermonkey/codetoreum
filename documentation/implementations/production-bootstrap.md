# Production Bootstrap Wiring

## Summary

This document covers production bootstrap configuration including:
- **Phase sequence**: Seven primary phases plus inserted sub-phases (4b, 4c, 4d, 5a-5e) for adapter wiring, coding-agent resolution, event persistence, and orchestrator startup
- **Workspace Router Setup**: Factory functions to wire `BranchResolutionAdapter` into the workspace preparation flow
- **Agent Workspace Base**: Directory setup and ownership requirements for agent container execution

**WorkspaceRouter and BranchResolutionAdapter are wired in production bootstrap** (Phase 4b and Phase 5 respectively). `BranchResolutionAdapter` is created in Phase 4b with the resilience-wrapped `ticket_system` and `version_control` adapters; `WorkspaceRouter` is instantiated in Phase 5 with all dependencies injected. The factories documented here reflect the production wiring.

## Phase Sequence Overview

`ProductionApplicationBootstrap.setup()` (in `src/codetoreum/infrastructure/bootstrap/production_bootstrap.py`) runs seven primary phases. The numbering preserves architectural history while new sub-phases were inserted during DEF-015 (D6/D7):

| Phase | Purpose |
|---|---|
| 1 | Infrastructure creation (event bus, adapter factory, resolver setup) |
| 2 | Adapter resolution (creates all production output adapters with credential validation) |
| 3 / 3b | Critical path enforcement (no mocks on critical slots); production `event_emitter` validation |
| 4 | Resilience decoration (rate limiter → circuit breaker → timeout → retry on critical adapters) |
| 4b | `BranchResolutionAdapter` constructed against resilience-wrapped `ticket_system` + `version_control` |
| **4c** | **`ICodingAgent` resolution** — production `ClaudeCodeAdapter` wired via `resolver.resolve_coding_agent(...)`. Constructs the production event-sourced `WorkItemService` first so the adapter, executor, and REST API share one instance (DEF-016 fix). |
| **4d** | **`CodingAgent*` event persistence bridge** — wildcard event bus subscriber appends each `CodingAgent*` event to `coding-agent-<execution_id>` in the event store. Without this, agent telemetry never reached the audit trail (DEF-018 fix). |
| 5 | Application service instantiation (11 services with production adapters) |
| 5a-5e | Agent scheduler startup, codetoreum board init, project bootstrap loading, MultiProjectOrchestrator startup |
| 6 | Input port creation (17 input port implementations) |
| 7 | FastAPI app creation |

### Phase 2 — Repair-cycle adapter resolution (Issue #940 Phase 1/2)

The repair-cycle slot is resolved during Phase 2 adapter resolution, choosing between mock (for simulation) or production (for real execution). The `repair_cycle="production"` configuration in `ProductionApplicationBootstrap.__init__()` ensures the real `ProductionRepairCycleAdapter` is wired end-to-end.

**Configuration in ProductionApplicationBootstrap**:
```python
adapter_config = AdapterSelectionConfig(
    repair_cycle="production",  # Non-mock path; resolver uses factory.create_repair_cycle()
    systemic_analysis="production",  # Used by repair cycle for failure analysis
    environment_repair="production",  # Used by repair cycle for env rebuild
    # ... other adapters
)
```

**Resolver path** (Phase 2, `AdapterResolver.resolve_repair_cycle()`):
- If `repair_cycle == "mock"`: Engine creates time-aware mock (for simulation only)
- If `repair_cycle == "production"`: Factory creates production adapter with full dependency injection

**Dependencies wired into ProductionRepairCycleAdapter**:
In `AdapterResolver.resolve_repair_cycle()` (line 670), the factory call mirrors what the resolver has already prepared:
```python
return self._factory.create_repair_cycle(
    adapter_name=self._config.repair_cycle,
    coding_agent_factory=self._create_coding_agent_factory(),  # Per-call factory for LLM agents
    systemic_analysis_service=self._resolved.get("systemic_analysis_service"),  # For failure analysis
    environment_repair_service=self._resolved.get("environment_repair_service"),  # For env rebuild
    invocation_defaults_resolver=self._create_invocation_defaults_resolver(),  # Per-workflow-step config
    checkpoint_store=self._resolved.get("checkpoint_store"),  # Phase 1 fix: wired here (non-None)
)
```
The `checkpoint_store` is resolved first (step 6, line 944) before repair_cycle is resolved (step 10, line 967).

**Key dependencies**:
- **checkpoint_store**: `IRepairCycleCheckpointStore` instance (in-memory or persistent). Phase 1 fix wired this as non-None during Phase 2; previously was missing, causing `AttributeError` on checkpoint save.
- **coding_agent_factory**: Callable factory returning fresh `ICodingAgent` instances (e.g., Claude Code).
- **systemic_analysis_service**: `ISystemicAnalysisService` for analyzing test failure patterns.
- **environment_repair_service**: `IEnvironmentRepairService` for infrastructure/environment recovery.
- **invocation_defaults_resolver**: Async callback `(work_item_id, agent_name) -> AgentInvocationConfig` to honor per-workflow-step agent configurations.

**Classification**: `repair_cycle` is in `NON_CRITICAL_SLOTS` (not CRITICAL_ADAPTER_SLOTS). Repair cycles are background/optional repair workflows, not on the critical path of work-item creation or execution. Promotion to CRITICAL_ADAPTER_SLOTS is a future decision (see Issue #940 Phase 3).

**Validation outcome** (Issue #940 Phase 2):
Tests in `test_repair_cycle_bootstrap_resolution.py` verify:
- `test_adapter_resolver_resolves_production_repair_cycle()`: Confirms AdapterResolver.resolve_repair_cycle() with `repair_cycle="production"` returns a ProductionRepairCycleAdapter (not mock) and verifies checkpoint_store is wired (non-None).
- `test_resolved_repair_cycle_adapter_executes_scenario()`: Confirms the resolver-created adapter can execute a repair-cycle scenario end-to-end with mocked coding agent, verifying checkpoint_store remains accessible after execute().
- `test_repair_cycle_is_non_critical_slot()`: Confirms repair_cycle is in NON_CRITICAL_SLOTS (background workflows, not critical path).
- The Phase 1 fix (checkpoint_store wiring) is validated via the resolver's cached resolution (`self._resolved.get("checkpoint_store")`) before passing to the adapter.

### Phase 4c — `ICodingAgent` resolution (DEF-015 D3/D4)

The `coding_agent` slot replaces the retired `llm_provider` slot (the `ILLMProvider` port deleted in D5). The slot is resolved *after* Phase 4 resilience decoration so the resilient `IContainer` is passed into the containerized strategy.

```python
# Phase 4c: Wire the new ICodingAgent slot
self._production_work_item_service = WorkItemService(
    event_store=self.adapters.event_store,
)
self.adapters.coding_agent = resolver.resolve_coding_agent(
    prompt_builder=DefaultPromptBuilder(),
    agent_repository=self.adapters.agent_repository,
    work_item_service=self._production_work_item_service,
    container=self.adapters.container,
)
```

`AdapterResolver.resolve_coding_agent()` constructs the production `ClaudeCodeAdapter` (from `adapters/secondary/claude_code/`) wrapped by `ResilientCodingAgentDecorator`. The adapter's internal strategies (`strategies/containerized.py`, `strategies/host.py`) consume the resilience-wrapped container.

**DEF-016 footnote**: the production `WorkItemService` is constructed here (not in Phase 5) so the same instance backs the coding-agent adapter, the executor, and the REST API. Passing the mock `work_item_service` slot would cause `WorkItemNotFoundError` at prompt-build time because the API-side store and the adapter-side store would diverge.

### Phase 4d — `CodingAgent*` event persistence bridge (DEF-015 D7 / DEF-018)

The new `ContainerizedClaudeStrategy` (and the other strategies) publish the 11 `CodingAgent*` events directly to the `EventBus` via `event_bus.publish(event)`. The bus dispatches to subscribers but does not itself write to the event store — no application service writes these events either, since the agent owns the telemetry. Phase 4d closes the audit gap with a small wildcard subscriber:

```python
# Phase 4d: Bridge CodingAgent* events → event store
_coding_agent_event_types: tuple[type, ...] = (
    CodingAgentApiRetryEvent, CodingAgentCompletedEvent,
    CodingAgentInvokedEvent, CodingAgentOtlpSpanEvent,
    CodingAgentRateLimitEvent, CodingAgentReadyEvent,
    CodingAgentTextOutputEvent, CodingAgentThinkingEvent,
    CodingAgentTokensUsedEvent, CodingAgentToolCallEvent,
    CodingAgentToolResultEvent,
)

async def _persist_coding_agent_event(event: Any) -> None:
    if not isinstance(event, _coding_agent_event_types):
        return
    stream_id = f"coding-agent-{event.execution_id}"
    try:
        await _coding_agent_event_store.append(stream_id, [event])
    except Exception:
        logger.exception(
            "Failed to persist CodingAgent event_type=%s execution_id=%s",
            event.event_type, event.execution_id,
        )

self.infrastructure.event_bus.subscribe(None, _persist_coding_agent_event)
```

Persistence errors are logged (`exc_info=True`) but never crash the publisher — observability must not break the agent execution loop. Per-execution telemetry is namespaced (`coding-agent-<execution_id>`) separately from `WorkItem` and `Execution` streams so audit queries can target either layer cleanly.

**D7 validation**: the second D7 bootstrap run wrote 67+ `CodingAgent*` events to ES across 9 distinct event types under stream `coding-agent-0fbd301f-d1fc-4327-ada8-09f1d3272a79`.

### Agent invocation schema (DEF-015 D6)

Production agent configs (in `bootstrap/rounds.json` and the ES round-trip used by `register_project.py`) now carry an `invocation` block instead of the retired `requires_docker` flag:

```json
{
  "agents": [
    {
      "name": "senior_software_engineer",
      "coding_agent": "claude-code",
      "invocation": {
        "mode": "containerized",
        "model": "claude-sonnet-4-6",
        "timeout_seconds": 3600,
        "mode_config": {
          "image": "codetoreum-agent:latest",
          "cpu_limit": "2",
          "memory_limit": "4g"
        }
      },
      "capabilities": ["code_generation", "debugging", "refactoring", "testing"],
      "makes_code_changes": true,
      "commit_policy": "on_success"
    }
  ]
}
```

The bootstrap loader validates `coding_agent` resolves to a registered adapter, then validates `invocation.mode` is in that adapter's `supported_invocation_modes()`. Errors at load, not at first execution. `ExecutionServiceAgentExecutor._build_invocation_options` reads `agent.invocation` directly — the `requires_docker` bridge retired in D6.

## Phase 5e — MultiProjectOrchestrator Startup

`ProductionApplicationBootstrap.setup()` starts the `MultiProjectOrchestrator` poll loop in Phase 5e using `asyncio.ensure_future` rather than `await` — this keeps `setup()` non-blocking while the poll loop runs as a background task. The loop continues until `teardown()` stops it via `await multi_project_orchestrator.stop()`.

Phase 5e runs after Phases 5a-5d (scheduler start, board init, project loading, executor wiring) so that all services are fully constructed before the first 30-second poll cycle fires.

See `bootstrap/ARCHITECTURE.md` §3 and §6 (INV-13) for the full orchestration model. See DEF-015 in §9 for the coding-agent redesign history.

---

## Agent Workspace Base Setup

### Purpose

`AGENT_WORKSPACE_BASE` is the directory on the host where orchestrator mounts project workspaces for agent containers. All agent executions receive isolated snapshots of repositories as subdirectories under this base path.

### Configuration

**Environment Variable**: `AGENT_WORKSPACE_BASE`
- **Default**: `/tmp/codetoreum/workspaces`
- **Ownership**: Must be owned by UID 1000 (the `orchestrator` user)
- **Permissions**: Must be writable by UID 1000

### Setup Steps

1. **Create the directory** (during orchestrator startup or deployment):
   ```bash
   mkdir -p /tmp/codetoreum/workspaces
   ```

2. **Set correct ownership** (UID 1000, GID 1000):
   ```bash
   # If running orchestrator as root (not recommended):
   chown 1000:1000 /tmp/codetoreum/workspaces
   chmod 755 /tmp/codetoreum/workspaces

   # If running orchestrator as unprivileged user:
   # Let the orchestrator create it with its own user ownership
   ```

3. **Verify writability** (during application bootstrap):
   ```python
   from pathlib import Path
   import os

   agent_workspace_base = os.environ.get("AGENT_WORKSPACE_BASE", "/tmp/codetoreum/workspaces")
   Path(agent_workspace_base).mkdir(parents=True, exist_ok=True)

   # Verify it's writable
   test_file = Path(agent_workspace_base) / ".codetoreum_write_test"
   test_file.write_text("test")
   test_file.unlink()
   ```

### Docker Compose Integration

The orchestrator Dockerfile creates `/tmp/codetoreum/workspaces` with correct ownership:

```dockerfile
RUN mkdir -p /tmp/codetoreum/workspaces && \
    chown -R orchestrator:orchestrator /tmp/codetoreum
```

When using Docker Compose, the volume is created automatically. For host-based execution, you must create the directory manually with correct permissions.

### Ownership Invariant

**Critical**: Agent containers run as UID 1000. Files written to `AGENT_WORKSPACE_BASE` by agents must be readable and writable by the orchestrator (also UID 1000).

- ❌ Wrong: `AGENT_WORKSPACE_BASE` owned by root (UID 0) → agents cannot write to it
- ❌ Wrong: `AGENT_WORKSPACE_BASE` owned by UID 1001 → orchestrator cannot read agent output
- ✅ Correct: `AGENT_WORKSPACE_BASE` owned by UID 1000 → agents write files owned by 1000, orchestrator reads them without chown

This invariant ensures:
1. Agent containers can write their workspace snapshots
2. Orchestrator can immediately read and process agent output
3. No `chown` operations needed after agent execution (faster cleanup)

### Pre-Launch Verification

`DockerContainerAdapter.create()` runs a pre-launch write verification (by default, enabled via `DockerConfig.verify_workspace_writable=True`) before spending LLM API tokens. This verification:

1. Creates a temporary Alpine container with identical volume config
2. Attempts to write a test file to the mount point
3. Retries 3 times with 2-second delays (for transient Docker hiccups)
4. Fails fast with actionable error if all attempts fail

**Acceptance criteria**: Smoke test step 2 explicitly calls this verification and logs the result.

## Current Status

### Simulation Environment ✅ (Complete)
- `MockBranchResolutionAdapter` is wired in `SimulationApplicationBootstrap` (line 1306)
- `WorkspaceRouter` receives the service via constructor injection
- Resolution happens in `prepare_workspace()` where `repo_path` is available
- Tests verify resolution and fallback behavior

### Production Factories ✅ (Ready)
- `BranchResolutionAdapter` factory exists in `adapters/primary/factories/production.py:create_branch_resolution_adapter()`
- `create_workspace_router_with_branch_resolution()` factory wires adapter into WorkspaceRouter
- Unit tests verify factory behavior in `tests/unit/adapters/primary/factories/test_production.py`
- Factories are exported from `adapters/primary/factories/__init__.py` for use in production bootstrap

### Production Integration ✅ (Complete)
- `BranchResolutionAdapter` is created in Phase 4b of `ProductionApplicationBootstrap` with resilience-wrapped `ticket_system` and `version_control` adapters
- `WorkspaceRouter` is instantiated in Phase 5 with `BranchResolutionAdapter` injected as `branch_resolution_service`
- `WorkspaceRouter` is passed to `ExecutionServiceAgentExecutor` for agent workspace preparation

## Implementation Checklist for Production Bootstrap

### Factories Available ✅

The following factories are now available in `codetoreum.adapters.primary.factories` for use in production bootstrap:

#### Option A: Two-Step Instantiation (Fine-Grained Control)
```python
from codetoreum.adapters.primary.factories import (
    create_branch_resolution_adapter,
    create_workspace_router_with_branch_resolution,
)

# Step 1: Create adapter
branch_resolution_adapter = create_branch_resolution_adapter(
    ticket_system=ticket_system_adapter,    # Already resolved
    version_control=vcs_adapter,             # Already resolved
    event_emitter=event_emitter_adapter,     # Already resolved
    min_confidence_threshold=0.7,            # Tunable
    cache_ttl_seconds=30,                    # Tunable
)

# Step 2: Wire into router
workspace_router = create_workspace_router_with_branch_resolution(
    version_control=vcs_adapter,
    container=container_adapter,
    event_store=event_store_adapter,
    branch_resolution_service=branch_resolution_adapter,
)
```


### Production Bootstrap Integration Checklist

When integrating into your production bootstrap:

- [ ] Import factory functions from `codetoreum.adapters.primary.factories`
- [ ] Ensure `ticket_system`, `version_control`, `container`, `event_store`, and `event_emitter` adapters are fully initialized before factory call
- [ ] Call factory before agent execution begins (during application startup)
- [ ] Pass returned `workspace_router` to application services (ExecutionService, ExecutionServiceAgentExecutor, etc.)
- [ ] Verify branch resolution events are being emitted (check logs for "Instantiated BranchResolutionAdapter" and "Wired BranchResolutionAdapter")
- [ ] Existing tests for other components continue to pass

## Technical Details

### Architecture
- **Resolution happens in**: `WorkspaceRouter.prepare_workspace()` (not `route_workspace()`)
- **Reason**: Production `BranchResolutionAdapter` requires `repo_path` to call version control service
- **Repo path availability**: Only in `prepare_workspace()`, not in `route_workspace()`

### Adapter Dependencies
```
BranchResolutionAdapter requires:
  ├── ITicketSystem (for querying parent/sibling relationships)
  ├── IVersionControlService (for listing branches)
  ├── IEventEmitter (for emitting resolution events)
  └── Configuration (thresholds, cache TTL)
```

### Configuration Options
- `min_confidence_threshold=0.7` - Fuzzy match minimum confidence (0.0-1.0)
- `cache_ttl_seconds=30` - Cache duration for branch list queries

## Error Handling

The `WorkspaceRouter` includes fallback logic:
- If `branch_resolution_service` is `None` → uses default branch logic (backward-compatible)
- If resolution service raises exception → logs warning (ERROR_ID: ERR_BRANCH_RESOLUTION_FALLBACK) and falls back to default logic
- System never fails due to resolution service issues

## Integration in Production Bootstrap

When integrating branch resolution into production bootstrap (e.g., in `fastapi_app.py`'s `create_app()`):

```python
from codetoreum.adapters.primary.factories import (
    create_branch_resolution_adapter,
    create_workspace_router_with_branch_resolution,
)

# Assuming you have already created the output adapters:
# - ticket_system_adapter: GitHub ticket system implementation
# - vcs_adapter: GitHub/Git version control implementation
# - container_adapter: Docker container runtime
# - event_store_adapter: Redis or persistent event store
# - event_emitter_adapter: Event publishing service

# Step 1: Create branch resolution adapter
branch_resolution_adapter = create_branch_resolution_adapter(
    ticket_system=ticket_system_adapter,
    version_control=vcs_adapter,
    event_emitter=event_emitter_adapter,
)

# Step 2: Create workspace router with branch resolution wired in
workspace_router = create_workspace_router_with_branch_resolution(
    version_control=vcs_adapter,
    container=container_adapter,
    event_store=event_store_adapter,
    branch_resolution_service=branch_resolution_adapter,
)

# Now pass workspace_router to application services that need it:
# - ExecutionService
# - ExecutionServiceAgentExecutor
# - Any other service that prepares workspaces for agent execution

execution_service = ExecutionService(
    workspace_router=workspace_router,
    # ... other dependencies
)
```

**Key Integration Points:**
1. Call factory **after** all output adapters are initialized
2. Call factory **before** agent execution services are created
3. Pass the returned `workspace_router` to all services that call `prepare_workspace()` or `finalize_workspace()`

## Related Files

- **Implementation**: `src/codetoreum/application/workspace_router.py`
- **Adapter**: `src/codetoreum/adapters/secondary/branch_resolution_adapter.py`
- **Simulation Bootstrap Example**: `src/codetoreum/infrastructure/simulation/bootstrap.py:1306`
- **Tests**: `tests/integration/application/test_workspace_router.py`
- **Architecture Design**: `documentation/architecture/`

## Next Steps

1. ✅ **Factories & Tests** - Production bootstrap factories are available with unit tests in `adapters/primary/factories/production.py` and `tests/unit/adapters/primary/factories/test_production.py`

2. **Integration Validation** - Verify the wired production path:
   - Confirm branch resolution events are emitted in server logs (`Instantiated BranchResolutionAdapter`, `Wired BranchResolutionAdapter`)
   - Verify intelligent branch reuse works for agent executions
   - Verify fallback logic activates correctly when branch resolution is unavailable
