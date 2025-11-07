# Simulation Mode - Quick Reference Guide

## Component Quick Access

### 1. Bootstrap Flow
**File**: `/workspace/src/codetoreum/infrastructure/simulation/bootstrap.py`
**Class**: `SimulationApplicationBootstrap`
**Key Method**: `async def setup() -> None`
**Purpose**: Wire entire application stack in simulation mode
**Usage**: 
```python
bootstrap = SimulationApplicationBootstrap(config)
await bootstrap.setup()
app = bootstrap.app
```

### 2. Mock LLM Adapter
**File**: `/workspace/src/codetoreum/adapters/testing/mock_llm_adapter.py`
**Class**: `MockLLMAdapter`
**Key Features**: Pattern-based responses, rate limiting simulation, token tracking
**Usage**:
```python
llm = MockLLMAdapter()
llm.add_response_pattern(r".*generate.*", "Generated code...")
result = await llm.execute("generate code")
```

### 3. Event Store
**File**: `/workspace/src/codetoreum/adapters/testing/in_memory_event_store.py`
**Class**: `InMemoryEventStore`
**Key Features**: Event sourcing, replay, type indexing
**Usage**:
```python
await event_store.append("stream-id", [event1, event2])
events = await event_store.get_events("stream-id")
```

### 4. Simulation Clock
**File**: `/workspace/src/codetoreum/infrastructure/simulation/simulation_clock.py`
**Class**: `SimulationClock`
**Key Features**: 10-100x time acceleration, callback scheduling
**Usage**:
```python
clock = SimulationClock(speed_multiplier=100.0)
await clock.advance(timedelta(hours=1))  # Runs in 36 seconds
```

### 5. Simulation Config
**File**: `/workspace/src/codetoreum/infrastructure/simulation/simulation_config.py`
**Class**: `SimulationConfig`
**Key Features**: YAML loading, agent patterns, container commands
**Usage**:
```python
config = SimulationConfig.from_yaml("scenarios/demo.yaml")
# OR
config = SimulationConfig.create_fast_config("test", speed_multiplier=100.0)
```

### 6. Simulation Server CLI
**File**: `/workspace/src/codetoreum/cli/simulation_server.py`
**Entry Point**: `main()`
**Command**: `python -m codetoreum.cli.simulation_server --port 8000 --scenario demo`
**Features**: Interactive server, data seeding, real-time monitoring

### 7. Data Seeding
**File**: `/workspace/src/codetoreum/infrastructure/simulation/seeding.py`
**Class**: `SimulationDataSeeder`
**Key Methods**: 
- `create_project(name, description, ...)`
- `create_workflow(name, stages, ...)`
- `create_agent(agent_id, name, ...)`
- `create_work_items(count, ...)`
**Usage**:
```python
seeder = SimulationDataSeeder(bootstrap)
await seeder.create_project(name="test-project")
await seeder.create_workflow(name="3-stage-workflow")
```

### 8. E2E Test Client
**File**: `/workspace/tests/simulation/e2e_client.py`
**Class**: `SimulationE2EClient`
**Key Methods**:
- `create_work_item(**kwargs) -> Dict`
- `trigger_workflow(work_item_id, workflow_id)`
- `connect_websocket() -> WebSocket`
- `advance_minutes(minutes)`
- `assert_metrics_recorded(metric_name, min_count)`
**Usage**:
```python
client = SimulationE2EClient(app, bootstrap)
work_item = client.create_work_item(title="Test")
ws = client.connect_websocket()
client.advance_minutes(5)
```

### 9. WebSocket Adapter
**File**: `/workspace/src/codetoreum/adapters/primary/websocket_adapter.py`
**Class**: `WebSocketAdapter`
**Endpoint**: `ws://localhost:8000/ws`
**Features**: Event filtering, backpressure handling, authentication
**Usage**: See E2E Client WebSocket usage above

### 10. Observability APIs
**Metrics**: `/workspace/src/codetoreum/adapters/primary/routers/metrics.py`
**Events**: `/workspace/src/codetoreum/adapters/primary/routers/events.py`
**Endpoints**:
- `GET /api/v2/metrics/health` - System health
- `GET /api/v2/metrics?name=...` - Query metrics
- `GET /api/events?aggregate_id=...` - Query events
- `POST /api/events/replay` - Replay events

---

## Scenario Files

**Location**: `/workspace/scenarios/`

| File | Purpose | Speed | Use Case |
|------|---------|-------|----------|
| `default.yaml` | Minimal scenario | 10x | Smoke testing |
| `demo.yaml` | Full-featured demo | 5x | Presentations |
| `stress_test.yaml` | High-load scenario | 100x | Performance testing |
| `review_cycle.yaml` | Feedback loops | 10x | Review workflows |
| `failure_recovery.yaml` | Error handling | 10x | Resilience testing |

---

## Test Fixtures

**File**: `/workspace/tests/simulation/conftest.py`

### Core Fixtures
```python
@pytest.fixture
async def simulation_bootstrap() -> SimulationApplicationBootstrap
    # Full bootstrap with all components

@pytest.fixture
async def simulation_app() -> FastAPI
    # FastAPI application for testing

@pytest.fixture
async def simulation_adapters() -> SimulationAdapters
    # All 9 mock adapters

@pytest.fixture
async def simulation_services() -> SimulationServices
    # All 8 application services
```

### Data & E2E Fixtures
```python
@pytest.fixture
async def simulation_seeder() -> SimulationDataSeeder
    # For creating test data

@pytest.fixture
async def e2e_client() -> SimulationE2EClient
    # For E2E testing via REST/WebSocket
```

### Configuration Fixtures
```python
@pytest.fixture
def simulation_clock() -> SimulationClock
    # 100x speed clock

@pytest.fixture
def fast_simulation_config() -> SimulationConfig
    # Fast config (100x)

@pytest.fixture
def realistic_simulation_config() -> SimulationConfig
    # Realistic config (10x)
```

---

## E2E Test Pattern

```python
@pytest.mark.asyncio
async def test_workflow(e2e_client, simulation_seeder):
    # ========================================================================
    # Setup: Seed data
    # ========================================================================
    await simulation_seeder.create_project(name="test-project")
    await simulation_seeder.create_workflow(name="workflow")
    await simulation_seeder.create_agent(agent_id="agent-1")
    
    # ========================================================================
    # Test: Create work item
    # ========================================================================
    work_item = e2e_client.create_work_item(
        project_id="test-project",
        title="Test Item"
    )
    assert work_item["id"] is not None
    
    # ========================================================================
    # Test: WebSocket monitoring
    # ========================================================================
    ws = e2e_client.connect_websocket()
    e2e_client.trigger_workflow(work_item["id"], "workflow")
    ws.wait_for_event("workflow_started")
    
    # ========================================================================
    # Test: Time advancement & completion
    # ========================================================================
    e2e_client.advance_minutes(30)
    final = await e2e_client.wait_for_work_item_status(
        work_item["id"],
        expected_status="COMPLETED"
    )
    assert final["status"] == "COMPLETED"
    
    # ========================================================================
    # Test: Verify observability
    # ========================================================================
    e2e_client.assert_metrics_recorded("workflow_duration")
    e2e_client.assert_events_recorded("WorkflowCompleted")
```

---

## CLI Commands

### Start Server
```bash
# Default (localhost:8000, demo scenario)
python -m codetoreum.cli.simulation_server

# Custom port and scenario
python -m codetoreum.cli.simulation_server --port 9000 --scenario stress_test

# Custom scenario file
python -m codetoreum.cli.simulation_server --scenario-file custom.yaml

# 10x time acceleration
python -m codetoreum.cli.simulation_server --speed-multiplier 10

# Skip data seeding
python -m codetoreum.cli.simulation_server --no-seed

# Debug logging
python -m codetoreum.cli.simulation_server --debug
```

### Run Tests
```bash
# All simulation tests
pytest tests/simulation/ -v

# E2E tests only
pytest tests/simulation/e2e/ -v

# Single test
pytest tests/simulation/e2e/test_e2e_simple_workflow.py::test_simple_workflow_success -v

# With markers
pytest -m simulation tests/

# Fast simulation only (skip slow ones)
pytest -m "simulation and not slow_simulation" tests/
```

---

## API Endpoints

### REST API
```bash
# Work Items
POST   /api/work-items                    # Create
GET    /api/work-items                    # List
GET    /api/work-items/{id}              # Get
PUT    /api/work-items/{id}              # Update

# Workflows
POST   /api/workflows                     # Create
GET    /api/workflows                     # List
GET    /api/workflows/{id}               # Get

# Orchestration
POST   /api/orchestrator/work-items/{id}/workflow  # Trigger

# Metrics (no auth)
GET    /api/v2/metrics/health            # Health check
GET    /api/v2/metrics?name=...          # Query metrics
GET    /api/v2/metrics/names             # Available metrics

# Events
GET    /api/events                        # Query events
POST   /api/events/replay                # Replay events
GET    /api/events/stats                 # Statistics
```

### WebSocket
```
ws://localhost:8000/ws

Subscribe Message:
{
  "type": "subscribe",
  "subscription_type": "all_events",
  "work_item_id": "optional-filter",
  "event_types": ["WorkflowStarted", "WorkflowCompleted"]
}

Event Message (from server):
{
  "type": "event",
  "event_type": "WorkflowStarted",
  "aggregate_id": "work-item-123",
  "payload": {...},
  "timestamp": "2025-01-01T12:00:00Z"
}
```

---

## Common Patterns

### Create Full Test Environment
```python
# In conftest.py or test
@pytest.fixture
async def full_test_env():
    # Bootstrap
    config = SimulationConfig.create_fast_config("test")
    bootstrap = SimulationApplicationBootstrap(config)
    await bootstrap.setup()
    
    # Seed data
    seeder = SimulationDataSeeder(bootstrap)
    await seeder.seed_default_scenario()
    
    # Create client
    client = SimulationE2EClient(bootstrap.app, bootstrap)
    
    yield client
    await bootstrap.teardown()
```

### Assert Event Occurred
```python
def test_event(e2e_client, simulation_seeder):
    # ... trigger workflow ...
    
    # Query events
    response = e2e_client.client.get(
        f"/api/events?event_type=WorkflowCompleted"
    )
    events = response.json()["events"]
    assert len(events) > 0
```

### Monitor Workflow with Time Control
```python
async def test_with_time(e2e_client):
    clock = e2e_client.bootstrap.infrastructure.clock
    
    # Start workflow
    work_item = e2e_client.create_work_item(title="Test")
    e2e_client.trigger_workflow(work_item["id"], "workflow")
    
    # Advance time in stages
    for i in range(5):
        await clock.advance(timedelta(minutes=10))
        status = e2e_client.client.get(
            f"/api/work-items/{work_item['id']}"
        ).json()
        print(f"Stage {i}: {status['status']}")
```

---

## Key Differences: Simulation vs Production

| Aspect | Simulation | Production |
|--------|-----------|-----------|
| External APIs | Mock adapters | Real services |
| Data Storage | In-memory | Database/Redis |
| Container Execution | Fake adapter | Docker |
| Time Speed | 10-100x faster | Real-time |
| Network Latency | Zero | Variable |
| Test Duration | Seconds | Minutes/Hours |
| Determinism | 100% | Variable |
| Dependencies | None | Multiple |

---

## Performance Tips

1. **Use 100x speed for unit/integration tests** (36 seconds per simulated hour)
2. **Use 10x speed for realistic scenarios** (6 minutes per simulated hour)
3. **Advance time in 30-minute chunks** (avoids too many clock callbacks)
4. **Use fixture-based seeding** (faster than YAML for tests)
5. **Clear data between tests** (keeps suite fast)

---

## Debugging Tips

### Enable Debug Logging
```bash
python -m codetoreum.cli.simulation_server --debug
```

### Check Events
```python
# In Python
events = bootstrap.adapters.event_store.get_all_events_list()
for event in events:
    print(f"{event.event_type}: {event.payload}")
```

### Monitor Metrics
```python
metrics = bootstrap.adapters.metrics.get_all_metrics()
for metric_name, values in metrics.items():
    print(f"{metric_name}: {len(values)} records")
```

### Inspect WebSocket Traffic
```python
ws = client.connect_websocket()
for _ in range(10):
    event = ws.collect_event(timeout=1.0)
    print(f"Event: {event}")
```

---

## Documentation Reference

**Complete Guide**: `/workspace/SIMULATION_MODE_COMPLETE_GUIDE.md`
**Planning Document**: `/workspace/documentation/simulation_mode_testing_plan.md`
**Project Instructions**: `/workspace/CLAUDE.md`

---

**Version**: 1.0 | **Last Updated**: 2025-11-06 | **Python**: 3.11+ | **Framework**: FastAPI 0.100+
