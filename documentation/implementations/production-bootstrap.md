# Production Bootstrap Wiring

## Summary

This document provides factory functions to wire `BranchResolutionAdapter` into the workspace preparation flow. These factories are ready for integration into a production bootstrap path once it exists.

**Important Note**: A production bootstrap entry point for `WorkspaceRouter` does not yet exist in `fastapi_app.py`. Currently, only the simulation bootstrap (`infrastructure/simulation/bootstrap.py`) instantiates `WorkspaceRouter`. The factories in this document are designed to be called from production startup code once such an entry point is created.

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

### Production Integration 🔄 (Blocked - No Entry Point)
- **Blocker**: No production bootstrap entry point exists for instantiating `WorkspaceRouter`
- The `fastapi_app.py:create_app()` function does not currently instantiate `WorkspaceRouter`
- Only the simulation bootstrap instantiates `WorkspaceRouter` (simulation/bootstrap.py:1602)
- **Next step**: Create production bootstrap entry point (e.g., in CLI startup or app initialization), then wire factories

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

2. **Production Entry Point** (Future Work) - Create production bootstrap entry point:
   - Determine where `WorkspaceRouter` should be instantiated in production (CLI startup, app initialization, etc.)
   - Call `create_branch_resolution_adapter()` and `create_workspace_router_with_branch_resolution()` factories during bootstrap
   - Inject `WorkspaceRouter` into `ExecutionServiceAgentExecutor` (per simulation pattern)
   - This completes the acceptance criterion: "Integration into workflow startup before agent execution begins"

3. **Integration Validation** - After production bootstrap is created:
   - Verify branch resolution events are emitted correctly
   - Verify intelligent branch reuse works for agent executions
   - Verify fallback logic activates correctly when branch resolution is unavailable
