# Simulation Adapters Reference

Complete mapping of all 57 simulation/mock adapters to their port interfaces.

> **Counting Methodology**: One concrete class explicitly inheriting one port ABC = one counted implementation. Abstract bases, decorators, mixins, and helper dataclasses are excluded.

## Overview

The Simulation Implementation provides:
- **37 Testing Adapters**: Mock/in-memory implementations of output ports
- **2 Secondary Adapters**: In-memory identity service and event emitter
- **18 Input Port Adapters**: Mock adapters wrapping application services for HTTP endpoints

All adapters implement the same port contracts as production adapters, ensuring the simulation exercises identical business logic.

> **DEF-015 (Phase D5) retired three slots**: `ILLMProvider` (with `MockLLMAdapter`), `IAgentLauncher`, and `IStorage` (with `InMemoryStorageAdapter`). The simulation now wires a single `MockClaudeCodeAdapter` implementing the new `ICodingAgent` port — see entry #2 below and the dedicated section [MockClaudeCodeAdapter design](#mockclaudecodeadapter-design).

## Output Port Adapters (37 Testing Adapters)

Complete list of mock implementations for all output ports in `adapters/testing/`.

| # | Port Interface | Adapter Class | File | Purpose |
|---|---|---|---|---|
| 1 | `ITicketSystem` | `InMemoryTicketAdapter` | `adapters/testing/in_memory_ticket_adapter.py` | Simulates GitHub Issues — work item CRUD, comments, labels |
| 2 | `ICodingAgent` | `MockClaudeCodeAdapter` | `adapters/testing/mock_claude_code_adapter.py` | Simulates a coding agent — records invocations and emits a deterministic `CodingAgent*` event stream (see [design notes](#mockclaudecodeadapter-design)) |
| 3 | `IContainer` | `FakeContainerAdapter` | `adapters/testing/fake_container_adapter.py` | Simulates Docker — agent execution without real containers |
| 4 | `IRepository` | `InMemoryRepositoryAdapter` | `adapters/testing/in_memory_repository_adapter.py` | Simulates Git — branch operations, commits, PRs |
| 5 | `IEventStore` | `InMemoryEventStore` | `adapters/testing/in_memory_event_store.py` | In-memory event persistence — complete audit trail |
| 6 | `IMetrics` | `InMemoryMetricsAdapter` | `adapters/testing/in_memory_metrics_adapter.py` | In-memory metrics — timing, operation counts |
| 7 | `IConfigStore` | `InMemoryConfigStore` | `adapters/testing/in_memory_config_store.py` | In-memory configuration — workflow, agent, project config |
| 8 | `INotifier` | `MockNotifierAdapter` | `adapters/testing/mock_notifier_adapter.py` | Mock notifications — Slack, email (not sent) |
| 9 | `IEncryptionService` | `SimpleEncryptionAdapter` | `adapters/testing/simple_encryption_adapter.py` | Simple encryption — base64 encoding for testing |
| 10 | `IBoardService` | `MockBoardAdapter` | `adapters/testing/mock_board_adapter.py` | Simulates GitHub Projects — columns, cards, automation |
| 11 | `IRepairCycle` | `MockRepairCycleAdapter` | `adapters/testing/mock_repair_cycle_adapter.py` | Simulates repair/fix cycles — test-fix-validate loops |
| 12 | `IProjectManagerService` | `MockProjectManagerAdapter` | `adapters/testing/mock_project_manager_adapter.py` | Simulates project management — status, planning |
| 13 | `IWorkflowConfigService` | `InMemoryWorkflowConfigService` | `adapters/testing/in_memory_workflow_config_service.py` | In-memory workflow configuration — stages, agents |
| 14 | `IPipelineQueueService` | `InMemoryQueueService` | `adapters/testing/in_memory_queue_service.py` | In-memory task queue — execution ordering |
| 15 | `IEventEmitter` | `CapturingMockEventEmitter` | `adapters/testing/capturing_mock_event_emitter.py` | Captures events for testing assertions |
| 16 | `IVersionControlService` | `InMemoryVersionControlService` | `adapters/testing/in_memory_version_control_service.py` | Simulates version control — branches, commits |
| 17 | `IMessageBroker` | `InMemoryMessageBroker` | `adapters/testing/in_memory_message_broker.py` | In-memory pub/sub — event distribution |
| 18 | `IDiscussionAdapter` | `MockDiscussionAdapter` | `adapters/testing/mock_discussion_adapter.py` | Simulates discussions — comments, threading |
| 19 | `IReviewCycle` | `MockReviewCycleAdapter` | `adapters/testing/mock_review_cycle_adapter.py` | Simulates code review — PR review workflows |
| 20 | `IPRReviewCycle` | `MockPRReviewCycleAdapter` | `adapters/testing/mock_pr_review_cycle_adapter.py` | Simulates PR review — approval, feedback, revisions |
| 21 | `ICodeReviewService` | `InMemoryCodeReviewAdapter` | `adapters/testing/in_memory_code_review_adapter.py` | In-memory code review tracking |
| 22 | `IRepairCycleCheckpointStore` | `InMemoryCheckpointStore` | `adapters/testing/in_memory_checkpoint_store.py` | In-memory repair cycle checkpoints |
| 23 | `ICIPipelineService` | `MockCIPipelineAdapter` | `adapters/testing/mock_ci_pipeline_adapter.py` | Simulates CI/CD — build, test execution |
| 24 | `IAgentRepository` | `InMemoryAgentRepository` | `adapters/testing/in_memory_agent_repository.py` | In-memory agent catalog — capabilities, models |
| 25 | `IActiveWorkflowRunRegistry` | `InMemoryActiveWorkflowRunRegistry` | `adapters/testing/in_memory_active_workflow_run_registry.py` | In-memory tracking of active workflow runs |
| 26 | `IWorkItemBranchTracker` | `InMemoryWorkItemBranchTracker` | `adapters/testing/in_memory_work_item_branch_tracker.py` | In-memory branch tracking — work item to branch mapping |
| 27 | `IWorkItemService` | `MockWorkItemService` | `adapters/testing/mock_work_item_service.py` | Mock work item service — CRUD operations |
| 28 | `IAgentContainerRecoveryService` | `MockContainerRecoveryAdapter` | `adapters/testing/mock_container_recovery_adapter.py` | Simulates container recovery — failure handling |
| 29 | `ISystemicAnalysisService` | `MockSystemicAnalysisAdapter` | `adapters/testing/mock_systemic_analysis_adapter.py` | Simulates systemic failure analysis |
| 30 | `IEnvironmentRepairService` | `MockEnvironmentRepairAdapter` | `adapters/testing/mock_environment_repair_adapter.py` | Simulates environment repair — dependency fixes |
| 31 | `IBranchResolutionService` | `MockBranchResolutionAdapter` | `adapters/testing/mock_branch_resolution_adapter.py` | Simulates intelligent branch resolution |
| 32 | `ITracer` | `InMemoryTracer` | `adapters/testing/in_memory_tracer.py` | In-memory distributed tracing — trace propagation |
| 33 | `IAgentExecutor` | `MockAgentExecutor` | `adapters/testing/mock_agent_executor.py` | Mock agent executor — simulates agent execution without invoking a coding agent |
| 34 | `IDistributedLock` | `InMemoryDistributedLock` | `adapters/testing/in_memory_distributed_lock.py` | In-memory distributed locking — task coordination |
| 35 | `IFailedEventStore` | `InMemoryFailedEventStore` | `adapters/testing/in_memory_failed_event_store.py` | In-memory dead-letter queue — failed event capture |
| 36 | `IOrphanScanRegistry` | `InMemoryOrphanScanRegistry` | `adapters/testing/in_memory_orphan_scan_registry.py` | In-memory orphan scan tracking — container recovery |
| 37 | `IPipelineQueue` | `InMemoryPipelineQueue` | `adapters/testing/in_memory_pipeline_queue.py` | In-memory FIFO queue — work item coordination |

## Secondary Adapters (2 Adapters in `adapters/secondary/`)

Adapters located in `adapters/secondary/` but used in simulation testing:

| # | Port Interface | Adapter Class | File | Purpose |
|---|---|---|---|---|
| 1 | `IIdentityService` | `ConfigurableIdentityService` | `adapters/secondary/configurable_identity_service.py` | Simulates identity — bot/human user detection |
| 2 | `IEventEmitter` | `MockEventEmitter` | `adapters/secondary/mock_event_emitter.py` | In-memory event emitter for testing — handles event subscription and synchronous dispatch |

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
| 18 | `IAuditQueryPort` | `MockAuditQueryAdapter` | `adapters/primary/input_port_adapters/mock/mock_audit_query_adapter.py` | Audit log queries |

## Adapter Organization

### Testing Adapters Location
```
src/codetoreum/adapters/testing/
├── in_memory_*.py          (19 files) - In-memory backing stores
├── mock_*.py               (15 files) - Mock external systems (incl. mock_claude_code_adapter.py)
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

### In-Memory Adapters (19)
- **Purpose**: Backing stores without external services
- **Thread-Safe**: Protected by locks for concurrent test execution
- **Persisted During Session**: Data survives for event replay
- **Examples**: `InMemoryEventStore`, `InMemoryTicketAdapter`, `InMemoryConfigStore`

### Mock Adapters (15)
- **Purpose**: Simulate external systems with configurable responses
- **Deterministic**: Same input produces same output
- **Configurable**: Responses set via YAML or programmatically
- **Examples**: `MockClaudeCodeAdapter`, `MockBoardAdapter`, `MockRepairCycleAdapter`

### Special Adapters (1)
- **`SimpleEncryptionAdapter`**: Basic encryption (base64) for testing, not secure for production

## Adapter Relationships and Dependencies

```
┌─────────────────────────────────┐
│   Application Services          │
│   (WorkflowOrchestrator, etc.)  │
└────────────┬────────────────────┘
             │
             ├─── ITicketSystem ──────────────── InMemoryTicketAdapter
             ├─── ICodingAgent ──────────────── MockClaudeCodeAdapter
             ├─── IContainer ────────────────── FakeContainerAdapter
             ├─── IRepository ───────────────── InMemoryRepositoryAdapter
             ├─── IEventStore ───────────────── InMemoryEventStore
             ├─── IMetrics ──────────────────── InMemoryMetricsAdapter
             ├─── IConfigStore ──────────────── InMemoryConfigStore
             ├─── INotifier ─────────────────── MockNotifierAdapter
             ├─── IEncryptionService ────────── SimpleEncryptionAdapter
             ├─── IBoardService ─────────────── MockBoardAdapter
             ├─── IRepairCycle ──────────────── MockRepairCycleAdapter
             ├─── IProjectManagerService ────── MockProjectManagerAdapter
             ├─── IWorkflowConfigService ────── InMemoryWorkflowConfigService
             ├─── IPipelineQueueService ─────── InMemoryQueueService
             ├─── IEventEmitter ─────────────── CapturingMockEventEmitter
             ├─── IAuditStore ───────────────── InMemoryAuditStore
             ├─── IVersionControlService ────── InMemoryVersionControlService
             ├─── IMessageBroker ────────────── InMemoryMessageBroker
             ├─── IDiscussionAdapter ────────── MockDiscussionAdapter
             ├─── IReviewCycle ──────────────── MockReviewCycleAdapter
             ├─── IPRReviewCycle ────────────── MockPRReviewCycleAdapter
             ├─── ICodeReviewService ────────── InMemoryCodeReviewAdapter
             ├─── IIdentityService ──────────── ConfigurableIdentityService
             ├─── IRepairCycleCheckpointStore ─ InMemoryCheckpointStore
             ├─── ICIPipelineService ────────── MockCIPipelineAdapter
             ├─── IAgentRepository ──────────── InMemoryAgentRepository
             ├─── IActiveWorkflowRunRegistry ── InMemoryActiveWorkflowRunRegistry
             ├─── IWorkItemBranchTracker ────── InMemoryWorkItemBranchTracker
             ├─── IWorkItemService ──────────── MockWorkItemService
             ├─── IAgentContainerRecoveryService MockContainerRecoveryAdapter
             ├─── ISystemicAnalysisService ──── MockSystemicAnalysisAdapter
             ├─── IEnvironmentRepairService ─── MockEnvironmentRepairAdapter
             ├─── IBranchResolutionService ──── MockBranchResolutionAdapter
             ├─── ITracer ────────────────────── InMemoryTracer
             └─── IAgentExecutor ────────────── MockAgentExecutor

┌──────────────────────────────────┐
│   HTTP Input Ports               │
│   (FastAPI Routes)               │
└────────────┬─────────────────────┘
             │
             ├─── IOrchestrationCommandPort ──── MockOrchestrationCommandAdapter
             ├─── IWorkflowCommandPort ──────── MockWorkflowCommandAdapter
             ├─── IWorkflowDefinitionCommandPort MockWorkflowDefinitionCommandAdapter
             ├─── IWorkflowQueryPort ────────── MockWorkflowQueryAdapter
             ├─── IWorkflowRunQueryPort ─────── MockWorkflowRunQueryAdapter
             ├─── IWorkItemCommandPort ──────── MockWorkItemCommandAdapter
             ├─── IWorkItemQueryPort ────────── MockWorkItemQueryAdapter
             ├─── IExecutionCommandPort ─────── MockExecutionCommandAdapter
             ├─── IExecutionQueryPort ───────── MockExecutionQueryAdapter
             ├─── IAgentCommandPort ─────────── MockAgentCommandAdapter
             ├─── IAgentQueryPort ───────────── MockAgentQueryAdapter
             ├─── IConfigurationCommandPort ─── MockConfigCommandAdapter
             ├─── IConfigurationQueryPort ───── MockConfigQueryAdapter
             ├─── ITaskQueryPort ────────────── MockTaskQueryAdapter
             ├─── IMetricsQueryPort ─────────── MockMetricsQueryAdapter
             ├─── IWorkspaceQueryPort ───────── MockWorkspaceQueryAdapter
             ├─── IAuditQueryPort ───────────── MockAuditQueryAdapter
             └─── ConfigurationService ──────── MockConfigServiceAdapter
```

## Integration Pattern

All adapters follow the same integration pattern:

```python
# 1. Adapter implements port interface
class InMemoryTicketAdapter(ITicketSystem):
    pass

# 2. Bootstrap wires adapter to application service (34 output adapters total)
adapters = SimulationAdapters(
    ticket_system=InMemoryTicketAdapter(),
    coding_agent=MockClaudeCodeAdapter(event_bus=event_bus),
    container=FakeContainerAdapter(),
    # ... all 34 output port adapters
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
coding_agent = result.simulation.adapters.coding_agent  # MockClaudeCodeAdapter

# Use mock-specific methods
await ticket_adapter.add_work_item(...)
movements = board_adapter.get_column_movements()
invocations = coding_agent.invocations  # list of _Invocation records
```

### Configure Coding-Agent Behaviour

```python
# Override the default 5-event ledger with a custom script
async def custom_script(execution, workspace_context, options):
    events = [
        # ...build any list of CodingAgent* events...
    ]
    result = CodingAgentResult(success=True, summary_text="custom", ...)
    return events, result

coding_agent = MockClaudeCodeAdapter(event_bus=event_bus, script=custom_script)

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

# Check coding-agent invocations
assert len(coding_agent.invocations) == 1
assert coding_agent.invocations[0].invocation_mode == InvocationMode.CONTAINERIZED
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

## MockClaudeCodeAdapter design

`MockClaudeCodeAdapter` (in `adapters/testing/mock_claude_code_adapter.py`) is the simulation-side `ICodingAgent`. It is the deterministic counterpart to the production `ClaudeCodeAdapter` and ensures scenarios exercise the same port the production bootstrap wires — without spawning containers or subprocesses.

### Minimum shape

- **Explicit port inheritance**: `class MockClaudeCodeAdapter(ICodingAgent)` — no duck typing, no `TYPE_CHECKING`-only imports (mirrors the production-side constraint in `CLAUDE.md`).
- **`supported_invocation_modes()`**: returns `frozenset({InvocationMode.CONTAINERIZED, InvocationMode.HOST})` by default, matching the modes the production adapter supports. Tests that need to exercise mode validation can override via the `supported_modes` constructor argument.
- **`execute(execution, workspace_context, options) -> CodingAgentResult`**: records every invocation in `self.invocations` for assertions, then publishes either the default 5-event ledger or a script-supplied custom ledger to the injected `event_bus`, then returns the configured `CodingAgentResult`.
- **`invocations: list[_Invocation]`**: ordered record of `(execution_id, work_item_id, agent_id, invocation_mode, model)` per call. Test code reads this directly.

### Default event ledger (5 events per `execute()`)

When the mock is constructed without a `script`, every `execute()` publishes the same five-event stream to the bus. This is the minimum sequence that exercises the bootstrap Phase 4d event-persistence bridge and any subscribers (e.g. `BoardColumnEventHandler` via `AgentExecutionCompletedEvent`) without representing a realistic agent run:

1. `CodingAgentInvokedEvent` (lifecycle bookend: invocation begins)
2. `CodingAgentReadyEvent` (lifecycle bookend: init complete, ready for prompt)
3. `CodingAgentTextOutputEvent` (a single assistant text response = the configured `summary_text`)
4. `CodingAgentTokensUsedEvent` (resource accounting from `default_result`)
5. `CodingAgentCompletedEvent` (lifecycle bookend: outcome)

Each event carries `execution_id`, `correlation_id = work_item_id`, and a `source = "mock_claude_code"` tag so test assertions can filter cleanly.

### Override hooks

```python
ScriptCallable = Callable[
    [AgentExecution, WorkspaceContext, CodingAgentInvocationOptions],
    Awaitable[tuple[list[CodetoreumEvent], CodingAgentResult]],
]

MockClaudeCodeAdapter(
    event_bus=event_bus,
    supported_modes=frozenset({InvocationMode.API}),  # narrow modes for negative tests
    default_result=CodingAgentResult(success=False, summary_text="planned failure", ...),
    script=my_async_script,  # full control over events + result per invocation
)
```

- **`default_result`**: replace the success/cost/token defaults without writing a script.
- **`script`**: supply richer ledgers — tool calls, rate limits, API retries, thinking events, OTel spans — when the 5-event default is not enough. The script returns `(events, result)`; the adapter publishes the events and returns the result.

### Why this shape

- **Simulation parity**: tests wire `MockClaudeCodeAdapter` into the same `coding_agent` slot the production bootstrap wires `ClaudeCodeAdapter` into. No simulation-specific application-layer branches.
- **Event-bus contract validation**: the default ledger exercises Phase 4d's event-store persistence subscriber in scenarios that point at an `InMemoryEventStore`, so the bridge is covered end-to-end in unit tests.
- **Determinism**: no randomness, no clock dependencies, no subprocesses. The same scenario produces the same event stream across runs.

See `~/.claude/plans/coding-agent-port-redesign.md` §3a–§3c for the production-side `ICodingAgent` contract and the full 11-event `CodingAgent*` taxonomy.

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

**Total Adapter Count**: 37 testing + 2 secondary + 18 input port = **57 adapters**

All adapters implement port contracts to provide a complete, testable implementation of the Codetoreum architecture.
