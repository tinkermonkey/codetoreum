# Comprehensive Output Ports Reference

**Status**: Complete inventory of all 28+ output port interfaces in Codetoreum Gen 2

## Overview

This document provides a complete reference for all output ports in the Codetoreum system. Ports define the interfaces through which the core domain interacts with external systems, following the Dependency Inversion Principle of hexagonal architecture.

## Port Categories and Index

### 1. **Core Orchestration Ports** (3)
- IAgentExecutor - Agent execution interface
- ILLMProvider - Large Language Model provider
- IContainer - Container orchestration

### 2. **Vendor-Agnostic Integration Ports** (8)
- IBoardService - Project board management
- IWorkItemService - Work item CRUD operations
- ICodeReviewService - Code review lifecycle
- IDiscussionAdapter - Comment/discussion threads
- IVersionControlService - Git operations
- IIdentityService - User identity (bot vs human)
- IPipelineLockService - Distributed workflow locking
- IEventEmitter - Event publication

### 3. **Workflow/Repair Cycle Ports** (3)
- IRepairCycle - Repair cycle orchestration
- IRepairCycleCheckpointStore - Repair cycle state persistence
- IAgentContainerRecoveryService - Container failure recovery

### 4. **Queue and Lock Management Ports** (2)
- IPipelineQueueService - Work item queue management
- IPipelineLockService - Pipeline mutual exclusion

### 5. **Persistence Ports** (4)
- IEventStore - Event sourcing and replay
- IStorage - File and object storage
- IRepository - Git repository operations
- IWorkflowConfigService - Workflow configuration storage

### 6. **System Configuration Ports** (1)
- IMessageBroker - Distributed event publication

### 7. **Observability/Infrastructure Ports** (3)
- IMetrics - Metrics collection
- IEncryptionService - Data encryption/decryption
- IMonitoredService - Service lifecycle monitoring (mixin)

### 8. **Legacy/Specialized Ports** (2)
- ITicketSystem - Legacy ticket system (being replaced by vendor-agnostic ports)
- INotifier - Notification delivery

---

## Detailed Port Specifications

### Core Orchestration Ports

#### 1. IAgentExecutor
**File**: `agent_executor.py`
**Purpose**: Execute specialized AI agents to perform work on containers
**Category**: Core LLM Orchestration

**Core Methods**:
- `execute_agent()` - Run agent with context files and capture output
- `get_execution_status()` - Check agent execution status

**Key Implementations**:
- ClaudeCodeExecutor (production)
- MockAgentExecutor (testing)

**Dependencies**: IContainer, ILLMProvider (indirectly through container)

---

#### 2. ILLMProvider
**File**: `llm_provider.py`
**Purpose**: Abstract interface for LLM providers (Claude, OpenAI, etc.)
**Category**: Core Agent Integration

**Core Methods**:
- `execute()` - Run a simple completion
- `execute_with_tools()` - Execution with tool definitions
- `stream()` - Stream completions
- `get_model_info()` - Query model capabilities
- `count_tokens()` - Token usage calculation

**Data Classes**:
- ExecutionContext, ExecutionResult
- ToolDefinition, ToolCall
- StreamChunk, UsageStats

**Key Implementations**:
- ClaudeCodeAdapter (containerized execution)
- MockLLMAdapter (deterministic testing)
- AiderAdapter, OpenAIProvider (alternative providers)

**Dependencies**: None (standalone)

---

#### 3. IContainer
**File**: `container.py`
**Purpose**: Container runtime abstraction for agent execution environments
**Category**: Core Infrastructure

**Core Methods**:
- `create_container()` - Create new container instance
- `start_container()` - Start container execution
- `run_command()` - Execute command in container
- `get_container_status()` - Check running status
- `stop_container()` - Stop container
- `cleanup()` - Remove container

**Data Classes**:
- ContainerResult (exit code, stdout, stderr)
- ContainerStatus (RUNNING, STOPPED, ERROR)

**Key Implementations**:
- DockerContainerAdapter (production)
- FakeContainerAdapter (testing/simulation)
- KubernetesAdapter (alternative)

**Dependencies**: None (standalone)

---

### Vendor-Agnostic Integration Ports

#### 4. IBoardService
**File**: `board_service.py`
**Purpose**: Project board management (columns, work items, reconciliation)
**Extends**: IEventEmitter, IMonitoredService
**Events**: `workitem.column_changed`, `board.reconciled`

**Query Methods**:
- `get_board()` - Retrieve board structure
- `get_columns()` - List all columns
- `get_items_in_column()` - Work items in specific column
- `get_item_position()` - Column and position of work item

**Command Methods**:
- `move_item_to_column()` - Move work item between columns
- `reconcile_board()` - Sync board structure with external system

**Data Classes**:
- ProjectBoard, BoardColumn, WorkItemPosition
- ReconciliationResult

**Key Implementations**:
- GitHubBoardAdapter (GitHub Projects v2)
- MockBoardAdapter (testing)
- JiraBoardAdapter (Jira boards)

**Use Case**: Workflow orchestrator monitors column changes to trigger next stage

---

#### 5. IWorkItemService
**File**: `work_item_service.py`
**Purpose**: Work item CRUD and querying
**Extends**: IEventEmitter, IMonitoredService
**Events**: `workitem.created`, `workitem.updated`

**Query Methods**:
- `get_work_item()` - Fetch individual work item
- `get_work_items_by_status()` - Filter by status
- `get_work_items_by_column()` - Filter by board column

**Command Methods**:
- `create_work_item()` - Create new issue/task
- `update_work_item()` - Update work item fields

**Key Implementations**:
- GitHubWorkItemAdapter (GitHub Issues)
- MockWorkItemAdapter (testing)
- JiraWorkItemAdapter (Jira issues)

**Use Case**: Create issues, fetch issue details, batch updates

---

#### 6. ICodeReviewService
**File**: `code_review_service.py`
**Purpose**: Code review lifecycle (PR approval, change requests)
**Extends**: IEventEmitter, IMonitoredService
**Events**: `review.status_changed`, `review.comment_added`

**Query Methods**:
- `get_review_for_work_item()` - Find PR for issue
- `get_review_status()` - OPEN, APPROVED, CHANGES_REQUESTED, MERGED
- `get_review_comments()` - Comments from reviewers

**Command Methods**:
- `request_changes()` - Add comment requesting changes
- `approve()` - Approve review

**Key Implementations**:
- GitHubCodeReviewAdapter (GitHub PRs)
- MockCodeReviewAdapter (testing)
- GitLabCodeReviewAdapter (GitLab MRs)

**Use Case**: Orchestrator manages review cycles, tracks approval status

---

#### 7. IDiscussionAdapter
**File**: `discussion_adapter.py`
**Purpose**: Comment threads and discussion monitoring
**Extends**: IEventEmitter
**Events**: `comment.needs_response`, `comment.posted`
**Note**: Monitoring is work-item-specific, not project-wide

**Query Methods**:
- `get_thread()` - Retrieve discussion thread for work item
- `add_comment()` - Post comment (optionally reply to parent)

**Monitoring Methods** (work-item-specific):
- `start_monitoring()` - Watch for new comments on specific work item
- `stop_monitoring()` - Stop watching

**Data Classes**:
- DiscussionThread, Comment
- DiscussionMonitoringConfig

**Key Implementations**:
- GitHubDiscussionAdapter (GitHub issue comments)
- MockDiscussionAdapter (testing)

**Use Case**: Agent responds to reviewer feedback in comments

---

#### 8. IVersionControlService
**File**: `version_control_service.py`
**Purpose**: Git operations (clone, branch, commit, push)
**Note**: Synchronous, no event emission, no monitoring
**Events**: None

**Command Methods**:
- `clone_repository()` - Clone repo to local path
- `pull_latest()` - Fetch latest changes
- `checkout()` - Switch branches
- `commit()` - Create commit
- `push()` - Push to remote

**Query Methods**:
- `get_repository()` - Retrieve repository metadata

**Key Implementations**:
- GitVersionControlAdapter (Git CLI)
- MockVersionControlAdapter (testing)

**Use Case**: Agent working directory setup, commit/push workflow

---

#### 9. IIdentityService
**File**: `identity_service.py`
**Purpose**: Identify bot vs human users
**Note**: Query-only, no event emission, no monitoring
**Events**: None

**Query Methods**:
- `is_bot_user()` - Check if username is bot
- `get_bot_username()` - Retrieve configured bot account
- `get_human_users()` - Filter list to humans only

**Configuration**:
- `configure()` - Set bot username patterns

**Key Implementations**:
- IdentityService (static configuration)
- MockIdentityService (testing)

**Use Case**: Determine if comment author is human (needs response) or bot (skip)

---

#### 10. IPipelineLockService
**File**: `pipeline_lock_service.py`
**Purpose**: Distributed workflow locking for mutual exclusion
**Extends**: IEventEmitter
**Events**: `lock.acquired`, `lock.released`, `lock.stale_detected`

**Query Methods**:
- `get_lock()` - Check if work item has lock
- `get_all_locks()` - List all active locks

**Command Methods**:
- `try_acquire_lock()` - Attempt to acquire lock (returns bool, reason)
- `release_lock()` - Release lock

**Data Classes**:
- PipelineLock (project_id, board_id, work_item_id, status)

**Key Implementations**:
- RedisPipelineLockService (production)
- MockPipelineLockService (testing)

**Use Case**: Prevent concurrent processing of same work item across instances

---

#### 11. IEventEmitter
**File**: `event_emitter.py`
**Purpose**: Event publication and subscription (mixin/protocol)
**Category**: Infrastructure/Mixin

**Methods**:
- `on()` - Subscribe to event type
- `off()` - Unsubscribe from event
- `emit()` - Publish event to subscribers

**Implementations**:
- SimpleEventEmitter (in-memory)
- MockEventEmitter (testing, with assertion helpers)

**Usage**: Mixed into other services (IBoardService, IWorkItemService, etc.)

---

### Workflow/Repair Cycle Ports

#### 12. IRepairCycle
**File**: `repair_cycle_service.py`
**Purpose**: Orchestrate repair cycles for agent failure recovery
**Category**: Workflow Management

**Core Methods**:
- `start_repair_cycle()` - Initiate repair attempt
- `get_repair_status()` - Check repair progress
- `complete_repair_cycle()` - Mark repair complete
- `log_repair_step()` - Record repair attempt

**Data Classes**:
- RepairCycleContext (failing execution, error, recovery attempts)

**Key Implementations**:
- RepairCycleOrchestrator (production)
- MockRepairCycleAdapter (testing)

**Use Case**: When agent execution fails, attempt recovery with different prompts

---

#### 13. IRepairCycleCheckpointStore
**File**: `repair_cycle_checkpoint_store.py`
**Purpose**: Persist repair cycle state for recovery across restarts
**Category**: Persistence

**Core Methods**:
- `save_checkpoint()` - Persist repair cycle state
- `get_checkpoint()` - Retrieve saved state
- `delete_checkpoint()` - Clean up completed repairs

**Key Implementations**:
- InMemoryRepairCycleCheckpointStore (testing)
- RedisRepairCycleCheckpointStore (production)

**Use Case**: Resume repair attempts if orchestrator restarts

---

#### 14. IAgentContainerRecoveryService
**File**: `container_recovery.py`
**Purpose**: Recover agent containers from network/crash failures
**Category**: Reliability

**Core Methods**:
- `assess_recovery()` - Determine if container can be recovered
- `recover_container()` - Attempt recovery steps
- `get_recovery_status()` - Check recovery state

**Data Classes**:
- ContainerMetadata, RecoveryAssessment, RecoveryResult

**Key Implementations**:
- DockerContainerRecoveryService (production)
- MockContainerRecoveryAdapter (testing)

**Use Case**: Handle container crashes during long-running agent execution

---

### Queue and Lock Management Ports

#### 15. IPipelineQueueService
**File**: `pipeline_queue_service.py`
**Purpose**: Work item queue for ordered processing
**Category**: Workflow Management

**Core Methods**:
- `enqueue()` - Add work item to queue
- `dequeue()` - Remove from front of queue
- `get_queue_position()` - Position in queue
- `get_queue_length()` - Total items in queue
- `requeue()` - Move to back after processing

**Data Classes**:
- PipelineQueueEntry (work_item_id, position, enqueued_at)

**Key Implementations**:
- InMemoryPipelineQueueService (testing)
- RedisPipelineQueueService (production)

**Use Case**: Ensure work items are processed in order

---

### Persistence Ports

#### 16. IEventStore
**File**: `event_store.py`
**Purpose**: Event sourcing storage for audit trail and replay
**Category**: Persistence

**Core Methods**:
- `append_event()` - Store domain event
- `get_events_for_aggregate()` - Retrieve events for entity
- `get_all_events()` - Get event stream
- `subscribe()` - Watch for new events

**Key Implementations**:
- RedisEventStore (production - Redis Streams)
- PostgreSQLEventStore (alternative)
- InMemoryEventStore (testing)

**Use Case**: Complete audit trail, event replay for debugging

---

#### 17. IStorage
**File**: `storage.py`
**Purpose**: File and object storage (artifacts, logs, code)
**Category**: Persistence

**Core Methods**:
- `put_object()` - Upload file
- `get_object()` - Download file
- `delete_object()` - Remove file
- `list_objects()` - Directory listing

**Data Classes**:
- StorageObject (key, size, modified_at)

**Key Implementations**:
- S3StorageAdapter (AWS S3, production)
- FilesystemStorageAdapter (local files)
- InMemoryStorageAdapter (testing)

**Use Case**: Store agent outputs, logs, code snippets

---

#### 18. IRepository
**File**: `repository.py`
**Purpose**: Source code repository operations
**Category**: Persistence

**Core Methods**:
- `clone()` - Clone repository
- `create_branch()` - Create new branch
- `checkout()` - Switch branches
- `commit()` - Commit changes
- `push()` - Push to remote
- `get_diff()` - Get diff between commits
- `merge()` - Merge branches

**Key Implementations**:
- GitRepositoryAdapter (Git CLI, production)
- InMemoryRepositoryAdapter (testing)

**Use Case**: Version control for workflow-generated code

---

#### 19. IWorkflowConfigService
**File**: `workflow_config_service.py`
**Purpose**: Persist and retrieve workflow definitions
**Category**: Persistence

**Core Methods**:
- `get_workflow_config()` - Retrieve workflow definition
- `save_workflow_config()` - Store workflow definition
- `list_workflows()` - Get all workflows

**Key Implementations**:
- DatabaseWorkflowConfigService (PostgreSQL)
- InMemoryWorkflowConfigService (testing)

**Use Case**: Store pipeline definitions, stage configs

---

### System Configuration Ports

#### 20. IMessageBroker
**File**: `message_broker.py`
**Purpose**: Distributed pub/sub for multi-instance deployments
**Category**: Infrastructure

**Core Methods**:
- `initialize()` - Set up connection
- `publish_event()` - Broadcast domain event
- `publish_control_message()` - Send control signals

**Key Implementations**:
- RedisMessageBroker (production)
- InMemoryMessageBroker (testing)

**Use Case**: Share events across multiple orchestrator instances

---

### Observability/Infrastructure Ports

#### 21. IMetrics
**File**: `metrics.py`
**Purpose**: Metrics collection and reporting
**Category**: Observability

**Core Methods**:
- `increment_counter()` - Increment counter metric
- `set_gauge()` - Set gauge value
- `record_histogram()` - Record distribution
- `record_timer()` - Time operation

**Data Classes**:
- MetricData (name, value, timestamp, tags)

**Key Implementations**:
- PrometheusMetrics (production)
- InMemoryMetricsAdapter (testing)

**Use Case**: Performance monitoring, throughput tracking

---

#### 22. IEncryptionService
**File**: `encryption_service.py`
**Purpose**: Encrypt/decrypt sensitive data
**Category**: Security

**Core Methods**:
- `encrypt()` - Encrypt plaintext
- `decrypt()` - Decrypt ciphertext
- `get_key_id()` - Current key identifier

**Data Classes**:
- EncryptionError, DecryptionError (exceptions)

**Key Implementations**:
- KMSEncryptionService (AWS KMS)
- SimpleEncryptionService (in-process)
- MockEncryptionService (testing)

**Use Case**: Encrypt agent credentials, API keys

---

#### 23. IMonitoredService
**File**: `monitoring.py`
**Purpose**: Service lifecycle monitoring (mixin/protocol)
**Category**: Infrastructure/Mixin

**Methods**:
- `start_monitoring()` - Begin monitoring project
- `stop_monitoring()` - End monitoring
- `get_monitoring_status()` - Current status

**Data Classes**:
- MonitoringConfig, MonitoringStatus
- MonitoringState (STOPPED, STARTING, ACTIVE, STOPPING, ERROR)

**Usage**: Mixed into event-emitting services

---

### Legacy/Specialized Ports

#### 24. ITicketSystem
**File**: `ticket_system.py`
**Purpose**: Legacy ticket system (deprecated in favor of vendor-agnostic ports)
**Status**: Maintained for backward compatibility
**Being Replaced By**: IBoardService, IWorkItemService, ICodeReviewService

**Core Methods**:
- `get_work_item()` - Fetch ticket
- `update_work_item()` - Update ticket
- `create_comment()` - Post comment
- `get_comments()` - Retrieve comments

**Key Implementations**:
- GitHubTicketAdapter (GitHub, legacy)
- InMemoryTicketAdapter (testing)

**Migration Path**: Use vendor-agnostic ports instead (IBoardService, IWorkItemService)

---

#### 25. INotifier
**File**: `notifier.py`
**Purpose**: Send notifications to users
**Category**: Communication

**Core Methods**:
- `send_notification()` - Deliver notification
- `send_batch()` - Send multiple notifications
- `get_status()` - Check delivery status

**Data Classes**:
- Notification (channel, recipient, subject, body)
- NotificationChannel (EMAIL, SLACK, WEBHOOK)
- NotificationResult (delivery_status)

**Key Implementations**:
- SlackNotifier (production)
- EmailNotifier (production)
- MockNotifierAdapter (testing)

**Use Case**: Notify users of workflow completion, approvals needed

---

## Port Summary Table

| Port Name | File | Category | Status | Dependencies |
|-----------|------|----------|--------|---|
| IAgentExecutor | agent_executor.py | Core | Active | IContainer |
| ILLMProvider | llm_provider.py | Core | Active | None |
| IContainer | container.py | Core | Active | None |
| IBoardService | board_service.py | Integration | Active | IEventEmitter, IMonitoredService |
| IWorkItemService | work_item_service.py | Integration | Active | IEventEmitter, IMonitoredService |
| ICodeReviewService | code_review_service.py | Integration | Active | IEventEmitter, IMonitoredService |
| IDiscussionAdapter | discussion_adapter.py | Integration | Active | IEventEmitter |
| IVersionControlService | version_control_service.py | Integration | Active | None |
| IIdentityService | identity_service.py | Integration | Active | None |
| IPipelineLockService | pipeline_lock_service.py | Integration | Active | IEventEmitter |
| IEventEmitter | event_emitter.py | Infrastructure | Active | None |
| IRepairCycle | repair_cycle_service.py | Workflow | Active | IRepairCycleCheckpointStore |
| IRepairCycleCheckpointStore | repair_cycle_checkpoint_store.py | Persistence | Active | None |
| IAgentContainerRecoveryService | container_recovery.py | Workflow | Active | IContainer |
| IPipelineQueueService | pipeline_queue_service.py | Queue | Active | None |
| IEventStore | event_store.py | Persistence | Active | None |
| IStorage | storage.py | Persistence | Active | None |
| IRepository | repository.py | Persistence | Active | None |
| IWorkflowConfigService | workflow_config_service.py | Persistence | Active | None |
| IMessageBroker | message_broker.py | Infrastructure | Active | None |
| IMetrics | metrics.py | Observability | Active | None |
| IEncryptionService | encryption_service.py | Security | Active | None |
| IMonitoredService | monitoring.py | Infrastructure | Mixin | None |
| ITicketSystem | ticket_system.py | Integration | Legacy | None |
| INotifier | notifier.py | Communication | Active | None |

---

## Design Principles

### 1. **Vendor-Agnostic Interfaces**
New ports (IWorkItemService, IBoardService, etc.) use domain-neutral terminology. No vendor-specific concepts in interfaces.

### 2. **Event-Based External Change Detection**
Services extend IEventEmitter to emit events when external systems change. Orchestrator subscribes to detect work (no polling).

### 3. **Consistent Monitoring Lifecycle**
Event-emitting services implement IMonitoredService for consistent start/stop monitoring pattern.

### 4. **Clear Error Semantics**
Some methods return (bool, reason) for error cases (e.g., `try_acquire_lock`) instead of exceptions. Others use exceptions for exceptional conditions.

### 5. **Mixin/Protocol Composition**
Multiple interfaces can be mixed together:
```python
# IBoardService extends both
class IBoardService(IEventEmitter, IMonitoredService):
    ...
```

### 6. **Synchronous Queries, Async Commands**
Queries are often synchronous (return cached data). Commands are async (may call external services).

---

## Migration Guide: Gen 1 → Gen 2

### Old (Gen 1) Architecture
```
ITicketSystem (monolithic)
├── Issue management
├── Comment threads
├── Work item lifecycle
└── Code reviews (partially)
```

### New (Gen 2) Architecture
```
Vendor-Agnostic Ports:
├── IBoardService      (columns, reconciliation)
├── IWorkItemService   (CRUD, querying)
├── ICodeReviewService (approval, status)
├── IDiscussionAdapter (comments, threads)
├── IPipelineLockService (mutual exclusion)
├── IVersionControlService (git ops)
└── IIdentityService   (user classification)
```

### Migration Strategy
1. **Implement new port adapters** (GitHub, Jira, etc.)
2. **Write contract tests** validating both old and new adapters
3. **Gradual transition** in orchestrator code
4. **Keep ITicketSystem** for backward compatibility during transition
5. **Deprecate ITicketSystem** after migration complete

---

## Contract Testing

Each port should have a contract test class that validates implementations:

```python
# Example: TestBoardServiceContract
class TestBoardServiceContract(ABC):
    @abstractmethod
    async def get_board_adapter(self) -> IBoardService:
        pass

    async def test_get_board_returns_valid_structure(self):
        adapter = await self.get_board_adapter()
        board = await adapter.get_board("proj-1", "board-1")
        assert board.id
        assert board.columns
```

Benefits:
- New adapters can verify compliance with interface
- Discover contract violations early
- Multiple implementations can be tested identically

---

## Next Steps

1. **Implement missing adapters** (Jira, Linear, GitLab, etc.)
2. **Add contract tests** for each adapter
3. **Integrate event bus** with event-emitting services
4. **Add resilience patterns** (circuit breakers, rate limiting)
5. **Document adapter-specific configuration**
6. **Create adapter decision matrix** for users

---

## See Also

- `NEW_INTERFACES_QUICK_REFERENCE.md` - Quick reference for main 8 ports
- `REPAIR_CYCLE_CONTRACT.md` - Repair cycle service specification
- `/design/output_ports/` - Individual port design documents (legacy)
- `/src/codetoreum/ports/output/` - Port implementations
