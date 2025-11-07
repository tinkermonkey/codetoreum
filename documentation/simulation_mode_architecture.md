# Simulation Mode Architecture

## Overview

Simulation mode is a complete testing environment that enables end-to-end workflow testing without any external dependencies. It provides a fully functional Codetoreum application stack using in-memory adapters, achieving 10-100x faster execution than production mode while maintaining complete determinism and observability.

**Key Benefits:**
- **Zero External Dependencies**: No GitHub, Docker, Claude API, Redis, or Elasticsearch required
- **Deterministic Execution**: Reproducible test results every time
- **Fast Execution**: 10-100x speed multiplier via time manipulation
- **Complete Observability**: Full event sourcing with replay capability
- **Developer Friendly**: Start testing in <5 minutes

## Architecture Overview

Simulation mode implements the full hexagonal architecture with mock adapters replacing all external integrations:

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI Application                      │
│                    (REST + WebSocket APIs)                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                        Input Ports                               │
│  (IWorkflowCommandPort, IWorkItemQueryPort, etc.)               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                   Application Services                           │
│  WorkflowOrchestrator, ExecutionService, AgentScheduler, etc.   │
└─────────┬───────────────────────────────────────────┬───────────┘
          │                                           │
┌─────────▼─────────────┐                 ┌──────────▼────────────┐
│   Domain Layer        │                 │  Infrastructure       │
│  (Pure Business Logic)│                 │  EventBus, Clock      │
└───────────────────────┘                 └───────────────────────┘
          │                                           │
┌─────────▼───────────────────────────────────────────▼───────────┐
│                        Output Ports                              │
│  (ITicketSystem, ILLMProvider, IContainer, etc.)                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                     Mock Adapters (9 total)                      │
│  InMemoryTicketAdapter    │  MockLLMAdapter                     │
│  FakeContainerAdapter     │  InMemoryEventStore                 │
│  InMemoryRepositoryAdapter│  InMemoryMetricsAdapter            │
│  InMemoryStorageAdapter   │  InMemoryConfigStore               │
│  MockNotifierAdapter      │  SimpleEncryptionAdapter           │
└─────────────────────────────────────────────────────────────────┘
```

## Bootstrap Flow

The `SimulationApplicationBootstrap` class orchestrates the entire initialization sequence in 5 phases:

### Phase 1: Create Adapters

Creates all 9 mock adapters using the `AdapterFactory` in simulation mode:

```python
# Location: src/codetoreum/infrastructure/simulation/bootstrap.py:294-340

factory_config = AdapterFactoryConfig(
    operation_mode=OperationMode.SIMULATION,
    enable_resilience=False,  # ADR-005: No resilience in simulation
)
adapter_factory = AdapterFactory(factory_config)

# Create primary adapters via factory
ticket_system = adapter_factory.create_ticket_system(adapter_name="in_memory")
llm_provider = adapter_factory.create_llm_provider(adapter_name="mock")
container = adapter_factory.create_container(adapter_name="fake")
repository = adapter_factory.create_repository(adapter_name="in_memory")
event_store = adapter_factory.create_event_store(adapter_name="in_memory")

# Create supporting adapters directly
metrics = InMemoryMetricsAdapter()
storage = InMemoryStorageAdapter()
config_store = InMemoryConfigStore()
notifier = MockNotifierAdapter()
encryption = SimpleEncryptionAdapter()
```

**Mock Adapters:**
1. **InMemoryTicketAdapter** - Simulates GitHub issues, projects, labels
2. **MockLLMAdapter** - Pattern-based LLM responses with token tracking
3. **FakeContainerAdapter** - Simulates Docker container execution
4. **InMemoryRepositoryAdapter** - In-memory Git operations
5. **InMemoryEventStore** - Complete event sourcing with replay
6. **InMemoryMetricsAdapter** - Metrics collection and querying
7. **InMemoryStorageAdapter** - Artifact storage (logs, outputs)
8. **InMemoryConfigStore** - Configuration management
9. **MockNotifierAdapter** - Notification delivery simulation

### Phase 2: Create Infrastructure

Sets up cross-cutting infrastructure components:

```python
# Location: src/codetoreum/infrastructure/simulation/bootstrap.py:346-375

# Simulation clock with time manipulation
clock = SimulationClock(
    speed_multiplier=config.time.speed_multiplier,  # 10-100x faster
    auto_advance=config.time.auto_advance,
)
clock.start_at(config.time.start_time)  # Deterministic start time

# Event bus for domain events
event_bus = EventBus()

# Application logger
logger = logging.getLogger("codetoreum")
```

**Infrastructure Components:**
- **SimulationClock**: Time manipulation for fast execution (see "Time Manipulation" section)
- **EventBus**: In-memory pub/sub for domain events
- **Logger**: Standard Python logging

### Phase 3: Create Services

Wires application services with dependencies:

```python
# Location: src/codetoreum/infrastructure/simulation/bootstrap.py:381-545

# Configuration Service
configuration_service = ConfigurationService(
    config_store=adapters.config_store,
    event_bus=event_bus,
    encryption_service=adapters.encryption,
)

# Execution Service
execution_service = ExecutionService(
    llm_provider=adapters.llm_provider,
    container=adapters.container,
    event_store=adapters.event_store,
    storage=adapters.storage,
)

# Agent Scheduler with mock dependencies
task_queue = InMemoryTaskQueue()
resource_monitor = MockResourceMonitor()
rate_limiter = MockRateLimiter()
agent_scheduler = AgentScheduler(
    task_queue=task_queue,
    resource_monitor=resource_monitor,
    rate_limiter=rate_limiter,
    config=project_config,
    event_store=adapters.event_store,
)

# ... 6 more services created similarly
```

**Application Services (9 total):**
1. ConfigurationService
2. ExecutionService
3. WorkspaceRouter
4. ReviewService
5. FeedbackProcessor
6. PipelineManager
7. AgentScheduler
8. WorkflowOrchestrator
9. WorkItemService

### Phase 4: Create Ports

Creates port implementations (mock adapters for input ports in simulation):

```python
# Location: src/codetoreum/infrastructure/simulation/bootstrap.py:551-600

# Mock port adapters provide standalone implementations
work_item_command = MockWorkItemCommandAdapter()
work_item_query = MockWorkItemQueryAdapter()
agent_command = MockAgentCommandAdapter()
execution_query = MockExecutionQueryAdapter()

# Metrics query port integrates with real adapters
metrics_query = MockMetricsQueryAdapter(
    metrics_adapter=adapters.metrics,
    event_store=adapters.event_store,
    clock=clock,
)

# ... 10 more ports created
```

**Port Interfaces (15 total):**
- **Command Ports**: Work items, workflows, agents, executions, config
- **Query Ports**: Tasks, metrics, workspaces, events

### Phase 5: Create FastAPI App

Wires all ports to FastAPI routers:

```python
# Location: src/codetoreum/infrastructure/simulation/bootstrap.py:606-649

app = create_app(
    # Command ports
    workflow_command_port=ports.workflow_command,
    work_item_command_port=ports.work_item_command,
    agent_command_port=ports.agent_command,
    execution_command_port=ports.execution_command,

    # Query ports
    task_query_port=ports.task_query,
    metrics_query_port=ports.metrics_query,
    work_item_query_port=ports.work_item_query,

    # Infrastructure
    event_store=adapters.event_store,
    event_bus=event_bus,
    config_service=config_service_interface,
    logger=logger_interface,

    # ADR-003: Simulation mode settings
    disable_auth=True,  # No authentication in simulation
    cors_origins=["*"],  # Allow all origins
)
```

## Adapter Wiring: Hexagonal Architecture

The simulation mode strictly follows hexagonal architecture principles:

### Inbound Flow (Primary Adapters)

```
HTTP Request → FastAPI Router → Input Port → Application Service → Domain Logic
```

**Example: Create Work Item**

```python
# 1. FastAPI receives HTTP POST to /api/v2/work-items
# 2. Router calls input port
work_item = await work_item_command_port.create_work_item(request_data)

# 3. Port delegates to application service
result = await work_item_service.create(project_id, title, description)

# 4. Service uses domain logic
work_item = WorkItem.create(...)  # Pure domain model

# 5. Service persists via output port
await event_store.append(work_item.id, work_item.events)
```

### Outbound Flow (Secondary Adapters)

```
Domain Logic → Application Service → Output Port → Mock Adapter → In-Memory Storage
```

**Example: Execute Agent**

```python
# 1. ExecutionService receives command
execution = await execution_service.execute_agent(agent_id, context)

# 2. Service calls LLM provider port
response = await llm_provider.generate_code(prompt, model="claude-3-5-sonnet")

# 3. Port delegates to mock adapter
# Location: src/codetoreum/adapters/testing/mock_llm_adapter.py
class MockLLMAdapter(ILLMProvider):
    async def generate_code(self, prompt: str, model: str) -> LLMResponse:
        # Pattern matching for deterministic responses
        if "authentication" in prompt.lower():
            return LLMResponse(content="# OAuth2 implementation...", tokens=500)
        # ... more patterns
        return self._default_response

# 4. Mock response returned through the chain
```

### Dependency Injection

All dependencies flow inward toward the domain:

```
Adapters → Services → Domain
         ↑
    (Ports define interfaces)
```

**Benefits:**
- Domain has zero external dependencies
- Adapters are swappable (mock ↔ production)
- Port interfaces enforce contracts
- Easy testing at every layer

## Time Manipulation

The `SimulationClock` enables deterministic, fast-forwarding time:

### Basic Time Control

```python
# Location: src/codetoreum/infrastructure/simulation/simulation_clock.py:10-321

clock = SimulationClock(speed_multiplier=10.0)  # 10x faster
clock.start_at(datetime(2025, 1, 1, 12, 0, 0))

# Advance time programmatically
await clock.advance(timedelta(hours=1))  # Takes 6 minutes real time
current = clock.now()  # Returns 2025-01-01 13:00:00
```

### Speed Multipliers

- **1.0x**: Real-time (for debugging, demos)
- **10.0x**: Realistic simulation (for manual testing)
- **100.0x**: Fast testing (for automated E2E tests)

**Example: Agent execution taking 30 minutes in production:**
- At 10x: 3 minutes real time
- At 100x: 18 seconds real time

### Scheduled Callbacks

Schedule events to trigger at specific times:

```python
def on_timeout(trigger_time: datetime):
    logger.warning(f"Execution timeout at {trigger_time}")

clock.schedule_callback(
    callback=on_timeout,
    after_delta=timedelta(minutes=30),  # 18 seconds at 100x
)
```

### Integration with Tests

```python
# In E2E tests
client = SimulationE2EClient(app, bootstrap)

# Advance time to trigger scheduled tasks
client.advance_minutes(5)  # Fast-forward 5 minutes
await client.wait_for_work_item_status(item_id, "COMPLETED")
```

## Event Sourcing Integration

The `InMemoryEventStore` provides complete audit trail and replay capability:

### Event Storage

```python
# Location: src/codetoreum/adapters/testing/in_memory_event_store.py:18-48

class InMemoryEventStore(IEventStore):
    def __init__(self):
        # Stream storage: stream_id -> events
        self._streams: Dict[str, List[DomainEvent]] = {}

        # Global event list for queries
        self._all_events: List[DomainEvent] = []

        # Type index for fast lookups
        self._events_by_type: Dict[str, List[DomainEvent]] = {}

        # Correlation tracking
        self._events_by_correlation: Dict[str, List[DomainEvent]] = {}

        # Thread-safe for concurrent tests
        self._lock = threading.Lock()
```

### Event Append

```python
await event_store.append(
    stream_id="work-item-123",
    events=[
        WorkItemCreated(...),
        WorkItemAssigned(...),
    ],
    expected_version=0,  # Optimistic concurrency control
)
```

### Event Queries

```python
# Get all events for a work item
events = await event_store.get_events("work-item-123")

# Query by type across all streams
execution_events = await event_store.query_events(
    event_type="AgentExecutionCompleted",
    limit=100,
)

# Query by correlation ID (trace entire workflow)
workflow_events = await event_store.query_events(
    correlation_id="workflow-abc-123",
)
```

### Event Replay

Replay events to reconstruct aggregate state:

```python
# Rebuild work item from events
events = await event_store.get_events("work-item-123")
work_item = WorkItem.from_events(events)

# Verify state transitions
assert work_item.status == WorkItemStatus.COMPLETED
assert len(work_item.executions) == 3
```

## Testing Strategy

Simulation mode supports multiple testing levels:

### 1. Unit Tests

Test individual components in isolation:

```python
@pytest.mark.asyncio
async def test_work_item_creation():
    """Test WorkItem domain model."""
    work_item = WorkItem.create(
        project_id="proj-1",
        title="Test item",
        description="Test description",
    )

    assert work_item.status == WorkItemStatus.NEW
    assert len(work_item.events) == 1
    assert work_item.events[0].event_type == "WorkItemCreated"
```

### 2. Integration Tests

Test service integration with mock adapters:

```python
@pytest.mark.asyncio
async def test_execution_service(mock_llm, fake_container, in_memory_event_store):
    """Test ExecutionService with mock adapters."""
    service = ExecutionService(
        llm_provider=mock_llm,
        container=fake_container,
        event_store=in_memory_event_store,
        storage=InMemoryStorageAdapter(),
    )

    result = await service.execute_agent(
        agent_id="agent-1",
        context={"issue": "Add authentication"},
    )

    assert result.status == ExecutionStatus.COMPLETED
    assert mock_llm.get_stats()["total_calls"] == 1
```

### 3. Simulation Tests

Test complete workflows with SimulationRunner:

```python
@pytest.mark.simulation
@pytest.mark.asyncio
async def test_simple_workflow():
    """Test complete workflow execution."""
    config = SimulationConfig.create_fast_config(
        scenario_name="test",
        speed_multiplier=100.0,
    )
    runner = SimulationRunner(config)

    async def scenario(runner: SimulationRunner):
        # Setup
        work_item = await runner.create_work_item(...)
        await runner.trigger_workflow(work_item.id, "workflow-1")

        # Wait for completion
        await runner.wait_for_status(work_item.id, "COMPLETED")

        # Assertions
        events = runner.get_events_by_type("AgentExecutionCompleted")
        assert len(events) == 3  # 3 stages completed

    result = await runner.run(scenario)
    assert result.success
    assert result.speed_multiplier == 100.0
```

### 4. E2E Tests with Bootstrap

Test via HTTP API using full application stack:

```python
@pytest.mark.asyncio
async def test_e2e_workflow(simulation_bootstrap, e2e_client):
    """Test workflow via REST API."""
    # Create work item via API
    response = e2e_client.create_work_item(
        project_id="proj-1",
        title="Add authentication",
        description="Implement OAuth2",
    )
    work_item_id = response["id"]

    # Trigger workflow
    e2e_client.trigger_workflow(work_item_id, "feature-workflow")

    # Wait for completion
    await e2e_client.wait_for_work_item_status(
        work_item_id,
        "COMPLETED",
        timeout=30.0,
    )

    # Verify observability
    e2e_client.assert_metrics_recorded("execution_duration")
    e2e_client.assert_events_recorded("AgentExecutionCompleted")
```

### 5. Manual Testing with CLI

Interactive testing via simulation server:

```bash
# Start server
python -m codetoreum.cli.simulation_server --scenario demo

# Interact via curl
curl -X POST http://localhost:8000/api/v2/work-items \
  -H "Content-Type: application/json" \
  -d '{"project_id": "proj-1", "title": "Test item", ...}'
```

## Architecture Decision Records (ADRs)

### ADR-001: Hexagonal Architecture with Simulation Adapters

**Decision**: Implement complete hexagonal architecture with swappable adapters for testing.

**Rationale**:
- Enables testing without external dependencies
- Maintains production parity (same domain/service code)
- Allows easy adapter replacement (mock ↔ production)

**Consequences**:
- All external interactions must go through ports
- Adapters must conform to port interfaces
- Domain layer remains pure and testable

### ADR-002: In-Memory Event Store

**Decision**: Use in-memory event store with full event sourcing support.

**Rationale**:
- Complete audit trail for debugging
- Event replay for state reconstruction
- Zero external dependencies (no Redis/Elasticsearch)
- Fast queries via in-memory indexes

**Consequences**:
- All data lost on shutdown (acceptable for testing)
- Memory usage grows with event count
- Thread-safe implementation required for concurrent tests

### ADR-003: Disabled Authentication in Simulation

**Decision**: Disable authentication and enable CORS wildcard in simulation mode.

**Rationale**:
- Simplifies testing (no token management)
- Enables frontend development without auth complexity
- Reduces test setup overhead

**Consequences**:
- Simulation mode MUST NOT be used in production
- Clear warnings required in documentation and UI
- Configuration flag enforces simulation-only usage

### ADR-004: Time Manipulation with SimulationClock

**Decision**: Implement deterministic clock with speed multiplier for fast execution.

**Rationale**:
- Tests run 10-100x faster than real time
- Deterministic timestamps for reproducibility
- Scheduled callbacks for timeout testing
- Same interface as production RealTimeClock

**Consequences**:
- All time operations must use clock abstraction
- Real asyncio.sleep must be avoided in services
- Thread-safe implementation required

### ADR-005: No Resilience Patterns in Simulation

**Decision**: Disable circuit breakers, rate limiting, and retries in simulation adapters.

**Rationale**:
- Resilience patterns add non-determinism (timeouts, backoff)
- Testing focus is on business logic, not failure handling
- Dedicated resilience tests in integration layer
- Faster test execution without delays

**Consequences**:
- Resilience patterns tested separately with real adapters
- Simulation focuses on happy path + explicit failures
- Clear separation between functional and resilience testing

## Component Interactions

### Example: Complete Workflow Execution

```
1. HTTP POST /api/v2/orchestrator/trigger
   ↓
2. FastAPI Router → IOrchestrationCommandPort
   ↓
3. MockOrchestrationCommandAdapter → WorkflowOrchestrator
   ↓
4. Orchestrator.trigger_workflow()
   ├─ Load WorkItem from InMemoryEventStore
   ├─ Load Workflow definition from InMemoryConfigStore
   ├─ Schedule first stage via AgentScheduler
   └─ Emit WorkflowStarted event
   ↓
5. AgentScheduler dequeues task
   ├─ Check resources (MockResourceMonitor)
   ├─ Check rate limits (MockRateLimiter)
   └─ Start execution via ExecutionService
   ↓
6. ExecutionService.execute_agent()
   ├─ Prepare context (WorkspaceRouter)
   ├─ Call MockLLMAdapter.generate_code()
   ├─ Run in FakeContainerAdapter.run()
   ├─ Store artifacts in InMemoryStorageAdapter
   └─ Emit AgentExecutionCompleted event
   ↓
7. EventBus notifies subscribers
   ├─ WorkflowOrchestrator advances to next stage
   ├─ MetricsAdapter records execution duration
   └─ WebSocket pushes event to connected clients
   ↓
8. Repeat steps 5-7 for remaining stages
   ↓
9. Final stage completion → WorkflowCompleted event
   ↓
10. HTTP Response: {"status": "success", "workflow_id": "..."}
```

## Performance Characteristics

### Execution Speed

| Scenario | Real Time | 10x Simulation | 100x Simulation |
|----------|-----------|----------------|-----------------|
| Simple workflow (3 stages, 30m total) | 30 minutes | 3 minutes | 18 seconds |
| Complex workflow (5 stages, 2h total) | 2 hours | 12 minutes | 1.2 minutes |
| Parallel executions (10 items, 1h each) | 1 hour | 6 minutes | 36 seconds |
| Review cycle (2 iterations, 45m total) | 45 minutes | 4.5 minutes | 27 seconds |

### Memory Footprint

- **Minimal simulation**: ~50 MB (1 project, 1 workflow, 5 work items)
- **Demo scenario**: ~150 MB (3 projects, 5 workflows, 25 work items)
- **Stress test**: ~500 MB (10 projects, 20 workflows, 500 work items)

### Scalability

- **Concurrent tests**: Thread-safe adapters support parallel pytest execution
- **Event storage**: O(1) append, O(n) query by type, O(log n) query by time
- **Metrics storage**: O(1) record, O(n) query with filters

## File Locations

| Component | File Path |
|-----------|-----------|
| Bootstrap | `/workspace/src/codetoreum/infrastructure/simulation/bootstrap.py` |
| Simulation Clock | `/workspace/src/codetoreum/infrastructure/simulation/simulation_clock.py` |
| Simulation Config | `/workspace/src/codetoreum/infrastructure/simulation/simulation_config.py` |
| Data Seeder | `/workspace/src/codetoreum/infrastructure/simulation/seeding.py` |
| CLI Server | `/workspace/src/codetoreum/cli/simulation_server.py` |
| E2E Client | `/workspace/tests/simulation/e2e_client.py` |
| Mock LLM | `/workspace/src/codetoreum/adapters/testing/mock_llm_adapter.py` |
| In-Memory Event Store | `/workspace/src/codetoreum/adapters/testing/in_memory_event_store.py` |
| Fake Container | `/workspace/src/codetoreum/adapters/testing/fake_container_adapter.py` |
| Test Fixtures | `/workspace/tests/simulation/conftest.py` |
| Scenario Examples | `/workspace/scenarios/*.yaml` |

## Next Steps

- **Usage Guide**: [guides/simulation_mode_usage.md](guides/simulation_mode_usage.md) - Learn how to start the simulation server and interact via API
- **Testing Guide**: [guides/testing_with_simulation_mode.md](guides/testing_with_simulation_mode.md) - Write E2E tests using simulation mode
- **Design Documentation**: [01_design/02_high_level_arch.md](01_design/02_high_level_arch.md) - Detailed architecture design
- **Implementation Plan**: [01_design/03_implementation_plan.md](01_design/03_implementation_plan.md) - Phase-by-phase implementation details

## References

- [Hexagonal Architecture (Ports and Adapters)](https://alistair.cockburn.us/hexagonal-architecture/)
- [Event Sourcing Pattern](https://martinfowler.com/eaaDev/EventSourcing.html)
- [Domain-Driven Design](https://martinfowler.com/bliki/DomainDrivenDesign.html)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pytest Asyncio](https://pytest-asyncio.readthedocs.io/)
