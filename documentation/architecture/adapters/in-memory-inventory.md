# In-Memory Adapter Inventory

Complete catalog of all in-memory and file-backed adapters in the Codetoreum codebase. This document is the single source of truth for which adapters are suitable for different deployment contexts (unit tests, integration tests, simulation, local dev, production).

**Note on restart fragility**: An adapter is "restart-fragile" if losing in-memory state would break tests, workflows, or data integrity. File-backed adapters survive process restarts; in-memory adapters lose state on exit.

---

## File-Backed Adapters (Persist Across Process Restarts)

These adapters use JSONL files for persistence with fsync for durability. Single-process guard via PID lockfile. Suitable for local dev and bootstrap harness.

| Adapter | Port Interface | Location | Purpose | Format | Notes |
|---------|---|---------|---------|--------|-------|
| `FileBackedDistributedLock` | `IDistributedLock` | `adapters/secondary/file_backed_distributed_lock.py` | Distributed lock with TTL and metadata | JSONL + fsync | PID lockfile ensures single-process access; survives restarts; replays log on startup |
| `FileBackedPipelineQueue` | `IPipelineQueue` | `adapters/secondary/file_backed_pipeline_queue.py` | FIFO queue for work item coordination | JSONL + fsync | PID lockfile ensures single-process access; survives restarts; replays log on startup |

---

## Secondary (Output Port) In-Memory Adapters

These implement secondary (outbound) port interfaces and are used by the application layer.

### Lock & Queue Services

| Adapter | Port Interface | Location | Restart-Fragile | Status | Decision |
|---------|---|---------|---------|--------|----------|
| `InMemoryLockService` | `IPipelineLockService` | `adapters/secondary/in_memory_pipeline_lock_service.py` | ✅ YES | Deprecated | DELETE — superseded by `FileBackedDistributedLock` + `FileBackedPipelineQueue` (issue #904) |
| `InMemoryQueueLockService` | `IQueuedPipelineLockService` | `adapters/secondary/in_memory_queue_lock_service.py` | ✅ YES | Deprecated | DELETE — superseded by separate lock + queue (issue #904) |

### Code Review

| Adapter | Port Interface | Location | Restart-Fragile | Status | Decision |
|---------|---|---------|---------|--------|----------|
| `MockCodeReviewAdapter` | `ICodeReviewService` | `adapters/secondary/mock_code_review_adapter.py` | ✅ YES | Active | KEEP EPHEMERAL — unit test mock; no persistence needed |

### Repository & Identity

| Adapter | Port Interface | Location | Restart-Fragile | Status | Decision |
|---------|---|---------|---------|--------|----------|
| `InMemoryUserRepository` | `IUserRepository` | `adapters/secondary/in_memory_user_repository.py` | ✅ YES | Active | KEEP EPHEMERAL — initialized per test from config |
| `InMemoryApiKeyRepository` | `IApiKeyRepository` | `adapters/secondary/in_memory_api_key_repository.py` | ✅ YES | Active | KEEP EPHEMERAL — test fixture; no multi-process use |

### Event Emission

| Adapter | Port Interface | Location | Restart-Fragile | Status | Decision |
|---------|---|---------|---------|--------|----------|
| `MockEventEmitter` | `IEventEmitter` | `adapters/secondary/mock_event_emitter.py` | ❌ NO | Active | KEEP EPHEMERAL — test double; captures events during test; discarded after |
| `CapturingMockEventEmitter` | `IEventEmitter` | `adapters/testing/capturing_mock_event_emitter.py` | ❌ NO | Active | KEEP EPHEMERAL — test observation tool; scoped to single test |

---

## Testing (Input Port Adapters)

These implement primary (input) port interfaces for testing. Located in `adapters/primary/input_port_adapters/mock/` and `adapters/testing/`.

### Input Port Mocks (Primary Adapters)

| Adapter | Implements | Location | Restart-Fragile | Decision |
|---------|---|---------|---------|----------|
| `MockAgentCommandAdapter` | Agent command input port | `primary/input_port_adapters/mock/mock_agent_command_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockAgentQueryAdapter` | Agent query input port | `primary/input_port_adapters/mock/mock_agent_query_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockAuditQueryAdapter` | Audit query input port | `primary/input_port_adapters/mock/mock_audit_query_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockConfigCommandAdapter` | Config command input port | `primary/input_port_adapters/mock/mock_config_command_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockConfigQueryAdapter` | Config query input port | `primary/input_port_adapters/mock/mock_config_query_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockConfigServiceAdapter` | Config service input port | `primary/input_port_adapters/mock/mock_config_service_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockExecutionCommandAdapter` | Execution command input port | `primary/input_port_adapters/mock/mock_execution_command_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockExecutionQueryAdapter` | Execution query input port | `primary/input_port_adapters/mock/mock_execution_query_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockLoggerAdapter` | Logger input port | `primary/input_port_adapters/mock/mock_logger_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockMetricsQueryAdapter` | Metrics query input port | `primary/input_port_adapters/mock/mock_metrics_query_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockOrchestrationCommandAdapter` | Orchestration command input port | `primary/input_port_adapters/mock/mock_orchestration_command_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockTaskQueryAdapter` | Task query input port | `primary/input_port_adapters/mock/mock_task_query_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockWorkItemCommandAdapter` | Work item command input port | `primary/input_port_adapters/mock/mock_work_item_command_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockWorkItemQueryAdapter` | Work item query input port | `primary/input_port_adapters/mock/mock_work_item_query_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockWorkflowCommandAdapter` | Workflow command input port | `primary/input_port_adapters/mock/mock_workflow_command_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockWorkflowDefinitionCommandAdapter` | Workflow definition command input port | `primary/input_port_adapters/mock/mock_workflow_definition_command_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockWorkflowQueryAdapter` | Workflow query input port | `primary/input_port_adapters/mock/mock_workflow_query_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockWorkflowRunQueryAdapter` | Workflow run query input port | `primary/input_port_adapters/mock/mock_workflow_run_query_adapter.py` | ❌ NO | KEEP EPHEMERAL |
| `MockWorkspaceQueryAdapter` | Workspace query input port | `primary/input_port_adapters/mock/mock_workspace_query_adapter.py` | ❌ NO | KEEP EPHEMERAL |

### Testing (Secondary Output Adapters)

| Adapter | Port Interface | Location | Restart-Fragile | Decision |
|---------|---|---------|---------|----------|
| `InMemoryActiveWorkflowRunRegistry` | `IActiveWorkflowRunRegistry` | `adapters/testing/in_memory_active_workflow_run_registry.py` | ✅ YES | KEEP EPHEMERAL — simulation fixture |
| `InMemoryAgentRepository` | `IAgentRepository` | `adapters/testing/in_memory_agent_repository.py` | ❌ NO | KEEP EPHEMERAL — initialized from domain model |
| `InMemoryCheckpointStore` | `IRepairCycleCheckpointStore` | `adapters/testing/in_memory_checkpoint_store.py` | ✅ YES | KEEP EPHEMERAL — repair cycle state |
| `InMemoryCodeReviewAdapter` | `ICodeReviewService` | `adapters/testing/in_memory_code_review_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation mock |
| `InMemoryConfigStore` | `IConfigStore` | `adapters/testing/in_memory_config_store.py` | ❌ NO | KEEP EPHEMERAL — initialized from config |
| `InMemoryEventStore` | `IEventStore` | `adapters/testing/in_memory_event_store.py` | ✅ YES | KEEP EPHEMERAL — test event audit trail |
| `InMemoryFailedEventStore` | `IFailedEventStore` | `adapters/testing/in_memory_failed_event_store.py` | ✅ YES | KEEP EPHEMERAL — DLQ for test observation |
| `InMemoryMessageBroker` | `IMessageBroker` | `adapters/testing/in_memory_message_broker.py` | ✅ YES | KEEP EPHEMERAL — simulation message transport |
| `InMemoryMetricsAdapter` | `IMetricsAdapter` | `adapters/testing/in_memory_metrics_adapter.py` | ✅ YES | KEEP EPHEMERAL — test metric capture |
| `InMemoryQueueService` | `IQueueService` | `adapters/testing/in_memory_queue_service.py` | ✅ YES | KEEP EPHEMERAL — simulation queue |
| `InMemoryRepositoryAdapter` | `IVersionControlService` | `adapters/testing/in_memory_repository_adapter.py` | ✅ YES | KEEP EPHEMERAL — mock git operations |
| `InMemoryTicketAdapter` | `ITicketSystem` | `adapters/testing/in_memory_ticket_adapter.py` | ✅ YES | KEEP EPHEMERAL — mock board operations |
| `InMemoryTracer` | `ITracer` | `adapters/testing/in_memory_tracer.py` | ❌ NO | KEEP EPHEMERAL — test observation |
| `InMemoryVersionControlService` | `IVersionControlService` | `adapters/testing/in_memory_version_control_service.py` | ✅ YES | KEEP EPHEMERAL — simulation VCS |
| `InMemoryWorkItemBranchTracker` | `IWorkItemBranchTracker` | `adapters/testing/in_memory_work_item_branch_tracker.py` | ✅ YES | KEEP EPHEMERAL — branch tracking for tests |
| `InMemoryWorkflowConfigService` | `IWorkflowConfigService` | `adapters/testing/in_memory_workflow_config_service.py` | ❌ NO | KEEP EPHEMERAL — initialized from config |

### Testing (Mock Orchestration Adapters)

| Adapter | Port Interface | Location | Restart-Fragile | Decision |
|---------|---|---------|---------|----------|
| `MockAgentExecutor` | `IAgentExecutor` | `adapters/testing/mock_agent_executor.py` | ✅ YES | KEEP EPHEMERAL — simulation agent executor |
| `MockBoardAdapter` | `IBoardService` | `adapters/testing/mock_board_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation board operations |
| `MockBranchResolutionAdapter` | `IBranchResolutionService` | `adapters/testing/mock_branch_resolution_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation branch resolver |
| `MockCIPipelineAdapter` | `ICIPipelineService` | `adapters/testing/mock_ci_pipeline_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation CI operations |
| `MockClaudeCodeAdapter` | `ICodingAgent` | `adapters/testing/mock_claude_code_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation agent execution |
| `MockContainerRecoveryAdapter` | `IContainerRecoveryService` | `adapters/testing/mock_container_recovery_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation recovery |
| `MockDiscussionAdapter` | `IDiscussionAdapter` | `adapters/testing/mock_discussion_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation discussions |
| `MockEnvironmentRepairAdapter` | `IEnvironmentRepairService` | `adapters/testing/mock_environment_repair_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation repair |
| `MockNotifierAdapter` | `INotifier` | `adapters/testing/mock_notifier_adapter.py` | ❌ NO | KEEP EPHEMERAL — test notification capture |
| `MockPRReviewCycleAdapter` | `IPRReviewCycleService` | `adapters/testing/mock_pr_review_cycle_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation review cycle |
| `MockProjectManagerAdapter` | `IProjectManagerService` | `adapters/testing/mock_project_manager_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation project management |
| `MockRepairCycleAdapter` | `IRepairCycleService` | `adapters/testing/mock_repair_cycle_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation repair cycle |
| `MockReviewCycleAdapter` | `IReviewCycleService` | `adapters/testing/mock_review_cycle_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation review cycle |
| `MockSystemicAnalysisAdapter` | `ISystemicAnalysisService` | `adapters/testing/mock_systemic_analysis_adapter.py` | ✅ YES | KEEP EPHEMERAL — simulation analysis |
| `MockWorkItemService` | `IWorkItemService` | `adapters/testing/mock_work_item_service.py` | ✅ YES | KEEP EPHEMERAL — simulation work item operations |

---

## Decisions Summary

### File-Backed (Persist Across Restarts)
- `FileBackedDistributedLock` — for pipeline lock coordination in local dev / harness
- `FileBackedPipelineQueue` — for work item queue coordination in local dev / harness

### Keep Ephemeral (No Persistence)
- **All input port mocks** (primary adapters) — test doubles; discarded after test
- **All event emission mocks** — test observation; test-scoped lifetime
- **Most testing adapters** — simulation fixtures; recreated per test

### Delete
- `InMemoryLockService` — superseded by separated lock + queue ports (issue #904)
- `InMemoryQueueLockService` — superseded by separated lock + queue ports (issue #904)

---

## Deployment Contexts

### Unit Tests
- Use input port mocks (`MockAgentCommandAdapter`, etc.)
- Use event emission mocks (`MockEventEmitter`)
- Use simple in-memory adapters (`InMemoryConfigStore`)
- **File-backed**: Not needed; tests have short lifetime

### Integration Tests
- Use in-memory adapters from `adapters/testing/`
- May use file-backed adapters if state needs to survive across process restarts
- **File-backed**: Consider for distributed lock / queue tests that need persistence

### Simulation Testing
- Use all adapters from `adapters/testing/`
- Use `FileBackedDistributedLock` and `FileBackedPipelineQueue` if simulating restart scenarios
- Bootstrap harness uses file-backed adapters to test production paths

### Local Development
- Use file-backed adapters for lock/queue coordination
- Use in-memory adapters for everything else
- State persists across process restarts in `/tmp/codetoreum/`

### Production
- **No in-memory adapters** — all state must be persistent
- Use production adapters: `RedisDistributedLock`, `RedisPipelineQueue`, `GitHubBoardAdapter`, etc.
- Use persistent stores: PostgreSQL, Redis, GitHub Projects v2

---

## File Format Notes

### JSONL (JSON Lines)
**Used by**: `FileBackedDistributedLock`, `FileBackedPipelineQueue`

One JSON object per line. Each line is a complete, self-contained event.

**Example** (distributed lock file):
```json
{"type": "lock_acquired", "lock_key": "proj-1:board-1", "holder_id": "item-123", "acquired_at": "2025-06-01T12:00:00+00:00", "ttl_seconds": 7200, "holder_metadata": {"project_id": "proj-1"}}
{"type": "lock_released", "lock_key": "proj-1:board-1", "holder_id": "item-123"}
```

**Example** (pipeline queue file):
```json
{"type": "enqueued", "queue_key": "proj-1:board-1", "work_item_id": "item-1", "stage_name": "In Progress", "board_position": 0, "enqueued_at": "2025-06-01T12:00:00+00:00", "metadata": {"project_id": "proj-1"}}
{"type": "dequeued", "queue_key": "proj-1:board-1", "work_item_id": "item-1"}
```

**Migration**: No schema migration implemented. If format changes, delete the file and restart. Single-process guard ensures atomicity.

---

## Cross-References

- `documentation/architecture/ports/output/board-management.md` — Lock and queue port specifications
- `tests/unit/ports/output/test_distributed_lock_contract.py` — Contract tests for `IDistributedLock`
- `tests/unit/ports/output/test_pipeline_queue_contract.py` — Contract tests for `IPipelineQueue`
- `tests/unit/adapters/secondary/test_file_backed_distributed_lock.py` — File-backed lock tests
- `tests/unit/adapters/secondary/test_file_backed_pipeline_queue.py` — File-backed queue tests
- GitHub issue #904 — Pipeline coordination redesign (lock + queue separation)
