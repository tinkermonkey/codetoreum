# Simulation Scenarios

This directory contains pre-built YAML scenario files for Codetoreum simulation testing.

## Available Scenarios

### 1. default.yaml
**Purpose**: Basic smoke testing
**Work Items**: 3
**Agents**: 3 (architect, coder, tester)
**Workflow Stages**: 3 (design, implementation, testing)
**Speed**: 10x
**Use Cases**:
- Quick validation of simulation infrastructure
- Basic workflow testing
- CI/CD smoke tests

### 2. demo.yaml
**Purpose**: Product demonstration
**Work Items**: 5
**Agents**: 5 (software architect, senior developer, code reviewer, QA engineer, security analyst)
**Workflow Stages**: 5 (architecture design, implementation, code review, testing, security scan)
**Speed**: 5x (slower for observability)
**Use Cases**:
- Demonstrating platform capabilities
- Showcasing complete feature development lifecycle
- Training and onboarding

### 3. stress_test.yaml
**Purpose**: Performance and scalability testing
**Work Items**: 10 (can be extended to 100+ programmatically)
**Agents**: 2 (worker, validator)
**Workflow Stages**: 2 (process, validate)
**Speed**: 100x (maximum speed)
**Use Cases**:
- Performance benchmarking
- Concurrent execution testing
- Resource management validation
- Scalability limits identification

### 4. review_cycle.yaml
**Purpose**: Review and feedback loop testing
**Work Items**: 5
**Agents**: 3 (coder, peer reviewer, senior reviewer)
**Workflow Stages**: 5 (implement, peer review, revise, senior review, final revise)
**Speed**: 10x
**Use Cases**:
- Testing maker-checker workflows
- Validating feedback mechanisms
- Iterative development simulation
- Code review process validation

### 5. failure_recovery.yaml
**Purpose**: Error handling and resilience testing
**Work Items**: 5
**Agents**: 4 (flaky agent, recovery agent, slow agent, error handler)
**Workflow Stages**: 4 (flaky stage, recovery stage, timeout-prone stage, error handling stage)
**Speed**: 10x
**Use Cases**:
- Testing retry mechanisms
- Validating error handling
- Chaos engineering
- Timeout behavior validation
- Recovery strategy testing

### 6. mixed_github_real.yaml
**Purpose**: Real GitHub integration with simulated agents
**Adapter Configuration**: Real GitHub + Simulated LLM/Agents
**Speed**: 10x
**Credentials Required**:
- GITHUB_TOKEN (repo, project scopes)
- GITHUB_ORG
- GITHUB_REPO
**Use Cases**:
- Testing workflow logic with real issue data
- Avoiding Claude Code API costs during testing
- Verifying GitHub integration without agent variability
- Integration testing against actual GitHub projects

### 7. mixed_full_github.yaml
**Purpose**: Real GitHub and infrastructure with simulated agents
**Adapter Configuration**: Real GitHub + Docker + Redis + PostgreSQL + Simulated LLM
**Speed**: 10x
**Credentials Required**:
- GITHUB_TOKEN, GITHUB_ORG, GITHUB_REPO
- REDIS_URL
- DATABASE_URL
- Docker daemon socket
**Use Cases**:
- Integration testing with real GitHub and complete infrastructure
- Testing container execution and database interactions
- Avoiding Claude Code API costs while testing real systems
- Production-like testing environment

### 8. mixed_full_real.yaml
**Purpose**: Complete production deployment with all real systems
**Adapter Configuration**: All Real Systems (GitHub, Claude Code API, Docker, AWS S3, Redis, PostgreSQL, Slack)
**Speed**: 1x (real-time, no acceleration)
**Credentials Required**:
- GITHUB_TOKEN, GITHUB_ORG, GITHUB_REPO
- CLAUDE_CODE_API_KEY
- Docker daemon socket
- AWS credentials (S3)
- Redis URL
- PostgreSQL connection
- Slack bot token
**Use Cases**:
- Production deployment and testing
- End-to-end testing with real services
- Performance and load testing
- Chaos engineering with real external systems

## Usage

### Loading a Scenario (Programmatic)

```python
from codetoreum.infrastructure.simulation import (
    SimulationApplicationBootstrap,
    SimulationDataSeeder,
)

# Setup bootstrap
bootstrap = SimulationApplicationBootstrap()
await bootstrap.setup()

# Create seeder
seeder = SimulationDataSeeder(bootstrap)

# Load scenario
await seeder.seed_from_yaml("scenarios/default.yaml")
```

### Loading a Scenario (CLI)

```bash
# Start simulation server with scenario
python -m codetoreum.cli.simulation_server \
    --scenario scenarios/demo.yaml \
    --host 0.0.0.0 \
    --port 8000
```

### Using Pre-built Methods

Instead of YAML, you can use pre-built scenario methods:

```python
# Default scenario
await seeder.seed_default_scenario()

# Simple workflow
await seeder.seed_simple_workflow()

# Parallel workflow
await seeder.seed_parallel_workflow()

# Review cycle
await seeder.seed_review_cycle()

# Failure scenario
await seeder.seed_failure_scenario()
```

## Important Notes on Adapter Configuration

### Adapter Field Names
All mixed scenario files use adapter configuration sections that define which implementations to use for each adapter slot. The correct field names must match the `AdapterSelectionConfig` dataclass fields in `simulation_config.py`. Common field names:

- `discussion_adapter` (NOT `discussion`)
- `board`, `ticket`, `llm`, `container`
- `event_store`, `message_broker`, `lock_service`
- `config_store`, `storage`, `metrics`
- `review_cycle`, `repair_cycle`, etc.

**Important**: If you use an incorrect field name (e.g., `discussion` instead of `discussion_adapter`), the configuration will raise a clear `ValueError` with a list of valid field names.

### Unregistered Adapter Implementations
If you specify an adapter implementation that is not registered (e.g., `event_store: vault` when Vault adapter is not available), the system will raise an `AdapterConfigurationError` during bootstrap with a helpful message indicating which adapter is unknown.

## Creating Custom Scenarios

### YAML Schema

```yaml
name: "Scenario Name"
description: "Scenario description"
version: "1.0"

# Simulation settings
speed_multiplier: 10.0
auto_advance: false

# Projects
projects:
  - name: "project-name"
    description: "Project description"
    repository_url: "https://github.com/org/repo.git"  # Optional
    default_branch: "main"
    metadata: {}

# Workflows
workflows:
  - name: "workflow-name"
    description: "Workflow description"
    stages:
      - name: "stage-name"
        agent_type: "agent-type"
        description: "Stage description"
        order: 1
        max_retries: 3
        timeout_seconds: 3600
        entry_conditions: {}
        exit_conditions: {}

# Agents
agents:
  - name: "agent-name"
    agent_type: "agent-type"
    description: "Agent description"
    capabilities:
      - "code_generation"
      - "code_review"
    llm_model: "claude-sonnet-4-5-20250929"
    temperature: 0.7
    max_tokens: 4096
    system_prompt: ""
    enabled: true
    metadata: {}

# Work Items
work_items:
  - title: "Work item title"
    description: "Work item description"
    labels: []
    priority: "medium"  # low, medium, high, critical
    status: "new"       # new, assigned, in_progress, under_review, completed, failed, blocked
    metadata: {}

# Additional metadata
metadata:
  scenario_type: "custom"
  author: "your-name"
  tags: []
```

### Validation

Scenarios are validated using Pydantic models. Common validation errors:

- **Missing required fields**: `name` is required
- **Invalid priority**: Must be one of: low, medium, high, critical
- **Invalid status**: Must be one of: new, assigned, in_progress, under_review, completed, failed, blocked
- **Invalid capabilities**: Must be valid capability types
- **Duplicate names**: Project, workflow, and agent names must be unique
- **Stage order**: Must be sequential 1, 2, 3, ...

### Performance Guidelines

**Speed Multiplier Recommendations**:
- `1.0` - Real-time (for debugging)
- `5.0` - Slow motion (for demos)
- `10.0` - Default (good balance)
- `50.0` - Fast (for integration tests)
- `100.0` - Maximum (for stress tests)

**Work Item Limits**:
- Small scenario: 1-10 items
- Medium scenario: 10-50 items
- Large scenario: 50-100 items
- Stress test: 100+ items (use programmatic creation)

## Testing Scenarios

Run unit tests for scenario loading:

```bash
pytest tests/unit/infrastructure/simulation/test_seeding.py -v
```

Run integration tests:

```bash
pytest tests/integration/simulation/test_scenario_loading.py -v
```

## Troubleshooting

**Error: "Scenario file not found"**
- Check file path is correct
- Use absolute path or path relative to working directory

**Error: "Scenario validation failed"**
- Check YAML syntax (use YAML linter)
- Verify all required fields are present
- Check field values match valid options

**Error: "No project context"**
- Ensure at least one project is defined in the scenario
- Projects must be created before workflows, agents, and work items

**Performance Issues**
- Reduce work item count
- Increase speed multiplier
- Simplify workflow stages
- Reduce max_tokens for agents

## Contributing

To add a new scenario:

1. Create YAML file in `scenarios/` directory
2. Follow the schema documented above
3. Test with validation: `await seeder.seed_from_yaml("scenarios/your_scenario.yaml")`
4. Add description to this README
5. Submit pull request

## License

All scenario files are part of the Codetoreum project and follow the same license.
