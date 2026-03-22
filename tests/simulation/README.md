# Simulation Testing Framework

## Overview

The simulation testing framework enables fast, deterministic end-to-end testing of Codetoreum workflows without external dependencies. Tests run **10-100x faster than real time** while maintaining realistic behavior.

### Full Application Service Chain Active

All simulation runs activate the **complete application service execution chain**:
- **ExecutionService**: LLM execution orchestration with output capture and result tracking
- **WorkspaceRouter**: Repository cloning, branch management, and workspace preparation
- **InMemoryVersionControlService**: VCS operations without external Git dependencies

The **ExecutionServiceAgentExecutor** is the unconditional default agent executor for all simulations, ensuring that all agent executions flow through the full application service chain. There is no optional "fast path" or mock-only execution mode—simulations always exercise the complete production code path for agent execution.

## Key Features

- **Time Manipulation**: Fast-forward through hours of simulated time in seconds
- **Deterministic**: Same inputs always produce same outputs
- **No External Dependencies**: All adapters are mocked/in-memory
- **Event Sourcing**: Complete audit trail of all domain events
- **Comprehensive Assertions**: Built-in helpers for common checks
- **Fast Execution**: Tests complete in seconds, not minutes
- **Full Service Chain**: ExecutionService, WorkspaceRouter, and InMemoryVersionControlService always active

## Execution Model

### Agent Execution Flow

Every agent execution in simulation follows the complete production flow:

```
Agent Execution Request
    ↓
BoardColumnEventHandler
    ↓
ExecutionServiceAgentExecutor (unconditional default)
    ↓
ExecutionService (LLM orchestration)
    ↓
WorkspaceRouter (repository/workspace management)
    ↓
InMemoryVersionControlService (VCS operations)
    ↓
MockLLMAdapter → LLM response simulation
    ↓
FakeContainerAdapter → Optional Docker simulation
    ↓
Execution completion → Auto-progression to next workflow stage
```

### What's Active vs. Mocked

**Always Active (Production Code)**:
- ExecutionService
- WorkspaceRouter
- InMemoryVersionControlService
- ExecutionContextBuilder
- Agent domain objects and lookups

**Always Mocked (Testing Adapters)**:
- LLM responses (MockLLMAdapter with configurable patterns)
- Container execution (FakeContainerAdapter without Docker)
- Git repository (InMemoryRepositoryAdapter)
- External ticket system (InMemoryTicketAdapter)
- All other output port adapters (24 total)

### No Mock-Only Mode

There is **no optional lightweight execution mode**. The architecture ensures that:
1. ExecutionServiceAgentExecutor is wired as the sole agent executor implementation
2. All agent executions route through the full service chain
3. Simulation tests verify production execution paths, not simplified mocks

This design choice ensures simulation tests catch integration issues between ExecutionService, WorkspaceRouter, and VCS operations before production deployment.

### Unit Test Utilities (Not Used in Simulation Bootstrap)

**MockAgentExecutor** is a unit-test-only utility for isolated test scenarios. It is NOT wired by SimulationApplicationBootstrap. It is used exclusively in board automation unit tests that manually construct BoardColumnEventHandler instances to test event handler logic without invoking the full execution chain. For simulation bootstrap wiring, ExecutionServiceAgentExecutor is always used unconditionally.

## Architecture

```
┌─────────────────────────────────────────────────┐
│    SimulationApplicationBootstrap (6 Phases)    │
├─────────────────────────────────────────────────┤
│ Phase 0: SimulationEngine (clock, timing)       │
│ Phase 1: Infrastructure (event bus, logger)     │
│ Phase 2: 24 Adapters (mock/in-memory)           │
│ Phase 3: 11 Services (execution, orchestration) │
│ Phase 4: 16 Ports (input/output interfaces)     │
│ Phase 5: FastAPI App + Event Handlers           │
│          - Board event bridge (to EventBus)     │
│          - BoardColumnEventHandler (automation) │
│          - RepairCycleEventHandler              │
│          - ExecutionServiceAgentExecutor        │
└─────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────┐
│       Simulation Runner                         │
│  ┌───────────────────────────────────────────┐  │
│  │  Simulation Clock (Time Control)          │  │
│  │  Speed: 10-100x faster than real time     │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │  24 Mock Adapters                         │  │
│  │  • MockLLMAdapter (LLM responses)         │  │
│  │  • FakeContainerAdapter (execution)       │  │
│  │  • InMemoryVersionControlService (VCS)    │  │
│  │  • 21 other output port mocks             │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │  Full Service Chain                       │  │
│  │  • ExecutionService                       │  │
│  │  • WorkspaceRouter                        │  │
│  │  • WorkflowOrchestrator                   │  │
│  │  • 8 other application services           │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │  Event Capture & Assertions               │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Bootstrap Phases

The SimulationApplicationBootstrap wires all components in 6 phases, ensuring the full execution chain is always active:

### Phase 0: SimulationEngine
Creates the clock for time manipulation and coordination of time-aware adapters.

### Phase 1: Infrastructure
Creates the event bus, logger, error registry, and dead letter queue for event reliability.

### Phase 2: 24 Adapters
Creates all output port adapters:
- **5 main adapters** (via AdapterFactory): ticket_system, llm_provider, container, repository, event_store
- **19 additional adapters**: metrics, storage, config, notifier, encryption, board, repair_cycle, project_manager, lock_service, workflow_config, queue_service, event_emitter, version_control, message_broker, discussion, review_cycle, identity_service, checkpoint_store, agent_repository, branch_tracker

**Key Point**: InMemoryVersionControlService is created in Phase 2 and wired into the execution chain.

### Phase 3: Services & ExecutionServiceAgentExecutor
Creates all application services including ExecutionService and WorkspaceRouter. Then creates **ExecutionServiceAgentExecutor** as the unconditional agent executor, wiring it with:
- ExecutionService (LLM orchestration)
- WorkspaceRouter (repository management)
- InMemoryVersionControlService (VCS operations)
- Supporting adapters (config store, agent repository, work item service, run registry, branch tracker)

**This is the critical step**: ExecutionServiceAgentExecutor becomes the sole agent executor, ensuring all executions route through the full service chain.

### Phase 4: Input/Output Ports
Creates all port implementations that form the REST API and query interfaces.

### Phase 5: FastAPI App & Event Handlers
Creates the FastAPI application and registers event handlers:
- **Board Event Bridge**: Translates board events to domain events and publishes to EventBus
- **BoardColumnEventHandler**: Listens for column changes and triggers agent execution via ExecutionServiceAgentExecutor
- **RepairCycleEventHandler**: Manages repair cycle automation

The BoardColumnEventHandler calls ExecutionServiceAgentExecutor, which in turn calls ExecutionService → WorkspaceRouter → InMemoryVersionControlService, completing the full chain.

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

### 2. SimulationConfig & Fidelity Levels

Configures mock adapter behavior and timing accuracy.

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

#### Fidelity Levels

Fidelity levels control timing accuracy and realism in simulations:

| Level | Timing | Delays | Use Case | Speed |
|-------|--------|--------|----------|-------|
| **LOW** | Disabled | None | Unit tests, fast regression | 100x+ |
| **MEDIUM** | Proportional | By token/file ops | Integration tests, workflow validation | 10-50x |
| **HIGH** | Realistic | With jitter/failures | Performance testing, chaos engineering | 1-5x |

**Choose the right level**:

- **LOW** (Default): Use for quick CI/CD feedback. Fastest execution, no timing overhead.
  ```python
  config = SimulationConfig.create_fast_config(
      "test",
      fidelity_level=FidelityLevel.LOW,
      speed_multiplier=100.0
  )
  ```

- **MEDIUM**: Use for realistic behavior testing without performance focus.
  ```python
  config = SimulationConfig.create_fast_config(
      "test",
      fidelity_level=FidelityLevel.MEDIUM,
      ms_per_token=50.0,           # 50ms per LLM token
      ms_per_file_operation=10.0,  # 10ms per file operation
      speed_multiplier=20.0
  )
  ```

- **HIGH**: Use for performance testing and chaos engineering.
  ```python
  config = SimulationConfig.create_realistic_config(
      "test",
      fidelity_level=FidelityLevel.HIGH,
      ms_per_token=100.0,
      ms_per_file_operation=50.0,
      speed_multiplier=1.0  # Real-time for accurate measurements
  )
  ```

**Timing Mechanism**:

- **LLM Adapter**: Delay = (prompt_tokens + response_tokens) × ms_per_token
- **Container Adapter**: Delay = base_overhead + (file_operations × ms_per_file_operation)
- All delays respect `SimulationClock` speed multiplier for proper time scaling

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

### 4. ExecutionServiceAgentExecutor

The agent executor wired as the unconditional default for all simulations. Routes all agent executions through the complete application service chain:

```python
ExecutionServiceAgentExecutor(
    execution_service=execution_service,
    workspace_router=workspace_router,
    config_store=config_store,
    agent_repository=agent_repository,
    work_item_service=work_item_service,
    run_registry=run_registry,
    branch_tracker=branch_tracker,
    vcs=version_control_service,
)
```

This executor:
- Looks up active workflow runs from the registry
- Loads Agent and WorkItem domain objects
- Routes workspace setup via WorkspaceRouter
- Tracks VCS branches and file content
- Executes LLM via MockLLMAdapter (production code path)
- Executes containers via FakeContainerAdapter (when `requires_docker=True`)
- Calls completion callbacks for automation (auto-progression to next stage)

**No Mock-Only Alternative**: Every agent execution exercises the full production code path through ExecutionService and WorkspaceRouter.

### 5. Mock Adapters

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

#### InMemoryVersionControlService
Handles VCS operations (clone, commit, push) without external Git dependencies.

```python
await vcs.clone_repository("https://repo.git", "branch", workspace_path)
await vcs.commit("message", author="agent", workspace_path)
await vcs.push("branch", workspace_path)
```

This service is wired into WorkspaceRouter and is always active during simulations, ensuring that repository operations are exercised as part of the full execution chain.

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

## Execution Chain Design

### Always-Active Services

The simulation framework ensures that **all agent executions exercise the production code path** through these services:

1. **ExecutionService**: Orchestrates LLM execution, captures outputs, tracks results
2. **WorkspaceRouter**: Manages repository cloning, branch setup, workspace preparation
3. **InMemoryVersionControlService**: Handles VCS operations without external Git

These services are NOT optional or configurable. They are always wired via **ExecutionServiceAgentExecutor**, which is the unconditional default agent executor for all simulations.

### Benefits of Full Service Chain

- **Catch Integration Issues**: Repository operations, branch management, and workspace setup are tested
- **Production Path Testing**: Simulations exercise the same code path as production
- **Complete Audit Trail**: All operations are captured in event store and event bus
- **Realistic Delays**: Service overhead is accounted for in timing simulation

### Configuration Points

You can configure **mock adapter behavior** to test different scenarios without changing the execution chain:

```python
config = SimulationConfig.create_fast_config("test")

# Configure LLM responses
config.add_agent_response_pattern(r"generate.*", "Generated code")

# Configure container results
config.set_container_command_result("test", exit_code=0, stdout="Passed")

# Configure timing (fidelity level)
config.fidelity_level = FidelityLevel.MEDIUM
config.ms_per_token = 50.0
```

The underlying services (ExecutionService, WorkspaceRouter, InMemoryVersionControlService) remain constant.

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
