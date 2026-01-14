# Pipeline Lock Service - Implementation Guide

## Overview

The pipeline lock service manages concurrent work item execution in pipeline trigger columns. It ensures only one work item can execute in a trigger column at a time, while maintaining a position-based queue for other work items waiting for the lock.

## Components

### 1. IPipelineLockService Interface
**Location**: `src/codetoreum/application/pipeline_lock_service.py`

The abstract interface defining the pipeline lock service contract. Implementations must provide:

- **`try_acquire_lock(project_id, board_id, work_item_id, board_position)`**
  - Attempts to acquire lock for exclusive execution
  - Returns `LockAcquisitionResult` with status: ACQUIRED, QUEUED, or ALREADY_HELD
  - QUEUED items are sorted by board_position (lowest position = topmost = highest priority)

- **`release_lock(project_id, board_id, work_item_id)`**
  - Releases lock held by work_item_id
  - Returns next work item to receive lock (if any)
  - Grants lock to topmost queued item (by board position)

- **`get_queue_state(project_id, board_id)`**
  - Returns current lock holder and complete queue state
  - Useful for monitoring and debugging

- **`update_queue_positions(project_id, board_id, updated_positions)`**
  - Called when humans reorder cards in the board UI
  - Re-sorts queue based on new positions

### 2. InMemoryLockService Implementation
**Location**: `src/codetoreum/adapters/secondary/in_memory_queue_lock_service.py`

Thread-safe in-memory implementation suitable for:
- Single-orchestrator deployments
- Testing and simulation
- Development environments

**Features**:
- Lock state and queue stored in memory
- Thread-safe via internal threading lock
- Immediate position-based queue ordering
- No external dependencies

## Usage Example

```python
from codetoreum.adapters.secondary.in_memory_queue_lock_service import InMemoryLockService

# Initialize service
lock_service = InMemoryLockService()

# Try to acquire lock when work item enters trigger column
result = await lock_service.try_acquire_lock(
    project_id="proj-123",
    board_id="board-456",
    work_item_id="item-1",
    board_position=0  # Position in column (0 = topmost)
)

if result.status == LockStatus.ACQUIRED:
    # Lock granted - trigger agent immediately
    await execute_agent("item-1")

elif result.status == LockStatus.QUEUED:
    # Work item queued - wait for lock
    # Will emit WorkItemQueuedEvent with position
    logger.info(f"Queued at position {result.queue_position}")

elif result.status == LockStatus.ALREADY_HELD:
    # Work item already holds lock
    logger.info("Already holding lock")

# Release lock when work item reaches exit column
release_result = await lock_service.release_lock(
    project_id="proj-123",
    board_id="board-456",
    work_item_id="item-1"
)

if release_result.next_work_item_id:
    # Trigger agent for next queued item
    await execute_agent(release_result.next_work_item_id)

# Query current state
state = await lock_service.get_queue_state("proj-123", "board-456")
print(f"Lock holder: {state.lock_holder}")
print(f"Queue length: {len(state.queue)}")
for i, entry in enumerate(state.queue):
    print(f"  {i}: {entry.work_item_id} (position {entry.board_position})")

# Handle card reordering by humans
await lock_service.update_queue_positions(
    project_id="proj-123",
    board_id="board-456",
    updated_positions={
        "item-2": 1,  # New position in column
        "item-3": 0,  # Moved to top
    }
)
```

## Data Classes

### LockStatus Enum
```python
ACQUIRED = "acquired"          # Lock granted immediately
QUEUED = "queued"              # Added to queue, waiting
ALREADY_HELD = "already_held"  # Work item already holds lock
```

### LockAcquisitionResult
```python
@dataclass
class LockAcquisitionResult:
    status: LockStatus              # ACQUIRED, QUEUED, or ALREADY_HELD
    work_item_id: str               # Work item requesting lock
    queue_position: Optional[int]   # Position in queue if QUEUED
    queue_length: int               # Total items in queue after operation
```

### LockReleaseResult
```python
@dataclass
class LockReleaseResult:
    released_work_item_id: str      # Work item that held lock
    next_work_item_id: Optional[str] # Next in queue to receive lock
    queue_length_after_release: int # Remaining queue length
```

### QueueEntry
```python
@dataclass
class QueueEntry:
    work_item_id: str          # Work item in queue
    board_position: int        # Position in column (0 = topmost)
    enqueued_at: datetime      # When added to queue
```

### PipelineQueueState
```python
@dataclass
class PipelineQueueState:
    board_id: str              # Board containing pipeline
    project_id: str            # Project containing board
    lock_holder: Optional[str]  # Work item holding lock (None if available)
    lock_acquired_at: Optional[datetime] # When lock was acquired
    queue: List[QueueEntry]    # Queue ordered by board_position
```

## Domain Events

Three new domain events are emitted for audit trail and handler integration:

### PipelineLockAcquiredEvent
Emitted when a work item acquires the pipeline lock.

```python
event = PipelineLockAcquiredEvent(
    type="pipeline.lock_acquired",
    timestamp="2026-01-12T15:30:00Z",
    source="orchestrator",
    work_item_id="item-1",
    board_id="board-1",
    queue_length_at_acquire=0  # How many were waiting
)
```

### PipelineLockReleasedEvent
Emitted when a work item releases the pipeline lock.

```python
event = PipelineLockReleasedEvent(
    type="pipeline.lock_released",
    timestamp="2026-01-12T15:35:00Z",
    source="orchestrator",
    work_item_id="item-1",
    board_id="board-1",
    next_work_item_id="item-2"  # Next to execute (None if queue empty)
)
```

### WorkItemQueuedEvent
Emitted when a work item is added to the lock queue.

```python
event = WorkItemQueuedEvent(
    type="workitem.queued",
    timestamp="2026-01-12T15:32:00Z",
    source="orchestrator",
    work_item_id="item-2",
    board_id="board-1",
    queue_position=1  # Position in queue (0-based)
)
```

## Queue Ordering Rules

1. **By Board Position**: Items ordered by `board_position` (lowest first)
2. **Topmost Priority**: Position 0 (topmost in column) is highest priority
3. **Visual Alignment**: Queue order matches visual column order on board
4. **Position Updates**: Queue re-sorted when humans reorder cards

Example with positions [3, 0, 2, 1]:
- Queue priority: 0 → 1 → 2 → 3
- Next to receive lock: item at position 0 (topmost)

## Integration Points

### With Workflow Orchestrator
The workflow orchestrator calls pipeline lock service when:

1. **Work item enters trigger column**:
   ```python
   result = await lock_service.try_acquire_lock(...)
   if result.status == LockStatus.ACQUIRED:
       # Trigger agent immediately
       await execute_agent(work_item_id)
   ```

2. **Work item reaches exit column**:
   ```python
   release_result = await lock_service.release_lock(...)
   if release_result.next_work_item_id:
       # Trigger agent for next
       await execute_agent(release_result.next_work_item_id)
   ```

3. **Human reorders cards**:
   ```python
   # Called by event handler for column reordering events
   await lock_service.update_queue_positions(...)
   ```

### With Event Bus
Pipeline lock events are emitted to the event bus for handler subscription:

```python
event_bus.subscribe("pipeline.lock_acquired", handle_lock_acquired)
event_bus.subscribe("pipeline.lock_released", handle_lock_released)
event_bus.subscribe("workitem.queued", handle_item_queued)
```

## Testing

**Unit test file**: `tests/unit/application/test_pipeline_lock_service.py`

**Test coverage**:
- ✅ Lock acquisition (available, held, duplicate holder, independent boards/projects)
- ✅ Queue ordering by position (ascending, topmost priority, many items)
- ✅ Lock release (holder success, non-holder failure, queue advancement)
- ✅ Queue position updates (reordering, partial updates, edge cases)
- ✅ Queue state queries (empty, with holder, with items)
- ✅ 22 tests, all passing

**Run tests**:
```bash
pytest tests/unit/application/test_pipeline_lock_service.py -v
```

## Thread Safety

InMemoryLockService is thread-safe via internal `threading.Lock()`:

- All state access is protected by lock
- Safe for concurrent calls from multiple threads
- Suitable for async/await patterns with thread-safe semantics

For distributed deployments, a Redis implementation would be needed:
```python
class RedisLockService(IPipelineLockService):
    """Production implementation using Redis for distributed locking."""
    # Future: implementation for multi-orchestrator scenarios
```

## Key Properties

✅ **Concurrency Control**: Only one work item executes in trigger column at a time
✅ **Position-Based Ordering**: Respects visual column order
✅ **Queue Management**: Automatic sorting and re-sorting
✅ **Event Trail**: Complete audit via domain events
✅ **No External Deps**: In-memory implementation standalone
✅ **Thread-Safe**: Safe for concurrent access
✅ **Extensible**: Interface allows Redis/distributed implementations

---

**Related Files**:
- Interface: `src/codetoreum/application/pipeline_lock_service.py`
- Implementation: `src/codetoreum/adapters/secondary/in_memory_queue_lock_service.py`
- Events: `src/codetoreum/domain/events/lock_events.py` (new events added)
- Tests: `tests/unit/application/test_pipeline_lock_service.py`
