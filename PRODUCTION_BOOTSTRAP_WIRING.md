# Production Bootstrap Wiring - Phase 5 Integration

## Summary

Phase 5 of the intelligent branch resolution feature integrates `BranchResolutionAdapter` into the workspace preparation flow. The production bootstrap must wire this adapter to enable intelligent branch reuse in production environments.

## Current Status

### Simulation Environment ✅
- `MockBranchResolutionAdapter` is wired in `SimulationApplicationBootstrap` (line 1306)
- `WorkspaceRouter` receives the service via constructor injection
- Resolution happens in `prepare_workspace()` where `repo_path` is available
- Tests verify resolution and fallback behavior

### Production Environment ⏳ (Deferred)
- `BranchResolutionAdapter` exists and is functional
- No production bootstrap file currently instantiates `WorkspaceRouter`
- Wiring needed when production bootstrap is created

## Implementation Checklist for Production Bootstrap

When creating or updating the production bootstrap, follow this checklist:

### 1. Instantiate BranchResolutionAdapter
```python
from codetoreum.adapters.secondary.branch_resolution_adapter import BranchResolutionAdapter

branch_resolution_adapter = BranchResolutionAdapter(
    ticket_system=ticket_system_adapter,    # Already resolved
    version_control=vcs_adapter,             # Already resolved
    event_emitter=event_emitter_adapter,     # Already resolved
    min_confidence_threshold=0.7,            # Tunable
    cache_ttl_seconds=30,                    # Tunable
)
```

### 2. Wire into WorkspaceRouter
```python
workspace_router = WorkspaceRouter(
    vcs=vcs_adapter,
    container=container_adapter,
    event_store=event_store_adapter,
    config=workspace_router_config,
    branch_resolution_service=branch_resolution_adapter,  # ← Key addition
)
```

### 3. Verification Checklist
- [ ] `BranchResolutionAdapter` receives correct adapters for `ticket_system`, `version_control`, `event_emitter`
- [ ] `WorkspaceRouter` is instantiated with `branch_resolution_service` parameter
- [ ] Application servers and CLI commands use the wired bootstrap
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

## Related Files

- **Implementation**: `src/codetoreum/application/workspace_router.py`
- **Adapter**: `src/codetoreum/adapters/secondary/branch_resolution_adapter.py`
- **Simulation Bootstrap Example**: `src/codetoreum/infrastructure/simulation/bootstrap.py:1306`
- **Tests**: `tests/integration/application/test_workspace_router.py`
- **Architecture Design**: `documentation/01_design/`

## Next Steps

1. Create production bootstrap module (if not yet created)
2. Follow instantiation checklist above
3. Run existing tests to verify no regressions
4. Deploy to staging for validation
