# Complete Simulation Mode Implementation Guide

## Executive Summary

The Codetoreum simulation mode is a **fully functional, zero-dependency testing environment** that enables:
- Complete end-to-end application testing without external services (GitHub, Docker, Claude API, Redis)
- Workflow execution **10-100x faster** than real-time using time manipulation
- Deterministic, reproducible test scenarios with full observability
- Interactive server startup for demos and manual testing

This document provides complete technical details on all 10 components of the simulation architecture.

---

## Architecture Overview

### Component Stack (Bottom-Up)

```
┌─────────────────────────────────────────────────────────┐
│ FastAPI REST API + WebSocket (Real-time events)        │
├─────────────────────────────────────────────────────────┤
│ Input Ports (Command/Query Handlers)                    │
├─────────────────────────────────────────────────────────┤
│ Application Services (8 total)                          │
├─────────────────────────────────────────────────────────┤
│ Output Port Adapters (9 mock adapters)                  │
├─────────────────────────────────────────────────────────┤
│ Infrastructure (Event Bus, Clock, Logger)               │
├─────────────────────────────────────────────────────────┤
│ Bootstrap Orchestrator                                   │
└─────────────────────────────────────────────────────────┘
```

### Simulation Bootstrap Flow

```
SimulationApplicationBootstrap.setup()
  ├─ Create Infrastructure
  │   ├─ SimulationClock (time manipulation)
  │   ├─ EventBus (domain event pub/sub)
  │   └─ Logger
  │
  ├─ Create 9 Mock Adapters
  │   ├─ InMemoryTicketAdapter (work items)
  │   ├─ MockLLMAdapter (pattern-based responses)
  │   ├─ FakeContainerAdapter (container execution)
  │   ├─ InMemoryRepositoryAdapter (git operations)
  │   ├─ InMemoryEventStore (event sourcing)
  │   ├─ InMemoryMetricsAdapter (metrics collection)
  │   ├─ InMemoryStorageAdapter (file storage)
  │   ├─ InMemoryConfigStore (configuration)
  │   └─ MockNotifierAdapter (notifications)
  │
  ├─ Create 8 Application Services
  │   ├─ WorkflowOrchestrator
  │   ├─ ExecutionService
  │   ├─ AgentScheduler
  │   ├─ PipelineManager
  │   ├─ ReviewService
  │   ├─ FeedbackProcessor
  │   ├─ WorkspaceRouter
  │   ├─ ConfigurationService
  │   └─ WorkItemService
  │
  ├─ Create Input Port Implementations (15 ports)
  │   ├─ Command Ports (write operations)
  │   └─ Query Ports (read operations)
  │
  └─ Create FastAPI Application
      ├─ Wire ports to REST API routes
      ├─ Configure WebSocket endpoints
      ├─ Set up authentication
      └─ Register health check endpoints
```

---

## 1. Bootstrap Flow

**File**: `/workspace/src/codetoreum/infrastructure/simulation/bootstrap.py`

**Class**: `SimulationApplicationBootstrap`

### Purpose
Single entry point that wires up the entire application stack in simulation mode, handling dependency injection and component initialization.

### Key Methods

```python
class SimulationApplicationBootstrap:
    def __init__(self, config: SimulationConfig):
        """Initialize with simulation configuration."""
        self.config = config
        self.adapters: Optional[SimulationAdapters] = None
        self.infrastructure: Optional[SimulationInfrastructure] = None
        self.services: Optional[SimulationServices] = None
        self.ports: Optional[SimulationPorts] = None
        self.app: Optional[FastAPI] = None
        self._is_setup = False

    async def setup(self) -> None:
        """Set up entire application stack."""
        await self._create_infrastructure()
        await self._create_adapters()
        await self._create_services()
        await self._create_ports()
        await self._create_fastapi_app()
        self._is_setup = True

    async def teardown(self) -> None:
        """Clean up resources."""
        # Cleanup code here
```

### Initialization Order (Critical)
1. **Infrastructure first** - EventBus, Clock, Logger are foundational
2. **Adapters second** - Mock adapters that services depend on
3. **Services third** - Application logic that uses adapters
4. **Ports fourth** - Wiring services to port interfaces
5. **FastAPI app last** - Wiring ports to REST/WebSocket API

### Data Containers
```python
@dataclass
class SimulationAdapters:
    ticket_system: InMemoryTicketAdapter
    llm_provider: MockLLMAdapter
    container: FakeContainerAdapter
    repository: InMemoryRepositoryAdapter
    event_store: InMemoryEventStore
    metrics: InMemoryMetricsAdapter
    storage: InMemoryStorageAdapter
    config_store: InMemoryConfigStore
    notifier: MockNotifierAdapter
    encryption: SimpleEncryptionAdapter

@dataclass
class SimulationServices:
    workflow_orchestrator: WorkflowOrchestrator
    execution_service: ExecutionService
    agent_scheduler: AgentScheduler
    pipeline_manager: PipelineManager
    review_service: ReviewService
    feedback_processor: FeedbackProcessor
    workspace_router: WorkspaceRouter
    configuration_service: ConfigurationService
    work_item_service: WorkItemService

@dataclass
class SimulationPorts:
    # 7 command ports
    workflow_command: IWorkflowCommandPort
    work_item_command: IWorkItemCommandPort
    workflow_definition_command: IWorkflowDefinitionCommandPort
    orchestration_command: IOrchestrationCommandPort
    agent_command: IAgentCommandPort
    execution_command: IExecutionCommandPort
    config_command: IConfigurationCommandPort

    # 8 query ports
    task_query: ITaskQueryPort
    work_item_query: IWorkItemQueryPort
    workflow_query: IWorkflowQueryPort
    agent_query: IAgentQueryPort
    execution_query: IExecutionQueryPort
    config_query: IConfigurationQueryPort
    metrics_query: IMetricsQueryPort
    workspace_query: IWorkspaceQueryPort
```

---

## 2. Adapter Implementations

### 2.1 MockLLMAdapter

**File**: `/workspace/src/codetoreum/adapters/testing/mock_llm_adapter.py`

**Purpose**: Provides deterministic LLM responses for testing without calling real APIs.

**Features**:
- Pattern-based response matching (regex patterns)
- Configurable delays (simulating network latency)
- Rate limiting simulation
- Conversation history tracking
- Token usage statistics
- Streaming support

**Key Methods**:
```python
async def execute(prompt: str) -> ExecutionResult:
    """Execute a prompt and return pre-configured response."""
    response = self._get_response_for_prompt(prompt)
    # Calculate tokens, record usage, return result

def add_response_pattern(pattern: str, response: str):
    """Add pattern -> response mapping."""
    compiled_pattern = re.compile(pattern, re.IGNORECASE)
    self._response_patterns.append((compiled_pattern, response))

async def execute_with_tools(prompt: str, tools: List[ToolDefinition]) -> ExecutionResult:
    """Support tool/function calling simulation."""
```

**Configuration Example** (from scenario):
```python
config.add_agent_response_pattern(
    agent_id="code-generator",
    pattern=r".*generate.*",
    response="```python\ndef authenticate():\n    pass\n```"
)
```

### 2.2 InMemoryEventStore

**File**: `/workspace/src/codetoreum/adapters/testing/in_memory_event_store.py`

**Purpose**: In-memory event sourcing storage for complete audit trail.

**Features**:
- Thread-safe event storage with locks
- Event replay for debugging
- Stream-based event organization
- Event type indexing for fast queries
- Correlation ID indexing
- Snapshot support for performance

**Key Data Structures**:
```python
class InMemoryEventStore:
    _streams: Dict[str, List[DomainEvent]]  # stream_id -> events
    _all_events: List[DomainEvent]          # Global event list
    _events_by_type: Dict[str, List[DomainEvent]]  # Fast type lookup
    _events_by_correlation: Dict[str, List[DomainEvent]]  # Correlation tracking
    _snapshots: Dict[str, Dict[str, Any]]   # Snapshots for replay
```

**Example Usage**:
```python
# Append events
await event_store.append(
    stream_id="work-item-123",
    events=[
        WorkItemCreated(...),
        WorkItemAssigned(...)
    ]
)

# Query events
events = await event_store.get_events("work-item-123")
workflow_events = await event_store.get_events_by_type("WorkflowStarted")

# Replay for debugging
async for event in event_store.replay_events("work-item-123"):
    print(f"Event: {event.event_type}")
```

### 2.3 InMemoryTicketAdapter

**File**: `/workspace/src/codetoreum/adapters/testing/in_memory_ticket_adapter.py`

**Purpose**: In-memory ticket/work item system (replaces GitHub).

**Features**:
- CRUD operations on work items
- Label, priority, and status management
- Search and filtering
- Comment/discussion thread support

**Typical Usage**:
```python
work_item_id = await ticket_adapter.create_work_item(
    title="Add authentication",
    description="Implement OAuth2",
    labels=["feature", "security"],
    priority="HIGH"
)

work_item = await ticket_adapter.get_work_item(work_item_id)
all_items = await ticket_adapter.list_work_items(
    labels=["feature"],
    priority="HIGH"
)
```

### 2.4 FakeContainerAdapter

**File**: `/workspace/src/codetoreum/adapters/testing/fake_container_adapter.py`

**Purpose**: Simulated container execution (replaces Docker).

**Features**:
- Command execution with configurable exit codes
- Stdout/stderr capture
- Command pattern matching
- Execution delay simulation

**Usage**:
```python
adapter.set_command_result(
    command_pattern="pytest",
    exit_code=0,
    stdout="====== 10 passed in 2.5s ======",
    stderr=""
)

result = await adapter.run_command("pytest tests/")
assert result.exit_code == 0
```

### 2.5 Other Mock Adapters

- **InMemoryRepositoryAdapter**: Git operations (clone, commit, push)
- **InMemoryStorageAdapter**: File storage for artifacts
- **InMemoryConfigStore**: Configuration storage
- **InMemoryMetricsAdapter**: Metrics collection and querying
- **MockNotifierAdapter**: Notification sending simulation
- **SimpleEncryptionAdapter**: Encryption for sensitive data

---

## 3. Time Manipulation (SimulationClock)

**File**: `/workspace/src/codetoreum/infrastructure/simulation/simulation_clock.py`

**Purpose**: Enables workflows to execute 10-100x faster by manipulating simulated time.

### Core Features

**Deterministic Time Control**:
```python
class SimulationClock:
    def __init__(self, speed_multiplier: float = 1.0):
        """Initialize clock with speed multiplier."""
        self._current_time = datetime.now(timezone.utc)
        self._speed_multiplier = speed_multiplier
        self._scheduled_callbacks = []

    def now(self) -> datetime:
        """Get current simulated time."""
        return self._current_time

    async def advance(self, delta: timedelta) -> None:
        """Advance time by delta."""
        real_delay = delta.total_seconds() / self._speed_multiplier
        await asyncio.sleep(real_delay)
        self._current_time += delta
```

**Speed Multiplier Examples**:
- 1.0 = real time
- 10.0 = 1 simulated hour = 6 real minutes
- 100.0 = 1 simulated hour = 36 real seconds

**Callback Scheduling**:
```python
# Schedule callback at specific time
clock.schedule_callback(
    callback=async_function,
    at_time=datetime(2025, 1, 2, 12, 0, 0)
)

# Schedule callback after delay
clock.schedule_callback(
    callback=sync_function,
    after_delta=timedelta(minutes=30)
)
```

**Usage in Tests**:
```python
clock = SimulationClock(speed_multiplier=100.0)
clock.start_at(datetime(2025, 1, 1, 12, 0, 0))

# Advance 1 hour of simulation time in 36 real seconds
await clock.advance(timedelta(hours=1))

assert clock.now() == datetime(2025, 1, 1, 13, 0, 0)
```

---

## 4. Event Sourcing Integration

### Flow

```
Domain Service
    ↓
Emit DomainEvent
    ↓
EventBus.publish()
    ↓
Event Store (InMemoryEventStore)
    ├─ Store in stream
    ├─ Update indexes
    └─ Broadcast to WebSocket subscribers
```

### Event Capture in Tests

```python
# In simulation runner
runner.capture_event(event)

# Query captured events
events = runner.get_events_by_type("WorkflowStarted")
assert len(events) == 1

# Assert event occurred
runner.assert_event_occurred(
    event_type="WorkflowCompleted",
    aggregate_id="work-item-123"
)
```

---

## 5. CLI Implementation (Simulation Server)

**File**: `/workspace/src/codetoreum/cli/simulation_server.py`

**Purpose**: Start the full application in simulation mode as an interactive HTTP server.

### Bootstrap Process

```
main()
  ├─ Parse CLI arguments
  ├─ bootstrap_application()
  │   ├─ Load SimulationConfig (from YAML or defaults)
  │   ├─ Create SimulationApplicationBootstrap
  │   └─ await bootstrap.setup()
  │
  ├─ seed_data()
  │   ├─ Create SimulationDataSeeder
  │   └─ Load scenario from YAML (projects, workflows, agents, work items)
  │
  ├─ display_startup_info()
  │   └─ Show URLs, configured settings
  │
  └─ run_server()
      └─ uvicorn.run(bootstrap.app)
```

### CLI Options

```bash
python -m codetoreum.cli.simulation_server \
  --host localhost \
  --port 8000 \
  --scenario demo \                    # Pre-built scenario
  --scenario-file custom.yaml \        # Custom scenario file
  --speed-multiplier 10 \              # Time acceleration
  --no-seed \                          # Skip data seeding
  --debug                              # Enable debug logging
```

### Startup Output

```
═══════════════════════════════════════════
   Codetoreum Simulation Server
═══════════════════════════════════════════

Loading Configuration
  Speed multiplier: 10x

Bootstrapping Application
  ✓ Application bootstrapped successfully

Seeding Test Data
  Created 1 projects, 1 workflows, 3 agents, 5 work items

URLs:
  API Docs:      http://localhost:8000/docs
  Health Check:  http://localhost:8000/api/health
  WebSocket:     ws://localhost:8000/ws
```

---

## 6. E2E Test Examples

**File**: `/workspace/tests/simulation/e2e/test_e2e_simple_workflow.py`

### Structure of E2E Tests

```python
@pytest.mark.asyncio
async def test_simple_workflow_success(e2e_client, simulation_seeder):
    # ========================================================================
    # Setup: Seed test data
    # ========================================================================
    await simulation_seeder.create_project(name="test-project")
    await simulation_seeder.create_workflow(name="3-stage-workflow")
    
    # ========================================================================
    # Test: Create work item
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="test-project",
        title="Add authentication"
    )
    assert work_item["status"] == "PENDING"
    
    # ========================================================================
    # Test: Connect WebSocket and trigger workflow
    # ========================================================================
    ws = e2e_client.connect_websocket()
    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="test-workflow"
    )
    
    # ========================================================================
    # Test: Monitor progress with time manipulation
    # ========================================================================
    ws.wait_for_event("workflow_started")
    e2e_client.advance_minutes(5)
    ws.wait_for_event("stage_completed", filter_fn=...)
    
    # ========================================================================
    # Test: Verify completion
    # ========================================================================
    final = await e2e_client.wait_for_work_item_status(
        work_item["id"],
        "COMPLETED"
    )
    assert final["status"] == "COMPLETED"
    
    # ========================================================================
    # Test: Verify metrics and events
    # ========================================================================
    e2e_client.assert_metrics_recorded("workflow_duration", min_count=1)
    e2e_client.assert_events_recorded("WorkflowCompleted", min_count=1)
```

### E2E Client Features

**File**: `/workspace/tests/simulation/e2e_client.py`

```python
class SimulationE2EClient:
    """High-level client for E2E testing."""
    
    def __init__(self, app: FastAPI, bootstrap: SimulationApplicationBootstrap):
        self.client = TestClient(app)  # Synchronous HTTP client
        self.bootstrap = bootstrap
        self.clock = bootstrap.infrastructure.clock
    
    # REST API methods
    def create_work_item(self, **kwargs) -> Dict:
        response = self.client.post("/api/work-items", json=kwargs)
        return response.json()
    
    def trigger_workflow(self, work_item_id: str, workflow_id: str) -> Dict:
        response = self.client.post(
            f"/api/orchestrator/work-items/{work_item_id}/workflow",
            json={"workflow_id": workflow_id}
        )
        return response.json()
    
    # WebSocket methods
    def connect_websocket(self, subscription_type: str = "all_events"):
        return self.client.websocket_connect("/ws")
    
    # Time manipulation
    def advance_minutes(self, minutes: int):
        asyncio.run(self.clock.advance(timedelta(minutes=minutes)))
    
    # Assertion methods
    def assert_metrics_recorded(self, metric_name: str, min_count: int = 1):
        metrics = self.client.get(f"/api/metrics?name={metric_name}").json()
        assert len(metrics) >= min_count
```

---

## 7. Test Fixtures

**File**: `/workspace/tests/simulation/conftest.py`

### Bootstrap Fixtures (for Phase 1)

```python
@pytest.fixture
async def simulation_bootstrap(fast_simulation_config):
    """Provide fully set up simulation bootstrap."""
    bootstrap = SimulationApplicationBootstrap(fast_simulation_config)
    await bootstrap.setup()
    yield bootstrap
    await bootstrap.teardown()

@pytest.fixture
async def simulation_app(simulation_bootstrap):
    """Provide FastAPI application."""
    return simulation_bootstrap.app

@pytest.fixture
async def simulation_adapters(simulation_bootstrap):
    """Provide all 9 mock adapters."""
    return simulation_bootstrap.adapters

@pytest.fixture
async def simulation_services(simulation_bootstrap):
    """Provide all 8 application services."""
    return simulation_bootstrap.services
```

### E2E Test Fixtures (for Phase 3)

```python
@pytest.fixture
async def simulation_seeder(simulation_bootstrap):
    """Provide data seeder for creating test data."""
    seeder = SimulationDataSeeder(simulation_bootstrap)
    yield seeder
    seeder.created_items.clear()

@pytest.fixture
async def e2e_client(simulation_app, simulation_bootstrap):
    """Provide E2E test client."""
    client = SimulationE2EClient(simulation_app, simulation_bootstrap)
    yield client
    if hasattr(client.client, 'close'):
        client.client.close()
```

### Configuration Fixtures

```python
@pytest.fixture
def simulation_clock():
    """Provide simulation clock."""
    clock = SimulationClock(speed_multiplier=100.0)
    clock.start_at(datetime(2025, 1, 1, 12, 0, 0))
    return clock

@pytest.fixture
def fast_simulation_config():
    """Provide fast simulation config (100x speed)."""
    return SimulationConfig.create_fast_config(
        scenario_name="test",
        speed_multiplier=100.0
    )

@pytest.fixture
def realistic_simulation_config():
    """Provide realistic config (10x speed)."""
    return SimulationConfig.create_realistic_config(
        scenario_name="test",
        speed_multiplier=10.0
    )
```

---

## 8. Scenario Files (YAML)

**Files**: `/workspace/scenarios/{default,demo,stress_test,review_cycle,failure_recovery}.yaml`

### Scenario Structure

```yaml
name: "Default Scenario"
description: "Basic test scenario"
version: "1.0"

# Simulation settings
speed_multiplier: 10.0
auto_advance: false

# Projects (seeded data)
projects:
  - name: "default-project"
    description: "Default test project"
    default_branch: "main"

# Workflows (multi-stage pipelines)
workflows:
  - name: "default-workflow"
    description: "3-stage workflow"
    stages:
      - name: "design"
        agent_type: "architect"
        order: 1
        max_retries: 3
        timeout_seconds: 3600
      - name: "implementation"
        agent_type: "coder"
        order: 2
      - name: "testing"
        agent_type: "tester"
        order: 3

# Agents (with capabilities and LLM settings)
agents:
  - name: "architect"
    agent_type: "architect"
    capabilities: ["code_generation", "code_review"]
    llm_model: "claude-3-5-sonnet-20241022"
    temperature: 0.7
    max_tokens: 4096
    enabled: true

# Work items (issues/tickets)
work_items:
  - title: "Add authentication"
    description: "Implement OAuth2"
    labels: ["feature", "security"]
    priority: "high"
    status: "new"

# Metadata
metadata:
  scenario_type: "demo"
  author: "codetoreum-team"
  tags: ["demo", "realistic"]
```

### Loading Scenarios

```python
# From YAML file
config = SimulationConfig.from_yaml("scenarios/demo.yaml")

# Programmatically
config = SimulationConfig.create_fast_config("test", speed_multiplier=100.0)
config.add_agent_response_pattern(
    agent_id="coder",
    pattern=r".*generate.*",
    response="Generated code..."
)
```

---

## 9. WebSocket Implementation

**File**: `/workspace/src/codetoreum/adapters/primary/websocket_adapter.py`

### Features

- **Token-based authentication** via query parameter
- **Client-side filtering** by event type, work item, workflow, agent
- **Backpressure handling** with buffer limits
- **Automatic disconnection** for slow consumers
- **Heartbeat/ping-pong** for connection health

### Subscription Types

```python
class SubscriptionType(Enum):
    WORKFLOW_EVENTS = "workflow_events"
    EXECUTION_EVENTS = "execution_events"
    ALL_EVENTS = "all_events"
    LOGS = "logs"
```

### WebSocket Messages

```python
# Subscribe to all events
{
    "type": "subscribe",
    "subscription_type": "all_events",
    "work_item_id": "work-item-123",
    "event_types": ["WorkflowStarted", "WorkflowCompleted"]
}

# Event message from server
{
    "type": "event",
    "event_type": "WorkflowStarted",
    "aggregate_id": "work-item-123",
    "payload": {...},
    "timestamp": "2025-01-01T12:00:00Z"
}
```

### E2E Client WebSocket Usage

```python
ws = e2e_client.connect_websocket(subscription_type="all_events")

# Wait for specific event
event = ws.wait_for_event(
    event_type="workflow_started",
    timeout=5.0,
    filter_fn=lambda e: e["data"]["work_item_id"] == "123"
)

# Collect multiple events
events = ws.collect_events(count=5, timeout=10.0)
```

---

## 10. Observability APIs

### Metrics API

**File**: `/workspace/src/codetoreum/adapters/primary/routers/metrics.py`

```bash
# Get health status
GET /api/v2/metrics/health
Response: {
  "status": "healthy",
  "components": [
    {
      "component_name": "event_store",
      "status": "healthy",
      "message": "Connected",
      "response_time_ms": 5.2
    }
  ]
}

# Get system metrics
GET /api/v2/metrics?name=agent_execution_duration&start_time=...&end_time=...
Response: {
  "metrics": [
    {
      "name": "agent_execution_duration",
      "value": 2500,
      "timestamp": "2025-01-01T12:05:00Z",
      "labels": {"agent_id": "coder", "status": "success"}
    }
  ]
}

# Get metric names
GET /api/v2/metrics/names
Response: {
  "metric_names": [
    "workflow_duration",
    "agent_execution_count",
    "stage_completion_time"
  ]
}
```

### Events API

**File**: `/workspace/src/codetoreum/adapters/primary/routers/events.py`

```bash
# Query events
GET /api/events?aggregate_id=work-item-123&event_type=WorkflowStarted
Response: {
  "events": [
    {
      "event_id": "evt-123",
      "event_type": "WorkflowStarted",
      "aggregate_id": "work-item-123",
      "occurred_at": "2025-01-01T12:00:00Z",
      "payload": {...}
    }
  ],
  "count": 1
}

# Replay events
POST /api/events/replay
Body: {
  "stream_id": "work-item-123",
  "from_version": 0
}
Response: {
  "replay_id": "replay-123",
  "status": "accepted",
  "estimated_event_count": 10
}

# Get event statistics
GET /api/events/stats
Response: {
  "total_events": 1250,
  "total_streams": 42,
  "event_types": {
    "WorkflowStarted": 42,
    "WorkflowCompleted": 40,
    "AgentExecutionStarted": 126
  }
}
```

---

## Complete Example: Run E2E Test

### 1. Create Bootstrap

```python
config = SimulationConfig.create_fast_config("e2e_test", speed_multiplier=100.0)
bootstrap = SimulationApplicationBootstrap(config)
await bootstrap.setup()
```

### 2. Seed Data

```python
seeder = SimulationDataSeeder(bootstrap)
await seeder.create_project(name="test-project")
await seeder.create_workflow(
    name="3-stage-workflow",
    stages=[
        {"name": "analysis", "agent_id": "analyzer", "order": 0},
        {"name": "coding", "agent_id": "coder", "order": 1},
        {"name": "review", "agent_id": "reviewer", "order": 2}
    ]
)
```

### 3. Create E2E Client

```python
client = SimulationE2EClient(bootstrap.app, bootstrap)
```

### 4. Test Flow

```python
# Create work item
work_item = client.create_work_item(
    project_id="test-project",
    title="Add auth",
    description="OAuth2"
)

# Connect WebSocket
ws = client.connect_websocket(subscription_type="all_events")

# Trigger workflow
client.trigger_workflow(work_item["id"], "3-stage-workflow")

# Wait for workflow started
ws.wait_for_event("workflow_started", timeout=5.0)

# Advance time in large chunks (10-100x faster)
await bootstrap.infrastructure.clock.advance(timedelta(minutes=30))

# Wait for completion
final = await client.wait_for_work_item_status(
    work_item["id"],
    expected_status="COMPLETED",
    timeout=5.0
)

# Verify metrics
metrics = client.client.get(
    "/api/v2/metrics?name=workflow_duration"
).json()
assert len(metrics["metrics"]) > 0

# Verify events
events = client.client.get(
    f"/api/events?aggregate_id={work_item['id']}"
).json()
assert len(events["events"]) > 5
```

---

## Performance Characteristics

### Real Execution vs Simulation

| Metric | Real | Simulation (10x) | Simulation (100x) |
|--------|------|------------------|-------------------|
| 1 workflow (3 stages) | 10 minutes | 60 seconds | 6 seconds |
| 10 parallel workflows | 10 minutes | 60 seconds | 6 seconds |
| 100 work items | 100 minutes | 10 minutes | 1 minute |
| Full E2E test suite | 2 hours | 12 minutes | 1.2 minutes |

### No External Dependencies

- ✅ No GitHub API calls
- ✅ No Docker daemon required
- ✅ No Claude API calls
- ✅ No Redis/Elasticsearch
- ✅ All data in-memory
- ✅ Zero network latency
- ✅ Deterministic execution

---

## Error Handling

### Rate Limiting Simulation

```python
mock_llm = MockLLMAdapter(simulate_rate_limits=True)

# Succeeds for first 100 requests
for i in range(100):
    await mock_llm.execute("prompt")

# Fails on 101st request
with pytest.raises(RateLimitError):
    await mock_llm.execute("prompt")
```

### Container Execution Failures

```python
container = FakeContainerAdapter(default_exit_code=0)

# Set specific command to fail
container.set_command_result(
    command_pattern="pytest",
    exit_code=1,
    stderr="Test failed"
)

result = await container.run_command("pytest")
assert result.exit_code == 1
```

### Notification Failures

```python
notifier = MockNotifierAdapter(
    simulate_failures=True,
    failure_rate=0.2  # 20% failure rate
)

# Some notifications will fail
for i in range(10):
    try:
        await notifier.send_notification(...)
    except NotificationFailedError:
        pass  # Expected occasionally
```

---

## Best Practices

### 1. Configuration Management

```python
# Use pre-built configs for common patterns
fast_config = SimulationConfig.create_fast_config("test", speed_multiplier=100.0)
realistic_config = SimulationConfig.create_realistic_config("test", speed_multiplier=10.0)

# Load from YAML for complex scenarios
config = SimulationConfig.from_yaml("scenarios/demo.yaml")
```

### 2. Time Management

```python
# Always use the clock from bootstrap
clock = bootstrap.infrastructure.clock

# Advance in reasonable chunks
await clock.advance(timedelta(hours=1))

# Avoid extremely large jumps (>1 week)
await clock.advance(timedelta(weeks=1))  # OK
# await clock.advance(timedelta(years=1))  # Avoid
```

### 3. Event Assertions

```python
# Always assert event occurred, not just checked
runner.assert_event_occurred("WorkflowStarted", aggregate_id="work-item-123")

# Use specific filters to avoid false positives
events = runner.get_events_by_type("WorkflowCompleted")
assert len(events) == 1
assert events[0].payload["work_item_id"] == "work-item-123"
```

### 4. WebSocket Handling

```python
# Always close WebSocket properly
ws = client.connect_websocket()
try:
    event = ws.wait_for_event("workflow_started", timeout=10.0)
finally:
    if hasattr(ws, 'disconnect'):
        ws.disconnect()
```

---

## Troubleshooting

### Issue: Tests hang waiting for events

**Cause**: Event not being published or WebSocket filter too specific

**Solution**: 
```python
# Add debugging
ws.collect_events(count=1)  # See what events you get
print(f"Received: {ws.received_events}")

# Use broader filter
ws.wait_for_event("workflow_started", timeout=30.0)  # Increase timeout
```

### Issue: Time doesn't advance as expected

**Cause**: Clock not set up in SimulationRunner

**Solution**:
```python
# Ensure using bootstrap clock
clock = bootstrap.infrastructure.clock
await clock.advance(timedelta(minutes=5))

# NOT
import asyncio
await asyncio.sleep(...)  # This won't affect simulated time
```

### Issue: Metrics not recorded

**Cause**: Metrics adapter not wired to services

**Solution**:
```python
# Verify metrics adapter is in bootstrap
assert bootstrap.adapters.metrics is not None

# Check services use it
events = bootstrap.adapters.metrics.get_all_metrics()
print(f"Metrics recorded: {events.keys()}")
```

---

## Key Files Summary

| Component | File | Class |
|-----------|------|-------|
| Bootstrap | `simulation/bootstrap.py` | `SimulationApplicationBootstrap` |
| Clock | `simulation/simulation_clock.py` | `SimulationClock` |
| Config | `simulation/simulation_config.py` | `SimulationConfig` |
| Runner | `simulation/simulation_runner.py` | `SimulationRunner` |
| Seeding | `simulation/seeding.py` | `SimulationDataSeeder` |
| LLM Mock | `adapters/testing/mock_llm_adapter.py` | `MockLLMAdapter` |
| Event Store | `adapters/testing/in_memory_event_store.py` | `InMemoryEventStore` |
| Server CLI | `cli/simulation_server.py` | `main()` |
| WebSocket | `adapters/primary/websocket_adapter.py` | `WebSocketAdapter` |
| Metrics API | `adapters/primary/routers/metrics.py` | `create_metrics_router()` |
| Events API | `adapters/primary/routers/events.py` | `create_events_router()` |
| E2E Client | `tests/simulation/e2e_client.py` | `SimulationE2EClient` |
| Fixtures | `tests/simulation/conftest.py` | Pytest fixtures |

---

**Document Version**: 1.0
**Last Updated**: 2025-11-06
**Compatibility**: Python 3.11+, Pytest 8.0+

