# Mock Adapters Reference

**Complete inventory of 24 testing and simulation adapters**

## Overview

Mock adapters provide fast, deterministic implementations of port interfaces for testing and simulation without external dependencies. All adapters are located in `src/codetoreum/adapters/testing/`.

## Adapter Categories

### 1. **Mock Workflow Adapters** (4)
- MockLLMAdapter - Agent/LLM execution simulation
- MockBoardAdapter - Project board operations
- MockReviewCycleAdapter - Code review workflow
- MockDiscussionAdapter - Discussion/comment thread management

### 2. **Mock System Adapters** (3)
- MockNotifierAdapter - Notification delivery
- MockRepairCycleAdapter - Test-fix-validate loops
- MockContainerRecoveryAdapter - Container failure recovery

### 3. **In-Memory Persistence Adapters** (8)
- InMemoryEventStore - Event sourcing
- InMemoryStorageAdapter - File/object storage
- InMemoryRepositoryAdapter - Git operations
- InMemoryTicketAdapter - Ticket system (legacy)
- InMemoryWorkflowConfigService - Workflow configuration
- InMemoryQueueService - Work item queue
- InMemoryCheckpointStore - Repair cycle state
- InMemoryVersionControlService - Version control operations

### 4. **In-Memory Infrastructure Adapters** (2)
- InMemoryMessageBroker - Pub/sub message distribution
- InMemoryMetricsAdapter - Metrics collection

### 5. **Utility Adapters** (5)
- FakeContainerAdapter - Container execution
- SimpleEncryptionAdapter - Data encryption
- InMemoryConfigStore - Configuration storage
- ConfigurableIdentityService - Bot/user identification
- MockProjectManagerAdapter - Multi-project management

### 6. **Support Adapters** (2)
- CapturingMockEventEmitter - Domain event capture
- MockAgentExecutor - Agent execution simulation (unit-test utility only, not used in bootstrap)

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

#### 4. MockDiscussionAdapter
**File**: `mock_discussion_adapter.py`
**Implements**: IDiscussionAdapter
**Purpose**: Simulate discussion threads and comment management

**Key Features**:
- ✅ In-memory discussion thread storage
- ✅ Comment creation and retrieval
- ✅ Work-item-specific monitoring
- ✅ Event emission for comment actions
- ✅ Test helpers for setup and verification

**Configuration**:
```python
adapter = MockDiscussionAdapter(identity_service=identity_svc)
config = DiscussionMonitoringConfig(project_id="proj-1")
adapter.start_monitoring("item-1", config)
```

**Core Methods**:
```python
# Query
thread = await adapter.get_thread("item-1")
comments = adapter.get_comments_by_author("item-1", "alice")
count = adapter.get_comment_count("item-1")

# Commands
comment = await adapter.add_comment("item-1", "Agent response")

# Monitoring
adapter.start_monitoring("item-1", config)
adapter.stop_monitoring("item-1")
```

**Test Helpers**:
- `simulate_comment()` - Simulate human comment (emits event)
- `simulate_bot_comment()` - Simulate bot comment
- `create_thread()` - Create discussion with initial comment
- `get_processed_comment_ids()` - Get comment IDs for deduplication
- `reset_monitoring_state()` - Reset for restart simulation
- `clear_threads()` - Clear all threads
- `clear_monitoring()` - Clear monitoring state
- `get_thread_info()` - Get diagnostic thread information

**Event Emission**:
- `comment.needs_response` - Human comment posted (if monitoring)
- `comment.posted` - Bot comment posted

**Use Cases**:
- Discussion monitoring workflow testing
- Comment response handling validation
- Duplicate prevention testing

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
- ✅ **Thread-safe concurrent access** (using `threading.Lock()`)

**Usage**:
```python
storage = InMemoryStorageAdapter()

# Store file
await storage.upload(
    key="outputs/result.txt",
    content=b"Agent output here"
)

# Retrieve
content = await storage.download("outputs/result.txt")

# List objects
objects = await storage.list_files("outputs/")

# Delete
await storage.delete("outputs/result.txt")
```

**Thread Safety Contract**:

All storage operations are protected by an internal lock to ensure thread-safe concurrent access matching production storage adapter behavior (S3, Azure Blob Storage, etc.).

| Operation | Concurrency | Behavior |
|-----------|-------------|----------|
| Multiple uploads to **same key** | Concurrent | **Last-write-wins**: One completely overwrites the other. Result is deterministic (one of the uploaded contents), never corrupted partial data. |
| Upload + download **same key** | Concurrent | Download returns either old or new complete content, never partial/corrupted data. Lock ensures consistent snapshot. |
| Upload + delete **same key** | Concurrent | One operation wins: either artifact exists (if upload won) or doesn't (if delete won). Final state is consistent. |
| Multiple downloads **same key** | Concurrent | All downloads return identical, complete content. No partial reads or corruption. |
| List + upload **different keys** | Concurrent | List returns consistent snapshot: either sees new file or doesn't, but never partial/corrupted data. |
| Multiple deletes **same key** | Concurrent | First delete succeeds, second raises `ResourceNotFoundError`. Lock ensures serialization. |

**Guarantees**:
- ✅ All state changes are atomic (protected by lock)
- ✅ No partial writes or reads due to concurrent operations
- ✅ No data corruption from simultaneous access
- ✅ Deterministic results (not racy/flaky)
- ✅ Same concurrency semantics as production storage (eventual consistency with atomic operations)

**Use Cases**:
- Agent output storage testing
- Artifact management validation
- **Concurrent workflow testing** (ensures multi-threaded code is tested realistically)
- **Production adapter behavior simulation** (matches S3/Azure concurrency guarantees)

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

#### 14. InMemoryVersionControlService
**File**: `in_memory_version_control_service.py`
**Implements**: IVersionControlService
**Purpose**: Version control operations without git

**Key Features**:
- ✅ Repository cloning simulation
- ✅ Branch management (checkout, create)
- ✅ Commit simulation with SHA generation
- ✅ Push simulation
- ✅ Repository metadata retrieval

**Usage**:
```python
service = InMemoryVersionControlService()

# Clone repository
await service.clone_repository(
    url="https://github.com/org/repo.git",
    target_path="/workspace/repo",
    branch="main"
)

# Checkout branch
await service.checkout("/workspace/repo", "feature/new-feature")

# Commit changes
commit_sha = await service.commit(
    "/workspace/repo",
    "Add feature implementation"
)

# Push to remote
await service.push("/workspace/repo", "feature/new-feature")

# Get repository info
repo = await service.get_repository("repo-123")
assert repo.name == "repo"
```

**Use Cases**:
- Version control workflow testing
- Git operation orchestration validation
- Branch management testing

---

#### 15. InMemoryMessageBroker
**File**: `in_memory_message_broker.py`
**Implements**: IMessageBroker
**Purpose**: Pub/sub message distribution without Redis

**Key Features**:
- ✅ Channel-based pub/sub messaging
- ✅ Event and control message publication
- ✅ Async and sync callback support
- ✅ Statistics tracking
- ✅ Test helper methods

**Configuration**:
```python
broker = InMemoryMessageBroker()

# Initialize
await broker.initialize()

# Subscribe to channel
messages = []
async def handler(msg):
    messages.append(msg)

await broker.subscribe("events.workflow", handler)
```

**Core Methods**:
```python
# Publish
await broker.publish_event(domain_event)
await broker.publish_control_message("disconnect", {"client_id": "123"})

# Subscribe
await broker.subscribe("channel_name", callback)
await broker.unsubscribe("channel_name", callback)

# Statistics
stats = broker.get_stats()
# Returns: {
#   'events_published': N,
#   'control_messages_published': N,
#   'messages_delivered': N,
#   'delivery_failures': N,
#   'active_subscriptions': N,
#   'channels': N
# }
```

**Test Helpers**:
- `get_published_messages()` - Get all published messages
- `get_subscriptions_for_channel()` - Count subscriptions on channel
- `clear_published_messages()` - Clear message log

**Use Cases**:
- Pub/sub message distribution testing
- Horizontal scalability testing
- Control message coordination testing

---

### In-Memory Infrastructure Adapters

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

### Utility Adapters

#### 17. FakeContainerAdapter
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

#### 18. SimpleEncryptionAdapter
**File**: `simple_encryption_adapter.py`
**Implements**: IEncryptionService
**Purpose**: In-process encryption for testing

**Features**:
- ✅ Basic encryption/decryption
- ✅ Key management
- ✅ Error handling

**Usage**:
```python
service = SimpleEncryptionAdapter()

# Encrypt
ciphertext = await service.encrypt("secret data")

# Decrypt
plaintext = await service.decrypt(ciphertext)
assert plaintext == "secret data"
```

**Note**: For production use KMS-backed service

---

#### 19. InMemoryConfigStore
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

#### 20. ConfigurableIdentityService
**File**: `../secondary/configurable_identity_service.py`
**Implements**: IIdentityService
**Purpose**: Bot/user identification with configuration

**Key Features**:
- ✅ Bot user identification
- ✅ Human user identification
- ✅ Configurable bot username
- ✅ Testing and debugging support

**Configuration**:
```python
service = ConfigurableIdentityService(bot_username="codetoreum-bot")

# Identify users
is_bot = service.is_bot_user("codetoreum-bot")  # True
is_bot = service.is_bot_user("alice")  # False

# Get bot username
name = service.get_bot_username()  # "codetoreum-bot"
```

**Use Cases**:
- Bot comment filtering
- Author attribution testing
- Discussion thread filtering

---

#### 21. MockProjectManagerAdapter
**File**: `mock_project_manager_adapter.py`
**Implements**: IProjectManager
**Purpose**: Multi-project management simulation

**Key Features**:
- ✅ Project CRUD operations
- ✅ Project configuration management
- ✅ Test helper methods

**Configuration**:
```python
adapter = MockProjectManagerAdapter()

# Add project
adapter.add_project("proj-1", ProjectConfig(...))

# Get project
project = adapter.get_project("proj-1")

# List projects
projects = adapter.list_projects()
```

**Use Cases**:
- Multi-project orchestration testing
- Project configuration validation

---

### Support Adapters

#### 22. CapturingMockEventEmitter
**File**: `capturing_mock_event_emitter.py`
**Implements**: IEventEmitter
**Purpose**: Event capture and verification for testing

**Key Features**:
- ✅ Event capture
- ✅ Event history tracking
- ✅ Query and assertion helpers
- ✅ Event filtering

**Usage**:
```python
emitter = CapturingMockEventEmitter()

# Capture events
emitter.emit(domain_event)

# Query
events = emitter.get_all_events()
filtered = emitter.get_events_by_type("WorkItemColumnChanged")

# Assertions
assert len(events) == 1
assert events[0].event_type == "WorkItemColumnChanged"

# Clear
emitter.clear()
```

**Use Cases**:
- Domain event capture testing
- Event workflow validation
- Event source verification

---

#### 23. MockAgentExecutor (Unit-Test Utility Only)
**File**: `mock_agent_executor.py`
**Purpose**: Unit-test utility for isolated executor testing (NOT used in SimulationApplicationBootstrap)
**Status**: ⚠️ **DEPRECATED FROM BOOTSTRAP** - SimulationApplicationBootstrap uses ExecutionServiceAgentExecutor exclusively

**Important Note**: As of Phase 1 of issue #371, MockAgentExecutor is retained only as a unit-test utility for tests that construct their own BoardColumnEventHandler instances. It is no longer wired by SimulationApplicationBootstrap. The bootstrap now uses ExecutionServiceAgentExecutor directly as the unconditional default executor.

**Key Features**:
- ✅ Agent execution simulation with configurable delays
- ✅ Execution tracking for test assertions
- ✅ Completion callbacks for auto-progression
- ✅ Fire-and-forget async execution via asyncio.create_task()

**Configuration**:
```python
# Unit-test usage only
executor = MockAgentExecutor(execution_delay_seconds=3.0)

# Set completion handler
async def on_complete(work_item_id, board_id, success):
    print(f"Agent execution completed: {success}")

executor.set_completion_handler(on_complete, "board-1")
```

**Use Cases** (Unit Tests Only):
- Isolated board automation handler testing (test_board_automation_scenario_*.py)
- Handler logic validation without full execution chain
- Custom test scenarios with specific executor behavior

**Bootstrap Usage**: ❌ Not used. Use ExecutionServiceAgentExecutor for all simulation/E2E testing through SimulationApplicationBootstrap.

---

#### 24. MockEventEmitter (Legacy)
**File**: `../secondary/mock_event_emitter.py`
**Purpose**: Basic event emission mock (deprecated in favor of CapturingMockEventEmitter)

**Note**: Use CapturingMockEventEmitter for new tests. This adapter is maintained for backward compatibility.

---

## Thread Safety in Mock Adapters

Mock adapters replicate production storage adapter concurrency semantics using `threading.Lock()` for thread-safe access. This ensures multi-threaded code is tested realistically without introducing subtle race conditions.

### Adapters with Thread Safety

The following adapters protect concurrent access with internal locks:

1. **InMemoryStorageAdapter** - File/object storage with atomic operations
2. **InMemoryQueueService** - Queue operations (enqueue, dequeue, position updates)
3. **InMemoryEventStore** - Event persistence and retrieval (if applicable)

### Design Principle

Mock adapters use the same thread-safety pattern as production adapters:
- Each adapter maintains internal state in dictionaries/lists
- All state-changing operations (`upload`, `download`, `delete`, `enqueue`, etc.) are protected by `with self._lock:`
- Read-only operations (`exists`, `list_files`, `get_queue_entries`) also acquire the lock for consistent snapshots
- No external locks required - thread safety is internal to the adapter

### Concurrent Testing Example

```python
@pytest.mark.asyncio
async def test_concurrent_storage_operations():
    """Test that concurrent storage operations don't corrupt data."""
    storage = InMemoryStorageAdapter()

    # Setup initial data
    await storage.upload("file-1", b"initial content")

    # Race: concurrent operations
    results = await asyncio.gather(
        storage.upload("file-1", b"updated content"),
        storage.download("file-1")
    )

    # Download returns consistent snapshot (not partial data)
    download_result = results[1]
    assert download_result in [b"initial content", b"updated content"]

    # No corruption or partial reads
    assert len(download_result) > 0
```

### Testing Concurrent Failures

```python
@pytest.mark.asyncio
async def test_concurrent_delete_race():
    """Test that delete operations are atomic even under concurrency."""
    storage = InMemoryStorageAdapter()
    await storage.upload("file-1", b"content")

    # Two concurrent deletes
    results = await asyncio.gather(
        storage.delete("file-1"),  # Should succeed
        storage.delete("file-1"),  # Should fail with ResourceNotFoundError
        return_exceptions=True
    )

    # One succeeds, one raises error
    assert any(isinstance(r, Exception) for r in results)
    assert any(r is None for r in results)

    # File must not exist
    with pytest.raises(ResourceNotFoundError):
        await storage.download("file-1")
```

### Production Behavior Fidelity

Thread-safe mock adapters ensure:
- ✅ Concurrent tests don't produce flaky/racy results
- ✅ Same concurrency semantics as production (S3, etc.)
- ✅ Error conditions are tested realistically (race conditions, concurrent failures)
- ✅ Multi-threaded code paths are covered (agents executing in parallel)

See `tests/unit/adapters/testing/test_adapter_error_handling.py` for comprehensive concurrent access tests.

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
