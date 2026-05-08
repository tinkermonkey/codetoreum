# Coverage Analysis - Phase 5 Revision 1

**Date**: 2026-05-01
**Test Run**: 5,893 passed, 2 failed, 78 skipped (1,343.74 seconds)

## Per-Layer Coverage Assessment

### Domain Layer
- **Coverage**: 86.24% (5,333 / 6,184 lines)
- **Status**: ❌ **FAIL** (target: ≥100%)
- **Missing Lines**: 851
- **Files Below 100%**: 28 files

**Uncovered Files (sorted by coverage)**:
1. `execution_events.py`: 70.00% (9 missing)
2. `pr_review_cycle_events.py`: 71.13% (136 missing)
3. `repair_cycle_events.py`: 71.82% (239 missing)
4. `review_cycle_events.py`: 74.87% (49 missing)
5. `user.py`: 75.74% (33 missing)
6. `board_workflow_template.py`: 75.97% (31 missing)
7. `lock_events.py`: 76.40% (42 missing)
8. `pr_review_cycle_types.py`: 76.43% (62 missing)
9. `discussion_events.py`: 79.46% (46 missing)
10. `queue_events.py`: 81.82% (20 missing)
11. And 18 more files between 82-98% coverage

### Application Layer
- **Coverage**: 78.67% (3,976 / 5,054 lines)
- **Status**: ❌ **FAIL** (target: ≥90%)
- **Missing Lines**: 1,078
- **Files Below 90%**: 18 files

**Critical Coverage Gaps** (lowest 5):
1. `metrics_service.py`: 39.81% (186 missing)
2. `execution_service.py`: 48.90% (185 missing)
3. `workflow_orchestrator.py`: 68.71% (179 missing)
4. `context_builder.py`: 70.59% (45 missing)
5. `review_service.py`: 75.57% (32 missing)

**Remaining Files Below 90%**:
- `pipeline_manager.py`: 76.65% (53 missing)
- `agent_execution_recovery_service.py`: 77.65% (19 missing)
- `conversational_loop_orchestrator.py`: 78.63% (50 missing)
- `event_handlers/board_event_handler.py`: 78.81% (57 missing)
- `board_polling_service.py`: 82.08% (19 missing)
- `workflow_run_query_service.py`: 83.28% (48 missing)
- `configuration_service.py`: 83.38% (60 missing)
- `event_bus_wiring.py`: 86.96% (15 missing)
- `workspace_router.py`: 87.17% (24 missing)
- `multi_project_orchestrator.py`: 88.39% (18 missing)
- `authentication_service.py`: 88.60% (22 missing)
- `event_handlers/branch_resolution_event_handler.py`: 89.47% (4 missing)
- `event_handlers/pr_review_cycle_dispatch_handler.py`: 89.53% (9 missing)

### Overall Project Coverage
- **Coverage**: 70.32% (44,367 lines, 13,170 missing)
- **Status**: ❌ **FAIL** (target: ≥80%)
- **Gap to Target**: 1,179 lines to reach 80%

## Test Failures (2 Pre-existing)

**Location**: `tests/simulation/test_planning_design_review_cycle_e2e.py`

### Failure 1: `test_issues_found_path`
```
AssertionError: No PR review cycle events found in event store
```
**Root Cause**: PR review cycle event handler integration incomplete. The test expects `PRReviewCycleStartedEvent` but none is emitted.
**Pre-existing**: Yes (not introduced by Phase 5 changes)

### Failure 2: `test_approved_path`
```
Similar event handler integration issue
```
**Pre-existing**: Yes (not introduced by Phase 5 changes)

## Recommendations

### Gap Issue: Domain Layer Coverage (to file)
**Title**: Coverage Gap: Domain Layer below 100%
**Description**:
- Current: 86.24% (851 lines missing)
- Target: 100%
- Largest gaps: repair_cycle_events.py (239 missing), pr_review_cycle_events.py (136 missing)

### Gap Issue: Application Layer Coverage (to file)
**Title**: Coverage Gap: Application Layer below 90%
**Description**:
- Current: 78.67% (1,078 lines missing)
- Target: 90%
- Critical gaps: metrics_service.py (186 missing), execution_service.py (185 missing), workflow_orchestrator.py (179 missing)

### Fix for Test Failures
**Issue**: PR review cycle event handler not fully integrated
**Action**: Verify handler registration in `_register_pr_review_cycle_handler()`

## Configuration

✅ **fail_under = 80** is configured in `pyproject.toml`

---

**Generated**: 2026-05-01
**Coverage Data**: pytest --cov=src/codetoreum --cov-report=term-missing
