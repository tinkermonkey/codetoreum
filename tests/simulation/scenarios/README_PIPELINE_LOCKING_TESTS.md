# Pipeline Locking Comprehensive Test Suite

This document describes the comprehensive test suite for the pipeline locking system, which includes both unit tests and simulation tests.

## Overview

The pipeline locking system ensures that workflow pipeline stages process work items sequentially, preventing concurrent modifications and ensuring data consistency. The test suite verifies:

- **Lock Lifecycle**: Acquisition, holding, and release
- **Queue Management**: FIFO with position-based ordering
- **Concurrency**: Multiple items competing for single lock
- **Stale Lock Recovery**: Automatic detection and recovery
- **Deadlock Prevention**: Queue-based design prevents deadlocks
- **Event Sourcing**: All state changes emit domain events
- **Edge Cases**: Input validation, empty states, duplicates

## Test Structure

```
tests/
├── unit/
│   └── application/
│       └── test_pipeline_lock_service.py (26 tests)
│   └── adapters/secondary/
│       └── test_in_memory_lock_service_events.py (686+ lines)
│
└── simulation/scenarios/
    ├── scenario_10_pipeline_locking.py (15 tests, 750+ lines)
    ├── SCENARIO_10_DOCUMENTATION.md
    └── README_PIPELINE_LOCKING_TESTS.md (this file)
```

## Test Categories

### Unit Tests (26 tests)
**Location**: `tests/unit/application/test_pipeline_lock_service.py`

**Coverage**:
- Lock acquisition in various states
- Queue ordering by board position
- Lock release and queue advancement
- Queue position updates (human reordering)
- Queue state queries
- Orphaned lock holder scenarios
- Multiple projects and boards
- Boundary conditions

**Run**:
```bash
python -m pytest tests/unit/application/test_pipeline_lock_service.py -v
```

### Event Emission Tests (686+ lines)
**Location**: `tests/unit/adapters/secondary/test_in_memory_lock_service_events.py`

**Coverage**:
- Lock acquired event emission
- Lock released event emission
- Work item queued event emission
- Stale lock detected event emission
- Event format and payload validation
- Complete lifecycle event sequences
- Event source and timestamp validation

**Run**:
```bash
python -m pytest tests/unit/adapters/secondary/test_in_memory_lock_service_events.py -v
```

### Simulation Tests (15 tests, 750+ lines)
**Location**: `tests/simulation/scenarios/scenario_10_pipeline_locking.py`

**Coverage**:
1. Basic lock acquisition and release
2. Lock queuing when held
3. Queue position-based ordering
4. Lock release advances queue
5. Concurrent lock contention (10 items)
6. Stale lock detection and recovery
7. Queue position updates (reordering)
8. Multiple independent boards
9. Duplicate holder request
10. Release by non-holder (error handling)
11. Empty queue after release
12. Event bus integration
13. Deadlock prevention guarantee
14. Stress test (100 items)
15. Input validation

**Run**:
```bash
python -m pytest tests/simulation/scenarios/scenario_10_pipeline_locking.py -v
```

## Key Test Scenarios

### Scenario 1: Lock Acquisition
```python
# Item-1 acquires lock
await service.try_acquire_lock("proj-1", "board-1", "item-1", position=0)
# Status: ACQUIRED, queue_length: 0
```

### Scenario 2: Queue Under Contention
```python
# Item-2 tries to acquire (held by item-1)
await service.try_acquire_lock("proj-1", "board-1", "item-2", position=1)
# Status: QUEUED, queue_position: 0, queue_length: 1
```

### Scenario 3: Position-Based Ordering
```python
# Items arrive in order: position 5, then 2, then 8
# Queue is automatically sorted: [2, 5, 8]
# Item with position 2 (topmost) has highest priority
```

### Scenario 4: Lock Release
```python
# Item-1 releases lock
await service.release_lock("proj-1", "board-1", "item-1")
# Result: next_work_item_id = "item-2", queue_length = 1
# Item-2 now holds the lock
```

### Scenario 5: Stale Lock Recovery
```python
# Lock held for > threshold (default 2 hours, 1 second in test)
# Item-2 tries to acquire
result = await service.try_acquire_lock("proj-1", "board-1", "item-2", position=1)
# Status: ACQUIRED (stale lock detected and recovered)
```

### Scenario 6: Deadlock Prevention
```python
# A holds lock → B queued → C queued
# A releases → B gets lock
# B releases → C gets lock
# GUARANTEED: No item waits indefinitely (deadlock-free)
```

## Test Statistics

| Metric | Value |
|--------|-------|
| **Total Unit Tests** | 26 |
| **Total Event Tests** | 686+ lines |
| **Total Simulation Tests** | 15 |
| **Combined Test Lines** | 750+ |
| **Test Execution Time** | <1 second |
| **Coverage Areas** | 8 categories |

## Running Tests

### Run All Pipeline Locking Tests
```bash
python -m pytest tests/unit/application/test_pipeline_lock_service.py \
                  tests/unit/adapters/secondary/test_in_memory_lock_service_events.py \
                  tests/simulation/scenarios/scenario_10_pipeline_locking.py -v
```

### Run Only Simulation Tests
```bash
python -m pytest tests/simulation/scenarios/scenario_10_pipeline_locking.py -v
```

### Run with Coverage Report
```bash
python -m pytest tests/simulation/scenarios/scenario_10_pipeline_locking.py \
  --cov=codetoreum.adapters.secondary.in_memory_queue_lock_service \
  --cov-report=html
```

### Run Specific Test
```bash
python -m pytest tests/simulation/scenarios/scenario_10_pipeline_locking.py::test_scenario_10_concurrent_lock_contention -v
```

### Run as Standalone Script
```bash
python tests/simulation/scenarios/scenario_10_pipeline_locking.py
```

## Design Properties Verified

### 1. Mutual Exclusion
- ✓ Only one item can hold lock at a time
- ✓ Lock must be released before next acquisition
- ✓ No concurrent holders

### 2. FIFO Ordering
- ✓ Queue maintains position-based order
- ✓ Topmost items (lowest position) get priority
- ✓ Items progress in predictable order

### 3. Deadlock-Free Guarantee
- ✓ Queue ensures lock always transfers
- ✓ No circular waiting possible
- ✓ Every item eventually acquires lock

### 4. Board Isolation
- ✓ Different boards have independent locks
- ✓ Operations on one board don't affect others
- ✓ Multiple locks can be held simultaneously (different boards)

### 5. Stale Lock Recovery
- ✓ Automatic detection of hung locks
- ✓ Configurable timeout threshold
- ✓ Waiting items automatically take lock

### 6. Event Sourcing
- ✓ All state changes emit events
- ✓ Complete audit trail maintained
- ✓ Event replay enables debugging

### 7. Thread Safety
- ✓ Concurrent access protected
- ✓ No race conditions
- ✓ Consistent state under contention

### 8. Input Validation
- ✓ Empty parameters rejected
- ✓ Negative positions rejected
- ✓ Non-holder releases rejected

## Test Coverage Matrix

| Feature | Unit | Events | Simulation |
|---------|------|--------|-----------|
| Acquisition | ✓ | ✓ | ✓ |
| Queuing | ✓ | ✓ | ✓ |
| Position Ordering | ✓ | ✓ | ✓ |
| Release | ✓ | ✓ | ✓ |
| Concurrency | ✓ | | ✓ |
| Stale Recovery | ✓ | ✓ | ✓ |
| Reordering | ✓ | | ✓ |
| Board Isolation | ✓ | | ✓ |
| Event Emission | | ✓ | ✓ |
| Deadlock Prevention | | | ✓ |
| Stress Testing | | | ✓ |
| Input Validation | | | ✓ |

## Implementation Details

### Service Classes

**InMemoryLockService**: Application-level service
- Location: `src/codetoreum/adapters/secondary/in_memory_queue_lock_service.py`
- Methods:
  - `try_acquire_lock()` → LockAcquisitionResult
  - `release_lock()` → LockReleaseResult
  - `get_queue_state()` → PipelineQueueState
  - `update_queue_positions()` → None
  - `set_lock_acquired_at()` → None (test helper)

**Domain Events**:
- `PipelineLockAcquiredEvent` - Lock acquired by item
- `PipelineLockReleasedEvent` - Lock released, next granted
- `WorkItemQueuedEvent` - Item added to queue
- `LockStaleDetectedEvent` - Stale lock detected

**Data Structures**:
- `LockStatus` enum: ACQUIRED, QUEUED, ALREADY_HELD
- `LockAcquisitionResult`: status, work_item_id, queue_position, queue_length
- `LockReleaseResult`: released_work_item_id, next_work_item_id, queue_length_after_release
- `PipelineQueueState`: board_id, project_id, lock_holder, lock_acquired_at, queue
- `QueueEntry`: work_item_id, board_position, enqueued_at

## Key Insights

1. **Position-Based Ordering**: Unlike timestamps, board position provides user-visible priority (topmost items are next)

2. **Stale Lock Threshold**: Default 2 hours allows for long-running operations without false positives

3. **Thread Safety**: Internal `threading.Lock()` protects all state modifications

4. **Queue Efficiency**: O(n log n) sorting acceptable for typical queue sizes (< 50 items)

5. **Event Completeness**: Every state change generates event for audit trail

6. **Deadlock-Free Design**: Queue-based waiting is fundamentally deadlock-free because:
   - Only one holder at a time
   - Lock always transfers to waiting item
   - No circular dependencies possible

## Future Enhancements

1. **Distributed Locking**: Redis-based implementation for multi-instance deployments

2. **Lock Timeout**: Automatic forced release after timeout (currently manual)

3. **Lock Monitoring**: Metrics and alerts for long-held locks

4. **Queue Prioritization**: Custom priority functions beyond board position

5. **Lock Preemption**: Ability to interrupt long-running items

6. **Performance Optimization**: Lock-free queue data structures

## Related Documentation

- **Design Document**: `documentation/01_design/ports/output/pipeline_lock_service_design.md`
- **Port Interface**: `src/codetoreum/ports/output/pipeline_lock_service.py`
- **Domain Events**: `src/codetoreum/domain/events/lock_events.py`
- **Implementation**: `src/codetoreum/adapters/secondary/in_memory_queue_lock_service.py`

## Troubleshooting

### Test Failures

**Issue**: Stale lock test timing out
- **Solution**: Ensure system clock is accurate, check `stale_threshold_seconds` parameter

**Issue**: Deadlock prevention test failing
- **Solution**: Verify queue sorting algorithm is correct, check position comparison logic

**Issue**: Event emission test failing
- **Solution**: Ensure mock event bus is properly configured with AsyncMock

### Performance

**Slow test execution**:
- Check for blocking I/O in test setup
- Verify asyncio event loop is properly configured
- Use `--durations=10` flag to identify slow tests

## Contributing

When adding new tests:

1. **Unit Tests**: Add to `test_pipeline_lock_service.py` for specific feature coverage
2. **Simulation Tests**: Add to `scenario_10_pipeline_locking.py` for integration scenarios
3. **Documentation**: Update this README and SCENARIO_10_DOCUMENTATION.md
4. **Coverage**: Ensure new scenarios cover one specific aspect thoroughly
5. **Performance**: Keep tests fast (<100ms per test)

## Contact & Support

For questions about the pipeline locking system or tests:
- Review design documentation in `documentation/01_design/`
- Check existing test cases for usage examples
- Refer to domain event definitions for event structure
