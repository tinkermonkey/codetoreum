# YAML Scenario Configuration Reference

**Updated**: 2026-03-20

## Flexible YAML Key Support

The `SimulationConfig.from_yaml()` method now supports flexible key naming to accommodate different YAML formats.

### Supported Key Variants

#### Speed Multiplier (Time Configuration)

Both of these are equivalent:

```yaml
# Top-level format
name: my_scenario
speed_multiplier: 10.0

# Nested under simulation: format
name: my_scenario
simulation:
  speed_multiplier: 10.0
  auto_advance: false
  start_time: null
```

#### Fidelity Level

Both of these are equivalent:

```yaml
# Using 'fidelity_level' key
fidelity_level: medium

# Using 'fidelity' key (shorter)
fidelity: medium

# Values are normalized to lowercase
fidelity: MEDIUM  # becomes → medium
fidelity: HIGH    # becomes → high
```

#### Container Configuration

Both of these are equivalent:

```yaml
# Singular form (standard)
container:
  default_exit_code: 0
  execution_delay: 0.1

# Plural form (also supported)
containers:
  default_exit_code: 0
  execution_delay: 0.1
```

#### Agents Configuration

Both of these are equivalent:

```yaml
# Dict format (agent_id as key)
agents:
  reviewer:
    execution_delay: 0.2
    success_rate: 0.95
  analyzer:
    execution_delay: 0.15
    success_rate: 0.98

# List-of-objects format (agent_id in object)
agents:
  - agent_id: reviewer
    execution_delay: 0.2
    success_rate: 0.95
  - agent_id: analyzer
    execution_delay: 0.15
    success_rate: 0.98
```

## Complete YAML Example

```yaml
# Scenario name (required)
name: complete_scenario
description: Complete simulation scenario with all options

# Time configuration (supports both top-level and nested formats)
simulation:
  speed_multiplier: 20.0
  auto_advance: false
  start_time: null

# Fidelity level (supports both 'fidelity' and 'fidelity_level', case-insensitive)
fidelity: MEDIUM

# Timing parameters
ms_per_token: 75.0
ms_per_file_operation: 15.0
ms_per_event: 2.5
event_handler_count: 2

# Adapter configuration
adapters:
  board: github
  ticket: github
  llm: mock
  container: fake
  version_control: in_memory
  event_store: in_memory
  storage: in_memory
  metrics: in_memory
  config_store: in_memory
  notifier: mock
  encryption: simple
  discussion_adapter: mock
  review_cycle: mock
  repair_cycle: mock
  code_review: mock
  project_manager: mock
  lock_service: in_memory
  workflow_config: in_memory
  queue_service: in_memory
  event_emitter: capturing
  message_broker: in_memory
  identity_service: configurable
  checkpoint_store: in_memory
  agent_repository: in_memory
  run_registry: in_memory
  branch_tracker: in_memory
  work_item_service: mock
  repository: in_memory
  container_recovery: mock

# Agent configuration (supports both dict and list-of-objects formats)
agents:
  - agent_id: reviewer
    execution_delay: 0.2
    success_rate: 0.95
    response_patterns:
      code_review: "Code review completed"
    token_usage:
      input: 100
      output: 50
  - agent_id: analyzer
    execution_delay: 0.15
    success_rate: 0.98

# Container configuration (supports both 'container' and 'containers' keys)
container:
  default_exit_code: 0
  execution_delay: 0.1
  command_exit_codes:
    pytest: 0
    npm test: 0
  command_outputs:
    pytest:
      stdout: "===== 42 passed in 0.12s ====="
      stderr: ""

# Notification configuration
notifications:
  send_delay: 0.01
  simulate_failures: false
  failure_rate: 0.0

# Metrics configuration
metrics:
  enabled: true
  tracked_metrics:
    - workflow.stage.duration
    - agent.execution.count

# Metadata
metadata:
  project_id: my_project
  environment: test
```

## Migration Guide

If you have existing YAML scenario files, they will continue to work unchanged. However, you can now use alternative key names:

### Old Format (Still Works)

```yaml
name: scenario_v1
speed_multiplier: 10.0
fidelity_level: low
container:
  default_exit_code: 0
agents:
  agent_id: my_agent
    execution_delay: 0.1
```

### New Format (Also Works Now)

```yaml
name: scenario_v2
simulation:
  speed_multiplier: 10.0
fidelity: LOW
containers:
  default_exit_code: 0
agents:
  - agent_id: my_agent
    execution_delay: 0.1
```

## Known Limitations

### Adapter Registration

Some scenarios reference adapters that are not yet implemented. See `documentation/01_design/adapters/ADAPTER_REGISTRATION_STATUS.md` for details.

**Affected Scenarios**:
- `mixed_full_github.yaml` - Redis adapters not implemented
- `mixed_full_real.yaml` - Multiple production adapters not implemented

**Impact**: YAML parsing succeeds, but adapter instantiation will fail at runtime with `AdapterConfigurationError`.

## Testing

To verify your YAML scenario files can be loaded:

```bash
# Python code
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

config = SimulationConfig.from_yaml("scenarios/my_scenario.yaml")
print(f"Loaded: {config.scenario_name}")
print(f"Speed: {config.time.speed_multiplier}x")
print(f"Fidelity: {config.fidelity_level.value}")
print(f"Agents: {list(config.agents.keys())}")
```

```bash
# Pytest
python -m pytest tests/unit/infrastructure/simulation/test_load_actual_scenario_files.py -v
```

## Code References

- **YAML Loading**: `src/codetoreum/infrastructure/simulation/simulation_config.py:599-730`
- **Configuration Parsing**: `src/codetoreum/infrastructure/simulation/simulation_config.py:507-596`
- **Tests**: `tests/unit/infrastructure/simulation/test_simulation_config.py:757-830`
- **Scenario File Tests**: `tests/unit/infrastructure/simulation/test_load_actual_scenario_files.py`

## Related Issues

- #474 - YAML Scenario Configuration Parsing (RESOLVED)
- #478 - Adapter Resolver Credential Validation
- #476 - CLI Simulation Server
