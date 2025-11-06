# Simulation Mode Testing Plan

## Overview

This document details the plan for building and testing Codetoreum in **simulation mode** - a complete end-to-end environment using mock/in-memory adapters that allows for:
- Fast, deterministic testing without external dependencies
- Full UX validation with fake data
- Observability verification through metrics and events
- Time manipulation for accelerated workflow testing

## Current State Analysis

### ✅ Already Implemented

**Testing Adapters (Complete)**
- `InMemoryTicketAdapter` - Fake ticket system with CRUD operations
- `MockLLMAdapter` - Configurable mock LLM with pattern-based responses
- `FakeContainerAdapter` - Simulated container runtime
- `InMemoryRepositoryAdapter` - In-memory git repository
- `InMemoryEventStore` - Event sourcing storage
- `InMemoryMetricsAdapter` - Metrics collection
- `InMemoryStorageAdapter` - Artifact storage
- `InMemoryConfigStore` - Configuration management
- `MockNotifierAdapter` - Notification simulation

**Simulation Infrastructure (Complete)**
- `SimulationClock` - Time manipulation with speed multipliers
- `SimulationConfig` - Configuration for simulation scenarios
- `SimulationRunner` - Test orchestration and assertions
- Pytest fixtures and test scenarios (5 scenarios implemented)

**Application Services (Complete)**
- `WorkflowOrchestrator` - Workflow execution coordination
- `ExecutionService` - Agent execution lifecycle management
- `AgentScheduler` - Work queue and scheduling
- `PipelineManager` - Pipeline stage management
- `ReviewService` - Review cycle handling
- `FeedbackProcessor` - Agent feedback processing
- `WorkspaceRouter` - Container workspace management
- `ConfigurationService` - Configuration CRUD
- `WorkItemService` - Work item management

**UX Layer (Migrated from Legacy)**
- FastAPI application factory
- REST API with routers:
  - `/api/work-items` - Work item management
  - `/api/workflows` - Workflow operations
  - `/api/agents` - Agent configuration
  - `/api/executions` - Execution monitoring
  - `/api/orchestrator` - Orchestration control
  - `/api/config` - Configuration management
  - `/api/metrics` - Metrics queries
  - `/api/workspace` - Workspace operations
- WebSocket adapter for real-time updates
- Authentication system (simple token-based)
- DTOs and mappers for all endpoints

**Adapter Factory (Complete)**
- Registry-based adapter creation
- Support for production and testing adapters
- Resilience decorator application
- Mode switching (production/testing/simulation)

### ❌ What's Missing

**Critical Gaps**
1. **Simulation Mode Bootstrap** - No unified way to wire up all mock adapters → services → ports → FastAPI app
2. **End-to-End Test Harness** - No integration between simulation infrastructure and UX layer
3. **Simulation Server Runner** - No CLI/script to start server in simulation mode
4. **Test Data Seeding** - No utilities to create realistic fake tickets, workflows, agents
5. **UX + Simulation Integration** - Simulation tests don't exercise the full REST/WebSocket APIs
6. **Observability Verification** - No way to validate metrics/events through the UX during simulation

**Secondary Gaps**
7. User documentation for simulation mode
8. Example simulation scenarios that use the UX
9. Performance benchmarks for simulation vs real execution
10. Visual dashboard for simulation metrics (optional)

---

## Implementation Plan

### Phase 1: Application Bootstrap for Simulation Mode

**Objective**: Create a unified bootstrap module that wires up the entire application stack in simulation mode.

**Deliverables**:

#### 1.1 Simulation Mode Bootstrap (`src/codetoreum/infrastructure/simulation/bootstrap.py`)

```python
class SimulationApplicationBootstrap:
    """
    Bootstrap the entire application in simulation mode.

    Creates and wires:
    - All mock adapters
    - Application services
    - Input/output ports
    - FastAPI application
    - Event bus and handlers
    """

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.adapters = {}
        self.services = {}
        self.ports = {}
        self.app = None

    async def setup(self) -> FastAPI:
        """Set up entire application stack."""
        # 1. Create all mock adapters
        await self._create_adapters()

        # 2. Create infrastructure (event bus, clock, etc.)
        await self._create_infrastructure()

        # 3. Create application services
        await self._create_services()

        # 4. Create input ports (wire services to ports)
        await self._create_ports()

        # 5. Create FastAPI app (wire ports to REST/WebSocket)
        await self._create_fastapi_app()

        return self.app

    async def teardown(self):
        """Clean up resources."""
        pass
```

**Key Features**:
- Single entry point for simulation mode setup
- Proper dependency injection order
- Configurable via `SimulationConfig`
- Returns fully wired FastAPI app ready for testing

**Estimated Time**: 2-3 days

---

#### 1.2 Adapter Creation Helper (`_create_adapters()`)

Wire up all testing adapters with configuration:

```python
async def _create_adapters(self):
    """Create all mock/in-memory adapters."""

    # Use AdapterFactory in simulation mode
    factory = AdapterFactory(
        config=AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False  # No resilience in simulation
        )
    )

    # Create ticket system adapter
    self.adapters['ticket_system'] = factory.create_ticket_system(
        adapter_name='in_memory'
    )

    # Create LLM adapter with scenario responses
    self.adapters['llm_provider'] = factory.create_llm_provider(
        adapter_name='mock'
    )

    # Configure mock responses from SimulationConfig
    for agent_id, agent_config in self.config.agents.items():
        for pattern, response in agent_config.response_patterns.items():
            self.adapters['llm_provider'].add_response_pattern(
                pattern, response
            )

    # Container, repository, storage, metrics, notifier adapters...
    # Event store, config store...
```

**Estimated Time**: 1 day

---

#### 1.3 Service Creation Helper (`_create_services()`)

Instantiate all application services with proper dependencies:

```python
async def _create_services(self):
    """Create all application services."""

    # Create WorkflowOrchestrator
    self.services['workflow_orchestrator'] = WorkflowOrchestrator(
        ticket_system=self.adapters['ticket_system'],
        event_bus=self.infrastructure['event_bus'],
        logger=self.infrastructure['logger'],
        metrics=self.adapters['metrics']
    )

    # ExecutionService
    self.services['execution_service'] = ExecutionService(
        llm_provider=self.adapters['llm_provider'],
        container=self.adapters['container'],
        repository=self.adapters['repository'],
        storage=self.adapters['storage'],
        event_bus=self.infrastructure['event_bus'],
        logger=self.infrastructure['logger']
    )

    # AgentScheduler, PipelineManager, ReviewService, etc.
    # ...
```

**Estimated Time**: 1 day

---

#### 1.4 Port Creation Helper (`_create_ports()`)

Wire application services to input/output ports:

```python
async def _create_ports(self):
    """Create input ports (command/query handlers)."""

    # Command ports (write operations)
    self.ports['workflow_command'] = WorkflowCommandPort(
        orchestrator=self.services['workflow_orchestrator'],
        event_bus=self.infrastructure['event_bus']
    )

    self.ports['work_item_command'] = WorkItemCommandPort(
        work_item_service=self.services['work_item_service'],
        event_bus=self.infrastructure['event_bus']
    )

    # Query ports (read operations)
    self.ports['work_item_query'] = WorkItemQueryPort(
        work_item_service=self.services['work_item_service'],
        ticket_system=self.adapters['ticket_system']
    )

    # ... all other ports
```

**Estimated Time**: 1 day

---

#### 1.5 FastAPI App Creation (`_create_fastapi_app()`)

Wire ports to the FastAPI application:

```python
async def _create_fastapi_app(self):
    """Create FastAPI application with all routes."""

    from codetoreum.adapters.primary.fastapi_app import create_app

    self.app = create_app(
        workflow_command_port=self.ports['workflow_command'],
        task_query_port=self.ports['task_query'],
        config_command_port=self.ports['config_command'],
        config_query_port=self.ports['config_query'],
        metrics_query_port=self.ports['metrics_query'],
        workspace_query_port=self.ports['workspace_query'],
        work_item_command_port=self.ports['work_item_command'],
        work_item_query_port=self.ports['work_item_query'],
        workflow_query_port=self.ports['workflow_query'],
        workflow_definition_command_port=self.ports['workflow_definition_command'],
        orchestration_command_port=self.ports['orchestration_command'],
        agent_command_port=self.ports['agent_command'],
        agent_query_port=self.ports['agent_query'],
        execution_command_port=self.ports['execution_command'],
        execution_query_port=self.ports['execution_query'],
        event_bus=self.infrastructure['event_bus'],
        config_service=self.services['configuration_service'],
        logger=self.infrastructure['logger'],
        disable_auth=True,  # Disable auth in simulation mode
        cors_origins=["*"]  # Allow all origins in simulation
    )
```

**Estimated Time**: 1 day

---

### Phase 2: Test Data Seeding

**Objective**: Create utilities to populate the simulation environment with realistic test data.

**Deliverables**:

#### 2.1 Data Seeding Module (`src/codetoreum/infrastructure/simulation/seeding.py`)

```python
class SimulationDataSeeder:
    """
    Seed the simulation environment with test data.

    Creates:
    - Projects
    - Work items (tickets)
    - Workflows
    - Agents
    - Pipeline configurations
    """

    def __init__(self, bootstrap: SimulationApplicationBootstrap):
        self.bootstrap = bootstrap
        self.created_items = {
            'projects': [],
            'work_items': [],
            'workflows': [],
            'agents': []
        }

    async def seed_default_scenario(self):
        """Seed a default scenario with typical data."""
        await self.create_project("codetoreum-test")
        await self.create_workflow("basic-dev-workflow")
        await self.create_agents([
            "code-generator",
            "code-reviewer",
            "test-runner"
        ])
        await self.create_work_items([
            {"id": "ISSUE-1", "title": "Add auth", "status": "open"},
            {"id": "ISSUE-2", "title": "Fix bug", "status": "open"},
            {"id": "ISSUE-3", "title": "Refactor", "status": "open"}
        ])

    async def create_work_items(self, items: List[Dict]) -> List[str]:
        """Create fake work items in ticket system."""
        created_ids = []
        ticket_adapter = self.bootstrap.adapters['ticket_system']

        for item in items:
            work_item_id = await ticket_adapter.create_work_item(
                title=item['title'],
                description=item.get('description', ''),
                work_item_type=item.get('type', 'issue'),
                metadata=item.get('metadata', {})
            )
            created_ids.append(work_item_id)
            self.created_items['work_items'].append(work_item_id)

        return created_ids

    # Similar methods for workflows, agents, projects...
```

**Pre-built Scenarios**:
- `seed_simple_workflow()` - Single work item through 3-stage workflow
- `seed_parallel_workflow()` - Multiple work items executing in parallel
- `seed_review_cycle()` - Work items with review feedback loops
- `seed_complex_scenario()` - Multi-agent, multi-workflow scenario
- `seed_failure_scenario()` - Includes execution failures and retries

**Estimated Time**: 2 days

---

#### 2.2 Scenario Configuration Files

Create YAML/JSON scenario definitions:

```yaml
# scenarios/simple_workflow.yaml
name: "Simple 3-Stage Workflow"
description: "Single work item through generate -> review -> test"

projects:
  - id: "test-project"
    name: "Test Project"
    repository: "https://github.com/test/repo"

workflows:
  - id: "basic-workflow"
    name: "Basic Dev Workflow"
    stages:
      - name: "Code Generation"
        agent: "code-generator"
      - name: "Code Review"
        agent: "code-reviewer"
      - name: "Testing"
        agent: "test-runner"

agents:
  - id: "code-generator"
    name: "Code Generator"
    responses:
      - pattern: ".*generate.*"
        response: "Generated code: ..."

  - id: "code-reviewer"
    name: "Code Reviewer"
    responses:
      - pattern: ".*review.*"
        response: "LGTM!"

work_items:
  - id: "ISSUE-123"
    title: "Implement OAuth authentication"
    status: "open"
    workflow: "basic-workflow"
```

**Estimated Time**: 1 day

---

### Phase 3: End-to-End Test Harness

**Objective**: Create integration tests that exercise the full UX + application stack in simulation mode.

**Deliverables**:

#### 3.1 E2E Test Client (`tests/simulation/e2e_client.py`)

```python
class SimulationE2EClient:
    """
    Client for end-to-end testing via REST API and WebSocket.

    Provides high-level methods to:
    - Create work items
    - Trigger workflows
    - Monitor execution progress
    - Query metrics and events
    - Verify observability data
    """

    def __init__(self, app: FastAPI, simulation_clock: SimulationClock):
        self.client = TestClient(app)
        self.clock = simulation_clock
        self.ws_client = None

    async def create_work_item(self, title: str, **kwargs) -> str:
        """Create work item via REST API."""
        response = self.client.post("/api/work-items", json={
            "title": title,
            **kwargs
        })
        assert response.status_code == 201
        return response.json()['id']

    async def trigger_workflow(self, work_item_id: str, workflow_id: str):
        """Trigger workflow execution via REST API."""
        response = self.client.post(
            f"/api/orchestrator/work-items/{work_item_id}/workflow",
            json={"workflow_id": workflow_id}
        )
        assert response.status_code == 202

    async def get_work_item_status(self, work_item_id: str) -> dict:
        """Query work item status."""
        response = self.client.get(f"/api/work-items/{work_item_id}")
        assert response.status_code == 200
        return response.json()

    async def get_executions(self, work_item_id: str) -> List[dict]:
        """Query agent executions for work item."""
        response = self.client.get(
            f"/api/executions?work_item_id={work_item_id}"
        )
        assert response.status_code == 200
        return response.json()['executions']

    async def get_metrics(self, metric_name: str) -> List[dict]:
        """Query metrics."""
        response = self.client.get(
            f"/api/metrics?name={metric_name}"
        )
        assert response.status_code == 200
        return response.json()['metrics']

    async def connect_websocket(self) -> WebSocketTestSession:
        """Connect to WebSocket for real-time updates."""
        self.ws_client = self.client.websocket_connect("/ws")
        return self.ws_client

    async def wait_for_event(self, event_type: str, timeout: float = 10.0):
        """Wait for specific event via WebSocket."""
        # Implement event waiting logic
        pass
```

**Estimated Time**: 2 days

---

#### 3.2 E2E Test Scenarios (`tests/simulation/e2e/`)

Create comprehensive E2E tests:

**Test: Simple Workflow E2E** (`test_e2e_simple_workflow.py`)
```python
@pytest.mark.asyncio
async def test_simple_workflow_e2e(simulation_bootstrap, simulation_seeder):
    """
    Test simple workflow end-to-end:
    1. Create work item via API
    2. Trigger workflow via API
    3. Monitor progress via WebSocket
    4. Verify completion via API
    5. Check metrics via API
    """
    # Bootstrap application
    app = await simulation_bootstrap.setup()
    await simulation_seeder.seed_default_scenario()

    # Create E2E client
    client = SimulationE2EClient(app, simulation_bootstrap.clock)

    # 1. Create work item
    work_item_id = await client.create_work_item(
        title="Implement user authentication",
        description="Add OAuth2 support"
    )

    # 2. Connect WebSocket for real-time updates
    ws = await client.connect_websocket()

    # 3. Trigger workflow
    await client.trigger_workflow(work_item_id, "basic-workflow")

    # 4. Wait for workflow events (with time manipulation)
    await client.wait_for_event("WorkflowStarted", timeout=5.0)

    # Fast-forward time to speed up execution
    await simulation_bootstrap.clock.advance(timedelta(minutes=10))

    await client.wait_for_event("AgentExecutionStarted", timeout=5.0)
    await client.wait_for_event("AgentExecutionCompleted", timeout=5.0)

    # Repeat for all stages...

    # 5. Verify final status
    status = await client.get_work_item_status(work_item_id)
    assert status['workflow_status'] == 'completed'

    # 6. Verify executions
    executions = await client.get_executions(work_item_id)
    assert len(executions) == 3  # 3 agents
    assert all(e['status'] == 'completed' for e in executions)

    # 7. Verify metrics
    metrics = await client.get_metrics('agent_execution_duration')
    assert len(metrics) == 3

    # Cleanup
    await simulation_bootstrap.teardown()
```

**Additional E2E Tests**:
- `test_e2e_parallel_workflows.py` - Multiple work items in parallel
- `test_e2e_review_cycle.py` - Review feedback and revisions
- `test_e2e_execution_failure.py` - Agent failures and error handling
- `test_e2e_websocket_updates.py` - Real-time WebSocket event streaming
- `test_e2e_metrics_aggregation.py` - Metrics collection and queries
- `test_e2e_configuration_changes.py` - Dynamic workflow configuration

**Estimated Time**: 4 days

---

#### 3.3 Pytest Fixtures (`tests/simulation/conftest.py` additions)

```python
@pytest.fixture
async def simulation_bootstrap(simulation_clock):
    """Provide fully bootstrapped simulation application."""
    config = SimulationConfig.create_fast_config("e2e_test")
    bootstrap = SimulationApplicationBootstrap(config)
    await bootstrap.setup()
    yield bootstrap
    await bootstrap.teardown()

@pytest.fixture
async def simulation_seeder(simulation_bootstrap):
    """Provide data seeder."""
    seeder = SimulationDataSeeder(simulation_bootstrap)
    yield seeder

@pytest.fixture
async def e2e_client(simulation_bootstrap):
    """Provide E2E test client."""
    client = SimulationE2EClient(
        simulation_bootstrap.app,
        simulation_bootstrap.clock
    )
    yield client
```

**Estimated Time**: 1 day

---

### Phase 4: Simulation Mode Server

**Objective**: Provide a CLI command to start the full application server in simulation mode for interactive testing.

**Deliverables**:

#### 4.1 Simulation Server CLI (`src/codetoreum/cli/simulation_server.py`)

```python
#!/usr/bin/env python3
"""
Simulation Mode Server

Start Codetoreum in simulation mode with mock adapters.
Useful for:
- Manual UX testing
- Demo purposes
- Development without external dependencies
"""

import asyncio
import click
import uvicorn
from pathlib import Path

from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationApplicationBootstrap,
    SimulationDataSeeder
)


@click.command()
@click.option('--host', default='localhost', help='Server host')
@click.option('--port', default=8000, type=int, help='Server port')
@click.option('--scenario', default='default', help='Scenario to seed')
@click.option('--scenario-file', type=Path, help='Custom scenario YAML file')
@click.option('--speed-multiplier', default=1.0, type=float,
              help='Time speed multiplier (e.g., 10 = 10x faster)')
@click.option('--no-seed', is_flag=True, help='Skip seeding test data')
@click.option('--debug', is_flag=True, help='Enable debug logging')
def main(host, port, scenario, scenario_file, speed_multiplier, no_seed, debug):
    """Start Codetoreum in simulation mode."""

    click.echo("🚀 Starting Codetoreum in Simulation Mode")
    click.echo(f"   Host: {host}")
    click.echo(f"   Port: {port}")
    click.echo(f"   Speed: {speed_multiplier}x")
    click.echo()

    # Create simulation config
    config = SimulationConfig.create_fast_config(
        scenario_name=scenario,
        speed_multiplier=speed_multiplier
    )

    # Load custom scenario if provided
    if scenario_file:
        click.echo(f"📄 Loading scenario: {scenario_file}")
        config = SimulationConfig.from_yaml(scenario_file)

    # Bootstrap application
    click.echo("⚙️  Bootstrapping application...")
    loop = asyncio.get_event_loop()
    bootstrap = SimulationApplicationBootstrap(config)
    app = loop.run_until_complete(bootstrap.setup())

    # Seed data
    if not no_seed:
        click.echo(f"🌱 Seeding scenario: {scenario}")
        seeder = SimulationDataSeeder(bootstrap)
        loop.run_until_complete(seeder.seed_default_scenario())
        click.echo(f"   Created {len(seeder.created_items['work_items'])} work items")
        click.echo(f"   Created {len(seeder.created_items['workflows'])} workflows")
        click.echo(f"   Created {len(seeder.created_items['agents'])} agents")

    click.echo()
    click.echo("✅ Server ready!")
    click.echo(f"📊 API Documentation: http://{host}:{port}/api/docs")
    click.echo(f"🔌 WebSocket: ws://{host}:{port}/ws")
    click.echo()
    click.echo("Note: This is SIMULATION MODE - using mock adapters")
    click.echo("      No external services required!")
    click.echo()

    # Run server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="debug" if debug else "info"
    )


if __name__ == '__main__':
    main()
```

**Usage**:
```bash
# Start with defaults
python -m codetoreum.cli.simulation_server

# Start with custom port and 10x speed
python -m codetoreum.cli.simulation_server --port 9000 --speed-multiplier 10

# Load custom scenario
python -m codetoreum.cli.simulation_server --scenario-file scenarios/complex.yaml

# Start without seeding (empty state)
python -m codetoreum.cli.simulation_server --no-seed
```

**Estimated Time**: 2 days

---

#### 4.2 Interactive Testing Guide (`documentation/guides/simulation_mode_usage.md`)

Document how to use simulation mode for manual testing:

```markdown
# Simulation Mode Usage Guide

## Starting the Server

Start in simulation mode:
```bash
python -m codetoreum.cli.simulation_server --port 8000 --speed-multiplier 10
```

## Interacting via API

### Create a Work Item
```bash
curl -X POST http://localhost:8000/api/work-items \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Add dark mode",
    "description": "Implement dark mode toggle"
  }'
```

### Trigger Workflow
```bash
curl -X POST http://localhost:8000/api/orchestrator/work-items/ISSUE-1/workflow \
  -H "Content-Type: application/json" \
  -d '{"workflow_id": "basic-workflow"}'
```

### Monitor Progress
```bash
# Get work item status
curl http://localhost:8000/api/work-items/ISSUE-1

# Get agent executions
curl http://localhost:8000/api/executions?work_item_id=ISSUE-1

# Get metrics
curl http://localhost:8000/api/metrics?name=agent_execution_duration
```

### WebSocket Connection
```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data);
};
```

## Observability

### View Events
All events are stored in the in-memory event store:
```bash
curl http://localhost:8000/api/events?aggregate_id=ISSUE-1
```

### Query Metrics
```bash
# Agent execution metrics
curl http://localhost:8000/api/metrics?name=agent_execution_duration

# Workflow completion rate
curl http://localhost:8000/api/metrics?name=workflow_completion_rate
```

## Time Manipulation

Simulation mode supports time acceleration. A 10x speed multiplier means:
- 1 hour simulation time = 6 minutes real time
- 1 day simulation time = 2.4 hours real time

Workflows execute much faster than in production!
```

**Estimated Time**: 1 day

---

### Phase 5: Observability Integration

**Objective**: Ensure metrics, events, and logs collected during simulation are queryable via the UX.

**Deliverables**:

#### 5.1 Metrics Query Port Implementation

Verify `IMetricsQueryPort` properly integrates with `InMemoryMetricsAdapter`:

```python
class MetricsQueryPort(IMetricsQueryPort):
    """Query port for metrics data."""

    def __init__(self, metrics_adapter: IMetrics):
        self.metrics = metrics_adapter

    async def get_metrics(
        self,
        metric_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> List[MetricData]:
        """Query metrics with filters."""

        # Get from in-memory adapter
        all_metrics = self.metrics.get_all_metrics()

        # Filter by name
        if metric_name:
            all_metrics = {metric_name: all_metrics.get(metric_name, [])}

        # Filter by time range
        # Filter by labels
        # ...

        return [
            MetricData(
                name=name,
                value=m['value'],
                timestamp=m['timestamp'],
                labels=m['labels']
            )
            for name, metrics in all_metrics.items()
            for m in metrics
        ]
```

**Estimated Time**: 1 day

---

#### 5.2 Event Query Endpoints

Ensure event store is queryable via API:

```python
# In routers/events.py
@router.get("/events")
async def query_events(
    aggregate_id: Optional[str] = None,
    aggregate_type: Optional[str] = None,
    event_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100,
    event_store: IEventStore = Depends(get_event_store)
):
    """Query domain events."""
    events = await event_store.get_events(
        aggregate_id=aggregate_id,
        aggregate_type=aggregate_type,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )

    return {
        "events": [event.to_dict() for event in events],
        "count": len(events)
    }
```

**Estimated Time**: 1 day

---

#### 5.3 Real-Time WebSocket Event Streaming

Ensure simulation events are streamed via WebSocket:

```python
# In websocket_adapter.py
class WebSocketAdapter:
    async def handle_client(self, websocket: WebSocket):
        """Handle WebSocket client connection."""

        # Subscribe to event bus
        async def on_event(event: DomainEvent):
            # Send event to client
            await websocket.send_json({
                "type": "event",
                "event_type": event.event_type,
                "aggregate_id": event.aggregate_id,
                "payload": event.payload,
                "timestamp": event.timestamp.isoformat()
            })

        self.event_bus.subscribe(on_event)

        # Keep connection alive
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            self.event_bus.unsubscribe(on_event)
```

**Estimated Time**: 1 day

---

### Phase 6: Documentation and Examples

**Objective**: Document simulation mode architecture, usage, and best practices.

**Deliverables**:

#### 6.1 Architecture Documentation (`documentation/simulation_mode_architecture.md`)

- Component diagram showing bootstrap flow
- Adapter wiring explanation
- Time manipulation details
- Event sourcing integration
- Testing strategy

**Estimated Time**: 2 days

#### 6.2 Testing Guide (`documentation/guides/testing_with_simulation_mode.md`)

- How to write E2E tests
- How to use test fixtures
- Scenario configuration
- Best practices
- Troubleshooting

**Estimated Time**: 1 day

#### 6.3 Example Scenarios

Create 5-10 example scenario files:
- `scenarios/demo.yaml` - Demo scenario for presentations
- `scenarios/stress_test.yaml` - High-load scenario
- `scenarios/failure_recovery.yaml` - Error handling scenario
- `scenarios/review_intensive.yaml` - Multiple review cycles
- `scenarios/multi_project.yaml` - Multiple projects

**Estimated Time**: 1 day

---

## Testing Strategy

### Test Levels

**Level 1: Unit Tests (Existing)**
- Domain models
- Application service logic
- Adapter implementations
- ✅ Already have >80% coverage

**Level 2: Integration Tests (Existing)**
- Service integration with mock adapters
- Event bus integration
- Workflow orchestration
- ✅ Already implemented

**Level 3: Simulation Tests (Existing)**
- Isolated simulation scenarios
- Time manipulation
- Event assertions
- ✅ 5 scenarios already implemented

**Level 4: E2E Tests (NEW)**
- Full stack via REST/WebSocket APIs
- UX integration
- Observability verification
- Real user workflows

**Level 5: Manual Testing (NEW)**
- Interactive simulation server
- Manual scenario execution
- UX/UI validation
- Demo purposes

### Success Criteria

Simulation mode is complete when:

1. ✅ **Bootstrap**: Single command starts full stack in simulation mode
2. ✅ **E2E Tests**: >10 E2E tests passing via REST/WebSocket APIs
3. ✅ **Data Seeding**: Can create realistic test data programmatically
4. ✅ **Observability**: Metrics, events, logs queryable via UX
5. ✅ **Time Manipulation**: Workflows execute 10-100x faster than real-time
6. ✅ **CLI Server**: Interactive simulation server for manual testing
7. ✅ **Documentation**: Complete guides for developers and testers
8. ✅ **Zero Dependencies**: No external services required (no Docker, GitHub, Claude API, Redis, etc.)

---

## Timeline Estimate

| Phase | Component | Estimated Days |
|-------|-----------|----------------|
| 1.1 | Simulation Bootstrap | 2-3 |
| 1.2 | Adapter Creation | 1 |
| 1.3 | Service Creation | 1 |
| 1.4 | Port Creation | 1 |
| 1.5 | FastAPI App Creation | 1 |
| 2.1 | Data Seeding Module | 2 |
| 2.2 | Scenario Configs | 1 |
| 3.1 | E2E Test Client | 2 |
| 3.2 | E2E Test Scenarios | 4 |
| 3.3 | Pytest Fixtures | 1 |
| 4.1 | Simulation Server CLI | 2 |
| 4.2 | Interactive Guide | 1 |
| 5.1 | Metrics Integration | 1 |
| 5.2 | Event Query Endpoints | 1 |
| 5.3 | WebSocket Streaming | 1 |
| 6.1 | Architecture Docs | 2 |
| 6.2 | Testing Guide | 1 |
| 6.3 | Example Scenarios | 1 |
| **Total** | | **28-29 days** |

**Sprint Planning**: Can be broken into 3-4 two-week sprints:
- Sprint 1: Bootstrap + Data Seeding (Phases 1-2)
- Sprint 2: E2E Tests (Phase 3)
- Sprint 3: Simulation Server + Observability (Phases 4-5)
- Sprint 4: Documentation + Polish (Phase 6)

---

## File Structure

After implementation, the codebase will have:

```
codetoreum/
├── src/codetoreum/
│   ├── infrastructure/
│   │   └── simulation/
│   │       ├── bootstrap.py          # NEW: Application bootstrap
│   │       ├── seeding.py            # NEW: Data seeding
│   │       ├── simulation_clock.py   # ✅ Existing
│   │       ├── simulation_config.py  # ✅ Existing
│   │       └── simulation_runner.py  # ✅ Existing
│   ├── cli/
│   │   ├── simulation_server.py      # NEW: CLI server
│   │   └── yaml_import.py            # ✅ Existing
│   └── adapters/
│       └── testing/                   # ✅ All mock adapters exist
│
├── tests/
│   └── simulation/
│       ├── e2e/                      # NEW: E2E tests
│       │   ├── test_e2e_simple_workflow.py
│       │   ├── test_e2e_parallel_workflows.py
│       │   ├── test_e2e_review_cycle.py
│       │   └── ...
│       ├── scenarios/                # ✅ Existing
│       │   ├── scenario_01_simple_workflow.py
│       │   └── ...
│       ├── conftest.py               # Updated with new fixtures
│       └── helpers.py                # ✅ Existing
│
├── scenarios/                        # NEW: Scenario configs
│   ├── default.yaml
│   ├── demo.yaml
│   ├── stress_test.yaml
│   └── ...
│
└── documentation/
    ├── simulation_mode_architecture.md  # NEW
    ├── simulation_mode_testing_plan.md  # This file
    └── guides/
        ├── simulation_mode_usage.md     # NEW
        └── testing_with_simulation_mode.md  # NEW
```

---

## Benefits

### Development Velocity
- **Fast Tests**: E2E tests run 10-100x faster than real workflows
- **No Setup Time**: No need to configure GitHub, Docker, Claude API, etc.
- **Parallel Development**: Multiple developers can work without conflicts
- **Rapid Iteration**: Change code → run tests in seconds

### Quality Assurance
- **Deterministic**: Same scenario always produces same results
- **Full Coverage**: Test edge cases that are hard to reproduce in production
- **Regression Safety**: Detect breaking changes immediately
- **Event Auditing**: Complete event trail for debugging

### Demo & Training
- **Instant Demos**: Start server and showcase features immediately
- **Training Environment**: Safe environment for learning the system
- **Documentation Examples**: Real working examples for docs
- **Sales Engineering**: Show features without production access

### CI/CD Integration
- **No External Dependencies**: CI runs without GitHub API tokens, Docker daemon, etc.
- **Fast Pipeline**: Full test suite in minutes instead of hours
- **Cost Effective**: No external API costs
- **Reliable**: No flaky tests from network issues

---

## Next Steps

1. **Review and Approve Plan**: Get stakeholder buy-in
2. **Set Up Sprint Planning**: Break into 2-week sprints
3. **Create GitHub Issues**: One issue per deliverable
4. **Assign Ownership**: Assign team members to each phase
5. **Begin Implementation**: Start with Phase 1 (Bootstrap)

---

## Appendix: Key Design Decisions

### Why FastAPI TestClient vs Real Server?

For E2E tests, we use FastAPI's `TestClient` which provides:
- Synchronous and async HTTP requests
- WebSocket testing support
- No network overhead
- Deterministic behavior
- Easy assertions

For manual testing, we run a real Uvicorn server in simulation mode.

### Why YAML Scenario Files?

YAML provides:
- Human-readable configuration
- Easy to version control
- Sharable across team
- Can be generated programmatically
- Industry standard for config

### Why Not Use Production Adapters with Docker Compose?

Simulation mode aims for:
- **Zero external dependencies**: No Docker daemon required
- **Extreme speed**: 10-100x faster than real execution
- **Determinism**: No network flakiness or race conditions
- **Portability**: Run anywhere (CI, local, etc.)

Production adapters with Docker Compose still require external services and are slower.

### Why Time Manipulation?

Time manipulation allows:
- **Accelerated Testing**: Days of simulation in minutes
- **Timeout Testing**: Test long-running scenarios quickly
- **Deadline Testing**: Simulate time-based SLAs
- **Clock Synchronization**: Avoid race conditions in tests

---

## Questions & Answers

**Q: Can we use simulation mode in production?**
A: No. Simulation mode uses mock adapters that don't interact with real external systems. It's for testing and development only.

**Q: How do we switch between production and simulation?**
A: Via the `AdapterFactory` with different `OperationMode`:
- `OperationMode.PRODUCTION` → Real adapters (GitHub, Docker, etc.)
- `OperationMode.SIMULATION` → Mock adapters (in-memory, fake, etc.)

**Q: Can we mix real and mock adapters?**
A: Yes! The factory allows specifying adapter names individually. You could use a real GitHub adapter with a mock LLM adapter for hybrid testing.

**Q: Will simulation mode slow down production?**
A: No. Simulation code is only used in tests and the simulation CLI. Production deployments don't load simulation modules.

**Q: How do we keep simulation scenarios in sync with production?**
A: 1) Use integration tests that verify adapter contracts, 2) Periodically record real production scenarios and convert to simulation scenarios, 3) Use event replay from production event store.

---

## Conclusion

This plan provides a **comprehensive roadmap** for building a fully functional simulation mode testing environment. Once complete, developers will be able to:

1. ✅ Start the entire Codetoreum stack in seconds without external dependencies
2. ✅ Create and manipulate fake tickets via REST API
3. ✅ Watch workflows execute 10-100x faster than real-time
4. ✅ Verify system behavior via the real UX (REST + WebSocket)
5. ✅ Query metrics, events, and logs through observability endpoints
6. ✅ Write E2E tests that exercise the complete system
7. ✅ Use simulation mode for demos, training, and development

**Total Effort**: ~28-29 days (~4 sprints)

**Risk Level**: Low (building on existing solid foundation)

**Value**: Very High (enables fast development, reliable testing, easy demos)
