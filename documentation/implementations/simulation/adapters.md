# Simulation Adapters Reference

Complete mapping of all 54 simulation/mock adapters to their port interfaces.

## Overview

The Simulation Implementation provides:
- **36 Testing Adapters**: Mock/in-memory implementations of output ports
- **18 Input Port Adapters**: Mock adapters wrapping application services for HTTP endpoints

All adapters implement the same port contracts as production adapters, ensuring the simulation exercises identical business logic.

## Output Port Adapters (36 Testing Adapters)

Complete list of mock implementations for all output ports.

| # | Port Interface | Adapter Class | File | Purpose |
|---|---|---|---|---|
| 1 | `ITicketSystem` | `InMemoryTicketAdapter` | `adapters/testing/in_memory_ticket_adapter.py` | Simulates GitHub Issues — work item CRUD, comments, labels |
| 2 | `ILLMProvider` | `MockLLMAdapter` | `adapters/testing/mock_llm_adapter.py` | Simulates Claude API — returns configured responses based on patterns |
| 3 | `IContainer` | `FakeContainerAdapter` | `adapters/testing/fake_container_adapter.py` | Simulates Docker — agent execution without real containers |
| 4 | `IRepository` | `InMemoryRepositoryAdapter` | `adapters/testing/in_memory_repository_adapter.py` | Simulates Git — branch operations, commits, PRs |
| 5 | `IEventStore` | `InMemoryEventStore` | `adapters/testing/in_memory_event_store.py` | In-memory event persistence — complete audit trail |
| 6 | `IMetrics` | `InMemoryMetricsAdapter` | `adapters/testing/in_memory_metrics_adapter.py` | In-memory metrics — timing, operation counts |
| 7 | `IStorage` | `InMemoryStorageAdapter` | `adapters/testing/in_memory_storage_adapter.py` | In-memory artifact storage — files, logs, artifacts |
| 8 | `IConfigStore` | `InMemoryConfigStore` | `adapters/testing/in_memory_config_store.py` | In-memory configuration — workflow, agent, project config |
| 9 | `INotifier` | `MockNotifierAdapter` | `adapters/testing/mock_notifier_adapter.py` | Mock notifications — Slack, email (not sent) |
| 10 | `IEncryptionService` | `SimpleEncryptionAdapter` | `adapters/testing/simple_encryption_adapter.py` | Simple encryption — base64 encoding for testing |
| 11 | `IBoardService` | `MockBoardAdapter` | `adapters/testing/mock_board_adapter.py` | Simulates GitHub Projects — columns, cards, automation |
| 12 | `IRepairCycle` | `MockRepairCycleAdapter` | `adapters/testing/mock_repair_cycle_adapter.py` | Simulates repair/fix cycles — test-fix-validate loops |
| 13 | `IProjectManagerService` | `MockProjectManagerAdapter` | `adapters/testing/mock_project_manager_adapter.py` | Simulates project management — status, planning |
| 14 | `IPipelineLockService` | `InMemoryLockService` | `adapters/secondary/in_memory_queue_lock_service.py` | In-memory distributed locking — deadlock prevention |
| 15 | `IWorkflowConfigService` | `InMemoryWorkflowConfigService` | `adapters/testing/in_memory_workflow_config_service.py` | In-memory workflow configuration — stages, agents |
| 16 | `IPipelineQueueService` | `InMemoryQueueService` | `adapters/testing/in_memory_queue_service.py` | In-memory task queue — execution ordering |
| 17 | `IEventEmitter` | `CapturingMockEventEmitter` | `adapters/testing/capturing_mock_event_emitter.py` | Captures events for testing assertions |
| 18 | `IVersionControlService` | `InMemoryVersionControlService` | `adapters/testing/in_memory_version_control_service.py` | Simulates version control — branches, commits |
| 19 | `IMessageBroker` | `InMemoryMessageBroker` | `adapters/testing/in_memory_message_broker.py` | In-memory pub/sub — event distribution |
| 20 | `IDiscussionAdapter` | `MockDiscussionAdapter` | `adapters/testing/mock_discussion_adapter.py` | Simulates discussions — comments, threading |
| 21 | `IReviewCycle` | `MockReviewCycleAdapter` | `adapters/testing/mock_review_cycle_adapter.py` | Simulates code review — PR review workflows |
| 22 | `IPRReviewCycle` | `MockPRReviewCycleAdapter` | `adapters/testing/mock_pr_review_cycle_adapter.py` | Simulates PR review — approval, feedback, revisions |
| 23 | `ICodeReviewService` | `InMemoryCodeReviewAdapter` | `adapters/testing/in_memory_code_review_adapter.py` | In-memory code review tracking |
| 24 | `IIdentityService` | `ConfigurableIdentityService` | `adapters/secondary/configurable_identity_service.py` | Simulates identity — bot/human user detection |
| 25 | `IRepairCycleCheckpointStore` | `InMemoryCheckpointStore` | `adapters/testing/in_memory_checkpoint_store.py` | In-memory repair cycle checkpoints |
| 26 | `ICIPipelineService` | `MockCIPipelineAdapter` | `adapters/testing/mock_ci_pipeline_adapter.py` | Simulates CI/CD — build, test execution |
| 27 | `IAgentRepository` | `InMemoryAgentRepository` | `adapters/testing/in_memory_agent_repository.py` | In-memory agent catalog — capabilities, models |
| 28 | `IActiveWorkflowRunRegistry` | `InMemoryActiveWorkflowRunRegistry` | `adapters/testing/in_memory_active_workflow_run_registry.py` | In-memory tracking of active workflow runs |
| 29 | `IWorkItemBranchTracker` | `InMemoryWorkItemBranchTracker` | `adapters/testing/in_memory_work_item_branch_tracker.py` | In-memory branch tracking — work item to branch mapping |
| 30 | `IWorkItemService` | `MockWorkItemService` | `adapters/testing/mock_work_item_service.py` | Mock work item service — CRUD operations |
| 31 | `IAgentContainerRecoveryService` | `MockContainerRecoveryAdapter` | `adapters/testing/mock_container_recovery_adapter.py` | Simulates container recovery — failure handling |
| 32 | `ISystemicAnalysisService` | `MockSystemicAnalysisAdapter` | `adapters/testing/mock_systemic_analysis_adapter.py` | Simulates systemic failure analysis |
| 33 | `IEnvironmentRepairService` | `MockEnvironmentRepairAdapter` | `adapters/testing/mock_environment_repair_adapter.py` | Simulates environment repair — dependency fixes |
| 34 | `IBranchResolutionService` | `MockBranchResolutionAdapter` | `adapters/testing/mock_branch_resolution_adapter.py` | Simulates intelligent branch resolution |
| 35 | `IAgentExecutor` | `ExecutionServiceAgentExecutor` | `adapters/testing/execution_service_agent_executor.py` | Real agent executor wrapper — integrates with execution service |
| 36 | `ITracer` | `InMemoryTracer` | `adapters/testing/in_memory_tracer.py` | In-memory distributed tracing — trace propagation |

## Input Port Adapters (18 Mock Adapters)

Mock implementations of input ports that wrap application services for HTTP endpoints.

| # | Port Interface | Adapter Class | File | Purpose |
|---|---|---|---|---|
| 1 | `IOrchestrationCommandPort` | `MockOrchestrationCommandAdapter` | `adapters/primary/input_port_adapters/mock/mock_orchestration_command_adapter.py` | Workflow orchestration commands |
| 2 | `IWorkflowCommandPort` | `MockWorkflowCommandAdapter` | `adapters/primary/input_port_adapters/mock/mock_workflow_command_adapter.py` | Workflow definition commands |
| 3 | `IWorkflowDefinitionCommandPort` | `MockWorkflowDefinitionCommandAdapter` | `adapters/primary/input_port_adapters/mock/mock_workflow_definition_command_adapter.py` | Workflow stage definition commands |
| 4 | `IWorkflowQueryPort` | `MockWorkflowQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_workflow_query_adapter.py` | Workflow queries |
| 5 | `IWorkflowRunQueryPort` | `MockWorkflowRunQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_workflow_run_query_adapter.py` | Workflow run queries |
| 6 | `IWorkItemCommandPort` | `MockWorkItemCommandAdapter` | `adapters/primary/input_port_adapters/mock/mock_work_item_command_adapter.py` | Work item commands — create, update, label |
| 7 | `IWorkItemQueryPort` | `MockWorkItemQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_work_item_query_adapter.py` | Work item queries — search, list, get |
| 8 | `IExecutionCommandPort` | `MockExecutionCommandAdapter` | `adapters/primary/input_port_adapters/mock/mock_execution_command_adapter.py` | Execution lifecycle commands |
| 9 | `IExecutionQueryPort` | `MockExecutionQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_execution_query_adapter.py` | Execution queries — status, logs, metrics |
| 10 | `IAgentCommandPort` | `MockAgentCommandAdapter` | `adapters/primary/input_port_adapters/mock/mock_agent_command_adapter.py` | Agent management commands |
| 11 | `IAgentQueryPort` | `MockAgentQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_agent_query_adapter.py` | Agent queries — capabilities, status |
| 12 | `IConfigurationCommandPort` | `MockConfigCommandAdapter` | `adapters/primary/input_port_adapters/mock/mock_config_command_adapter.py` | Configuration commands — create, update |
| 13 | `IConfigurationQueryPort` | `MockConfigQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_config_query_adapter.py` | Configuration queries — read, list |
| 14 | `IConfigurationServicePort` | `MockConfigServiceAdapter` | `adapters/primary/input_port_adapters/mock/mock_config_service_adapter.py` | Configuration service interface |
| 15 | `ITaskQueryPort` | `MockTaskQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_task_query_adapter.py` | Task/job queries |
| 16 | `IMetricsQueryPort` | `MockMetricsQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_metrics_query_adapter.py` | Metrics queries — timing, counts |
| 17 | `IWorkspaceQueryPort` | `MockWorkspaceQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_workspace_query_adapter.py` | Workspace queries — containers, mounts |
| 18 | `IAuditQueryPort` | `AuditQueryAdapter` | `adapters/primary/audit_query_adapter.py` | Audit log queries |

## Adapter Organization

### Testing Adapters Location
```
src/codetoreum/adapters/testing/
├── in_memory_*.py          (11 files) - In-memory backing stores
├── mock_*.py               (18 files) - Mock external systems
├── fake_*.py               (1 file)  - Fake implementations
├── simple_*.py             (1 file)  - Simple implementations
├── execution_service_agent_executor.py
├── capturing_mock_event_emitter.py
└── __init__.py
```

### Input Port Adapters Location
```
src/codetoreum/adapters/primary/input_port_adapters/mock/
├── mock_*_command_adapter.py    (7 files) - Command handlers
├── mock_*_query_adapter.py      (11 files) - Query handlers
└── __init__.py
```

## Key Adapter Characteristics

### In-Memory Adapters (11)
- **Purpose**: Backing stores without external services
- **Thread-Safe**: Protected by locks for concurrent test execution
- **Persisted During Session**: Data survives for event replay
- **Examples**: `InMemoryEventStore`, `InMemoryTicketAdapter`, `InMemoryConfigStore`

### Mock Adapters (18)
- **Purpose**: Simulate external systems with configurable responses
- **Deterministic**: Same input produces same output
- **Configurable**: Responses set via YAML or programmatically
- **Examples**: `MockLLMAdapter`, `MockBoardAdapter`, `MockRepairCycleAdapter`

### Special Adapters (2)
- **`ExecutionServiceAgentExecutor`**: Real integration with execution service, not a mock
- **`SimpleEncryptionAdapter`**: Basic encryption (base64) for testing, not secure for production

## Adapter Relationships and Dependencies

```
┌─────────────────────────────────┐
│   Application Services          │
│   (WorkflowOrchestrator, etc.)  │
└────────────┬────────────────────┘
             │
             ├─── ITicketSystem ──────────── InMemoryTicketAdapter
             │
             ├─── ILLMProvider ──────────── MockLLMAdapter
             │
             ├─── IContainer ────────────── FakeContainerAdapter
             │
             ├─── IRepository ───────────── InMemoryRepositoryAdapter
             │
             ├─── IEventStore ───────────── InMemoryEventStore
             │
             ├─── IBoardService ─────────── MockBoardAdapter
             │
             ├─── IRepairCycle ──────────── MockRepairCycleAdapter
             │
             ├─── ... (30 more adapters)
             │
             └─── IAgentExecutor ────────── ExecutionServiceAgentExecutor

┌──────────────────────────────────┐
│   HTTP Input Ports               │
│   (FastAPI Routes)               │
└────────────┬─────────────────────┘
             │
             ├─── IWorkflowCommandPort ──── MockWorkflowCommandAdapter
             │
             ├─── IWorkItemQueryPort ────── MockWorkItemQueryAdapter
             │
             ├─── IExecutionCommandPort ─── MockExecutionCommandAdapter
             │
             └─── ... (15 more input adapters)
```

## Integration Pattern

All adapters follow the same integration pattern:

```python
# 1. Adapter implements port interface
class InMemoryTicketAdapter(ITicketSystem):
    pass

# 2. Bootstrap wires adapter to application service
adapters = SimulationAdapters(
    ticket_system=InMemoryTicketAdapter(),
    # ... more adapters
)

# 3. Application services use adapters via port interfaces
class WorkflowOrchestrator:
    def __init__(self, ticket_system: ITicketSystem, ...):
        self.ticket_system = ticket_system

# 4. All interactions go through port contracts (no direct dependencies)
```

## Testing with Adapters

### Access Adapters in Tests

```python
# Get simulation runner
runner = SimulationRunner(config)
result = await runner.run(scenario)

# Access adapters from simulation
ticket_adapter = result.simulation.adapters.ticket_as_mock()
board_adapter = result.simulation.adapters.board_as_mock()
llm_adapter = result.simulation.adapters.llm_as_mock()

# Use mock-specific methods
await ticket_adapter.add_work_item(...)
movements = board_adapter.get_column_movements()
responses = llm_adapter.get_all_responses()
```

### Configure Mock Responses

```python
# Configure LLM responses
llm_adapter = adapters.llm_as_mock()
llm_adapter.add_response(
    pattern=r"architecture.*design",
    response="Implemented clean architecture with ports and adapters."
)

# Configure board behavior
board_adapter = adapters.board_as_mock()
board_adapter.set_next_column_transition("Design", "Implementation")
```

### Verify Adapter Interactions

```python
# Check event emissions
events = adapters.event_emitter.captured_events
assert len(events) > 0

# Check container operations
container = adapters.container_as_fake()
executions = container.get_executions()
assert len(executions) == 3

# Check storage
storage = adapters.storage_as_memory()
artifacts = storage.list_artifacts()
assert len(artifacts) == 5
```

## Cross-References

- **Port Specifications**: See [Architecture: Ports](../../architecture/ports/)
  - [Core System Ports](../../architecture/ports/output/core-system.md)
  - [Work Coordination Ports](../../architecture/ports/output/work-coordination.md)
  - [Code Review Ports](../../architecture/ports/output/code-review.md)
  - [Infrastructure Services](../../architecture/ports/output/infrastructure-services.md)
  - [Input Ports](../../architecture/ports/input/)

- **Bootstrap Integration**: See [bootstrap-wiring.md](./bootstrap-wiring.md)
  - Phase 2: Adapter instantiation and dependency injection
  - Adapter resolver and factory patterns

- **Scenario Examples**: See [scenarios.md](./scenarios.md)
  - How scenarios configure and use adapters
  - Mock response patterns in YAML

---

**Total Adapter Count**: 36 testing + 18 input port = **54 adapters**

All adapters implement port contracts to provide a complete, testable implementation of the Codetoreum architecture.
