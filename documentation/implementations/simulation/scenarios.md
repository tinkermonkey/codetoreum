# Simulation Scenarios: Complete Catalog and Reference

Complete catalog of all 10 scenario directories and 80 YAML configuration files used for deterministic testing of the Codetoreum platform.

## Overview

Simulation scenarios are YAML-based configurations that define:
- **Projects**: Repositories and organizational context
- **Workflows**: Multi-stage pipelines with entry/exit conditions
- **Agents**: AI agents with capabilities and models
- **Work Items**: Issues/tickets to be processed
- **Board State**: Kanban board structure and automation rules

Each scenario directory contains 8 YAML files organized in two subdirectories:
- **external/**: External system definitions (projects, board structure, work items)
- **orchestrator/**: Orchestrator configuration (workflows, agents, simulation settings)

## Scenario Directories (10 Total)

### 1. `smoke`

**Purpose**: Lightweight smoke test for rapid validation

**YAML Files** (8 total):
- `external/projects.yaml` — Basic test project
- `external/board_structure.yaml` — Simple Kanban board (3 columns)
- `external/board_placements.yaml` — Initial work item placement
- `external/work_items.yaml` — 2-3 test items
- `orchestrator/workflows.yaml` — Single simple workflow
- `orchestrator/agents.yaml` — 1-2 basic agents
- `orchestrator/board_policy.yaml` — No automation rules
- `orchestrator/simulation.yaml` — Configuration (speed=10x, auto_advance=false)

**Execution**: < 5 seconds real-time

**Use Cases**:
- CI/CD pipeline smoke tests
- Quick validation after code changes
- Demo of basic workflow

**Location**: `scenarios/smoke/`

---

### 2. `sdlc_pipeline`

**Purpose**: Complete software development lifecycle simulation

**YAML Files** (8 total):
- `external/projects.yaml` — Realistic project setup
- `external/board_structure.yaml` — Full SDLC Kanban (Design → Implementation → Review → Testing → Done)
- `external/board_placements.yaml` — Work items in pipeline
- `external/work_items.yaml` — 5-10 realistic features/bugs
- `orchestrator/workflows.yaml` — Multi-stage SDLC workflow
- `orchestrator/agents.yaml` — Specialist agents (architect, coder, reviewer, tester)
- `orchestrator/board_policy.yaml` — Automation: auto-promote on completion
- `orchestrator/simulation.yaml` — Configuration (speed=10x)

**Execution**: 10-30 seconds real-time

**Use Cases**:
- Full workflow validation
- Multi-agent coordination testing
- Board automation verification
- Feature development simulation

**Location**: `scenarios/sdlc_pipeline/`

---

### 3. `review_cycle`

**Purpose**: Code review and feedback loop simulation

**YAML Files** (8 total):
- `external/projects.yaml` — Code review project
- `external/board_structure.yaml` — Review-focused board (Develop → Review → Revise → Approved)
- `external/board_placements.yaml` — Initial code submissions
- `external/work_items.yaml` — 5 code items awaiting review
- `orchestrator/workflows.yaml` — Review cycle workflow with feedback loops
- `orchestrator/agents.yaml` — Coder, reviewer, feedback processor
- `orchestrator/board_policy.yaml` — Review automation rules
- `orchestrator/simulation.yaml` — Configuration (speed=5x for slower observation)

**Execution**: 15-40 seconds real-time

**Use Cases**:
- Maker-checker workflow validation
- Feedback iteration testing
- Review cycle process validation
- Approval workflow verification

**Location**: `scenarios/review_cycle/`

---

### 4. `failure_recovery`

**Purpose**: Error handling, resilience, and recovery testing

**YAML Files** (8 total):
- `external/projects.yaml` — Resilience test project
- `external/board_structure.yaml` — Recovery-aware board (Failed → Retry → Recovery → Complete)
- `external/board_placements.yaml` — Intentional failures for testing
- `external/work_items.yaml` — 5-7 items with expected failures
- `orchestrator/workflows.yaml` — Multi-retry workflow with fallbacks
- `orchestrator/agents.yaml` — Flaky agent (intentional failures), recovery agent
- `orchestrator/board_policy.yaml` — Retry and recovery rules
- `orchestrator/simulation.yaml` — Configuration (speed=10x)

**Execution**: 20-50 seconds real-time

**Use Cases**:
- Circuit breaker testing
- Retry mechanism validation
- Error recovery procedures
- Resilience pattern verification
- Failure classification testing

**Location**: `scenarios/failure_recovery/`

---

### 5. `repair_cycle_test`

**Purpose**: Repair cycle and test-fix-validate loops

**YAML Files** (8 total):
- `external/projects.yaml` — Testing/repair project
- `external/board_structure.yaml` — Repair cycle board (Bug → Fix → Test → Validated)
- `external/board_placements.yaml` — Issues in repair process
- `external/work_items.yaml` — 5-8 bugs with fix iterations
- `orchestrator/workflows.yaml` — Repair cycle workflow with test validation
- `orchestrator/agents.yaml` — Bug analyst, developer, QA tester
- `orchestrator/board_policy.yaml` — Repair cycle automation
- `orchestrator/simulation.yaml` — Configuration (speed=10x)

**Execution**: 20-45 seconds real-time

**Use Cases**:
- Bug tracking workflow
- Test-fix validation loops
- Repair cycle automation
- Quality assurance process testing
- Defect tracking validation

**Location**: `scenarios/repair_cycle_test/`

---

### 6. `stress_test`

**Purpose**: Performance and scalability testing with high concurrency

**YAML Files** (8 total):
- `external/projects.yaml` — Large-scale project
- `external/board_structure.yaml` — Minimal board (Quick Process → Done)
- `external/board_placements.yaml` — 100+ work items
- `external/work_items.yaml` — 50-100 identical/similar items
- `orchestrator/workflows.yaml` — Simple, fast workflow
- `orchestrator/agents.yaml` — Minimal agents (1-2) for throughput
- `orchestrator/board_policy.yaml` — No complex rules
- `orchestrator/simulation.yaml` — Configuration (speed=100x, max speed)

**Execution**: 5-15 seconds real-time (100x faster)

**Use Cases**:
- Performance benchmarking
- Concurrency testing
- Throughput measurement
- Queue behavior under load
- Resource utilization testing
- Scalability limits identification

**Location**: `scenarios/stress_test/`

---

### 7. `planning_design_pipeline`

**Purpose**: Design phase and planning workflow

**YAML Files** (8 total):
- `external/projects.yaml` — Design project
- `external/board_structure.yaml` — Planning board (Ideate → Design → Approve → Ready for Dev)
- `external/board_placements.yaml` — Designs in process
- `external/work_items.yaml` — 5-8 design items
- `orchestrator/workflows.yaml` — Design workflow with approval gates
- `orchestrator/agents.yaml` — Product manager, UX designer, tech lead
- `orchestrator/board_policy.yaml` — Design approval automation
- `orchestrator/simulation.yaml` — Configuration (speed=5x)

**Execution**: 15-40 seconds real-time

**Use Cases**:
- Design workflow validation
- Planning process testing
- Approval workflow verification
- Requirements gathering automation
- Design review cycle testing

**Location**: `scenarios/planning_design_pipeline/`

---

### 8. `planning_design_review_cycle`

**Purpose**: Planning, design, and code review integration

**YAML Files** (8 total):
- `external/projects.yaml` — Full-stack project
- `external/board_structure.yaml` — Extended board (Plan → Design → Code → Review → Done)
- `external/board_placements.yaml` — Items at various stages
- `external/work_items.yaml` — 8-12 cross-functional items
- `orchestrator/workflows.yaml` — Multi-phase workflow with cross-stage transitions
- `orchestrator/agents.yaml` — Product, design, dev, review specialists
- `orchestrator/board_policy.yaml` — Cross-stage automation rules
- `orchestrator/simulation.yaml` — Configuration (speed=8x)

**Execution**: 25-60 seconds real-time

**Use Cases**:
- End-to-end feature development
- Multi-team coordination
- Cross-functional workflow testing
- Stage transition automation
- Handoff process validation

**Location**: `scenarios/planning_design_review_cycle/`

---

### 9. `pr_feedback_child_issue`

**Purpose**: PR feedback and child issue creation

**YAML Files** (8 total):
- `external/projects.yaml` — Multi-component project
- `external/board_structure.yaml` — PR-centric board (PR Open → Reviewed → Feedback → Child Issues)
- `external/board_placements.yaml` — PRs and related issues
- `external/work_items.yaml` — 5 PRs with associated child issues
- `orchestrator/workflows.yaml` — PR feedback workflow with child issue creation
- `orchestrator/agents.yaml` — Reviewer, implementer, QA for feedback items
- `orchestrator/board_policy.yaml` — PR automation and child issue rules
- `orchestrator/simulation.yaml` — Configuration (speed=8x)

**Execution**: 20-50 seconds real-time

**Use Cases**:
- PR feedback automation
- Child issue generation testing
- Dependency tracking validation
- Feedback loop implementation testing
- Multi-issue coordination

**Location**: `scenarios/pr_feedback_child_issue/`

---

### 10. `dev_environment_repair`

**Purpose**: Development environment issues and recovery

**YAML Files** (8 total):
- `external/projects.yaml` — Development infrastructure project
- `external/board_structure.yaml` — Ops board (Incident → Diagnose → Fix → Verify → Resolved)
- `external/board_placements.yaml` — Environment issues
- `external/work_items.yaml` — 5-8 environment/infrastructure issues
- `orchestrator/workflows.yaml` — Environment repair workflow
- `orchestrator/agents.yaml` — DevOps engineer, SRE, developer
- `orchestrator/board_policy.yaml` — Incident response automation
- `orchestrator/simulation.yaml` — Configuration (speed=10x)

**Execution**: 15-40 seconds real-time

**Use Cases**:
- Incident response automation
- Environment recovery testing
- Dependency resolution
- Infrastructure issue handling
- Incident classification and repair

**Location**: `scenarios/dev_environment_repair/`

---

## YAML File Structure

### External Directory Files

#### `projects.yaml`
**Purpose**: Define external projects and repositories

```yaml
projects:
  - name: "test-project"
    description: "Test project description"
    repository_url: "https://github.com/org/repo.git"
    default_branch: "main"
    metadata:
      team: "platform"
      environment: "test"
```

**Fields**:
- `name`: Project identifier (required)
- `description`: Human-readable description
- `repository_url`: Git repository URL (optional)
- `default_branch`: Default branch for operations
- `metadata`: Custom key-value pairs

---

#### `board_structure.yaml`
**Purpose**: Define Kanban board structure

```yaml
boards:
  - name: "project-board"
    description: "Workflow board"
    columns:
      - name: "Design"
        order: 1
        is_start_column: true
      - name: "Implementation"
        order: 2
      - name: "Review"
        order: 3
      - name: "Testing"
        order: 4
      - name: "Done"
        order: 5
        is_end_column: true
```

**Fields**:
- `boards[].name`: Board name
- `boards[].columns[].name`: Column name
- `boards[].columns[].order`: Display order (1-based)
- `boards[].columns[].is_start_column`: Initial column for new items
- `boards[].columns[].is_end_column`: Terminal column

---

#### `board_placements.yaml`
**Purpose**: Initial work item placements on board

```yaml
placements:
  - work_item: "issue-1"
    board: "project-board"
    column: "Design"
  - work_item: "issue-2"
    board: "project-board"
    column: "Implementation"
```

**Fields**:
- `placements[].work_item`: Work item identifier
- `placements[].board`: Target board name
- `placements[].column`: Target column name

---

#### `work_items.yaml`
**Purpose**: Define work items (issues/tickets)

```yaml
work_items:
  - id: "issue-1"
    title: "Implement feature X"
    description: "Detailed description"
    priority: "high"          # low, medium, high, critical
    status: "new"             # new, assigned, in_progress, etc.
    labels: ["feature", "backend"]
    metadata:
      effort: "5"
      owner: "team-platform"
```

**Fields**:
- `id`: Unique work item identifier
- `title`: Work item title (required)
- `description`: Detailed description
- `priority`: Priority level
- `status`: Current status
- `labels`: List of tags
- `metadata`: Custom fields

---

### Orchestrator Directory Files

#### `workflows.yaml`
**Purpose**: Define multi-stage workflows

```yaml
workflows:
  - name: "sdlc-workflow"
    description: "Standard SDLC workflow"
    stages:
      - name: "design"
        agent_type: "architect"
        order: 1
        max_retries: 3
        timeout_seconds: 3600
        entry_conditions:
          status: "new"
        exit_conditions:
          status: "designed"
      - name: "implementation"
        agent_type: "coder"
        order: 2
        max_retries: 5
        timeout_seconds: 7200
```

**Fields**:
- `workflows[].name`: Workflow name (required)
- `workflows[].stages[].name`: Stage name
- `workflows[].stages[].agent_type`: Agent type to assign
- `workflows[].stages[].order`: Execution order
- `workflows[].stages[].max_retries`: Retry count
- `workflows[].stages[].timeout_seconds`: Time limit
- `workflows[].stages[].entry_conditions`: Activation conditions
- `workflows[].stages[].exit_conditions`: Completion conditions

---

#### `agents.yaml`
**Purpose**: Define AI agents and their capabilities

```yaml
agents:
  - name: "architect"
    agent_type: "architect"
    description: "Software architect"
    capabilities:
      - "system_design"
      - "architecture_review"
    coding_agent: "claude-code"
    invocation:
      mode: "containerized"          # or "host" / "api"; validated against adapter.supported_invocation_modes()
      model: "claude-sonnet-4-6"
      timeout_seconds: 3600
      mode_config:
        image: "codetoreum-agent:latest"
        cpu_limit: "2"
        memory_limit: "4g"
    system_prompt: "You are a software architect..."
    enabled: true
    metadata:
      expertise_level: "senior"
```

**Fields**:
- `agents[].name`: Agent identifier
- `agents[].agent_type`: Type for matching to stages
- `agents[].capabilities`: List of capabilities
- `agents[].coding_agent`: Registered coding-agent adapter (e.g. `"claude-code"`). Replaces the retired `llm_provider` slot (DEF-015 D5).
- `agents[].invocation.mode`: One of `containerized`, `host`, `api`. Validated against the adapter's `supported_invocation_modes()` at config load — errors at load, not first execution. Replaces the retired `requires_docker` flag.
- `agents[].invocation.model`: Model identifier passed to the coding agent
- `agents[].invocation.timeout_seconds`: Per-execution timeout
- `agents[].invocation.mode_config`: Mode-specific settings (image/cpu/memory for containerized; ignored for host/api)
- `agents[].system_prompt`: Agent instructions
- `agents[].enabled`: Whether agent is active
- `agents[].metadata`: Custom attributes

---

#### `board_policy.yaml`
**Purpose**: Define board automation rules

```yaml
policies:
  - name: "auto-promote-completed"
    trigger: "work_item_completed"
    conditions:
      current_column: "implementation"
    actions:
      - type: "move_to_column"
        target_column: "review"
      - type: "assign_agent"
        agent_type: "reviewer"

  - name: "escalate-blocked"
    trigger: "work_item_blocked"
    conditions:
      current_column: "implementation"
      blocked_duration_minutes: 30
    actions:
      - type: "add_label"
        label: "escalated"
      - type: "notify"
        recipients: ["team-lead"]
```

**Fields**:
- `policies[].name`: Policy name
- `policies[].trigger`: Event that triggers policy
- `policies[].conditions`: Conditions to match
- `policies[].actions`: Actions to execute (move, assign, notify, etc.)

---

#### `simulation.yaml`
**Purpose**: Configure simulation behavior

```yaml
name: "sdlc-scenario"
description: "Standard SDLC workflow test"
version: "1.0"

# Simulation settings
speed_multiplier: 10.0
auto_advance: false
auto_advance_interval_seconds: 30

# Optional: override adapter selections
# Note: the `llm_provider` and `storage` slots retired in DEF-015 D5; the
# simulation bootstrap hard-wires MockClaudeCodeAdapter into the coding_agent
# slot, so scenarios do not configure it here.
adapters:
  ticket_system: "in_memory"
  container: "fake"
  board: "mock"
  event_store: "in_memory"

# Optional: seeding configuration
seeding:
  delay_between_work_items_ms: 100
  random_seed: 42
```

**Fields**:
- `name`: Scenario name (required)
- `description`: Scenario description
- `version`: Configuration version
- `speed_multiplier`: Time acceleration (1.0-100.0)
- `auto_advance`: Whether to auto-advance time
- `auto_advance_interval_seconds`: Advance interval
- `adapters`: Override default adapter selections
- `seeding`: Data seeding configuration

---

## Loading and Running Scenarios

### Programmatic Loading

```python
from codetoreum.infrastructure.simulation import (
    SimulationApplicationBootstrap,
    SimulationRunner,
)
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

# Load scenario from YAML
config = SimulationConfig.from_yaml("scenarios/sdlc_pipeline/orchestrator/simulation.yaml")

# Create runner
runner = SimulationRunner(config)

# Define test logic
async def scenario(sim):
    # Access adapters
    ticket_adapter = sim.adapters.ticket_as_mock()

    # Run scenario
    await sim.advance_time(timedelta(minutes=10))

    # Make assertions
    sim.assert_event_occurred("WorkItemColumnChanged")
    assert len(sim.adapters.event_emitter.captured_events) > 0

# Execute
result = await runner.run(scenario)
```

### CLI Loading

```bash
# Start simulation server with scenario
python -m codetoreum.cli.simulation_server \
    --scenario scenarios/sdlc_pipeline/orchestrator/simulation.yaml \
    --host 0.0.0.0 \
    --port 8000
```

### Test Integration

```python
import pytest

@pytest.mark.asyncio
async def test_sdlc_pipeline_workflow():
    """Test complete SDLC pipeline."""
    config = SimulationConfig.from_yaml("scenarios/sdlc_pipeline/orchestrator/simulation.yaml")
    runner = SimulationRunner(config)

    async def scenario(sim):
        # Test workflow execution
        await sim.advance_time(timedelta(minutes=30))
        # Assertions...

    result = await runner.run(scenario)
    assert result.success
```

---

## Scenario Configuration Best Practices

### Speed Multiplier Selection

| Scenario Type | Recommended | Reason |
|---|---|---|
| Smoke test | 100x | Fast validation |
| Feature demo | 5x | Observable progress |
| Integration test | 10x | Balance speed/visibility |
| Stress test | 100x | Maximum throughput |
| Debugging | 1x | Real-time observation |

### Work Item Counts

| Count | Use Case | Duration |
|---|---|---|
| 1-3 | Smoke tests | < 5s |
| 5-10 | Feature workflows | 10-30s |
| 20-50 | Complex scenarios | 30-120s |
| 50-100+ | Stress tests | 5-30s (100x) |

### Agent Configuration

```yaml
agents:
  - name: "fast-agent"          # For smoke tests
    coding_agent: "claude-code"
    invocation:
      mode: "host"              # No container overhead
      model: "claude-sonnet-4-6"
      timeout_seconds: 60

  - name: "thorough-agent"      # For feature tests
    coding_agent: "claude-code"
    invocation:
      mode: "containerized"
      model: "claude-sonnet-4-6"
      timeout_seconds: 1800
      mode_config:
        image: "codetoreum-agent:latest"

  - name: "heavy-agent"         # For stress tests
    coding_agent: "claude-code"
    invocation:
      mode: "containerized"
      model: "claude-opus-4-5"
      timeout_seconds: 3600
      mode_config:
        image: "codetoreum-agent:latest"
        cpu_limit: "4"
        memory_limit: "8g"
```

Note: per-agent temperature / max_tokens tuning is the coding-agent adapter's concern, not the orchestrator's — those parameters are passed via `invocation.mode_config` when the adapter exposes them.

---

## Scenario Format Reference

### Validation Rules

**Projects**:
- `name` is required and must be unique
- `repository_url` must be valid Git URL if provided

**Workflows**:
- `name` is required and must be unique
- Stages must have sequential `order` (1, 2, 3, ...)
- `timeout_seconds` must be positive

**Agents**:
- `name` is required and must be unique
- `agent_type` must match workflow stage agent_type
- `coding_agent` must resolve to a registered adapter (e.g. `"claude-code"`)
- `invocation.mode` must be in the adapter's `supported_invocation_modes()`
- `invocation.model` must be a model the adapter accepts
- `invocation.timeout_seconds` must be positive

**Work Items**:
- `id` is required and must be unique
- `title` is required (non-empty)
- `priority` must be: low, medium, high, critical
- `status` must be valid status value

**Board Structure**:
- Column `order` must be sequential (1, 2, 3, ...)
- Exactly one `is_start_column` required
- Exactly one `is_end_column` required

---

## Testing Scenarios with Examples

### Example: Smoke Test Execution

```bash
# Run smoke scenario
pytest tests/simulation/test_scenarios.py::test_smoke_scenario -v

# Expected output:
# - 2-3 work items processed
# - Completion in < 5 seconds
# - All assertions pass
```

### Example: SDLC Pipeline Execution

```bash
# Run full SDLC pipeline
pytest tests/simulation/test_scenarios.py::test_sdlc_pipeline -v

# Expected output:
# - 8-10 work items processed through 5 stages
# - Multi-agent coordination working
# - Board automation firing correctly
# - Completion in 10-30 seconds
```

### Example: Stress Test Execution

```bash
# Run stress test with 100 items
pytest tests/simulation/test_scenarios.py::test_stress_scenario -v

# Expected output:
# - 100+ work items processed
# - High throughput verified
# - Concurrency handling validated
# - Completion in 5-15 seconds (100x speed)
```

---

## Adding New Scenarios

To create a new scenario:

1. **Create directory**: `scenarios/your_scenario/`
2. **Create subdirectories**: `external/` and `orchestrator/`
3. **Create 8 YAML files** (see templates above)
4. **Validate YAML** syntax and schema
5. **Test scenario** programmatically:

```python
config = SimulationConfig.from_yaml("scenarios/your_scenario/orchestrator/simulation.yaml")
runner = SimulationRunner(config)
result = await runner.run(scenario)
assert result.success
```

6. **Update this README** with scenario description
7. **Commit scenario** to repository

---

## Directory Layout

```
scenarios/
├── smoke/
│   ├── external/
│   │   ├── projects.yaml
│   │   ├── board_structure.yaml
│   │   ├── board_placements.yaml
│   │   └── work_items.yaml
│   └── orchestrator/
│       ├── workflows.yaml
│       ├── agents.yaml
│       ├── board_policy.yaml
│       └── simulation.yaml
├── sdlc_pipeline/
│   ├── external/
│   │   ├── projects.yaml
│   │   ├── board_structure.yaml
│   │   ├── board_placements.yaml
│   │   └── work_items.yaml
│   └── orchestrator/
│       ├── workflows.yaml
│       ├── agents.yaml
│       ├── board_policy.yaml
│       └── simulation.yaml
├── review_cycle/
├── failure_recovery/
├── repair_cycle_test/
├── stress_test/
├── planning_design_pipeline/
├── planning_design_review_cycle/
├── pr_feedback_child_issue/
└── dev_environment_repair/
```

---

## Scenario Statistics

| Scenario | Items | Stages | Agents | Duration | Speed |
|---|---|---|---|---|---|
| smoke | 3 | 3 | 2 | 5s | 10x |
| sdlc_pipeline | 10 | 5 | 4 | 20s | 10x |
| review_cycle | 5 | 4 | 3 | 25s | 5x |
| failure_recovery | 7 | 4 | 3 | 30s | 10x |
| repair_cycle_test | 8 | 4 | 3 | 25s | 10x |
| stress_test | 100 | 2 | 2 | 10s | 100x |
| planning_design_pipeline | 8 | 4 | 3 | 20s | 5x |
| planning_design_review | 12 | 5 | 4 | 40s | 8x |
| pr_feedback_child_issue | 5 | 5 | 4 | 35s | 8x |
| dev_environment_repair | 8 | 5 | 3 | 25s | 10x |

**Total Scenarios**: 10
**Total YAML Files**: 80 (8 per scenario)
**Total Work Items**: ~70
**Total Agents**: ~30
**Total Workflows**: ~10

---

## See Also

- [Overview](./overview.md) — Simulation implementation overview
- [Adapters Reference](./adapters.md) — Complete adapter listing
- [Bootstrap Wiring](./bootstrap-wiring.md) — Bootstrap sequence
- [Architecture: Domain](../../architecture/domain/) — Domain models
- [Scenario Format Guide](../../templates/) — YAML schema documentation
