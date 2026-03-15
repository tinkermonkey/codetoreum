# Codetoreum - AI Agent Orchestration Platform

## Project Overview

Codetoreum is an AI agent orchestration platform that automates software development workflows using specialized AI agents. The system integrates with GitHub for work item management and uses Claude Code for agent execution in containerized environments.

**IMPORTANT**: Design documentation for the Gen 2 architecture is located in the `documentation/01_design/` directory. If a specific design document was not specified for a task, refer to that directory for the relevant design details.

## Architecture

**Gen 2 Design**: Hexagonal Architecture with Event Sourcing

### Layers
- **Domain Layer**: Pure business logic (WorkItem, Agent, Workflow, etc.) - NO external dependencies
- **Application Layer**: Orchestration services (WorkflowOrchestrator, ExecutionService, etc.)
- **Ports**: Clean interfaces between core and external systems
- **Adapters**: Swappable implementations (production + mock/simulation)
- **Infrastructure**: Cross-cutting concerns (resilience, event bus, observability)

### Event-Driven Architecture
- **Domain Events**: Immutable records of state changes (WorkItemColumnChangedEvent, etc.)
- **Event Bus**: Pub/sub infrastructure for event distribution
- **Event Emission**: Adapters emit events for external system changes
- **Event Store**: Redis-based persistence for complete audit trail and replay

## Key Design Principles

1. **Testability**: Full end-to-end testing without external services via simulation mode
2. **Observability**: Event sourcing provides complete audit trail
3. **Extensibility**: Plugin architecture for ticket systems and LLM providers
4. **Vendor-Agnostic**: Abstract interfaces hide external system details
5. **Immutability**: Events are immutable (frozen dataclasses) for audit integrity

## Project Structure

```
codetoreum/
├── documentation/01_design/    # Gen 2 design specifications
│   ├── domains/                # Domain model designs
│   ├── application_services/   # Orchestration service designs
│   ├── input_ports/            # Inbound port interfaces
│   ├── output_ports/           # Outbound port interfaces
│   ├── events/                 # Domain event catalog
│   └── infrastructure/         # Cross-cutting infrastructure
├── scenarios/                  # Simulation scenario YAML definitions
└── src/
    ├── domain/                 # Core business logic (pure)
    │   ├── events/             # Domain events (immutable)
    │   └── services/           # Domain services
    ├── application/            # Application services + event handlers
    ├── ports/                  # Port interfaces
    │   ├── input/              # Inbound ports (commands, queries, services)
    │   └── output/             # Outbound ports (28+ interfaces)
    ├── adapters/               # Adapter implementations
    │   ├── primary/            # FastAPI app, REST routers, webhook adapter
    │   │   └── input_port_adapters/mock/  # Mock implementations of all input ports
    │   ├── secondary/          # GitHub, Docker, Claude, Redis, Elasticsearch
    │   └── testing/            # ~25 mock/in-memory adapters for simulation
    ├── config/                 # Configuration management
    ├── cli/                    # CLI commands (simulation server, YAML import)
    └── infrastructure/         # Cross-cutting concerns
        ├── event_bus.py        # Event distribution
        ├── resilience/         # Circuit breakers, retries, rate limiting
        ├── observability/      # OpenTelemetry tracing, structured logging
        ├── simulation/         # Simulation framework (bootstrap, runner, clock)
        ├── auth/               # Authentication infrastructure
        ├── health/             # Health checks
        └── http/               # GitHub GraphQL client
```

## Core Concepts

### Domain Models (Pure Business Logic)
- **WorkItem**: Unit of work (issue, task, etc.)
- **Agent**: Specialized AI agent with specific capabilities
- **AgentExecution**: Instance of agent working on a work item
- **Workflow**: Multi-stage pipeline with stage transitions
- **PipelineStage**: Individual stage in workflow with entry conditions
- **ReviewCycle**: Maker-checker review process with feedback loops

### Domain Events (Immutable State Changes)
- **WorkItemColumnChangedEvent**: Work item moved between workflow columns
- **BoardReconciledEvent**: Board structure synchronized with external system
- **CommentNeedsResponseEvent**: Comment requiring agent attention
- **ReviewStatusChangedEvent**: Code review status updated
- **LockAcquiredEvent/LockReleasedEvent**: Pipeline lock lifecycle
- All events frozen (immutable) with serialization support

### Application Services (Orchestration)
- **WorkflowOrchestrator**: Coordinates workflow execution
- **AgentScheduler**: Queues and schedules agent executions
- **ExecutionService**: Manages agent execution lifecycle
- **ReviewService**: Handles review cycles and feedback
- **WorkspaceRouter**: Manages container workspaces and file mounting
- **ConversationalLoopOrchestrator**: Multi-turn agent dialogue management
- **ContainerRecoveryService**: Handles container failure recovery
- **MultiProjectOrchestrator**: Coordinates across multiple projects
- **Event Handlers** (`application/event_handlers/`): Board, workflow, review, execution, repair cycle

### Port Interfaces (Contracts)

**Core System Ports:**
- **ITicketSystem**: Abstract ticket system (GitHub, Jira, etc.)
- **ILLMProvider**: Abstract LLM provider (Claude Code, GPT-4, etc.)
- **IContainer**: Container runtime abstraction
- **IRepository**: Git repository operations
- **IEventStore**: Event sourcing storage
- **IStorage**: Artifact storage

**New Vendor-Agnostic Ports (PR #121):**
- **IBoardService**: Project board management (columns, work items)
- **ICodeReviewService**: Code review lifecycle (PRs, approvals)
- **IDiscussionAdapter**: Discussion/comment thread management
- **IWorkItemService**: Work item CRUD operations
- **IVersionControlService**: VCS operations (branches, commits)
- **IPipelineLockService**: Distributed locking for workflow coordination
- **IIdentityService**: Bot/human user identification
- **IEventEmitter**: Event publication interface
- **IMonitoredService**: Lifecycle management (start/stop monitoring)

### Infrastructure Layer (Cross-cutting Concerns)

**Resilience Patterns** (Centralized):
- Circuit breakers, rate limiting, retries, timeouts
- Applied via decorators that wrap adapters (ResilientBoardServiceDecorator)
- Production and mock implementations for simulation testing
- **Key Principle**: Adapters remain pure - resilience is infrastructure concern

**Event Bus**:
- Pub/sub event distribution with async handlers
- Event persistence to Redis for audit trail
- Support for event replay and debugging
- Stats tracking (events emitted, handler errors, etc.)

**Observability**:
- Structured logging with context (event_id, project_id, etc.)
- Metrics tracking (Prometheus-compatible)
- Distributed tracing (OpenTelemetry/Jaeger)
- Comprehensive error logging (no silent failures)
- Dead letter queue for failed events (`dead_letter_queue.py`)
- Audit logging (`infrastructure/audit/`)

### Adapters (Implementations)

**Production**:
- GitHubTicketAdapter, GitHubBoardAdapter, GitHubCodeReviewAdapter
- ClaudeCodeAdapter (LLM provider)
- DockerContainerAdapter

**Testing/Simulation** (`adapters/testing/`):
- MockLLMAdapter, MockBoardAdapter, MockCodeReviewAdapter, MockAgentExecutor
- MockReviewCycleAdapter, MockRepairCycleAdapter, MockContainerRecoveryAdapter
- InMemoryEventStore, InMemoryConfigStore, InMemoryMetricsAdapter
- FakeContainerAdapter, MockEventEmitter, CapturingMockEventEmitter

## Important Design Changes (Gen 1 → Gen 2)

### Containerized Agent Context
Context written to files and mounted into container:
- Issue details → `/context/issue.txt`
- Code snippets → `/context/code/`
- Previous outputs → `/context/previous_stage.txt`

### Agent Security Model
General purpose containerized agents:
- ✅ Internet access
- ✅ Mounted project files (read/write or read-only)
- ✅ Project-level environment variables
- ✅ MCP servers for artifacts, logging
- ❌ No git credentials or SSH keys
- ❌ No GitHub credentials or app keys
- ❌ No Docker socket access

**Implication**: Orchestrator handles all git operations (clone, commit, push) and provides files to agents.

### Configuration Management
Database-backed configuration with web UI:
- Project settings
- Workflow definitions
- Agent configurations
- Environment variables
- Replaces YAML-based configuration

## Testing Strategy

### Test Pyramid
- **Unit Tests**: Domain models and events (100% coverage target)
- **Integration Tests**: Application services with mock adapters (90% coverage)
- **Simulation Tests**: Full workflows with deterministic mock responses
- **Contract Tests**: Verify adapters conform to port interfaces
- **Performance Tests**: Load and stress testing

### Simulation Mode
- Time manipulation (fast-forward simulation)
- Deterministic LLM responses via mock adapters
- No external service dependencies
- Event replay for debugging
- 10-100x faster than real execution

## Technology Stack

- **Language**: Python 3.11+
- **Web Framework**: FastAPI (REST + WebSocket APIs)
- **ORM**: SQLAlchemy
- **Databases**: PostgreSQL (configuration), Redis (event store, caching)
- **Container Runtime**: Docker
- **Testing**: pytest, pytest-asyncio, testcontainers
- **Monitoring**: Prometheus, Grafana, Jaeger (OpenTelemetry)
- **Frontend**: React or Vue (configuration dashboard)
- **LLM Integration**: Claude Code API/CLI (primary), pluggable for others

## Development Workflow

1. **Local Development**: Docker Compose with mock adapters
2. **Simulation Testing**: Fast end-to-end tests without external services
3. **Staging**: Production-like environment with real services
4. **Production**: Full deployment with monitoring and alerting

## Working with Claude on This Project

### When Adding New Features
1. Review relevant design docs in `documentation/01_design/`
2. Check if domain models, ports, or adapters need updates
3. Follow hexagonal architecture patterns (no external deps in domain)
4. Write tests first (domain layer) or alongside (application layer)
5. Emit domain events for all state changes
6. Update design documentation to match implementation

### When Debugging
1. Check event store for audit trail (event replay capability)
2. Review structured logs with context (event_id, correlation_id)
3. Check adapter implementations for external system issues
4. Verify resilience patterns (circuit breakers, rate limits)

### When Refactoring
1. Maintain port interfaces (contracts) - adapters can change freely
2. Keep domain layer pure (no external dependencies)
3. Ensure tests still pass (especially simulation tests)
4. Update documentation to match changes

### Key Constraints (MUST FOLLOW)
- Domain layer MUST have no external dependencies
- All external interactions through port interfaces
- All state changes MUST emit domain events
- Events MUST be immutable (frozen dataclasses)
- Configuration MUST be database-backed
- Agents execute in isolated containers with limited privileges
- Resilience patterns MUST be centralized in infrastructure layer
- Adapters MUST remain pure (no resilience logic embedded)
- No silent error handling (all errors logged with exc_info=True)
- Simulation-only routes mount in `SimulationApplicationBootstrap`, NEVER in production `create_app()`

## Simulation Testing Infrastructure

The system includes a comprehensive simulation framework for fast, deterministic testing without external services.

### Key Components

**SimulationBootstrap** (`src/codetoreum/infrastructure/simulation/bootstrap.py`)
- Wires all mock adapters, input port adapters, and simulation-only routes
- Entry point for all simulation/test environments

**SimulationRunner** (`src/codetoreum/infrastructure/simulation/simulation_runner.py`)
- Orchestrates test scenarios
- Provides assertion helpers (assert_event_occurred, assert_metric_recorded, etc.)
- Access to mock adapters (llm_adapter, container_adapter, metrics_adapter, notifier_adapter)

**SimulationConfig** (`src/codetoreum/infrastructure/simulation/simulation_config.py`)
- Configuration for simulation behavior (time, agents, containers, notifications)
- `create_fast_config()` - 100x speed multiplier for tests
- `create_realistic_config()` - 1x speed for behavior testing
- Support for YAML configuration files via `from_yaml()`

**SimulationClock** (`src/codetoreum/infrastructure/simulation/simulation_clock.py`)
- Time control with configurable speed multipliers
- `advance(delta)` - Fast-forward by duration
- `advance_to(time)` - Jump to specific time
- `now()` - Get current simulation time

**Mock Adapters** (`src/codetoreum/adapters/testing/`)
- ~25 total adapters (mock + in-memory implementations)
- MockLLMAdapter, MockBoardAdapter, MockReviewCycleAdapter, MockRepairCycleAdapter
- InMemoryEventStore, InMemoryStorageAdapter, InMemoryMetricsAdapter
- See `MOCK_ADAPTERS_REFERENCE.md` for complete reference

### Simulation Scenarios

13+ predefined scenarios testing different workflows:
- **Scenarios 01-05**: Basic workflows (simple, parallel, review, failure, complex)
- **Scenarios 06-06b**: Full SDLC pipeline (with/without repair)
- **Scenario 07**: Repair cycle test-fix-validate loops
- **Scenario 09**: Queue position-based ordering
- **Scenarios 10-10b**: Agent execution and multi-turn dialogue
- **Scenario 12**: Container failure recovery
- **Scenario 13**: Multi-project orchestration
- **Board Automation A/B/C**: Board-driven workflow variants

YAML scenario definitions live in `scenarios/` (default, demo, review_cycle, failure_recovery, stress_test).

See `documentation/simulation_scenarios/SCENARIOS_COMPLETE.md` for detailed specifications.

### Testing Pattern

```python
@pytest.mark.asyncio
async def test_workflow():
    # 1. Create configuration
    config = SimulationConfig.create_fast_config("test_name", speed_multiplier=100.0)

    # 2. Create runner
    runner = SimulationRunner(config)

    # 3. Define scenario
    async def scenario(sim):
        # Trigger actions, advance time, make assertions
        await sim.advance_time(timedelta(minutes=5))
        sim.assert_event_occurred("WorkflowStarted")

    # 4. Run and verify
    result = await runner.run(scenario)
    assert result.success
    assert result.speed_multiplier >= 10.0
```

### Key Features

- **Time Manipulation**: 10-100x faster than real execution
- **Determinism**: Same input always produces same output
- **No External Dependencies**: All services mocked/in-memory
- **Complete Assertions**: Event, metric, and notification validation
- **Event Sourcing**: Full audit trail of all domain events
- **Fast Feedback**: Typical scenario runs in < 30 seconds real time

### Documentation References

- `tests/simulation/README.md` - Framework overview and best practices
- `tests/simulation/SCENARIO_FORMAT.md` - Scenario creation guide
- `documentation/simulation_scenarios/SCENARIOS_COMPLETE.md` - All scenario specifications
- `documentation/01_design/infrastructure/MOCK_ADAPTERS_REFERENCE.md` - Mock adapter guide

## Key Documentation

**Essential Reading:**
1. `documentation/01_design/02_high_level_arch.md` - Architecture overview
2. `documentation/01_design/03_implementation_plan.md` - Implementation plan
3. `documentation/01_design/infrastructure/resilience_infrastructure_design.md` - Resilience patterns
4. `documentation/01_design/ports/output/NEW_INTERFACES_QUICK_REFERENCE.md` - Port interface guide
5. `documentation/01_design/ports/output/COMPREHENSIVE_PORTS_REFERENCE.md` - Complete port inventory (28+ ports)

**Testing & Simulation:**
- `tests/simulation/README.md` - Simulation testing framework
- `documentation/simulation_scenarios/SCENARIOS_COMPLETE.md` - Scenario specifications
- `documentation/01_design/infrastructure/MOCK_ADAPTERS_REFERENCE.md` - Mock adapter reference

**Design Specifications:**
- `documentation/01_design/domains/` - Domain model specifications
- `documentation/01_design/application_services/` - Application service designs
- `documentation/01_design/ports/` - Port interface specifications
- `documentation/01_design/events/` - Domain event catalog
- `documentation/01_design/infrastructure/` - Cross-cutting infrastructure

---

*This project uses Claude Code for AI-assisted development and agent orchestration.*
