# Simulation Adapters Reference

Complete mapping of all 53 simulation/mock adapters to their port interfaces.

## Overview

The Simulation Implementation provides:
- **35 Testing Adapters**: Mock/in-memory implementations of output ports
- **18 Input Port Adapters**: Mock adapters wrapping application services for HTTP endpoints

All adapters implement the same port contracts as production adapters, ensuring the simulation exercises identical business logic.

## Output Port Adapters (35 Testing Adapters)

Complete list of mock implementations for all output ports in `adapters/testing/`.

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
| 14 | `IWorkflowConfigService` | `InMemoryWorkflowConfigService` | `adapters/testing/in_memory_workflow_config_service.py` | In-memory workflow configuration — stages, agents |
| 15 | `IPipelineQueueService` | `InMemoryQueueService` | `adapters/testing/in_memory_queue_service.py` | In-memory task queue — execution ordering |
| 16 | `IEventEmitter` | `CapturingMockEventEmitter` | `adapters/testing/capturing_mock_event_emitter.py` | Captures events for testing assertions |
| 17 | `IVersionControlService` | `InMemoryVersionControlService` | `adapters/testing/in_memory_version_control_service.py` | Simulates version control — branches, commits |
| 18 | `IMessageBroker` | `InMemoryMessageBroker` | `adapters/testing/in_memory_message_broker.py` | In-memory pub/sub — event distribution |
| 19 | `IDiscussionAdapter` | `MockDiscussionAdapter` | `adapters/testing/mock_discussion_adapter.py` | Simulates discussions — comments, threading |
| 20 | `IReviewCycle` | `MockReviewCycleAdapter` | `adapters/testing/mock_review_cycle_adapter.py` | Simulates code review — PR review workflows |
| 21 | `IPRReviewCycle` | `MockPRReviewCycleAdapter` | `adapters/testing/mock_pr_review_cycle_adapter.py` | Simulates PR review — approval, feedback, revisions |
| 22 | `ICodeReviewService` | `InMemoryCodeReviewAdapter` | `adapters/testing/in_memory_code_review_adapter.py` | In-memory code review tracking |
| 23 | `IRepairCycleCheckpointStore` | `InMemoryCheckpointStore` | `adapters/testing/in_memory_checkpoint_store.py` | In-memory repair cycle checkpoints |
| 24 | `ICIPipelineService` | `MockCIPipelineAdapter` | `adapters/testing/mock_ci_pipeline_adapter.py` | Simulates CI/CD — build, test execution |
| 25 | `IAgentRepository` | `InMemoryAgentRepository` | `adapters/testing/in_memory_agent_repository.py` | In-memory agent catalog — capabilities, models |
| 26 | `IActiveWorkflowRunRegistry` | `InMemoryActiveWorkflowRunRegistry` | `adapters/testing/in_memory_active_workflow_run_registry.py` | In-memory tracking of active workflow runs |
| 27 | `IWorkItemBranchTracker` | `InMemoryWorkItemBranchTracker` | `adapters/testing/in_memory_work_item_branch_tracker.py` | In-memory branch tracking — work item to branch mapping |
| 28 | `IWorkItemService` | `MockWorkItemService` | `adapters/testing/mock_work_item_service.py` | Mock work item service — CRUD operations |
| 29 | `IAgentContainerRecoveryService` | `MockContainerRecoveryAdapter` | `adapters/testing/mock_container_recovery_adapter.py` | Simulates container recovery — failure handling |
| 30 | `ISystemicAnalysisService` | `MockSystemicAnalysisAdapter` | `adapters/testing/mock_systemic_analysis_adapter.py` | Simulates systemic failure analysis |
| 31 | `IEnvironmentRepairService` | `MockEnvironmentRepairAdapter` | `adapters/testing/mock_environment_repair_adapter.py` | Simulates environment repair — dependency fixes |
| 32 | `IBranchResolutionService` | `MockBranchResolutionAdapter` | `adapters/testing/mock_branch_resolution_adapter.py` | Simulates intelligent branch resolution |
| 33 | `IAgentExecutor` | `ExecutionServiceAgentExecutor` | `adapters/testing/execution_service_agent_executor.py` | Real agent executor wrapper — integrates with execution service |
| 34 | `ITracer` | `InMemoryTracer` | `adapters/testing/in_memory_tracer.py` | In-memory distributed tracing — trace propagation |
| 35 | `IAgentExecutor` | `MockAgentExecutor` | `adapters/testing/mock_agent_executor.py` | Mock agent executor — simulates agent execution without LLM |

## Secondary Adapters (2 Adapters in `adapters/secondary/`)

These adapters are located in `adapters/secondary/` but are used in simulation testing:

| # | Port Interface | Adapter Class | File | Purpose |
|---|---|---|---|---|
| 1 | `IPipelineLockService` | `InMemoryLockService` | `adapters/secondary/in_memory_queue_lock_service.py` | In-memory distributed locking — deadlock prevention |
| 2 | `IIdentityService` | `ConfigurableIdentityService` | `adapters/secondary/configurable_identity_service.py` | Simulates identity — bot/human user detection |

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
| 14 | `ConfigurationService` | `MockConfigServiceAdapter` | `adapters/primary/input_port_adapters/mock/mock_config_service_adapter.py` | Configuration service wrapper |
| 15 | `ITaskQueryPort` | `MockTaskQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_task_query_adapter.py` | Task/job queries |
| 16 | `IMetricsQueryPort` | `MockMetricsQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_metrics_query_adapter.py` | Metrics queries — timing, counts |
| 17 | `IWorkspaceQueryPort` | `MockWorkspaceQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_workspace_query_adapter.py` | Workspace queries — containers, mounts |
| 18 | `IAuditQueryPort` | `AuditQueryAdapter` | `adapters/primary/audit_query_adapter.py` | Audit log queries |

## Adapter Organization

### Testing Adapters Location
```
src/codetoreum/adapters/testing/
├── in_memory_*.py          (16 files) - In-memory backing stores
├── mock_*.py               (15 files) - Mock external systems
├── fake_*.py               (1 file)  - Fake implementations
├── simple_*.py             (1 file)  - Simple implementations
├── execution_service_agent_executor.py
├── mock_agent_executor.py
├── capturing_mock_event_emitter.py
└── __init__.py
```

### Input Port Adapters Location
```
src/codetoreum/adapters/primary/input_port_adapters/mock/
├── mock_*_command_adapter.py    (7 files) - Command handlers
├── mock_*_query_adapter.py      (9 files) - Query handlers
└── __init__.py
```

## Key Adapter Characteristics

### In-Memory Adapters (16)
- **Purpose**: Backing stores without external services
- **Thread-Safe**: Protected by locks for concurrent test execution
- **Persisted During Session**: Data survives for event replay
- **Examples**: `InMemoryEventStore`, `InMemoryTicketAdapter`, `InMemoryConfigStore`

### Mock Adapters (15)
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

## Helper Classes and Data Structures

The simulation adapters use several helper classes and data structures to organize state and coordinate testing scenarios. These classes are not adapters themselves but provide essential utilities for adapter implementations.

### Execution and State Tracking

#### CommandExecution

**Location**: `src/codetoreum/adapters/testing/fake_container_adapter.py`

Represents the execution of a single command within a simulated container.

**Attributes**:
- `timestamp` (datetime): When execution occurred
- `command` (str): The command that was executed (e.g., "python -m pytest")
- `exit_code` (int): Exit code returned by command
- `stdout` (str): Standard output captured
- `stderr` (str): Standard error captured
- `duration_ms` (float): Execution duration in milliseconds

**Purpose**: Records a single command execution for verification in container simulation tests.

#### ActiveExecutionInfo

**Location**: `src/codetoreum/adapters/testing/execution_service_agent_executor.py`

Metadata about an in-progress agent execution, exposed for timeout detection.

**Attributes**:
- `execution_id` (str): Unique ID for this execution
- `work_item_id` (str): Work item being processed
- `started_at` (datetime): When execution started (UTC)
- `timeout_seconds` (int): Timeout threshold from Agent configuration
- `task` (asyncio.Task): The running asyncio Task for cancellation

**Purpose**: Provides execution metadata to timeout watchdog for detecting and canceling timed-out executions.

#### MockProjectState

**Location**: `src/codetoreum/adapters/testing/mock_project_manager_adapter.py`

Internal state tracking for a project in the mock adapter.

**Attributes**:
- `config` (ProjectConfig): Project configuration
- `cloned` (bool): Whether project has been successfully cloned
- `clone_path` (str): Path where project is cloned
- `last_clone_attempt` (datetime | None): Timestamp of last clone attempt
- `clone_failures` (int): Count of consecutive clone failures

**Purpose**: Tracks project state including clone status and failure counts for mock project management.

### Event and Movement Tracking

#### MovementEvent

**Location**: `src/codetoreum/adapters/testing/mock_board_adapter.py`

Represents the movement of a work item on a board (card movement between columns).

**Attributes**:
- `work_item_id` (str): ID of work item that moved
- `from_column` (str): Column the item moved from
- `to_column` (str): Column the item moved to
- `timestamp` (datetime): When movement occurred
- `moved_by` (str): What triggered the movement ("agent", "user", "automation")
- `reason` (Optional[str]): Why the movement occurred

**Purpose**: Tracks board card movements for verifying workflow progress in tests.

#### ReviewSequenceItem

**Location**: `src/codetoreum/adapters/testing/mock_review_cycle_adapter.py`

A single item in a pre-configured review sequence.

**Attributes**:
- `decision` (ReviewDecision): Reviewer's decision (APPROVE, REQUEST_CHANGES, ESCALATE)
- `findings` (list[ReviewFinding]): Optional list of findings from the review
- `summary` (str | None): Optional summary of the review

**Purpose**: Enables pre-scripted review sequences for deterministic testing of review cycles.

### Exception and Circuit Breaking

#### CircuitBreakerTripped

**Location**: `src/codetoreum/adapters/testing/mock_repair_cycle_adapter.py`

Exception raised when maximum agent calls are exceeded during repair cycle.

**Attributes**: None (bare Exception subclass)

**Purpose**: Signals circuit breaker activation when repair cycle max calls exceeded.

### Logging and Debugging

#### MockLoggerAdapter

**Location**: `src/codetoreum/adapters/primary/input_port_adapters/mock/mock_logger_adapter.py`

Simple logging interface adapter for FastAPI application layer.

**Methods**:
- `info(message)`: Log info level message
- `warning(message)`: Log warning level message
- `error(message)`: Log error level message
- `debug(message)`: Log debug level message

**Purpose**: Provides simple logging interface, delegating to Python's standard logging module.

### Mock Agents

#### MockAgentExecutor

**Location**: `src/codetoreum/adapters/testing/mock_agent_executor.py`

Mock implementation of IAgentExecutor for testing and port adapter coverage.

**Attributes**:
- `_execution_delay` (float): Seconds to simulate agent work (default 3.0)
- `_completion_callback` (Callable | None): Async callback invoked after execution
- `_default_board_id` (str): Board ID passed to completion callback
- `_executions` (list[dict]): Record of all executions for test assertions
- `_pending_tasks` (set[asyncio.Task]): Set of pending execution tasks
- `_execution_query` (MockExecutionQueryAdapter | None): Wired execution query adapter

**Methods**:
- `set_completion_handler(callback, default_board_id)`: Wire completion callback
- `set_execution_query(adapter)`: Wire execution query adapter
- `execute(agent, work_item)`: Simulate agent execution

**Purpose**: Simulates agent work for testing without running actual LLM models.

---

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

**Total Adapter Count**: 35 testing + 18 input port = **53 adapters**

All adapters implement port contracts to provide a complete, testable implementation of the Codetoreum architecture.
