# Bootstrap Wiring: Simulation System Startup Sequence

Complete documentation of how the Simulation Implementation wires all output adapters, 17 input ports, and 12 application services through a 6-phase bootstrap sequence.

> **DEF-015 impact**: The `llm_provider` (`MockLLMAdapter`) and `storage` (`InMemoryStorageAdapter`) slots retired in D5. The new `coding_agent` (`MockClaudeCodeAdapter`) slot is populated in Phase 2 and required by `ExecutionService.execute()` at dispatch. See `adapters.md` for the current 34-row adapter table.

## Bootstrap Overview

The Simulation Implementation bootstrap is implemented in:
```
src/codetoreum/infrastructure/simulation/bootstrap.py
  - SimulationApplicationBootstrap (main orchestrator)
  - SimulationAdapters (container for 33 required output adapters + 4 optional fields incl. coding_agent)
  - SimulationServices (container for 12 application services)
  - SimulationPorts (container for 17 input port implementations)
```

The bootstrap is called from test runners and scenario loaders to prepare a complete, wired system for testing.

## 6-Phase Bootstrap Sequence

### Phase 0: Create Simulation Engine

**Purpose**: Set up timing control and simulation-specific configuration

**What happens**:
1. Create `SimulationEngine` with clock and configuration
2. Create `SimulationClock` with speed multiplier (default: 100x)
3. Initialize timing state for fast-forwarding
4. Set up scenario configuration from YAML or defaults

**Code**:
```python
# Phase 0: Create simulation engine
engine = SimulationEngine(
    config=config,  # SimulationConfig with speed_multiplier
    clock=SimulationClock(speed_multiplier=100.0),
)
```

**Output**: Configured simulation engine ready for adapter creation

---

### Phase 1: Create Infrastructure (Early for Event Subscriptions)

**Purpose**: Set up event bus, logging, and error handling BEFORE adapters

**Why Early**: Adapters need to subscribe to domain events during instantiation. The event bus must exist before Phase 2.

**What happens**:
1. Create `EventBus` (pub/sub for domain events)
2. Create `ErrorRegistry` (error ID management)
3. Create logger configuration
4. Create `CausalLinkRegistry` (event tracing)
5. Create `BootstrapDegradedModeState` (failure tracking)

**Code**:
```python
# Phase 1: Create infrastructure (early for event subscriptions)
event_bus = EventBus()
error_registry = ErrorRegistry()
causal_link_registry = CausalLinkRegistry()
degraded_mode = BootstrapDegradedModeState()
```

**Output**: Wired infrastructure ready for adapter subscriptions

---

### Phase 2: Create Output Port Adapters (34 Adapters)

**Purpose**: Instantiate all mock and in-memory adapters for output ports

**Dependencies**: Requires Phase 1 (event bus must exist)

**How It Works**:
- Uses `AdapterResolver` for dependency injection
- `AdapterResolver` understands adapter dependencies and instantiation order
- Each adapter is created and registered in `SimulationAdapters` container
- Adapters can subscribe to domain events during initialization
- Returns 33 adapters via resolver + 1 manual (branch resolution) = 34 total

**Adapters Created** (34 total):
- **Ticket System**: `InMemoryTicketAdapter`
- **Coding Agent**: `MockClaudeCodeAdapter` (replaced `MockLLMAdapter` in DEF-015 D5)
- **Container**: `FakeContainerAdapter`
- **Repository**: `InMemoryRepositoryAdapter`
- **Event Store**: `InMemoryEventStore`
- **Metrics**: `InMemoryMetricsAdapter`
- **Config Store**: `InMemoryConfigStore`
- **Notifier**: `MockNotifierAdapter`
- **Encryption**: `SimpleEncryptionAdapter`
- **Board Service**: `MockBoardAdapter`
- **Repair Cycle**: `MockRepairCycleAdapter`
- **Project Manager**: `MockProjectManagerAdapter`
- **Pipeline Lock Service**: `InMemoryLockService`
- **Workflow Config**: `InMemoryWorkflowConfigService`
- **Pipeline Queue**: `InMemoryQueueService`
- **Event Emitter**: `CapturingMockEventEmitter`
- **Audit Store**: `InMemoryAuditStore`
- **Version Control**: `InMemoryVersionControlService`
- **Message Broker**: `InMemoryMessageBroker`
- **Discussion**: `MockDiscussionAdapter`
- **Review Cycle**: `MockReviewCycleAdapter`
- **PR Review Cycle**: `MockPRReviewCycleAdapter`
- **Code Review**: `InMemoryCodeReviewAdapter`
- **Identity Service**: `ConfigurableIdentityService`
- **Checkpoint Store**: `InMemoryCheckpointStore`
- **CI Pipeline**: `MockCIPipelineAdapter`
- **Agent Repository**: `InMemoryAgentRepository`
- **Active Workflow Run Registry**: `InMemoryActiveWorkflowRunRegistry`
- **Work Item Branch Tracker**: `InMemoryWorkItemBranchTracker`
- **Work Item Service**: `MockWorkItemService`
- **Container Recovery**: `MockContainerRecoveryAdapter`
- **Systemic Analysis Service**: `MockSystemicAnalysisAdapter`
- **Environment Repair Service**: `MockEnvironmentRepairAdapter`
- **Branch Resolution Service**: `MockBranchResolutionAdapter` *(created manually after resolver)*

**Code**:
```python
# Phase 2: Create adapters via resolver
resolver = AdapterResolver(
    event_bus=event_bus,
    config=config,
)
adapters = await resolver.create_all_adapters()
# Returns SimulationAdapters container with 34 typed adapters
```

**Key Outputs** (all typed as port interfaces):
- `adapters.ticket_system: ITicketSystem` (InMemoryTicketAdapter)
- `adapters.coding_agent: ICodingAgent` (MockClaudeCodeAdapter)
- `adapters.container: IContainer` (FakeContainerAdapter)
- `adapters.repository: IRepository` (InMemoryRepositoryAdapter)
- `adapters.event_store: IEventStore` (InMemoryEventStore)
- `adapters.metrics: IMetrics` (InMemoryMetricsAdapter)
- `adapters.config_store: IConfigStore` (InMemoryConfigStore)
- `adapters.notifier: INotifier` (MockNotifierAdapter)
- `adapters.encryption: IEncryptionService` (SimpleEncryptionAdapter)
- `adapters.board: IBoardService` (MockBoardAdapter)
- `adapters.repair_cycle: IRepairCycle` (MockRepairCycleAdapter)
- `adapters.project_manager: IProjectManagerService` (MockProjectManagerAdapter)
- `adapters.lock_service: IPipelineLockService` (InMemoryLockService)
- `adapters.workflow_config: IWorkflowConfigService` (InMemoryWorkflowConfigService)
- `adapters.queue_service: IPipelineQueueService` (InMemoryQueueService)
- `adapters.event_emitter: IEventEmitter` (CapturingMockEventEmitter)
- `adapters.audit_store: IAuditStore` (InMemoryAuditStore)
- `adapters.version_control: IVersionControlService` (InMemoryVersionControlService)
- `adapters.message_broker: IMessageBroker` (InMemoryMessageBroker)
- `adapters.discussion_adapter: IDiscussionAdapter` (MockDiscussionAdapter)
- `adapters.review_cycle: IReviewCycle` (MockReviewCycleAdapter)
- `adapters.pr_review_cycle: IPRReviewCycle` (MockPRReviewCycleAdapter)
- `adapters.code_review: ICodeReviewService` (InMemoryCodeReviewAdapter)
- `adapters.identity_service: IIdentityService` (ConfigurableIdentityService)
- `adapters.checkpoint_store: IRepairCycleCheckpointStore` (InMemoryCheckpointStore)
- `adapters.ci_pipeline: ICIPipelineService` (MockCIPipelineAdapter)
- `adapters.agent_repository: IAgentRepository` (InMemoryAgentRepository)
- `adapters.run_registry: IActiveWorkflowRunRegistry` (InMemoryActiveWorkflowRunRegistry)
- `adapters.branch_tracker: IWorkItemBranchTracker` (InMemoryWorkItemBranchTracker)
- `adapters.work_item_service: IWorkItemService` (MockWorkItemService)
- `adapters.container_recovery: IAgentContainerRecoveryService` (MockContainerRecoveryAdapter)
- `adapters.systemic_analysis_service: ISystemicAnalysisService` (MockSystemicAnalysisAdapter)
- `adapters.environment_repair_service: IEnvironmentRepairService` (MockEnvironmentRepairAdapter)
- `adapters.branch_resolution_service: IBranchResolutionService` (MockBranchResolutionAdapter)

---

### Phase 3: Create Application Services (12 Services)

**Purpose**: Instantiate domain orchestration logic with dependencies injected

**Dependencies**: Requires Phase 2 (adapters must exist)

**Services Created** (12 total):
1. `ConfigurationService` — Manages configuration
2. `ExecutionService` — Manages agent execution lifecycle
3. `WorkspaceRouter` — Manages container workspaces
4. `AgentExecutionRecoveryService` — Recovery logic for execution failures
5. `ExecutionServiceAgentExecutor` — Agent executor (wired into `adapters.agent_executor`)
6. `ReviewService` — Handles code review cycles
7. `FeedbackProcessor` — Processes review feedback
8. `PipelineManager` — Controls workflow progression
9. `AgentScheduler` — Queues and schedules executions
10. `ConversationalLoopOrchestrator` — Multi-turn agent dialogue management
11. `WorkflowOrchestrator` — Coordinates multi-stage workflows
12. `WorkItemService` — Work item operations
13. `ContainerRecoveryService` — Handles container failure recovery
14. `MultiProjectOrchestrator` — Multi-project coordination

Note: `ExecutionServiceAgentExecutor` and `ConversationalLoopOrchestrator` are created in this
phase but stored separately (`adapters.agent_executor` and `self.conversational_loop_orchestrator`).
`SimulationServices` contains the remaining 12 services.

**Dependency Injection Pattern**:
```python
# Example: ExecutionService receives adapter dependencies
# DEF-015 D4 slimmed ExecutionService: container/storage/log dependencies retired;
# the ICodingAgent slot now owns invocation, telemetry, and output flow.
execution_service = ExecutionService(
    coding_agent=adapters.coding_agent,
    event_store=adapters.event_store,
    vcs=adapters.version_control,
)
```

**Code**:
```python
# Phase 3: Create services
workflow_orchestrator = WorkflowOrchestrator(
    task_queue=task_queue,
    config=project_config,
    workflow_state=workflow_state_manager,
    decision_events=decision_events,
    event_store=adapters.event_store,
    ticket_system=adapters.ticket_system,
    projects_api=projects_api,
    event_bus=event_bus,
    board_service=adapters.board,
    workflow_config=adapters.workflow_config,
    conversational_loop_orchestrator=conversational_loop_orchestrator,
)

execution_service = ExecutionService(
    coding_agent=adapters.coding_agent,
    event_store=adapters.event_store,
    vcs=adapters.version_control,
)

# ... create remaining 12 services
```

**Output**: `SimulationServices` container with 12 fully-wired services

---

### Phase 4: Create Input Port Implementations (17 Input Ports)

**Purpose**: Wire backing adapters to input port contracts for HTTP request/response

**Dependencies**: Requires Phase 2 adapters and Phase 3 agent_executor

**Input Ports Created** (17 total):

*Command Ports (7)*:
1. `MockWorkflowCommandAdapter` → `IWorkflowCommandPort`
2. `MockWorkItemCommandAdapter` → `IWorkItemCommandPort`
3. `MockWorkflowDefinitionCommandAdapter` → `IWorkflowDefinitionCommandPort`
4. `MockOrchestrationCommandAdapter` → `IOrchestrationCommandPort`
5. `MockAgentCommandAdapter` → `IAgentCommandPort`
6. `MockExecutionCommandAdapter` → `IExecutionCommandPort`
7. `MockConfigCommandAdapter` → `IConfigurationCommandPort`

*Query Ports (10)*:
8. `MockTaskQueryAdapter` → `ITaskQueryPort`
9. `MockWorkItemQueryAdapter` → `IWorkItemQueryPort` (backed by `ticket_system`)
10. `MockWorkflowQueryAdapter` → `IWorkflowQueryPort`
11. `WorkflowRunQueryService` → `IWorkflowRunQueryPort` (backed by `event_store` + `ticket_system`)
12. `MockAgentQueryAdapter` → `IAgentQueryPort`
13. `MockExecutionQueryAdapter` → `IExecutionQueryPort` (backed by `agent_executor`)
14. `MockConfigQueryAdapter` → `IConfigurationQueryPort` (backed by `config_store`)
15. `SimulationMetricsQueryAdapter` → `IMetricsQueryPort` (backed by `metrics` + `event_store`)
16. `MockWorkspaceQueryAdapter` → `IWorkspaceQueryPort`
17. `MockAuditQueryAdapter` → `IAuditQueryPort` (backed by `audit_store`)

**Code**:
```python
# Phase 4: Create input ports (wired to backing adapters)
work_item_command = MockWorkItemCommandAdapter()
work_item_query = MockWorkItemQueryAdapter(ticket_adapter=adapters.ticket_system)
execution_query = MockExecutionQueryAdapter(agent_executor=adapters.agent_executor)
config_query = MockConfigQueryAdapter(config_store=adapters.config_store)
metrics_query = engine.create_metrics_query_adapter(
    metrics_adapter=adapters.metrics,
    event_store=adapters.event_store,
)
audit_query = MockAuditQueryAdapter(audit_store=adapters.audit_store)
workflow_run_query = WorkflowRunQueryService(
    event_store=adapters.event_store,
    ticket_system=adapters.ticket_system,
)
# ... 10 remaining ports (all standalone mocks, no injection)
```

**Output**: `SimulationPorts` container with 17 fully-wired input ports

---

### Phase 5: Create FastAPI App and Register Event Handlers

**Purpose**: Mount all input ports to HTTP endpoints and wire event subscriptions

**Dependencies**: Requires Phases 1-4 (all adapters and services)

**What Happens**:
1. Create FastAPI application instance
2. Import and mount simulation routers (for testing endpoints)
3. Register event handlers for domain events:
   - `BoardColumnEventHandler` — Work item column transitions
   - `ReviewEventHandler` — Review status changes
   - `PRReviewCycleEventHandler` — PR review workflows
   - `PRReviewCycleDispatchHandler` — PR dispatch logic
4. Wire input ports to HTTP endpoints
5. Configure CORS, middleware, exception handling
6. Return fully-configured FastAPI app

**Event Handler Registration** (7 handlers total):
```python
# Phase 5: Register event handlers

# 1. BoardColumnEventHandler — agent execution + auto-progression on column changes
event_bus.register_handler(BoardColumnEventHandler(
    board_service=adapters.board,
    lock_service=adapters.lock_service,
    workflow_config=adapters.workflow_config,
    event_store=adapters.event_store,
    agent_executor=adapters.agent_executor,
    event_bus=event_bus,
    run_registry=adapters.run_registry,
    event_emitter=adapters.event_emitter,
    recovery_service=services.agent_execution_recovery_service,
))

# 2. ConversationalLoopOrchestrator — terminates sessions when items leave conversational columns
event_bus.subscribe("WorkItemColumnChangedEvent",
    conversational_loop_orchestrator.handle_column_change_event)

# 3. RepairCycleEventHandler — triggers repair cycle on column changes
event_bus.register_handler(engine.create_repair_cycle_event_handler(
    repair_cycle=adapters.repair_cycle,
    workflow_config=adapters.workflow_config,
    event_bus=event_bus,
    ci_pipeline_service=adapters.ci_pipeline,
))

# 4. PRReviewCycleDispatchHandler — initiates PR review cycles on column entry
event_bus.register_handler(PRReviewCycleDispatchHandler(
    pr_review_cycle=adapters.pr_review_cycle,
    workflow_config=adapters.workflow_config,
    work_item_service=adapters.work_item_service,
    active_workflow_run_registry=adapters.run_registry,
))

# 5. PRReviewCycleEventHandler — moves work items based on PR review cycle outcomes
event_bus.register_handler(PRReviewCycleEventHandler(
    board_service=adapters.board,
))

# 6. ReviewEventHandler — processes review cycle events with CI pipeline integration
event_bus.register_handler(ReviewEventHandler(
    review_service=services.review_service,
    ci_pipeline_service=adapters.ci_pipeline,
))

# 7. BranchResolutionEventHandler — logs branch resolution events for audit trail
event_bus.register_handler(engine.create_branch_resolution_event_handler(
    event_bus=event_bus,
))
```

**Endpoint Mounting** (simulation-only routers, never in production `create_app()`):
```python
# Standard input port routers (all 17 ports mounted)
app.include_router(orchestration_router, prefix="/api/orchestration")
app.include_router(workflow_router, prefix="/api/workflows")
app.include_router(workflow_definition_router, prefix="/api/workflow-definitions")
app.include_router(workflow_run_router, prefix="/api/workflow-runs")
app.include_router(work_item_router, prefix="/api/work-items")
app.include_router(execution_router, prefix="/api/executions")
app.include_router(agent_router, prefix="/api/agents")
app.include_router(config_router, prefix="/api/config")
app.include_router(metrics_router, prefix="/api/metrics")
app.include_router(audit_router, prefix="/api/audit")
app.include_router(workspace_router, prefix="/api/workspaces")

# Simulation-only routers
app.include_router(sim_ticketing_router)         # /api/simulation/tickets
app.include_router(sim_clock_router)             # /api/simulation/clock
app.include_router(sim_board_state_router)       # /api/simulation/board-state
app.include_router(sim_stream_router)            # /api/simulation/stream (SSE)
app.include_router(sim_executions_router)        # /api/simulation/executions
```

**Code Example**:
```python
# Phase 5: Create FastAPI app
app = await create_app(
    adapters=adapters,
    services=services,
    ports=ports,
    event_bus=event_bus,
)
```

**Output**: Fully-configured FastAPI application ready for HTTP requests

---

## Bootstrap Wiring Diagram (Level 4 Mermaid Flowchart)

```mermaid
flowchart TD
    Start([Bootstrap Start]) --> Phase0["Phase 0: Simulation Engine<br/>━━━━━━━━━━━━<br/>• Create SimulationEngine<br/>• Create SimulationClock<br/>• Load configuration (YAML)"]

    Phase0 --> Phase1["Phase 1: Infrastructure<br/>━━━━━━━━━━━━<br/>• Create EventBus<br/>• Create ErrorRegistry<br/>• Create Logger<br/>• Create CausalLinkRegistry<br/>⚠️ EARLY: Event subscriptions needed!"]

    Phase1 --> Phase2["Phase 2: Output Port Adapters (34)<br/>━━━━━━━━━━━━━━━━━━━<br/>Depends on: Phase 1 (EventBus)"]

    Phase2 --> Phase2a["Create Ticket System<br/>InMemoryTicketAdapter"]
    Phase2a --> Phase2b["Create Coding Agent<br/>MockClaudeCodeAdapter"]
    Phase2b --> Phase2c["Create Container Runtime<br/>FakeContainerAdapter"]
    Phase2c --> Phase2d["Create Repository<br/>InMemoryRepositoryAdapter"]
    Phase2d --> Phase2e["Create Event Store<br/>InMemoryEventStore"]
    Phase2e --> Phase2f["Create Board Service<br/>MockBoardAdapter"]
    Phase2f --> Phase2g["Create 30 More Adapters<br/>Repair Cycle, Review Cycle,<br/>Storage, Config, Metrics, etc."]

    Phase2g --> Phase3["Phase 3: Application Services (12)<br/>━━━━━━━━━━━━━━<br/>Depends on: Phase 2 (Adapters)"]

    Phase3 --> Phase3a["Create WorkflowOrchestrator<br/>Inject: ticket, board, event_bus"]
    Phase3a --> Phase3b["Create ExecutionService<br/>Inject: 30+ adapter dependencies"]
    Phase3b --> Phase3c["Create AgentScheduler<br/>Inject: queue, event_bus"]
    Phase3c --> Phase3d["Create 8 More Services<br/>PipelineManager, ReviewService,<br/>WorkspaceRouter, ConfigService, etc."]

    Phase3d --> Phase4["Phase 4: Input Port Adapters (17)<br/>━━━━━━━━━━━━━━━━<br/>Depends on: Phase 3 (Services)"]

    Phase4 --> Phase4a["Create Command Ports (7)<br/>Wrap service methods as input ports"]
    Phase4a --> Phase4b["Create Query Ports (11)<br/>Wrap service queries as input ports"]

    Phase4b --> Phase5["Phase 5: FastAPI App<br/>━━━━━━━━━━━━<br/>Depends on: Phases 1-4"]

    Phase5 --> Phase5a["Create FastAPI instance"]
    Phase5a --> Phase5b["Mount Input Port Routers<br/>Orchestration, WorkItem,<br/>Execution, Agent, Config"]
    Phase5b --> Phase5c["Register Event Handlers<br/>BoardColumnEventHandler,<br/>ReviewEventHandler,<br/>PRReviewCycleEventHandler"]
    Phase5c --> Phase5d["Configure Middleware<br/>CORS, Exception Handling,<br/>Logging"]

    Phase5d --> Phase6["Phase 6 (Optional): Watchdog Services<br/>━━━━━━━━━━━━━━━━<br/>• Auto-advance clock<br/>• Stale lock watchdog<br/>• Execution timeout watchdog<br/>• SLA expiry watchdog<br/>• Column progression watchdog"]

    Phase6 --> End([Bootstrap Complete<br/>Ready for Testing])

    style Phase0 fill:#FFE4B5
    style Phase1 fill:#FFD700
    style Phase2 fill:#90EE90
    style Phase3 fill:#87CEEB
    style Phase4 fill:#DDA0DD
    style Phase5 fill:#F08080
    style Phase6 fill:#FFC0CB
    style End fill:#98FB98
```

---

## Detailed Bootstrap Process Code

### Complete Bootstrap Implementation

```python
# Location: src/codetoreum/infrastructure/simulation/bootstrap.py

class SimulationApplicationBootstrap:
    """Orchestrates 6-phase bootstrap of simulation system."""

    async def setup(self) -> FastAPI:
        """Execute complete 6-phase bootstrap."""

        try:
            # Phase 0: Create simulation engine
            logger.info("Phase 0: Creating simulation engine...")
            engine = self._create_engine(self.config)

            # Phase 1: Create infrastructure (EARLY)
            logger.info("Phase 1: Creating infrastructure...")
            infrastructure = self._create_infrastructure(engine)

            # Phase 2: Create adapters
            logger.info("Phase 2: Creating 34 adapters...")
            adapters = await self._create_adapters()

            # Phase 2b: Register causal links
            logger.info("Phase 2b: Registering causal links...")
            self._register_causal_links(adapters)

            # Phase 3: Create services
            logger.info("Phase 3: Creating 12 services...")
            services = await self._create_services()

            # Phase 4: Create input ports
            logger.info("Phase 4: Creating 17 input ports...")
            ports = self._create_ports()

            # Phase 5: Create FastAPI app
            logger.info("Phase 5: Creating FastAPI app...")
            app = await self._create_app()

            # Phase 5b: Validate causal links
            logger.info("Phase 5b: Validating causal link consistency...")
            self._validate_causal_links()

            # Phase 6+: Optional watchdogs
            self._start_optional_watchdogs()

            logger.info("Bootstrap complete!")
            return app

        except Exception as e:
            logger.error(f"Bootstrap failed: {e}", exc_info=True)
            raise
```

### Key Data Structures

```python
@dataclass
class SimulationAdapters:
    """All 33 required output port adapters (+ 4 optional fields assigned during bootstrap, including coding_agent)."""

    # Core output port adapters (required, no defaults)
    ticket_system: ITicketSystem                     # InMemoryTicketAdapter
    container: IContainer                            # FakeContainerAdapter
    repository: IRepository                          # InMemoryRepositoryAdapter
    event_store: IEventStore                         # InMemoryEventStore
    metrics: IMetrics                                # InMemoryMetricsAdapter
    config_store: IConfigStore                       # InMemoryConfigStore
    notifier: INotifier                              # MockNotifierAdapter
    encryption: IEncryptionService                   # SimpleEncryptionAdapter
    board: IBoardService                             # MockBoardAdapter
    repair_cycle: IRepairCycle                       # MockRepairCycleAdapter
    project_manager: IProjectManagerService          # MockProjectManagerAdapter
    lock_service: IPipelineLockService               # InMemoryLockService
    workflow_config: IWorkflowConfigService          # InMemoryWorkflowConfigService
    queue_service: IPipelineQueueService             # InMemoryQueueService
    event_emitter: IEventEmitter                     # CapturingMockEventEmitter
    audit_store: IAuditStore | None                  # InMemoryAuditStore
    version_control: IVersionControlService          # InMemoryVersionControlService
    message_broker: IMessageBroker                   # InMemoryMessageBroker
    discussion_adapter: IDiscussionAdapter           # MockDiscussionAdapter
    review_cycle: IReviewCycle                       # MockReviewCycleAdapter
    pr_review_cycle: IPRReviewCycle                  # MockPRReviewCycleAdapter
    code_review: ICodeReviewService                  # InMemoryCodeReviewAdapter
    identity_service: IIdentityService               # ConfigurableIdentityService
    checkpoint_store: IRepairCycleCheckpointStore    # InMemoryCheckpointStore
    ci_pipeline: ICIPipelineService                  # MockCIPipelineAdapter
    agent_repository: IAgentRepository               # InMemoryAgentRepository
    run_registry: IActiveWorkflowRunRegistry         # InMemoryActiveWorkflowRunRegistry
    branch_tracker: IWorkItemBranchTracker           # InMemoryWorkItemBranchTracker
    work_item_service: IWorkItemService              # MockWorkItemService
    container_recovery: IAgentContainerRecoveryService  # MockContainerRecoveryAdapter
    systemic_analysis_service: ISystemicAnalysisService # MockSystemicAnalysisAdapter
    environment_repair_service: IEnvironmentRepairService  # MockEnvironmentRepairAdapter

    # Optional fields assigned during bootstrap (default None)
    branch_resolution_service: IBranchResolutionService | None = None  # MockBranchResolutionAdapter (Phase 2)
    agent_executor: IAgentExecutor | None = None                       # ExecutionServiceAgentExecutor (Phase 3)
    tracer: ITracer | None = None                                      # InMemoryTracer (Phase 2)
    # DEF-015 D3/D4 — production wires the resilient ClaudeCodeAdapter,
    # simulation wires MockClaudeCodeAdapter. Required at ExecutionService dispatch.
    coding_agent: ICodingAgent | None = None                           # MockClaudeCodeAdapter (Phase 2)

    # Type-safe accessor methods
    def ticket_as_mock(self) -> InMemoryTicketAdapter:
        """Get ticket adapter as mock (for test code)."""
        return cast(InMemoryTicketAdapter, self.ticket_system)

@dataclass
class SimulationServices:
    """All 12 application services (9 required + 3 optional)."""

    # Required services
    workflow_orchestrator: WorkflowOrchestrator
    execution_service: ExecutionService
    agent_scheduler: AgentScheduler
    pipeline_manager: PipelineManager
    review_service: ReviewService
    feedback_processor: FeedbackProcessor
    workspace_router: WorkspaceRouter
    configuration_service: ConfigurationService
    work_item_service: WorkItemService

    # Optional services (may be None in minimal configurations)
    agent_execution_recovery_service: AgentExecutionRecoveryService | None = None
    multi_project_orchestrator: MultiProjectOrchestrator | None = None
    container_recovery_service: ContainerRecoveryService | None = None

@dataclass
class SimulationPorts:
    """All 17 input port implementations (7 command + 10 query)."""

    # Command ports (7)
    workflow_command: IWorkflowCommandPort           # MockWorkflowCommandAdapter
    work_item_command: IWorkItemCommandPort          # MockWorkItemCommandAdapter
    workflow_definition_command: IWorkflowDefinitionCommandPort  # MockWorkflowDefinitionCommandAdapter
    orchestration_command: IOrchestrationCommandPort # MockOrchestrationCommandAdapter
    agent_command: IAgentCommandPort                 # MockAgentCommandAdapter
    execution_command: IExecutionCommandPort         # MockExecutionCommandAdapter
    config_command: IConfigurationCommandPort        # MockConfigCommandAdapter

    # Query ports (10)
    task_query: ITaskQueryPort                       # MockTaskQueryAdapter
    work_item_query: IWorkItemQueryPort              # MockWorkItemQueryAdapter
    workflow_query: IWorkflowQueryPort               # MockWorkflowQueryAdapter
    workflow_run_query: IWorkflowRunQueryPort        # WorkflowRunQueryService
    agent_query: IAgentQueryPort                     # MockAgentQueryAdapter
    execution_query: IExecutionQueryPort             # MockExecutionQueryAdapter
    config_query: IConfigurationQueryPort            # MockConfigQueryAdapter
    metrics_query: IMetricsQueryPort                 # SimulationMetricsQueryAdapter
    workspace_query: IWorkspaceQueryPort             # MockWorkspaceQueryAdapter
    audit_query: IAuditQueryPort                     # MockAuditQueryAdapter
```

---

## Dependency Graph

### Simplified Dependency View

```
Phase 1 (EventBus) ←─ Required by ─→ Phase 2 (Adapters)
                                            ↓
                                      Phase 3 (Services)
                                            ↓
                                      Phase 4 (Input Ports)
                                            ↓
                                      Phase 5 (FastAPI App)
                                            ↓
                                      Phase 6 (Watchdogs)
```

### Adapter Dependencies (Phase 2 Internal Order)

Adapters are resolved in dependency order by `AdapterResolver`:

```
# Group 1: Leaf adapters (no dependencies)
InMemoryEventStore
InMemoryConfigStore
InMemoryMetricsAdapter
SimpleEncryptionAdapter
ConfigurableIdentityService

# Group 2: Event infrastructure
CapturingMockEventEmitter
InMemoryMessageBroker

# Group 3: Depend on event_emitter
FakeContainerAdapter        (event_emitter)
InMemoryVersionControlService (event_emitter)
MockBoardAdapter            (event_emitter)
InMemoryQueueService        (event_emitter)

# Group 4: External system interfaces
InMemoryTicketAdapter       (event_bus)
MockClaudeCodeAdapter       (event_bus)  # ICodingAgent — replaced MockLLMAdapter in DEF-015 D5

# Group 5: Coordination
MockDiscussionAdapter
InMemoryLockService

# Group 6: State tracking
InMemoryCheckpointStore
InMemoryAgentRepository
InMemoryActiveWorkflowRunRegistry
InMemoryWorkItemBranchTracker
MockWorkItemService
InMemoryWorkflowConfigService
MockNotifierAdapter

# Group 7: Composite
MockProjectManagerAdapter

# Group 8: Repository
InMemoryRepositoryAdapter   (event_emitter)

# Group 9: Engine-coupled (SimulationEngine injects clock)
MockReviewCycleAdapter      (engine/clock)
MockRepairCycleAdapter      (engine/clock)
MockPRReviewCycleAdapter    (engine/clock)

# Group 10: Additional services
InMemoryCodeReviewAdapter
MockContainerRecoveryAdapter
MockSystemicAnalysisAdapter
MockEnvironmentRepairAdapter
MockCIPipelineAdapter

# Group 11: Manual post-processing (34th adapter)
MockBranchResolutionAdapter (engine/clock)
```

### Service Dependencies (Phase 3 Internal Order)

```
ConfigurationService (config_store, event_bus, encryption)
  ↓
ExecutionService (coding_agent, event_store, version_control)  # DEF-015 D4 slimming
  ↓
WorkspaceRouter (version_control, container, event_store, branch_resolution_service)
  ↓
AgentExecutionRecoveryService (board, event_store, run_registry, failed_event_store)
  ↓
ExecutionServiceAgentExecutor → adapters.agent_executor
  (execution_service, workspace_router, config_store, agent_repository,
   work_item_service, run_registry, branch_tracker, version_control, clock,
   recovery_service)
  ↓
ReviewService (event_store)
  ↓
FeedbackProcessor ()
  ↓
PipelineManager (event_store)
  ↓
AgentScheduler (task_queue, resource_monitor, rate_limiter, config,
                scheduling_events, event_store)
  ↓
ConversationalLoopOrchestrator → self.conversational_loop_orchestrator
  (discussion_adapter, llm_provider, event_store, event_emitter)
  ↓
WorkflowOrchestrator (task_queue, config, workflow_state, decision_events,
                      event_store, ticket_system, projects_api, event_bus,
                      board_service, workflow_config,
                      conversational_loop_orchestrator)
  ↓
WorkItemService (event_store)
  ↓
ContainerRecoveryService (container_recovery, event_emitter, container_timeout_hours)
  ↓
MultiProjectOrchestrator (project_manager, workflow_orchestrator, board_service,
                           event_emitter, poll_interval_seconds)
```

---

## Bootstrap Configuration

### From Code

```python
# Create simulation with fast configuration
config = SimulationConfig.create_fast_config(
    name="test_workflow",
    speed_multiplier=100.0,  # 100x faster
)

bootstrap = SimulationApplicationBootstrap(config)
app = await bootstrap.setup()
```

### From YAML

```python
# Load scenario from YAML
config = SimulationConfig.from_yaml("scenarios/demo.yaml")

bootstrap = SimulationApplicationBootstrap(config)
app = await bootstrap.setup()
```

### YAML Configuration Example

```yaml
name: "smoke_test"
speed_multiplier: 10.0
auto_advance: false

# Optional: Override adapter selections
# Note: the `llm` / `storage` slots retired in DEF-015 D5; the new coding-agent
# slot is hard-wired in bootstrap to MockClaudeCodeAdapter for simulation.
adapters:
  ticket_system: "in_memory"
  container: "fake"
  event_store: "in_memory"
  board: "mock"

projects:
  - name: "test-project"
    description: "Test project"

workflows:
  - name: "test-workflow"
    stages:
      - name: "analyze"
        agent_type: "architect"
        order: 1
      - name: "code"
        agent_type: "coder"
        order: 2
```

---

## Error Handling and Degraded Mode

The bootstrap includes degraded mode support for graceful degradation:

```python
@dataclass
class BootstrapDegradedModeState:
    """Tracks bootstrap phase failures."""
    failed_phases: dict[BootstrapPhase, str]

    def mark_failed(self, phase: BootstrapPhase, error: str) -> None:
        """Mark a phase as failed."""
        self.failed_phases[phase] = error

    @property
    def is_degraded(self) -> bool:
        """True if any phases failed."""
        return bool(self.failed_phases)
```

**Phases That Can Degrade**:
- Phase 6 (Auto-advance)
- Phase 6b (Stale lock watchdog)
- Phase 6c (Execution timeout watchdog)
- Phase 6d (SLA expiry watchdog)
- Phase 6e (Column progression watchdog)

**Phases That Fail Hard**:
- Phase 0-5 (Critical infrastructure)

If a watchdog (Phase 6+) fails, the system logs a warning but continues with degraded mode.

---

## Absorbed Content from PRODUCTION_BOOTSTRAP_WIRING.md

This document absorbs relevant bootstrap integration patterns from the renamed `PRODUCTION_BOOTSTRAP_WIRING.md`:

### Factories for Production Bootstrap (Future Phase 7)

When production bootstrap is created, the following factories from `codetoreum.adapters.primary.factories` will be available:

```python
# Two-step instantiation pattern
branch_resolution = create_branch_resolution_adapter(
    ticket_system=real_github_adapter,
    version_control=real_vcs_adapter,
    event_emitter=real_event_emitter,
)

workspace_router = create_workspace_router_with_branch_resolution(
    version_control=real_vcs_adapter,
    container=real_container_adapter,
    event_store=real_event_store,
    branch_resolution_service=branch_resolution,
)
```

The simulation bootstrap already includes these adapters (simulation versions), serving as a template for production bootstrap integration.

---

## Testing Bootstrap Behavior

### Verify Bootstrap Completeness

```python
# After bootstrap completes, verify all adapters are wired
adapters = bootstrap.adapters
assert isinstance(adapters.ticket_system, ITicketSystem)       # InMemoryTicketAdapter
assert isinstance(adapters.coding_agent, ICodingAgent)         # MockClaudeCodeAdapter (Phase 2 — optional slot, populated in sim bootstrap)
assert isinstance(adapters.container, IContainer)              # FakeContainerAdapter
assert isinstance(adapters.repository, IRepository)            # InMemoryRepositoryAdapter
assert isinstance(adapters.event_store, IEventStore)           # InMemoryEventStore
assert isinstance(adapters.metrics, IMetrics)                  # InMemoryMetricsAdapter
assert isinstance(adapters.config_store, IConfigStore)         # InMemoryConfigStore
assert isinstance(adapters.notifier, INotifier)                # MockNotifierAdapter
assert isinstance(adapters.encryption, IEncryptionService)     # SimpleEncryptionAdapter
assert isinstance(adapters.board, IBoardService)               # MockBoardAdapter
assert isinstance(adapters.repair_cycle, IRepairCycle)         # MockRepairCycleAdapter
assert isinstance(adapters.project_manager, IProjectManagerService)
assert isinstance(adapters.lock_service, IPipelineLockService) # InMemoryLockService
assert isinstance(adapters.workflow_config, IWorkflowConfigService)
assert isinstance(adapters.queue_service, IPipelineQueueService)
assert isinstance(adapters.event_emitter, IEventEmitter)       # CapturingMockEventEmitter
assert adapters.audit_store is not None                        # InMemoryAuditStore
assert isinstance(adapters.version_control, IVersionControlService)
assert isinstance(adapters.message_broker, IMessageBroker)
assert isinstance(adapters.discussion_adapter, IDiscussionAdapter)
assert isinstance(adapters.review_cycle, IReviewCycle)
assert isinstance(adapters.pr_review_cycle, IPRReviewCycle)
assert isinstance(adapters.code_review, ICodeReviewService)
assert isinstance(adapters.identity_service, IIdentityService)
assert isinstance(adapters.checkpoint_store, IRepairCycleCheckpointStore)
assert isinstance(adapters.ci_pipeline, ICIPipelineService)
assert isinstance(adapters.agent_repository, IAgentRepository)
assert isinstance(adapters.run_registry, IActiveWorkflowRunRegistry)
assert isinstance(adapters.branch_tracker, IWorkItemBranchTracker)
assert isinstance(adapters.work_item_service, IWorkItemService)
assert isinstance(adapters.container_recovery, IAgentContainerRecoveryService)
assert isinstance(adapters.systemic_analysis_service, ISystemicAnalysisService)
assert isinstance(adapters.environment_repair_service, IEnvironmentRepairService)
assert adapters.branch_resolution_service is not None          # MockBranchResolutionAdapter
assert adapters.agent_executor is not None                     # ExecutionServiceAgentExecutor (Phase 3)

# Verify services are created
services = bootstrap.services
assert services.workflow_orchestrator is not None
assert services.execution_service is not None
assert services.agent_scheduler is not None
assert services.pipeline_manager is not None
assert services.review_service is not None
assert services.feedback_processor is not None
assert services.workspace_router is not None
assert services.configuration_service is not None
assert services.work_item_service is not None
assert services.agent_execution_recovery_service is not None
assert services.multi_project_orchestrator is not None
assert services.container_recovery_service is not None

# Verify input ports are wired
ports = bootstrap.ports
assert ports.workflow_command is not None
assert ports.work_item_command is not None
assert ports.workflow_definition_command is not None
assert ports.orchestration_command is not None
assert ports.agent_command is not None
assert ports.execution_command is not None
assert ports.config_command is not None
assert ports.task_query is not None
assert ports.work_item_query is not None
assert ports.workflow_query is not None
assert ports.workflow_run_query is not None
assert ports.agent_query is not None
assert ports.execution_query is not None
assert ports.config_query is not None
assert ports.metrics_query is not None
assert ports.workspace_query is not None
assert ports.audit_query is not None
```

### Monitor Bootstrap Phases

```python
# Bootstrap logs each phase
logger.info("Phase 0: Creating simulation engine...")
logger.info("Phase 1: Creating infrastructure...")
logger.info("Phase 2: Creating 34 adapters...")
logger.info("Phase 3: Creating 12 services...")
logger.info("Phase 4: Creating 17 input ports...")
logger.info("Phase 5: Creating FastAPI app...")
```

---

## Related Files and References

- **Bootstrap Implementation**: `src/codetoreum/infrastructure/simulation/bootstrap.py`
- **Adapter Resolver**: `src/codetoreum/infrastructure/adapters/resolver.py`
- **Adapter Factory**: `src/codetoreum/infrastructure/adapters/factory.py`
- **Configuration**: `src/codetoreum/infrastructure/simulation/simulation_config.py`
- **Simulation Engine**: `src/codetoreum/infrastructure/simulation/simulation_engine.py`
- **Port Specifications**: `documentation/architecture/ports/`
- **Adapters Reference**: [adapters.md](./adapters.md)
- **Overview**: [overview.md](./overview.md)

---

## Summary

The 6-phase bootstrap creates a complete, wired Simulation Implementation:

| Phase | What | How Many | Duration |
|-------|------|----------|----------|
| 0 | Simulation engine | 1 | < 1ms |
| 1 | Infrastructure | 5 components | < 1ms |
| 2 | Output adapters | 34 (+3 optional) | ~10-50ms |
| 3 | Services | 12 | ~20-100ms |
| 4 | Input ports | 17 | ~10-20ms |
| 5 | FastAPI app | 1 | ~50-200ms |
| **Total** | **Complete system** | **~70 components** | **~100-400ms** |

Total bootstrap time: **100-400ms** depending on adapter complexity and event subscription overhead.

Result: A production-quality simulation system ready for scenario testing.
