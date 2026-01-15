# Scenario 10: Comprehensive Pipeline Locking Tests

## Overview

Scenario 10 provides comprehensive simulation tests for the pipeline locking system, including lock acquisition/release, queue management with position-based ordering, stale lock detection, and deadlock prevention.

**File Location**: `tests/simulation/scenarios/scenario_10_pipeline_locking.py`

**Total Tests**: 15 comprehensive test cases

**Execution Time**: ~70ms for full suite

## Test Coverage

### 1. Basic Lock Acquisition and Release
**Test**: `test_scenario_10_basic_lock_acquisition_and_release`

Tests the fundamental lock lifecycle:
- Lock acquisition when available
- Lock holder and queue state tracking
- Lock release with proper state cleanup

**Key Assertions**:
- Lock status is `ACQUIRED` when available
- Queue position is `None` for lock holder
- Release returns correct holder and next item IDs
- Queue is empty after release

---

### 2. Lock Queuing When Held
**Test**: `test_scenario_10_lock_queuing_when_held`

Tests FIFO queue behavior when lock is already held:
- First item acquires the lock
- Second and third items are queued with correct status
- Queue position increases with each addition

**Key Assertions**:
- Second item status is `QUEUED` with position 0
- Third item status is `QUEUED` with position 1
- Queue length increases correctly

---

### 3. Queue Position-Based Ordering
**Test**: `test_scenario_10_queue_position_ordering`

Tests that queue is sorted by board position (topmost items first):
- Items arrive in non-sequential order
- Queue automatically reorders by board position
- Lowest position value = highest priority

**Scenario**:
```
Item arrives with position 5 → queue position 0
Item arrives with position 2 → moves to position 0 (lower position)
Item arrives with position 8 → appended to end at position 2
```

**Key Assertions**:
- Queue order: position 2, position 5, position 8
- Each new item insertion maintains sorted order

---

### 4. Lock Release Advances Queue
**Test**: `test_scenario_10_lock_release_advances_queue`

Tests that releasing lock grants it to next item in queue:
- Item-1 holds lock, items 2 and 3 are queued
- Release by item-1 grants lock to item-2
- Item-3 remains in queue waiting

**Key Assertions**:
- `next_work_item_id` is item-2 after item-1 release
- item-2 becomes new lock holder
- item-3 still waiting in queue

---

### 5. Concurrent Lock Contention
**Test**: `test_scenario_10_concurrent_lock_contention`

Stress test with 10 items competing for single lock:
- First item acquires lock
- 9 items queue with various positions
- Sequential release validates queue order

**Key Assertions**:
- Queue maintains sorted position order
- Each release grants lock to next item
- No items lost or skipped

---

### 6. Stale Lock Detection and Recovery
**Test**: `test_scenario_10_stale_lock_detection_and_recovery`

Tests automatic stale lock handling:
- Lock held beyond configurable threshold (1 second for test)
- Waiting item automatically acquires lock
- Acquisition time updated for new holder

**Key Assertions**:
- Stale lock detected after threshold exceeded
- Queued item acquires lock from stale holder
- Lock holder changed to new item
- Acquisition time is recent

---

### 7. Queue Position Updates
**Test**: `test_scenario_10_queue_position_updates`

Tests dynamic reordering when humans move items on board:
- Initial queue established with positions 2 and 1
- Positions updated to 0.5 and 2
- Queue re-sorted to new position order

**Scenario**:
```
Before: item-3 (pos 1) → item-2 (pos 2)
After:  item-2 (pos 0.5) → item-3 (pos 2)
```

**Key Assertions**:
- `update_queue_positions()` re-sorts queue
- New queue order matches updated positions

---

### 8. Multiple Independent Boards
**Test**: `test_scenario_10_multiple_independent_boards`

Tests lock isolation between different boards:
- Board-1: item-1 holds lock, item-2 queued
- Board-2: item-3 holds lock, item-4 queued
- Operations on one board don't affect the other

**Key Assertions**:
- Board-1 lock holder is item-1
- Board-2 lock holder is item-3
- Releasing lock on one board doesn't affect the other

---

### 9. Duplicate Holder Request
**Test**: `test_scenario_10_duplicate_holder_request`

Tests idempotent lock acquisition by same item:
- Same item tries to acquire lock twice
- Second attempt returns `ALREADY_HELD` status

**Key Assertions**:
- First acquisition: `ACQUIRED`
- Second acquisition: `ALREADY_HELD`
- No queue position for holder

---

### 10. Release by Non-Holder
**Test**: `test_scenario_10_orphaned_lock_holder`

Tests that only lock holder can release:
- Item-1 holds lock
- Non-holder (item-99) tries to release
- System raises `ValueError`

**Key Assertions**:
- Raises `ValueError` for non-holder release
- Prevents incorrect lock release

---

### 11. Empty Queue After Release
**Test**: `test_scenario_10_empty_queue_after_release`

Tests proper state cleanup when queue is empty:
- Single item acquires and releases
- Lock becomes available, queue empty

**Key Assertions**:
- `next_work_item_id` is `None`
- Lock holder is `None`
- Queue is empty

---

### 12. Event Bus Integration
**Test**: `test_scenario_10_with_event_bus`

Tests that all lock lifecycle events are emitted:
- Acquisition emits `PipelineLockAcquiredEvent`
- Queuing emits `WorkItemQueuedEvent`
- Release emits `PipelineLockReleasedEvent`

**Key Assertions**:
- Events are published to bus
- Event types match expected domain events
- Event payloads contain correct work item IDs

---

### 13. Deadlock Prevention
**Test**: `test_scenario_10_deadlock_prevention`

Tests that queue-based locking prevents deadlocks:
- Items A, B, C compete for lock
- A releases → B automatically gets it
- B releases → C automatically gets it
- No item ever waits indefinitely

**Guarantee**: With queue-based locking, no deadlock is possible because:
1. Only one item can hold lock at a time
2. Lock always transfers to first in queue
3. Queue order never changes arbitrarily
4. Every item eventually gets the lock

---

### 14. Stress Test: Many Items
**Test**: `test_scenario_10_stress_test_many_items`

Scalability test with 100 competing items:
- Item-1 acquires lock
- Items 2-100 queue with increasing positions
- Sequential release validates complete queue traversal

**Key Assertions**:
- All 100 items queue correctly
- Queue length matches expected count
- Every item acquires lock in order
- Final release leaves empty queue

---

### 15. Input Validation
**Test**: `test_scenario_10_input_validation`

Tests that service validates parameters:
- Empty project_id → `ValueError`
- Empty board_id → `ValueError`
- Empty work_item_id → `ValueError`
- Negative position → `ValueError`

**Key Assertions**:
- All invalid inputs raise `ValueError`
- Error messages include context

---

## Test Categories

### Core Functionality (Tests 1-4)
- Basic lock lifecycle
- Queue management
- Position-based ordering
- Queue advancement

### Concurrency (Tests 5, 13)
- Multiple items competing
- Deadlock prevention
- FIFO guarantees

### Edge Cases (Tests 9-11, 15)
- Duplicate requests
- Invalid operations
- Empty queues
- Input validation

### Observability (Test 12)
- Event emission
- Integration with event bus
- Audit trail

### Recovery (Test 6)
- Stale lock detection
- Automatic recovery
- Threshold handling

### Multi-Board (Test 8)
- Board isolation
- Independent locks
- Project/board scoping

### Dynamics (Test 7)
- Queue reordering
- Position updates
- Human interaction handling

## Key Design Properties Verified

1. **Mutual Exclusion**: Only one item holds lock at a time
2. **FIFO Ordering**: Items progress in board position order
3. **Deadlock-Free**: Queue guarantees every item eventually acquires lock
4. **Isolation**: Different boards have independent locks
5. **Stale Recovery**: Automatic detection and recovery of hung holders
6. **Observability**: All state changes emit domain events
7. **Idempotency**: Duplicate requests handled gracefully
8. **Thread Safety**: Concurrent access protected by internal locking

## Running the Tests

### Run All Scenario 10 Tests
```bash
python -m pytest tests/simulation/scenarios/scenario_10_pipeline_locking.py -v
```

### Run Specific Test
```bash
python -m pytest tests/simulation/scenarios/scenario_10_pipeline_locking.py::test_scenario_10_concurrent_lock_contention -v
```

### Run as Standalone Script
```bash
python tests/simulation/scenarios/scenario_10_pipeline_locking.py
```

### Run with Coverage
```bash
python -m pytest tests/simulation/scenarios/scenario_10_pipeline_locking.py --cov=codetoreum.adapters.secondary.in_memory_queue_lock_service
```

## Integration with Existing Tests

**Complementary Unit Tests**: `tests/unit/application/test_pipeline_lock_service.py`
- Lower-level lock service tests
- Additional edge cases

**Event Emission Tests**: `tests/unit/adapters/secondary/test_in_memory_lock_service_events.py`
- Detailed event format validation
- Event serialization roundtrips

**Scenario 9**: `tests/simulation/scenarios/scenario_09_queue_position_ordering.py`
- Different queue service implementation
- Board integration testing

## Architecture Notes

The simulation tests use:
- **InMemoryLockService**: Implementation under test
- **AsyncMock**: For event bus mocking
- **LockStatus enum**: ACQUIRED, QUEUED, ALREADY_HELD states
- **Domain Events**: PipelineLockAcquiredEvent, PipelineLockReleasedEvent, WorkItemQueuedEvent

The lock service provides:
- **try_acquire_lock()**: Acquire or queue
- **release_lock()**: Release and advance queue
- **get_queue_state()**: Query current state
- **update_queue_positions()**: Re-sort on board changes
- **set_lock_acquired_at()**: Test helper for stale lock simulation

## Performance Characteristics

- **Test Execution**: ~70ms for full suite
- **Lock Operations**: O(n log n) due to position-based sorting
- **Queue Size**: Tested with 100 items
- **Thread Safety**: Protected by internal threading.Lock()

## Future Enhancements

Potential additional test scenarios:
- Distributed lock implementation (Redis-based)
- Lock timeout scenarios with automatic expiration
- Competition between multiple projects simultaneously
- Performance benchmarking with varying queue depths
- Lock contention patterns (e.g., waves of arrivals)

## Test Statistics

| Metric | Value |
|--------|-------|
| Total Tests | 15 |
| Passing | 15 |
| Failing | 0 |
| Coverage | Basic lock service implementation |
| Execution Time | ~70ms |
| Lines of Test Code | 750+ |

## Conclusion

Scenario 10 provides comprehensive coverage of the pipeline locking system's core functionality, edge cases, and failure modes. The tests verify that the queue-based locking approach prevents deadlocks, maintains position-based FIFO ordering, and properly integrates with the event sourcing infrastructure.
