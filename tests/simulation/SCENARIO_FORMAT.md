# Simulation Scenario Format Specification

## Overview

Simulation scenarios are primarily defined using Python for maximum flexibility and clarity. YAML can be used to define simulation configuration (agent behavior, timing, container settings) and can be loaded and passed to Python scenarios for parameterization. This document describes both the Python format (primary) and YAML configuration format (supplemental).

## Python Format (Recommended)

Python scenarios provide maximum flexibility and are the primary way to write simulation tests.

### Basic Structure

```python
from datetime import timedelta
from codetoreum.infrastructure.simulation import (
    SimulationConfig,
    SimulationRunner,
)

async def test_my_scenario():
    # 1. Create configuration
    config = SimulationConfig.create_fast_config(
        scenario_name="my_scenario",
        speed_multiplier=100.0,
    )

    # 2. Configure agent responses
    config.add_agent_response_pattern(
        agent_id="code-generator",
        pattern=r"generate.*code",
        response="Here is the generated code..."
    )

    # 3. Configure container results
    config.set_container_command_result(
        command="pytest",
        exit_code=0,
        stdout="All tests passed",
    )

    # 4. Create and run simulation
    runner = SimulationRunner(config)

    async def scenario(sim: SimulationRunner):
        # Your scenario logic here
        # - Trigger workflows
        # - Advance time
        # - Make assertions

        await sim.advance_time(timedelta(minutes=5))
        sim.assert_event_occurred("WorkflowStarted")

    result = await runner.run(scenario)

    # 5. Verify results
    assert result.success
    assert result.assertions_passed > 0
```

### Scenario Structure

A simulation scenario function receives a `SimulationRunner` instance and can:

1. **Trigger Actions**: Call application services, move tickets, etc.
2. **Advance Time**: Fast-forward simulation clock
3. **Make Assertions**: Verify events, metrics, notifications

### Available Assertions

- `assert_true(condition, name, message)`
- `assert_false(condition, name, message)`
- `assert_equal(actual, expected, name, message)`
- `assert_event_occurred(event_type, aggregate_id, name)`
- `assert_event_count(event_type, expected_count, name)`
- `assert_metric_recorded(metric_name, name)`
- `assert_notification_sent(recipient, subject_contains, name)`

### Time Control

```python
# Advance by duration
await runner.advance_time(timedelta(hours=1))

# Advance to specific time
await runner.advance_to(datetime(2025, 1, 1, 14, 0, 0))

# Get current simulation time
current_time = runner.clock.now()
```

### Accessing Adapters

```python
# LLM adapter
runner.llm_adapter.add_response_pattern(pattern, response)

# Container adapter
runner.container_adapter.set_command_result(command, exit_code, stdout, stderr)

# Metrics adapter
metrics = await runner.metrics_adapter.query_metrics(...)

# Notifier adapter
notifications = runner.notifier_adapter.get_sent_notifications()
```

## YAML Configuration Format (Optional)

YAML files can be used to configure simulation behavior (time, agent responses, container settings) for parameterized testing. Configuration can be loaded and passed to Python scenario functions. **Note**: Scenario logic (workflow execution, assertions) must be implemented in Python.

### Basic Structure

```yaml
scenario:
  name: "Simple Workflow"
  description: "Single work item through 3-stage workflow"

  time:
    speed_multiplier: 100.0
    start_time: "2025-01-01T12:00:00Z"
    auto_advance: false

  agents:
    code-generator:
      execution_delay: 0.1
      success_rate: 1.0
      response_patterns:
        "generate.*class": "class MyClass:\n    pass"
        "write.*tests": "def test_my_class():\n    pass"
      token_usage:
        input: 100
        output: 50

    code-reviewer:
      execution_delay: 0.1
      response_patterns:
        "review.*code": "LGTM! The code looks good."

  container:
    default_exit_code: 0
    execution_delay: 0.1
    command_results:
      - command: "pytest"
        exit_code: 0
        stdout: "====== 10 passed in 2.5s ======="
        stderr: ""
      - command: "mypy"
        exit_code: 0
        stdout: "Success: no issues found"

  notifications:
    send_delay: 0.01
    simulate_failures: false
    failure_rate: 0.0

  metrics:
    enabled: true
    tracked_metrics:
      - "workflow.stage.duration"
      - "agent.execution.count"

  initial_state:
    work_items:
      - id: "ISSUE-123"
        title: "Add user authentication"
        description: "Implement OAuth2 login"
        status: "Ready"
        labels: ["feature", "high-priority"]

    workflows:
      - id: "basic-workflow"
        name: "Basic Development Workflow"
        stages:
          - name: "Code Generation"
            agent_id: "code-generator"
          - name: "Code Review"
            agent_id: "code-reviewer"
          - name: "Testing"
            agent_id: "test-runner"

  events:
    - time_offset: "0s"
      action: "move_card"
      params:
        work_item_id: "ISSUE-123"
        to_column: "In Progress"

    - time_offset: "5m"
      action: "advance_time"
      params:
        duration: "1h"

    - time_offset: "1h5m"
      action: "assert_event"
      params:
        event_type: "WorkflowCompleted"
        aggregate_id: "ISSUE-123"

  expected_outcomes:
    events:
      - type: "WorkflowStarted"
        count: 1
      - type: "AgentExecutionStarted"
        count: 3
      - type: "WorkflowCompleted"
        count: 1

    metrics:
      - name: "agent.execution.count"
        min_value: 3

    notifications:
      - recipient: "team@example.com"
        subject_contains: "Workflow completed"
```

### YAML Field Descriptions

#### `scenario`
- `name`: Scenario name (required)
- `description`: Human-readable description
- `time`: Time configuration
- `agents`: Agent behavior configuration
- `container`: Container behavior configuration
- `notifications`: Notification behavior
- `metrics`: Metrics configuration

#### `time`
- `speed_multiplier`: How much faster than real time (default: 10.0)
- `start_time`: Starting time (ISO 8601 format, optional)
- `auto_advance`: Whether to auto-advance clock (default: false)

#### `agents[agent_id]`
- `execution_delay`: Execution delay in seconds
- `success_rate`: Success rate 0.0-1.0
- `response_patterns`: Map of regex pattern -> response
- `token_usage`: Input/output token counts

#### `container`
- `default_exit_code`: Default exit code for commands
- `execution_delay`: Execution delay in seconds
- `command_results`: List of command-specific results
  - `command`: Command string
  - `exit_code`: Exit code
  - `stdout`: Standard output
  - `stderr`: Standard error (optional)

#### `initial_state`
- `work_items`: List of work items to create
- `workflows`: List of workflows to configure

#### `events`
Sequence of actions to perform:
- `time_offset`: When to perform action (e.g., "0s", "5m", "1h")
- `action`: Action type (move_card, advance_time, assert_event, etc.)
- `params`: Action-specific parameters

#### `expected_outcomes`
Assertions to verify:
- `events`: Expected event types and counts
- `metrics`: Expected metrics
- `notifications`: Expected notifications

## Scenario Loader

To load YAML scenarios in tests:

```python
from codetoreum.infrastructure.simulation import SimulationConfig
import yaml

def load_scenario(yaml_file: str) -> SimulationConfig:
    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    # Convert YAML to SimulationConfig
    return SimulationConfig.from_dict(data["scenario"])
```

## Best Practices

1. **Start Simple**: Begin with basic scenarios and add complexity
2. **Use Python for Complex Logic**: YAML is good for simple cases
3. **Test One Thing**: Each scenario should verify one workflow/behavior
4. **Fast by Default**: Use high speed multipliers (50-100x)
5. **Realistic Delays**: Keep execution delays realistic relative to speed
6. **Clear Assertions**: Name assertions clearly
7. **Document Scenarios**: Add descriptions explaining what's being tested

## Example Scenarios

See the `scenarios/` directory for complete Python examples:

1. **scenario_01_simple_workflow.py**: Single work item, 3 stages
2. **scenario_02_parallel_executions.py**: Multiple work items in parallel
3. **scenario_03_review_cycle.py**: Maker-checker with feedback loop
4. **scenario_04_execution_failure.py**: Agent failure and retry
5. **scenario_05_complex_workflow.py**: Multi-stage with branches

For complete documentation of all scenarios, see `SCENARIOS_COMPLETE.md`.

Each YAML scenario has a corresponding Python test in `test_scenarios.py`.
