# Simulation Testing Framework

## Overview

The simulation testing framework enables fast, deterministic end-to-end testing of Codetoreum workflows without external dependencies. Tests run **10-100x faster than real time** while maintaining realistic behavior.

## Key Features

- **Time Manipulation**: Fast-forward through hours of simulated time in seconds
- **Deterministic**: Same inputs always produce same outputs
- **No External Dependencies**: All adapters are mocked/in-memory
- **Event Sourcing**: Complete audit trail of all domain events
- **Comprehensive Assertions**: Built-in helpers for common checks
- **Fast Execution**: Tests complete in seconds, not minutes

## Architecture

```
┌─────────────────────────────────────────────────┐
│         Simulation Runner                       │
│  ┌───────────────────────────────────────────┐  │
│  │  Simulation Clock (Time Control)          │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │  Mock Adapters                            │  │
│  │  • MockLLMAdapter                         │  │
│  │  • FakeContainerAdapter                   │  │
│  │  • InMemoryMetricsAdapter                 │  │
│  │  • MockNotifierAdapter                    │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │  Event Capture & Assertions               │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Quick Start

### Basic Test Structure

```python
from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)

async def test_my_workflow():
    # 1. Configure simulation
    config = SimulationConfig.create_fast_config(
        scenario_name="my_test",
        speed_multiplier=100.0,
    )

    # 2. Create runner
    runner = SimulationRunner(config)

    # 3. Define scenario
    async def scenario(sim: SimulationRunner):
        # Your test logic here
        await sim.advance_time(timedelta(minutes=5))
        sim.assert_event_occurred("WorkflowStarted")

    # 4. Run and verify
    result = await runner.run(scenario)
    assert result.success
```

### Running Tests

```bash
# Run all simulation tests
pytest tests/simulation/

# Run specific scenario
pytest tests/simulation/test_scenarios.py::test_scenario_01_simple_workflow

# Run with verbose output
pytest tests/simulation/ -v -s

# Run only fast simulations (skip slow ones)
pytest tests/simulation/ -m simulation

# Run only scenario tests
pytest tests/simulation/ -m scenario
```

## Directory Structure

```
tests/simulation/
├── README.md                    # This file
├── SCENARIO_FORMAT.md           # Scenario specification
├── conftest.py                  # Pytest fixtures
├── helpers.py                   # Test helper functions
├── test_scenarios.py            # Scenario test suite
└── scenarios/                   # Predefined scenarios
    ├── scenario_01_simple_workflow.py
    ├── scenario_02_parallel_executions.py
    ├── scenario_03_review_cycle.py
    ├── scenario_04_execution_failure.py
    └── scenario_05_complex_workflow.py
```

## Components

### 1. SimulationClock

Controls time in simulation. Allows advancing time programmatically.

```python
clock = SimulationClock(speed_multiplier=100.0)
clock.start_at(datetime(2025, 1, 1, 12, 0, 0))

# Advance by duration
await clock.advance(timedelta(hours=1))

# Advance to specific time
await clock.advance_to(datetime(2025, 1, 1, 14, 0, 0))

# Get current time
current = clock.now()
```

**Performance**: With 100x multiplier, 1 hour of simulated time = 36 seconds real time.

### 2. SimulationConfig

Configures mock adapter behavior.

```python
config = SimulationConfig.create_fast_config("test", speed_multiplier=100.0)

# Configure agent responses
config.add_agent_response_pattern(
    agent_id="code-generator",
    pattern=r"generate.*",
    response="Generated code here"
)

# Configure container results
config.set_container_command_result(
    command="pytest",
    exit_code=0,
    stdout="Tests passed"
)
```

### 3. SimulationRunner

Orchestrates the simulation and provides assertion methods.

```python
runner = SimulationRunner(config)

# Run scenario
result = await runner.run(scenario_func)

# Assertions
runner.assert_event_occurred("EventType")
runner.assert_event_count("EventType", 3)
runner.assert_metric_recorded("metric.name")
runner.assert_notification_sent("user@example.com")

# Access adapters
runner.llm_adapter
runner.container_adapter
runner.metrics_adapter
runner.notifier_adapter
```

### 4. Mock Adapters

#### MockLLMAdapter
Simulates LLM responses based on pattern matching.

```python
adapter.add_response_pattern(r"code.*", "Here's the code")
result = await adapter.execute("generate code")
```

#### FakeContainerAdapter
Simulates container execution without Docker.

```python
adapter.set_command_result("build", exit_code=0, stdout="Success")
result = await adapter.run(image="test", command=["build"], ...)
```

#### InMemoryMetricsAdapter
Stores metrics in memory for verification.

```python
await adapter.increment_counter("requests", 1)
await adapter.set_gauge("queue_size", 42)
value = adapter.get_counter_value("requests")
```

#### MockNotifierAdapter
Captures notifications without sending.

```python
result = await adapter.send(
    channel=NotificationChannel.EMAIL,
    recipient="test@example.com",
    subject="Test",
    message="Message"
)
notifications = adapter.get_sent_notifications()
```

## Predefined Scenarios

### Scenario 1: Simple Workflow
**Purpose**: Basic workflow with 3 sequential stages
**Duration**: ~16 minutes simulated, ~10 seconds real
**Tests**: Basic agent execution, workflow completion

### Scenario 2: Parallel Executions
**Purpose**: Multiple work items executing concurrently
**Duration**: ~15 minutes simulated, ~9 seconds real
**Tests**: Concurrent execution, resource management

### Scenario 3: Review Cycle
**Purpose**: Maker-checker with feedback loop
**Duration**: ~16 minutes simulated, ~10 seconds real
**Tests**: Review rejection, resubmission, approval

### Scenario 4: Execution Failure
**Purpose**: Agent failure and retry logic
**Duration**: ~11 minutes simulated, ~7 seconds real
**Tests**: Error handling, retry mechanism

### Scenario 5: Complex Workflow
**Purpose**: Multi-stage with conditional branches
**Duration**: ~28 minutes simulated, ~17 seconds real
**Tests**: Branching logic, complex orchestration

## Writing Custom Scenarios

### Step 1: Create Configuration

```python
def create_config() -> SimulationConfig:
    config = SimulationConfig.create_fast_config(
        scenario_name="my_scenario",
        speed_multiplier=100.0,
    )

    # Configure mock behavior
    config.add_agent_response_pattern(
        agent_id="my-agent",
        pattern=r".*",
        response="Agent response"
    )

    return config
```

### Step 2: Define Scenario Logic

```python
async def run_scenario(runner: SimulationRunner) -> None:
    # Simulate events
    event = DomainEvent(
        aggregate_id="ITEM-1",
        aggregate_type="WorkItem",
        payload={"status": "started"}
    )
    event.event_type = "WorkflowStarted"
    runner.capture_event(event)

    # Advance time
    await runner.advance_time(timedelta(minutes=5))

    # Make assertions
    runner.assert_event_occurred("WorkflowStarted")
```

### Step 3: Create Test

```python
@pytest.mark.simulation
@pytest.mark.asyncio
async def test_my_scenario():
    config = create_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_scenario)

    assert result.success
    assert result.speed_multiplier >= 10.0
```

## Assertion Helpers

The `helpers.py` module provides convenient assertion functions:

```python
from helpers import AssertionHelpers, ScenarioHelpers

# Assert workflow completed
AssertionHelpers.assert_workflow_completed(
    runner,
    work_item_id="ISSUE-123",
    expected_stages=3
)

# Assert agent executed
AssertionHelpers.assert_agent_executed(
    runner,
    agent_id="code-generator",
    work_item_id="ISSUE-123"
)

# Assert event sequence
AssertionHelpers.assert_execution_sequence(
    runner,
    ["EventA", "EventB", "EventC"]
)

# Simulate workflow with helpers
await ScenarioHelpers.simulate_workflow_execution(
    runner,
    work_item_id="ISSUE-123",
    stages=[
        {"agent_id": "agent-1", "duration_minutes": 5},
        {"agent_id": "agent-2", "duration_minutes": 3},
    ]
)
```

## Debugging

### Print Event Timeline

```python
from helpers import print_event_timeline

result = await runner.run(scenario)
print_event_timeline(runner)
```

Output:
```
=== Event Timeline ===
 1. [   0.0s] WorkflowStarted            | WorkItem:ISSUE-123
 2. [   5.0s] AgentExecutionStarted      | AgentExecution:exec-1
 3. [   7.0s] AgentExecutionCompleted    | AgentExecution:exec-1
...
```

### Print Metrics Summary

```python
from helpers import print_metrics_summary

result = await runner.run(scenario)
print_metrics_summary(runner)
```

### Print Notifications

```python
from helpers import print_notifications_summary

result = await runner.run(scenario)
print_notifications_summary(runner)
```

### Simulation Summary

```python
runner.print_summary()
```

Output:
```
=== Simulation Summary: simple_workflow ===
Real time elapsed: 0.15s
Simulated time: 16.00s
Speed multiplier: 100.0x

Events captured: 8
Metrics recorded: 5
Notifications sent: 2

Assertions passed: 6
Assertions failed: 0
```

## Best Practices

### 1. Use High Speed Multipliers

```python
# Good: 100x speed
config = SimulationConfig.create_fast_config("test", speed_multiplier=100.0)

# Avoid: Too slow for CI
config = SimulationConfig.create_realistic_config("test", speed_multiplier=1.0)
```

### 2. Keep Scenarios Focused

Each scenario should test one specific workflow or behavior, not multiple unrelated things.

### 3. Use Meaningful Event Names

```python
# Good
runner.assert_event_occurred("WorkflowStarted", assertion_name="workflow_initiated")

# Avoid
runner.assert_event_occurred("WorkflowStarted", assertion_name="test1")
```

### 4. Verify Performance Goals

```python
assert result.speed_multiplier >= 10.0, "Must be at least 10x faster"
```

### 5. Use Fixtures for Common Setup

```python
@pytest.fixture
def configured_runner():
    config = create_config()
    # Common configuration here
    return SimulationRunner(config)

async def test_something(configured_runner):
    # Test uses pre-configured runner
    pass
```

## Performance Targets

| Metric | Target | Actual (scenarios) |
|--------|--------|-------------------|
| Speed Multiplier | 10-100x | 100x+ |
| Test Duration | < 30s | 7-17s |
| Event Capture | 100% | 100% |
| Determinism | 100% | 100% |

## Troubleshooting

### Tests Running Slowly

- Check speed_multiplier is >= 10
- Reduce execution_delay in config
- Use `create_fast_config()` instead of `create_realistic_config()`

### Assertions Failing

- Use `print_event_timeline()` to see what events occurred
- Check event types match exactly (case-sensitive)
- Verify aggregate_id filtering

### Events Not Captured

- Ensure `runner.capture_event()` is called
- Check event is created with correct event_type
- Verify scenario function is async and awaited

### Time Issues

- Ensure clock is advanced with `await runner.advance_time()`
- Check timedelta values are correct
- Verify clock starts at expected time

## Future Enhancements

Potential improvements for Phase 5+:

- [ ] YAML scenario loader for declarative tests
- [ ] Visual timeline generator (HTML report)
- [ ] Performance profiling and bottleneck detection
- [ ] Fuzzing support for robustness testing
- [ ] Integration with CI/CD metrics
- [ ] Snapshot testing for event streams
- [ ] Parallel scenario execution

## References

- **Design Doc**: `documentation/01_design/infrastructure/simulation_design.md`
- **Scenario Format**: `SCENARIO_FORMAT.md`
- **Source Code**: `src/codetoreum/infrastructure/simulation/`

## Support

For questions or issues:
1. Check this README and SCENARIO_FORMAT.md
2. Review existing scenario implementations
3. Check test output and use debugging helpers
4. Consult design documentation
