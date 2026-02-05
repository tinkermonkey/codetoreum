# Testing with Simulation Mode

## Overview

This guide teaches you how to write end-to-end (E2E) tests using simulation mode. Simulation mode enables testing complete workflows without external dependencies, achieving 10-100x faster execution while maintaining full determinism.

**Time to write your first E2E test: <15 minutes**

## Why Simulation Mode Testing?

**Benefits:**
- **Fast**: 10-100x faster than real execution
- **Deterministic**: Same inputs always produce same outputs
- **Isolated**: No external dependencies (GitHub, Docker, Redis)
- **Complete**: Test entire workflow from API to persistence
- **Observable**: Full event sourcing for debugging

**Use Cases:**
- End-to-end workflow testing
- Integration testing with multiple services
- Performance regression testing
- Scenario-based testing
- CI/CD pipeline testing

## Quick Start

### Your First E2E Test

Create a file `test_my_first_e2e.py`:

```python
import pytest
from datetime import timedelta

@pytest.mark.asyncio
async def test_simple_work_item_creation(e2e_client):
    """Test creating a work item via API."""
    # Create work item
    response = e2e_client.create_work_item(
        project_id="proj-001",
        title="Add authentication",
        description="Implement OAuth2 authentication",
        labels=["feature", "security"],
        priority="HIGH",
    )

    # Verify response
    assert response["title"] == "Add authentication"
    assert response["status"] == "NEW"
    assert "feature" in response["labels"]

    # Verify work item can be retrieved
    work_item = e2e_client.get_work_item(response["id"])
    assert work_item["id"] == response["id"]
    assert work_item["title"] == "Add authentication"
```

### Run Your Test

```bash
pytest tests/simulation/test_my_first_e2e.py -v
```

**Output:**
```
tests/simulation/test_my_first_e2e.py::test_simple_work_item_creation PASSED [100%]

========================= 1 passed in 0.15s =========================
```

## Using Pytest Fixtures

Simulation mode provides several pytest fixtures to simplify testing:

### Core Fixtures

#### `simulation_bootstrap`

Provides fully initialized application stack:

```python
@pytest.mark.asyncio
async def test_with_bootstrap(simulation_bootstrap):
    """Test using bootstrap directly."""
    # Access adapters
    event_store = simulation_bootstrap.adapters.event_store
    llm_adapter = simulation_bootstrap.adapters.llm_provider

    # Access services
    execution_service = simulation_bootstrap.services.execution_service

    # Access simulation engine (encapsulates clock and time operations)
    engine = simulation_bootstrap.engine
    # Advance simulation time via engine
    await engine.advance(timedelta(hours=1))
```

#### `e2e_client`

High-level test client for REST and WebSocket operations:

```python
@pytest.mark.asyncio
async def test_with_e2e_client(e2e_client):
    """Test using E2E client."""
    # Create work item
    work_item = e2e_client.create_work_item(
        project_id="proj-001",
        title="Test item",
        description="Test description",
    )

    # Trigger workflow
    e2e_client.trigger_workflow(work_item["id"], "feature-workflow")

    # Wait for completion
    await e2e_client.wait_for_work_item_status(
        work_item["id"],
        "COMPLETED",
        timeout=30.0,
    )

    # Assert observability
    e2e_client.assert_metrics_recorded("execution_duration")
    e2e_client.assert_events_recorded("AgentExecutionCompleted")
```

#### `simulation_seeder`

Seed test data programmatically:

```python
@pytest.mark.asyncio
async def test_with_seeder(simulation_seeder, e2e_client):
    """Test using data seeder."""
    # Seed a project
    project = await simulation_seeder.seed_project(
        name="test-project",
        description="Test project",
        repository_url="https://github.com/test/repo.git",
    )

    # Seed a workflow
    workflow = await simulation_seeder.seed_workflow(
        name="test-workflow",
        description="Test workflow",
        stages=[
            {"name": "design", "agent_type": "architect", "order": 1},
            {"name": "implement", "agent_type": "developer", "order": 2},
        ],
    )

    # Seed agents
    architect = await simulation_seeder.seed_agent(
        name="architect",
        agent_type="architect",
        capabilities=["code_generation"],
    )

    # Seed work item
    work_item = await simulation_seeder.seed_work_item(
        project_id=project.id,
        title="Test work item",
        description="Test description",
    )

    # Use in test
    response = e2e_client.get_work_item(work_item.id)
    assert response["title"] == "Test work item"
```

#### `simulation_clock`

Manipulate time in tests:

```python
@pytest.mark.asyncio
async def test_with_clock(simulation_clock):
    """Test using simulation clock."""
    from datetime import datetime, timezone

    # Set specific start time
    simulation_clock.start_at(datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))

    # Verify current time
    assert simulation_clock.now() == datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Advance time
    await simulation_clock.advance(timedelta(hours=1))
    assert simulation_clock.now() == datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
```

### Adapter Fixtures

Access individual mock adapters:

```python
@pytest.mark.asyncio
async def test_with_adapters(mock_llm, fake_container, in_memory_metrics):
    """Test using individual adapters."""
    # Configure LLM responses
    mock_llm.add_pattern(
        pattern="authentication",
        response="# OAuth2 implementation\n...",
    )

    # Configure container behavior
    fake_container.set_default_exit_code(0)
    fake_container.set_default_stdout("Tests passed")

    # Use adapters in test
    response = await mock_llm.generate_code("Implement authentication")
    assert "OAuth2" in response.content

    # Verify metrics
    metrics = in_memory_metrics.get_all_metrics()
    assert len(metrics) > 0
```

### Configuration Fixtures

```python
@pytest.mark.asyncio
async def test_fast_simulation(fast_simulation_config):
    """Test with fast configuration (100x speed)."""
    assert fast_simulation_config.time.speed_multiplier == 100.0

@pytest.mark.asyncio
async def test_realistic_simulation(realistic_simulation_config):
    """Test with realistic configuration (10x speed)."""
    assert realistic_simulation_config.time.speed_multiplier == 10.0
```

## Writing E2E Tests

### Complete Workflow Test

```python
import pytest

@pytest.mark.asyncio
async def test_complete_workflow(e2e_client, simulation_seeder):
    """Test complete workflow execution end-to-end."""
    # Setup: Seed test data
    project = await simulation_seeder.seed_project(
        name="test-project",
        repository_url="https://github.com/test/repo.git",
    )

    workflow = await simulation_seeder.seed_workflow(
        name="feature-workflow",
        stages=[
            {
                "name": "design",
                "agent_type": "architect",
                "order": 1,
                "timeout_seconds": 3600,
            },
            {
                "name": "implement",
                "agent_type": "developer",
                "order": 2,
                "timeout_seconds": 7200,
            },
            {
                "name": "test",
                "agent_type": "qa",
                "order": 3,
                "timeout_seconds": 3600,
            },
        ],
    )

    await simulation_seeder.seed_agents([
        {"name": "architect", "agent_type": "architect"},
        {"name": "developer", "agent_type": "developer"},
        {"name": "qa", "agent_type": "qa"},
    ])

    # Create work item via API
    work_item = e2e_client.create_work_item(
        project_id=project.id,
        title="Add user authentication",
        description="Implement OAuth2 authentication system",
        labels=["feature", "security"],
        priority="HIGH",
    )

    work_item_id = work_item["id"]

    # Trigger workflow
    trigger_response = e2e_client.trigger_workflow(
        work_item_id,
        workflow.id,
    )
    assert trigger_response["status"] == "triggered"

    # Wait for workflow completion
    final_work_item = await e2e_client.wait_for_work_item_status(
        work_item_id,
        "COMPLETED",
        timeout=60.0,  # 60 seconds real time (faster with speed multiplier)
    )

    # Verify final state
    assert final_work_item["status"] == "COMPLETED"

    # Verify all executions completed
    executions = e2e_client.get_executions(work_item_id=work_item_id)
    assert len(executions) == 3  # 3 stages
    for execution in executions:
        assert execution["status"] == "COMPLETED"

    # Verify observability
    e2e_client.assert_events_recorded(
        "AgentExecutionCompleted",
        aggregate_id=work_item_id,
        min_count=3,
    )

    e2e_client.assert_metrics_recorded(
        "execution_duration",
        labels={"work_item_id": work_item_id},
        min_count=3,
    )
```

### WebSocket Event Testing

```python
import pytest

@pytest.mark.asyncio
async def test_websocket_events(e2e_client, simulation_seeder):
    """Test real-time event delivery via WebSocket."""
    # Setup
    project = await simulation_seeder.seed_project(name="ws-test")
    work_item = e2e_client.create_work_item(
        project_id=project.id,
        title="WebSocket test",
        description="Test WebSocket event delivery",
    )

    # Connect WebSocket
    ws_collector = e2e_client.connect_websocket(
        subscription_type="work_item_events",
        work_item_id=work_item["id"],
    )

    # Trigger action that generates events
    e2e_client.trigger_workflow(work_item["id"], "simple-workflow")

    # Wait for specific event
    started_event = ws_collector.wait_for_event(
        "AgentExecutionStarted",
        timeout=10.0,
        filter_fn=lambda e: e.get("payload", {}).get("work_item_id") == work_item["id"],
    )

    assert started_event["type"] == "AgentExecutionStarted"
    assert started_event["payload"]["work_item_id"] == work_item["id"]

    # Collect multiple events
    events = ws_collector.collect_events(count=5, timeout=30.0)
    assert len(events) >= 2  # At least started and completed

    # Assert specific event was received
    completed_event = ws_collector.assert_event_received(
        "AgentExecutionCompleted",
        filter_fn=lambda e: e.get("payload", {}).get("work_item_id") == work_item["id"],
    )

    assert completed_event["type"] == "AgentExecutionCompleted"
```

### Time Manipulation Test

```python
import pytest
from datetime import timedelta

@pytest.mark.asyncio
async def test_timeout_behavior(e2e_client, simulation_seeder):
    """Test execution timeout with time manipulation."""
    # Setup
    project = await simulation_seeder.seed_project(name="timeout-test")
    work_item = e2e_client.create_work_item(
        project_id=project.id,
        title="Timeout test",
        description="Test execution timeout",
    )

    # Trigger long-running execution
    e2e_client.trigger_workflow(work_item["id"], "long-workflow")

    # Fast-forward time to trigger timeout
    e2e_client.advance_time(timedelta(hours=2))  # Fast with speed multiplier

    # Verify timeout was triggered
    executions = e2e_client.get_executions(work_item_id=work_item["id"])
    assert any(e["status"] == "TIMEOUT" for e in executions)

    # Verify timeout event was recorded
    timeout_events = e2e_client.get_events(
        event_type="ExecutionTimeout",
        aggregate_id=work_item["id"],
    )
    assert len(timeout_events) > 0
```

### Failure and Retry Test

```python
import pytest

@pytest.mark.asyncio
async def test_execution_failure_retry(e2e_client, simulation_seeder, mock_llm):
    """Test execution failure and retry logic."""
    # Setup
    project = await simulation_seeder.seed_project(name="retry-test")

    # Configure LLM to fail first, then succeed
    call_count = 0

    def llm_response_generator(prompt: str):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Simulated LLM failure")
        return "# Successful implementation\n..."

    mock_llm.set_response_generator(llm_response_generator)

    # Create and trigger workflow
    work_item = e2e_client.create_work_item(
        project_id=project.id,
        title="Retry test",
        description="Test retry logic",
    )
    e2e_client.trigger_workflow(work_item["id"], "retry-workflow")

    # Wait for eventual success
    await e2e_client.wait_for_work_item_status(
        work_item["id"],
        "COMPLETED",
        timeout=60.0,
    )

    # Verify failure was recorded
    failure_events = e2e_client.get_events(
        event_type="AgentExecutionFailed",
        aggregate_id=work_item["id"],
    )
    assert len(failure_events) == 1

    # Verify retry was scheduled
    retry_events = e2e_client.get_events(
        event_type="ExecutionRetryScheduled",
        aggregate_id=work_item["id"],
    )
    assert len(retry_events) == 1

    # Verify final success
    completed_events = e2e_client.get_events(
        event_type="AgentExecutionCompleted",
        aggregate_id=work_item["id"],
    )
    assert len(completed_events) == 1
```

## Creating Custom Scenarios

### Scenario File Method

Create a YAML file for reusable test scenarios:

```yaml
# tests/scenarios/custom_test_scenario.yaml

name: "Custom Test Scenario"
description: "Scenario for testing feature X"
version: "1.0"

speed_multiplier: 100.0
auto_advance: false

projects:
  - name: "test-project"
    description: "Test project"
    repository_url: "https://github.com/test/repo.git"
    default_branch: "main"

workflows:
  - name: "test-workflow"
    description: "Test workflow"
    stages:
      - name: "stage-1"
        agent_type: "agent-1"
        order: 1
        timeout_seconds: 3600

agents:
  - name: "agent-1"
    agent_type: "agent-1"
    capabilities: ["code_generation"]
    llm_model: "claude-3-5-sonnet-20241022"
    temperature: 0.7
    system_prompt: "You are a test agent."
    enabled: true

work_items:
  - title: "Test work item"
    description: "Test description"
    labels: ["test"]
    priority: "medium"
    status: "new"
```

### Load Scenario in Test

```python
import pytest
from pathlib import Path
from codetoreum.infrastructure.simulation import SimulationConfig

@pytest.mark.asyncio
async def test_with_custom_scenario(simulation_seeder):
    """Test using custom scenario file."""
    scenario_file = Path(__file__).parent / "scenarios" / "custom_test_scenario.yaml"

    # Load scenario
    await simulation_seeder.seed_from_yaml(scenario_file)

    # Get created items
    created = simulation_seeder.get_created_items()

    assert len(created.projects) == 1
    assert len(created.workflows) == 1
    assert len(created.agents) == 1
    assert len(created.work_items) == 1

    # Use seeded data in test
    project = created.projects[0]
    workflow = created.workflows[0]

    # ... continue test
```

### Programmatic Scenario Creation

```python
import pytest

@pytest.mark.asyncio
async def test_programmatic_scenario(simulation_seeder):
    """Create scenario programmatically."""
    # Seed multiple projects
    projects = []
    for i in range(3):
        project = await simulation_seeder.seed_project(
            name=f"project-{i}",
            description=f"Test project {i}",
            repository_url=f"https://github.com/test/repo{i}.git",
        )
        projects.append(project)

    # Seed workflow
    workflow = await simulation_seeder.seed_workflow(
        name="parallel-workflow",
        stages=[
            {"name": f"stage-{i}", "agent_type": f"agent-{i}", "order": i}
            for i in range(1, 4)
        ],
    )

    # Seed agents
    agents = []
    for i in range(3):
        agent = await simulation_seeder.seed_agent(
            name=f"agent-{i}",
            agent_type=f"agent-{i}",
            capabilities=["code_generation"],
        )
        agents.append(agent)

    # Seed work items (one per project)
    work_items = []
    for project in projects:
        work_item = await simulation_seeder.seed_work_item(
            project_id=project.id,
            title=f"Work item for {project.name}",
            description="Test description",
        )
        work_items.append(work_item)

    # Verify setup
    assert len(projects) == 3
    assert len(agents) == 3
    assert len(work_items) == 3
```

## Best Practices

### 1. Use Event Waiting, Not Sleeps

**Bad:**
```python
# DON'T DO THIS
e2e_client.trigger_workflow(work_item_id, workflow_id)
await asyncio.sleep(30)  # Hope it finishes
work_item = e2e_client.get_work_item(work_item_id)
```

**Good:**
```python
# DO THIS
e2e_client.trigger_workflow(work_item_id, workflow_id)
work_item = await e2e_client.wait_for_work_item_status(
    work_item_id,
    "COMPLETED",
    timeout=30.0,
)
```

### 2. Use Time Manipulation for Long Operations

**Bad:**
```python
# Test takes long time even in simulation
e2e_client.trigger_workflow(work_item_id, workflow_id)
await asyncio.sleep(1800)  # 30 minutes
```

**Good:**
```python
# Test runs in seconds
e2e_client.trigger_workflow(work_item_id, workflow_id)
e2e_client.advance_minutes(30)  # Fast-forward 30 minutes
await e2e_client.wait_for_work_item_status(work_item_id, "COMPLETED")
```

### 3. Use Deterministic Assertions

**Bad:**
```python
# Flaky: timing-dependent
executions = e2e_client.get_executions()
assert len(executions) > 0  # Might be 0 if execution hasn't started
```

**Good:**
```python
# Deterministic: wait for expected state
await e2e_client.wait_for_work_item_status(work_item_id, "COMPLETED")
executions = e2e_client.get_executions(work_item_id=work_item_id)
assert len(executions) == 3  # Exact count expected
```

### 4. Verify Observability Data

```python
# Always verify events and metrics were recorded
e2e_client.assert_events_recorded(
    "AgentExecutionCompleted",
    aggregate_id=work_item_id,
    min_count=3,
)

e2e_client.assert_metrics_recorded(
    "execution_duration",
    labels={"work_item_id": work_item_id},
    min_count=3,
)
```

### 5. Clean Up with Fixtures

```python
@pytest.fixture
async def clean_work_item(e2e_client, simulation_seeder):
    """Fixture that creates and cleans up work item."""
    project = await simulation_seeder.seed_project(name="test-project")

    work_item = e2e_client.create_work_item(
        project_id=project.id,
        title="Test item",
        description="Test",
    )

    yield work_item

    # Cleanup happens automatically with simulation_bootstrap teardown
    # No explicit cleanup needed
```

### 6. Use Markers for Organization

```python
# Mark simulation tests
@pytest.mark.simulation
@pytest.mark.asyncio
async def test_simulation_feature():
    pass

# Mark slow tests
@pytest.mark.slow_simulation
@pytest.mark.asyncio
async def test_long_workflow():
    pass

# Mark scenario tests
@pytest.mark.scenario
@pytest.mark.asyncio
async def test_predefined_scenario():
    pass
```

## Performance Tips

### 1. Use Fast Configuration

```python
@pytest.fixture
def custom_fast_config():
    """Ultra-fast configuration for unit-like tests."""
    return SimulationConfig.create_fast_config(
        scenario_name="test",
        speed_multiplier=1000.0,  # 1000x faster
    )
```

### 2. Parallel Test Execution

```bash
# Run tests in parallel with pytest-xdist
pytest tests/simulation -n auto
```

**Note:** All simulation adapters are thread-safe for concurrent execution.

### 3. Fixture Reuse

```python
# Reuse expensive fixtures across tests
@pytest.fixture(scope="module")
async def module_bootstrap():
    """Bootstrap shared across all tests in module."""
    config = SimulationConfig.create_fast_config("test")
    bootstrap = SimulationApplicationBootstrap(config)
    await bootstrap.setup()
    yield bootstrap
    await bootstrap.teardown()
```

### 4. Minimize Seeding

```python
# Only seed what you need
@pytest.mark.asyncio
async def test_minimal_seeding(simulation_seeder):
    """Seed only required data."""
    # Don't seed entire scenario if you only need 1 work item
    project = await simulation_seeder.seed_project(name="test")
    work_item = await simulation_seeder.seed_work_item(
        project_id=project.id,
        title="Test",
        description="Test",
    )
    # Skip seeding workflows, agents, etc. if not needed
```

### 5. Fast Assertions

```python
# Use indexed queries (fast)
events = e2e_client.get_events(
    event_type="AgentExecutionCompleted",  # Indexed
    aggregate_id=work_item_id,  # Indexed
)

# Avoid full scans
all_events = e2e_client.get_events(limit=10000)  # Slower
```

## Example Test Walkthrough

Let's walk through a complete example step by step:

### Scenario: Test Review Cycle

**Goal:** Test a workflow with a review stage that rejects once, then approves.

### Step 1: Define Test

```python
import pytest

@pytest.mark.simulation
@pytest.mark.asyncio
async def test_review_cycle_with_rejection(e2e_client, simulation_seeder, mock_llm):
    """
    Test workflow with review cycle: rejection → fix → approval.

    Scenario:
    1. Create work item
    2. Execute implementation stage
    3. Execute review stage → rejection
    4. Execute fix stage
    5. Execute review stage → approval
    6. Workflow completes
    """
```

### Step 2: Setup Test Data

```python
    # Seed project
    project = await simulation_seeder.seed_project(
        name="review-test-project",
        repository_url="https://github.com/test/repo.git",
    )

    # Seed workflow with review cycle
    workflow = await simulation_seeder.seed_workflow(
        name="review-workflow",
        stages=[
            {"name": "implement", "agent_type": "developer", "order": 1},
            {"name": "review", "agent_type": "reviewer", "order": 2},
            {"name": "fix", "agent_type": "developer", "order": 3},
            {"name": "final-review", "agent_type": "reviewer", "order": 4},
        ],
    )

    # Seed agents
    await simulation_seeder.seed_agents([
        {
            "name": "developer",
            "agent_type": "developer",
            "capabilities": ["code_generation"],
        },
        {
            "name": "reviewer",
            "agent_type": "reviewer",
            "capabilities": ["code_review"],
        },
    ])
```

### Step 3: Configure Mock Behavior

```python
    # Configure LLM responses for review
    review_count = 0

    def review_response_generator(prompt: str):
        nonlocal review_count
        if "review" in prompt.lower():
            review_count += 1
            if review_count == 1:
                return "REJECTED: Missing error handling"
            else:
                return "APPROVED: All issues resolved"
        return "# Implementation\n..."

    mock_llm.set_response_generator(review_response_generator)
```

### Step 4: Execute Test

```python
    # Create work item
    work_item = e2e_client.create_work_item(
        project_id=project.id,
        title="Add error handling",
        description="Implement proper error handling",
        labels=["enhancement"],
        priority="HIGH",
    )

    # Connect WebSocket to watch events
    ws_collector = e2e_client.connect_websocket(
        subscription_type="work_item_events",
        work_item_id=work_item["id"],
    )

    # Trigger workflow
    e2e_client.trigger_workflow(work_item["id"], workflow.id)

    # Wait for completion
    final_work_item = await e2e_client.wait_for_work_item_status(
        work_item["id"],
        "COMPLETED",
        timeout=90.0,
    )
```

### Step 5: Verify Results

```python
    # Verify workflow completed
    assert final_work_item["status"] == "COMPLETED"

    # Verify all stages executed
    executions = e2e_client.get_executions(work_item_id=work_item["id"])
    assert len(executions) == 4  # implement, review, fix, final-review

    # Verify review rejection event
    rejection_events = e2e_client.get_events(
        event_type="ReviewRejected",
        aggregate_id=work_item["id"],
    )
    assert len(rejection_events) == 1
    assert "Missing error handling" in rejection_events[0]["payload"]["feedback"]

    # Verify review approval event
    approval_events = e2e_client.get_events(
        event_type="ReviewApproved",
        aggregate_id=work_item["id"],
    )
    assert len(approval_events) == 1

    # Verify WebSocket events
    ws_collector.assert_event_received("ReviewRejected")
    ws_collector.assert_event_received("ReviewApproved")

    # Verify metrics
    e2e_client.assert_metrics_recorded(
        "review_duration",
        labels={"work_item_id": work_item["id"]},
        min_count=2,  # 2 review stages
    )
```

## Common Testing Patterns

### Pattern: Parallel Workflow Execution

```python
@pytest.mark.asyncio
async def test_parallel_workflows(e2e_client, simulation_seeder):
    """Test multiple workflows executing in parallel."""
    project = await simulation_seeder.seed_project(name="parallel-test")

    # Create multiple work items
    work_items = []
    for i in range(5):
        work_item = e2e_client.create_work_item(
            project_id=project.id,
            title=f"Parallel item {i}",
            description=f"Description {i}",
        )
        work_items.append(work_item)

    # Trigger all workflows
    for work_item in work_items:
        e2e_client.trigger_workflow(work_item["id"], "simple-workflow")

    # Wait for all to complete
    for work_item in work_items:
        await e2e_client.wait_for_work_item_status(
            work_item["id"],
            "COMPLETED",
            timeout=60.0,
        )

    # Verify all completed
    for work_item in work_items:
        final = e2e_client.get_work_item(work_item["id"])
        assert final["status"] == "COMPLETED"
```

### Pattern: Error Recovery

```python
@pytest.mark.asyncio
async def test_error_recovery(e2e_client, simulation_seeder, fake_container):
    """Test recovery from container execution error."""
    # Configure container to fail once
    failure_count = 0

    def container_executor(command: str, context: dict):
        nonlocal failure_count
        failure_count += 1
        if failure_count == 1:
            return {"exit_code": 1, "stdout": "", "stderr": "Error"}
        return {"exit_code": 0, "stdout": "Success", "stderr": ""}

    fake_container.set_execution_handler(container_executor)

    # Create and trigger workflow
    project = await simulation_seeder.seed_project(name="error-test")
    work_item = e2e_client.create_work_item(
        project_id=project.id,
        title="Error recovery test",
        description="Test error recovery",
    )

    e2e_client.trigger_workflow(work_item["id"], "retry-workflow")

    # Wait for eventual success
    await e2e_client.wait_for_work_item_status(
        work_item["id"],
        "COMPLETED",
        timeout=60.0,
    )

    # Verify retry occurred
    assert failure_count == 2  # Failed once, succeeded once
```

### Pattern: State Verification

```python
@pytest.mark.asyncio
async def test_state_verification(e2e_client, simulation_bootstrap):
    """Verify aggregate state via event replay."""
    # Create work item
    work_item = e2e_client.create_work_item(
        project_id="proj-001",
        title="State test",
        description="Test",
    )

    # Trigger multiple state changes
    e2e_client.trigger_workflow(work_item["id"], "simple-workflow")
    await e2e_client.wait_for_work_item_status(work_item["id"], "COMPLETED")

    # Get all events
    event_store = simulation_bootstrap.adapters.event_store
    events = await event_store.get_events(work_item["id"])

    # Verify event sequence
    event_types = [e.event_type for e in events]
    assert event_types == [
        "WorkItemCreated",
        "WorkflowTriggered",
        "AgentExecutionStarted",
        "AgentExecutionCompleted",
        "WorkItemCompleted",
    ]

    # Replay events to reconstruct state
    from codetoreum.domain.work_item import WorkItem
    reconstructed = WorkItem.from_events(events)
    assert reconstructed.status == "COMPLETED"
```

## Troubleshooting Tests

### Test Timeout

**Problem:** Test times out waiting for status

```python
TimeoutError: Work item xyz did not reach status 'COMPLETED' within 30s
```

**Solutions:**
1. Increase timeout: `await e2e_client.wait_for_work_item_status(..., timeout=60.0)`
2. Check for errors: `executions = e2e_client.get_executions(work_item_id=work_item_id)`
3. Review events: `events = e2e_client.get_events(aggregate_id=work_item_id)`
4. Enable debug logging: `pytest tests/simulation/test_my_test.py -v -s --log-cli-level=DEBUG`

### Flaky Tests

**Problem:** Test passes sometimes, fails other times

**Solutions:**
1. Use event waiting instead of sleeps
2. Increase speed multiplier: `speed_multiplier=100.0` (deterministic, no race conditions)
3. Use deterministic LLM responses: `mock_llm.add_pattern(...)`
4. Verify fixture cleanup: ensure `simulation_bootstrap` fixture used

### Missing Events

**Problem:** `assert_event_received` fails

```python
AssertionError: Event 'AgentExecutionCompleted' not found
```

**Solutions:**
1. Check event type spelling: `"AgentExecutionCompleted"` (case-sensitive)
2. Verify workflow was triggered: `e2e_client.trigger_workflow(...)`
3. Wait for event: `ws_collector.wait_for_event(..., timeout=30.0)`
4. Check event store directly: `events = e2e_client.get_events(event_type="...")`

## Next Steps

- **Usage Guide**: [simulation_mode_usage.md](simulation_mode_usage.md) - Learn how to use the simulation server
- **Architecture**: [../simulation_mode_architecture.md](../simulation_mode_architecture.md) - Understand the implementation
- **Example Tests**: `/workspace/tests/simulation/test_scenarios.py` - See more examples
- **API Reference**: http://localhost:8000/docs (when server is running)

## Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Asyncio](https://pytest-asyncio.readthedocs.io/)
- [FastAPI TestClient](https://fastapi.tiangelo.com/tutorial/testing/)
- [Event Sourcing Testing](https://martinfowler.com/eaaDev/EventSourcing.html)
