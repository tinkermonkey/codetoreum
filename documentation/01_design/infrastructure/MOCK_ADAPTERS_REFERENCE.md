# Mock Adapters Reference

**Complete inventory of 18 testing and simulation adapters**

## Overview

Mock adapters provide fast, deterministic implementations of port interfaces for testing and simulation without external dependencies. All adapters are located in `src/codetoreum/adapters/testing/`.

## Adapter Categories

### 1. **Mock Workflow Adapters** (3)
- MockLLMAdapter - Agent/LLM execution simulation
- MockBoardAdapter - Project board operations
- MockReviewCycleAdapter - Code review workflow

### 2. **Mock System Adapters** (3)
- MockNotifierAdapter - Notification delivery
- MockRepairCycleAdapter - Test-fix-validate loops
- MockContainerRecoveryAdapter - Container failure recovery

### 3. **In-Memory Persistence Adapters** (7)
- InMemoryEventStore - Event sourcing
- InMemoryStorageAdapter - File/object storage
- InMemoryRepositoryAdapter - Git operations
- InMemoryTicketAdapter - Ticket system (legacy)
- InMemoryWorkflowConfigService - Workflow configuration
- InMemoryQueueService - Work item queue
- InMemoryCheckpointStore - Repair cycle state

### 4. **Utility Adapters** (4)
- FakeContainerAdapter - Container execution
- SimpleEncryptionService - Data encryption
- InMemoryMetricsAdapter - Metrics collection
- InMemoryConfigStore - Configuration storage

### 5. **Support Adapters** (1)
- Specialized encryption, messaging (as needed)

---

## Detailed Adapter Specifications

### Mock Workflow Adapters

#### 1. MockLLMAdapter
**File**: `mock_llm_adapter.py`
**Implements**: ILLMProvider
**Purpose**: Simulate LLM responses with pattern matching

**Key Features**:
- ✅ Pattern-based response matching (regex patterns)
- ✅ Configurable execution delay
- ✅ Conversation history tracking
- ✅ Token usage simulation
- ✅ Stream simulation support
- ✅ Tool call simulation

**Configuration**:
```python
adapter = MockLLMAdapter(
    delay_seconds=0.1,  # Execution delay
    default_response="Response text"
)

# Add response patterns
adapter.add_response_pattern(
    pattern=r"generate.*code",
    response="class MyClass:\n    pass"
)
```

**Core Methods**:
```python
# Execute LLM call
result = await adapter.execute(
    prompt="Generate a function",
    execution_context=context
)

# Access conversation history
conversations = adapter.get_conversations()

# Clear for next test
adapter.clear_conversations()
```

**Use Cases**:
- Agent behavior simulation
- Prompt-response validation
- Conversation state testing

**Metrics Tracked**:
- Execution count
- Success/failure rate
- Token usage estimation

---

#### 2. MockBoardAdapter
**File**: `mock_board_adapter.py`
**Implements**: IBoardService
**Purpose**: Simulate project board operations

**Key Features**:
- ✅ In-memory board structure
- ✅ Column management
- ✅ Work item positioning
- ✅ Movement tracking
- ✅ Event emission (column_changed, reconciled)
- ✅ Reconciliation simulation

**Configuration**:
```python
adapter = MockBoardAdapter()
adapter.current_project = "proj-1"

# Create board
adapter.create_board(
    project_id="proj-1",
    board_id="board-1",
    board_name="Pipeline",
    column_names=["Backlog", "In Progress", "Done"]
)

# Add work item
adapter.add_item_to_column("board-1", "Backlog", "item-1")
```

**Core Methods**:
```python
# Query
board = await adapter.get_board("proj-1", "board-1")
columns = await adapter.get_columns("board-1")
items = await adapter.get_items_in_column("board-1", "In Progress")
position = await adapter.get_item_position("item-1")

# Commands
await adapter.move_item_to_column("item-1", "In Progress")
result = await adapter.reconcile_board(config)
```

**Event Emission**:
- `workitem.column_changed` - Item moved between columns
- `board.reconciled` - Board reconciliation complete

**State Tracking**:
```python
# Get movement history
moves = adapter.get_movements("board-1")
# Returns: [{work_item_id, from_column, to_column, timestamp}]

# Get current state
state = adapter.get_board_state("board-1")
```

**Use Cases**:
- Workflow column transition testing
- Board synchronization validation
- Queue ordering by column position

---

#### 3. MockReviewCycleAdapter
**File**: `mock_review_cycle_adapter.py`
**Implements**: ICodeReviewService (partially)
**Purpose**: Simulate code review cycles with approval/rejection

**Key Features**:
- ✅ Review state management (open, approved, changes_requested)
- ✅ Approval/rejection workflow
- ✅ Comment addition
- ✅ Iteration counting
- ✅ Event emission

**Configuration**:
```python
adapter = MockReviewCycleAdapter(clock=simulation_clock)

# Simulate review behavior
adapter.set_review_outcome(
    work_item_id="item-1",
    iteration_count=2,  # 2 revision cycles
    final_status="approved"
)
```

**Core Methods**:
```python
# Query review
review = await adapter.get_review_for_work_item("item-1")
status = await adapter.get_review_status("review-1")
comments = await adapter.get_review_comments("review-1")

# Commands
await adapter.request_changes("review-1", "Add error handling")
await adapter.approve("review-1")

# Testing
iteration_count = adapter.get_iteration_count("item-1")
assert_feedback = adapter.get_feedback_for_iteration("item-1", 1)
```

**Event Emission**:
- `review.status_changed` - Approval/rejection
- `review.comment_added` - Comment posted

**Use Cases**:
- Maker-checker workflow testing
- Revision cycle simulation
- Review gate validation

---

### Mock System Adapters

#### 4. MockNotifierAdapter
**File**: `mock_notifier_adapter.py`
**Implements**: INotifier
**Purpose**: Capture notifications without sending

**Key Features**:
- ✅ Notification capture
- ✅ Failure simulation (optional)
- ✅ Delivery status tracking
- ✅ Query by recipient/subject
- ✅ Assertion helpers

**Configuration**:
```python
adapter = MockNotifierAdapter(
    send_delay=0.01,
    simulate_failures=False,
    failure_rate=0.0
)

# Enable failure simulation
adapter.simulate_failures=True
adapter.failure_rate=0.1  # 10% failure rate
```

**Core Methods**:
```python
# Send notification
result = await adapter.send_notification(
    notification=Notification(
        channel=NotificationChannel.EMAIL,
        recipient="user@example.com",
        subject="Workflow complete",
        body="Your workflow has finished"
    )
)

# Query sent notifications
all = adapter.get_sent_notifications()
by_recipient = adapter.get_notifications_for("user@example.com")
by_subject = adapter.get_notifications_with_subject("complete")

# Assertions
sent = adapter.assert_notification_sent(
    recipient="user@example.com",
    subject_contains="complete"
)

# Statistics
count = adapter.get_notification_count()
```

**Failure Simulation**:
```python
# Simulate delivery failures
adapter.simulate_failures = True
adapter.failure_rate = 0.2

# Some sends will fail (return failure status)
result = await adapter.send_notification(notification)
# Returns: NotificationResult(status=DeliveryStatus.FAILED)
```

**Use Cases**:
- Notification workflow validation
- User communication testing
- Delivery reliability testing

---

#### 5. MockRepairCycleAdapter
**File**: `mock_repair_cycle_adapter.py`
**Implements**: IRepairCycle (partially)
**Purpose**: Simulate test-fix-validate repair cycles

**Key Features**:
- ✅ Test type sequence (UNIT → INTEGRATION → E2E)
- ✅ Failure/success simulation
- ✅ Iteration counting
- ✅ Fast-fail behavior (skip downstream if upstream fails)
- ✅ Repair attempt tracking
- ✅ Circuit breaker support

**Configuration**:
```python
adapter = MockRepairCycleAdapter(clock=simulation_clock)

# Set test outcomes
adapter.set_test_outcome(
    stage="testing",
    test_type="unit",
    iteration=1,
    success=False,  # First attempt fails
    error_message="AssertionError: x == y"
)

adapter.set_test_outcome(
    stage="testing",
    test_type="unit",
    iteration=2,
    success=True,  # Second attempt succeeds
)

# Set integration tests (these run because unit passed)
adapter.set_test_outcome(
    stage="testing",
    test_type="integration",
    iteration=1,
    success=True,
)
```

**Core Methods**:
```python
# Start repair cycle
cycle_id = await adapter.start_repair_cycle(
    work_item_id="item-1",
    failing_test_type="unit",
    test_output="AssertionError..."
)

# Get status
status = await adapter.get_repair_status(cycle_id)
# Returns: {test_type, iteration, success/failure, error}

# Complete cycle
result = await adapter.complete_repair_cycle(cycle_id)

# Query history
history = adapter.get_repair_history("item-1")
iterations = adapter.get_iteration_count("item-1", "unit")
```

**Fast-Fail Behavior**:
```
If UNIT tests fail in iteration 1:
  Repair cycle triggered
  UNIT tests retried → Pass in iteration 2 ✓
  INTEGRATION tests run (because UNIT passed) → Pass ✓
  E2E tests run (because all prior tests passed) → Pass ✓

If UNIT tests fail in iteration 1 AND 2:
  Repair cycle triggered after iteration 1
  UNIT tests retried → Fail in iteration 2 ❌
  INTEGRATION tests SKIPPED (UNIT didn't pass)
  E2E tests SKIPPED (UNIT didn't pass)
```

**Circuit Breaker**:
```python
# Set max iterations
adapter.set_max_iterations(test_type="unit", max=5)

# After 5 failed iterations
# → Circuit breaker activates
# → Return failure status
# → Skip downstream tests
```

**Use Cases**:
- Repair cycle mechanism testing
- Test sequence validation
- Error recovery testing
- Fast-fail behavior verification

---

#### 6. MockContainerRecoveryAdapter
**File**: `mock_container_recovery_adapter.py`
**Implements**: IAgentContainerRecoveryService
**Purpose**: Simulate container failure recovery

**Key Features**:
- ✅ Failure cause detection
- ✅ Recovery strategy assessment
- ✅ Configurable recovery outcomes
- ✅ Resource adjustment simulation
- ✅ Event emission

**Configuration**:
```python
adapter = MockContainerRecoveryAdapter()

# Simulate OOM failure with recovery
adapter.set_recovery_scenario(
    container_id="agent-exec-1",
    failure_cause="OOM",
    recoverable=True,
    recovery_strategy="INCREASE_MEMORY",
    recovery_success=True
)

# Simulate unrecoverable disk failure
adapter.set_recovery_scenario(
    container_id="agent-exec-2",
    failure_cause="DISK_FULL",
    recoverable=False,
    recovery_success=False
)
```

**Core Methods**:
```python
# Assess recovery possibility
assessment = await adapter.assess_recovery(
    container_id="agent-exec-1",
    failure_cause="OOM",
    container_logs="Cannot allocate memory..."
)
# Returns: {recoverable, recommended_strategy, reason}

# Attempt recovery
result = await adapter.recover_container(
    container_id="agent-exec-1",
    recovery_strategy=RecoveryStrategy.INCREASE_MEMORY,
    new_memory_limit="4GB"
)
# Returns: {success, message, new_config}

# Get recovery status
status = await adapter.get_recovery_status("agent-exec-1")
```

**Recovery Strategies**:
- `INCREASE_MEMORY` - Add memory for OOM
- `INCREASE_DISK` - Add disk space for full disk
- `RETRY_WITH_BACKOFF` - Retry transient failures
- `ALTERNATIVE_NODE` - Try different host
- `ESCALATE` - Manual intervention needed

**Use Cases**:
- Container failure recovery testing
- Resource adjustment validation
- Failure escalation workflow

---

### In-Memory Persistence Adapters

#### 7. InMemoryEventStore
**File**: `in_memory_event_store.py`
**Implements**: IEventStore
**Purpose**: Event sourcing without external storage

**Key Features**:
- ✅ Event append and retrieval
- ✅ Aggregate-based querying
- ✅ Full event stream access
- ✅ Subscription support
- ✅ Snapshot management (optional)

**Usage**:
```python
store = InMemoryEventStore()

# Append event
await store.append_event(event)

# Retrieve by aggregate
events = await store.get_events_for_aggregate("work-item-1")

# Full stream
all_events = await store.get_all_events()

# Subscribe to new events
async def on_event(event):
    print(f"Event: {event.event_type}")

await store.subscribe(on_event)
```

**Use Cases**:
- Event sourcing testing
- Audit trail validation
- Event replay testing

---

#### 8. InMemoryStorageAdapter
**File**: `in_memory_storage_adapter.py`
**Implements**: IStorage
**Purpose**: File/object storage without S3

**Key Features**:
- ✅ In-memory file storage
- ✅ Directory-like structure
- ✅ Metadata tracking
- ✅ Object retrieval

**Usage**:
```python
storage = InMemoryStorageAdapter()

# Store file
await storage.put_object(
    key="outputs/result.txt",
    data=b"Agent output here"
)

# Retrieve
obj = await storage.get_object("outputs/result.txt")
content = obj.data  # bytes

# List objects
objects = await storage.list_objects("outputs/")

# Delete
await storage.delete_object("outputs/result.txt")
```

**Use Cases**:
- Agent output storage testing
- Artifact management validation

---

#### 9. InMemoryRepositoryAdapter
**File**: `in_memory_repository_adapter.py`
**Implements**: IRepository
**Purpose**: Git operations without actual Git

**Key Features**:
- ✅ Repository simulation
- ✅ Branch management
- ✅ Commit simulation
- ✅ Diff operations
- ✅ Merge simulation

**Usage**:
```python
repo = InMemoryRepositoryAdapter()

# Clone
await repo.clone("https://github.com/...", "/local/path")

# Create branch
await repo.create_branch("/local/path", "feature/auth")

# Commit
commit_sha = await repo.commit(
    "/local/path",
    "Add authentication"
)

# Push
await repo.push("/local/path", "feature/auth")

# Merge
await repo.merge("/local/path", "feature/auth", "main")
```

**Use Cases**:
- Workflow git operations testing
- CI/CD integration validation

---

#### 10. InMemoryTicketAdapter
**File**: `in_memory_ticket_adapter.py`
**Implements**: ITicketSystem (legacy)
**Purpose**: Ticket management without external system

**Note**: Being phased out in favor of vendor-agnostic ports

**Usage**:
```python
adapter = InMemoryTicketAdapter()

# Create work item
item = await adapter.create_work_item(
    title="Add feature",
    description="Feature details"
)

# Update
await adapter.update_work_item(item.id, {"status": "done"})

# Add comment
await adapter.create_comment(item.id, "Fixed in PR #123")
```

---

#### 11. InMemoryWorkflowConfigService
**File**: `in_memory_workflow_config_service.py`
**Implements**: IWorkflowConfigService
**Purpose**: Workflow definition storage

**Usage**:
```python
service = InMemoryWorkflowConfigService()

# Save workflow
config = WorkflowConfig(
    name="SDLC Pipeline",
    stages=[...]
)
await service.save_workflow_config(config)

# Retrieve
retrieved = await service.get_workflow_config("SDLC Pipeline")

# List
workflows = await service.list_workflows()
```

---

#### 12. InMemoryQueueService
**File**: `in_memory_queue_service.py`
**Implements**: IPipelineQueueService
**Purpose**: Work item queue management

**Key Features**:
- ✅ Position-based ordering
- ✅ Queue entry tracking
- ✅ Status management (waiting vs. active)
- ✅ Dequeue operations

**Usage**:
```python
queue = InMemoryQueueService()

# Enqueue
entry = await queue.enqueue(
    work_item_id="item-1",
    position=0
)

# Get position
position = await queue.get_queue_position("item-1")

# Dequeue (get next by position)
next_item = await queue.dequeue()

# Requeue (move to back)
await queue.requeue("item-1")
```

**Use Cases**:
- FIFO queue ordering testing
- Position-based prioritization

---

#### 13. InMemoryCheckpointStore
**File**: `in_memory_checkpoint_store.py`
**Implements**: IRepairCycleCheckpointStore
**Purpose**: Repair cycle state persistence

**Usage**:
```python
store = InMemoryCheckpointStore()

# Save checkpoint
checkpoint = RepairCheckpoint(
    repair_cycle_id="cycle-1",
    iteration=2,
    state={"test_results": [...]}
)
await store.save_checkpoint(checkpoint)

# Retrieve
saved = await store.get_checkpoint("cycle-1")

# Resume from checkpoint
state = saved.state
```

**Use Cases**:
- Repair cycle resumption testing
- State persistence validation

---

### Utility Adapters

#### 14. FakeContainerAdapter
**File**: `fake_container_adapter.py`
**Implements**: IContainer
**Purpose**: Container execution without Docker

**Key Features**:
- ✅ Command execution simulation
- ✅ Exit code management
- ✅ Output capture (stdout, stderr)
- ✅ Container status tracking

**Configuration**:
```python
adapter = FakeContainerAdapter(
    execution_delay=0.1,
    default_exit_code=0
)

# Set command result
adapter.set_command_result(
    command_pattern="pytest",
    exit_code=0,
    stdout="All tests passed"
)
```

**Core Methods**:
```python
# Run command
result = await adapter.run(
    image="python:3.11",
    command=["pytest"],
    cwd="/workspace"
)
# Returns: {exit_code, stdout, stderr}

# Container lifecycle
await adapter.create_container(...)
await adapter.start_container(...)
await adapter.stop_container(...)
```

**Use Cases**:
- Agent execution simulation
- Container behavior testing

---

#### 15. SimpleEncryptionService
**File**: `simple_encryption_service.py`
**Implements**: IEncryptionService
**Purpose**: In-process encryption for testing

**Features**:
- ✅ Basic encryption/decryption
- ✅ Key management
- ✅ Error handling

**Usage**:
```python
service = SimpleEncryptionService()

# Encrypt
ciphertext = await service.encrypt("secret data")

# Decrypt
plaintext = await service.decrypt(ciphertext)
assert plaintext == "secret data"
```

**Note**: For production use KMS-backed service

---

#### 16. InMemoryMetricsAdapter
**File**: `in_memory_metrics_adapter.py`
**Implements**: IMetrics
**Purpose**: Metrics collection without Prometheus

**Usage**:
```python
adapter = InMemoryMetricsAdapter()

# Record metrics
await adapter.increment_counter("requests", 1)
await adapter.set_gauge("queue_size", 42)
await adapter.record_histogram("response_time", 150)

# Query
value = adapter.get_counter_value("requests")
all_metrics = adapter.get_all_metrics()

# Assertions
count = adapter.get_metric_count("requests")
assert count == 5
```

**Use Cases**:
- Metrics emission validation
- Performance tracking testing

---

#### 17. InMemoryConfigStore
**File**: `in_memory_config_store.py`
**Implements**: IConfigStore (if applicable)
**Purpose**: Configuration storage without database

**Usage**:
```python
store = InMemoryConfigStore()

# Save config
await store.save("app_config", {"timeout": 30})

# Retrieve
config = await store.get("app_config")

# List
all_keys = await store.list()
```

---

## Testing with Mock Adapters

### Basic Pattern
```python
@pytest.mark.asyncio
async def test_workflow_with_mocks():
    # Setup
    config = SimulationConfig.create_fast_config("test")
    runner = SimulationRunner(config)

    # Adapters available on runner
    runner.llm_adapter.add_response_pattern(...)
    runner.container_adapter.set_command_result(...)
    runner.metrics_adapter  # InMemoryMetricsAdapter
    runner.notifier_adapter  # MockNotifierAdapter

    # Run scenario
    result = await runner.run(scenario_func)

    # Assertions
    assert result.success
    runner.assert_event_occurred("WorkflowCompleted")
```

### Advanced: Mock Composition
```python
async def test_complex_workflow():
    # Setup multiple mocks
    board = MockBoardAdapter()
    review = MockReviewCycleAdapter(clock)
    repair = MockRepairCycleAdapter(clock)

    # Simulate complex interactions
    # 1. Item moved to In Progress
    await board.move_item_to_column("item-1", "In Progress")

    # 2. Code review requested
    await review.request_changes("review-1", "Add tests")

    # 3. Revision completed, retested
    await repair.set_test_outcome(...success=True...)

    # 4. Assertions on state
    assert board.get_item_position("item-1") == ("In Progress", 0)
    assert await review.get_review_status("review-1") == "approved"
```

---

## Best Practices

### 1. **Use Appropriate Adapter Level**
- Mock (high-level behavior): MockBoardAdapter, MockLLMAdapter
- InMemory (basic operations): InMemoryEventStore, InMemoryStorage
- Fake (low-level simulation): FakeContainerAdapter

### 2. **Clear Configuration**
```python
# Good: Explicit setup
adapter = MockLLMAdapter()
adapter.add_response_pattern(r"class.*", "class X: pass")
adapter.add_response_pattern(r"function.*", "def f(): pass")

# Avoid: Implicit defaults
adapter = MockLLMAdapter()
# → Relies on defaults, hard to understand
```

### 3. **Test Both Success and Failure**
```python
# Test success path
adapter.set_test_outcome(...success=True)

# Test failure path
adapter.set_test_outcome(...success=False, error_message="...")
```

### 4. **Verify Assertions**
```python
# Use adapter assertion helpers
notifications = runner.notifier_adapter.get_sent_notifications()
assert len(notifications) == 1
assert notifications[0].recipient == "user@example.com"

# Use runner assertion helpers
runner.assert_notification_sent("user@example.com", subject_contains="complete")
```

### 5. **Clean Up Between Tests**
```python
adapter.clear()  # Reset state
runner.clear_captured_data()  # Clear events/metrics
```

---

## Error Handling Contract

All mock adapters must raise appropriate exceptions when resources are not found, matching production adapter behavior. This ensures error handling code is tested realistically in simulations.

### Resource Not Found Errors

**Pattern**: Use `ResourceNotFoundError` (from `codetoreum.ports.exceptions`) when a single-item retrieval fails.

**Constructor**: `ResourceNotFoundError(resource_type: str, resource_id: str)`
- `resource_type`: Resource type label (e.g., "File", "Artifact", "Work item", "Column")
- `resource_id`: Programmatic identifier for the missing resource
- **Note**: The constructor formats the message as `"{resource_type} not found: {resource_id}"`

**Examples**:

```python
# File not found
if file_key not in self._files:
    raise ResourceNotFoundError("File", file_path)

# Artifact not found
if key not in self._objects:
    raise ResourceNotFoundError("Artifact", key)

# Work item not found
if work_item_id not in self._item_positions:
    raise ResourceNotFoundError("Work item", work_item_id)

# Column not found
if target_col is None:
    raise ResourceNotFoundError("Column", target_column)
```

### Collection Queries Return Empty

**Pattern**: Return empty list/dict when querying collections that may have zero items.

**Rationale**: Collection queries expect zero or more items; returning empty is a valid result.

**Examples**:

```python
# Queue entries - return empty list (valid state)
async def get_queue_entries(self, project_id: str, board_id: str) -> list[PipelineQueueEntry]:
    with self._lock:
        key = f"{project_id}:{board_id}"
        return self._queues.get(key, [])  # Empty list = no items in queue

# Board items in column - return empty list (valid state)
async def get_items_in_column(self, board_id: str, column_name: str) -> list[WorkItemPosition]:
    # ... validate inputs that are required ...
    # Return empty list if no items - this is normal, not an error
    return items
```

### Optional Result Return Patterns

**Pattern**: Return `None` only when explicitly documented in the interface as a valid optional result.

**Examples**:

```python
# get_next_waiting_item returns None when queue is empty (documented as valid)
async def get_next_waiting_item(self, project_id: str, board_id: str) -> PipelineQueueEntry | None:
    # Returns None if no waiting items - this is expected behavior
    # Does NOT raise error because None is documented as valid return value
```

### Adapter-Specific Error Behavior

| Adapter | Method | Missing Behavior | Exception |
|---------|--------|------------------|-----------|
| InMemoryRepositoryAdapter | `get_file_content()` | Raise error | `ResourceNotFoundError` |
| InMemoryRepositoryAdapter | `get_file_content()` | Repository missing | `ResourceNotFoundError` |
| InMemoryStorageAdapter | `download()` | Artifact missing | `ResourceNotFoundError` |
| InMemoryStorageAdapter | `delete()` | Artifact missing | `ResourceNotFoundError` |
| MockBoardAdapter | `get_item_position()` | Item missing | `ResourceNotFoundError` |
| MockBoardAdapter | `move_item_to_column()` | Item/column missing | `ResourceNotFoundError` |
| InMemoryQueueService | `get_next_waiting_item()` | Queue empty | Returns `None` (valid) |
| InMemoryQueueService | `mark_item_active()` | Item missing | `QueueItemNotFoundError` |

### Testing Error Conditions

All adapters must include tests validating error conditions:

```python
@pytest.mark.asyncio
async def test_get_file_content_missing_file_raises_error(self, adapter):
    """Test that missing file raises ResourceNotFoundError with details."""
    await adapter.clone(url="...", destination=Path("/tmp/test"))

    with pytest.raises(ResourceNotFoundError) as exc_info:
        await adapter.get_file_content(
            repo_path=Path("/tmp/test"),
            file_path="nonexistent.py"
        )

    # Verify error includes identifying information
    assert "nonexistent.py" in str(exc_info.value)
    assert exc_info.value.resource_id is not None
```

### Implementation Checklist

- [ ] Adapter raises `ResourceNotFoundError` for missing single items
- [ ] Error message includes resource identifier and context
- [ ] Error message is human-readable and helpful for debugging
- [ ] `resource_id` field contains programmatic identifier
- [ ] Adapter returns empty collection for zero-item queries (not error)
- [ ] Adapter returns `None` only if documented in interface
- [ ] Unit tests validate error conditions, not just happy paths
- [ ] Error behavior matches production adapters (GitHub, etc.)

---

## Performance Characteristics

| Adapter | Speed | Determinism | Memory |
|---------|-------|-------------|--------|
| MockLLMAdapter | 100x | 100% | Low |
| MockBoardAdapter | 100x | 100% | Low |
| InMemoryEventStore | 1000x | 100% | Medium (grows with events) |
| InMemoryMetricsAdapter | 1000x | 100% | Low |
| FakeContainerAdapter | 100x | 100% | Low |

---

## References

- `src/codetoreum/adapters/testing/` - Implementation source
- `tests/simulation/` - Usage examples
- `src/codetoreum/ports/output/` - Port interface definitions
