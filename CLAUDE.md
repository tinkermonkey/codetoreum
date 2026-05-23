# Codetoreum - AI Agent Orchestration Platform

## Project Overview

Codetoreum is an AI agent orchestration platform that automates software development workflows using specialized AI agents. The system integrates with GitHub for work item management and uses Claude Code for agent execution in containerized environments.

**IMPORTANT**: Architecture documentation for the Gen 2 design is located in the `documentation/architecture/` directory. For implementation details and simulation testing, refer to `documentation/implementations/`. If a specific design document was not specified for a task, use the `/arch-doc` command to generate or search for documentation.

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
├── documentation/              # Architecture and implementation documentation
│   ├── architecture/           # Gen 2 design specifications
│   │   ├── domain/             # Domain model specifications
│   │   ├── ports/              # Port interface specifications (19 input, 40 output)
│   │   ├── application-services/ # Orchestration service designs
│   │   └── infrastructure/     # Cross-cutting infrastructure
│   ├── implementations/        # Implementation and testing documentation
│   │   └── simulation/         # Simulation framework and scenarios
│   └── templates/              # Documentation templates
├── scenarios/                  # Simulation scenario YAML definitions
└── src/codetoreum/
    ├── domain/                 # Core business logic (pure, ~95 domain model classes)
    │   ├── events/             # 151 CodetoreumEvent subclasses (frozen dataclasses, immutable)
    │   └── services/           # Domain services
    ├── application/            # 23 application services + event handlers
    ├── ports/                  # Port interfaces
    │   ├── input/              # 19 inbound ports (commands, queries, services)
    │   └── output/             # 40 outbound port interfaces
    ├── adapters/               # Adapter implementations (54 total mock/in-memory adapters)
    │   ├── primary/            # FastAPI app, REST routers, webhook adapter
    │   │   └── input_port_adapters/mock/  # Mock implementations of all input ports (19 files)
    │   ├── secondary/          # GitHub, Docker, Claude, Redis, Elasticsearch
    │   └── testing/            # 35 mock/in-memory adapters for simulation
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
23 total application services for workflow orchestration, including:
- **WorkflowOrchestrator**: Coordinates workflow execution
- **AgentScheduler**: Queues and schedules agent executions
- **ExecutionService**: Manages agent execution lifecycle
- **ReviewService**: Handles review cycles and feedback
- **WorkspaceRouter**: Manages container workspaces and file mounting
- **ConversationalLoopOrchestrator**: Multi-turn agent dialogue management
- **ContainerRecoveryService**: Handles container failure recovery
- **MultiProjectOrchestrator**: Top-level polling orchestrator — started in Phase 5e of production bootstrap, polls all enabled projects every 30s, delegates per-project work to WorkflowOrchestrator. This is the sole orchestration entry point; BoardColumnEventHandler is its event-driven complement, not an independent entry point
- **Event Handlers** (`application/event_handlers/`): Board, workflow, review, execution, repair cycle

See `documentation/architecture/application-services/` for complete service documentation.

### Port Interfaces (Contracts)

**59 total ports**: 19 input ports + 40 output ports

**Input Ports** (19 total): Command, query, and service interfaces for inbound operations
- Agent management, work item management, workflow management
- Execution management, configuration, system services

**Output Ports** (40 total): Vendor-agnostic interfaces for external system interactions
- **Core System**: ITicketSystem, ILLMProvider, IContainer, IVersionControlService, IEventStore, IStorage
- **Board Management**: IBoardService, board reconciliation services
- **Code Review**: ICodeReviewService, PR/review lifecycle interfaces
- **Work Item Management**: IWorkItemService, work item CRUD and tracking
- **Infrastructure**: IEventEmitter, event bus, monitoring interfaces
- **Identity & Lock Services**: IIdentityService, IPipelineLockService
- **Domain Services**: Specialized business logic services

See `documentation/architecture/ports/` for complete port specifications.

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
- ClaudeCodeAdapter (LLM provider — see note below)
- DockerContainerAdapter

> **ClaudeCodeAdapter is an autonomous agent launcher, not a prompt→text API wrapper.**
> It invokes `claude --print` (headless/non-interactive mode), which still runs Claude Code's full agentic loop: reading files, editing code, executing bash commands, and making multi-step decisions. `ExecutionContext.working_directory` aims the agent at the target codebase. The subprocess is synchronous from Codetoreum's perspective (we `await` its completion), but *within* that subprocess Claude Code operates autonomously. Do not confuse "bounded duration" with "bounded capability."

**Testing/Simulation** (`adapters/testing/` + `adapters/primary/input_port_adapters/mock/`):
- 54 total mock and in-memory adapters for deterministic testing (35 in testing/, 19 in input port mocks)
- Examples: MockLLMAdapter, MockBoardAdapter, MockCodeReviewAdapter, MockAgentExecutor
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

## Python Virtual Environment

**IMPORTANT**: A virtual environment already exists at `.venv/` in the project root. **Do NOT create a new virtual environment.** Always use the existing one.

- **Run Python**: `.venv/bin/python`
- **Run tests**: `poetry run pytest` (poetry uses `.venv` automatically)
- **Install packages**: `poetry add <package>` or `.venv/bin/pip install <package>`
- **Never run**: `python -m venv`, `virtualenv`, `conda create`, or any command that creates a new environment

## Development Workflow

1. **Local Development**: Docker Compose with mock adapters
2. **Simulation Testing**: Fast end-to-end tests without external services
3. **Staging**: Production-like environment with real services
4. **Production**: Full deployment with monitoring and alerting

## Working with Claude on This Project

### When Adding New Features
1. Review relevant design docs in `documentation/architecture/`
2. Check if domain models, ports, or adapters need updates
3. Follow hexagonal architecture patterns (no external deps in domain)
4. Write tests first (domain layer) or alongside (application layer)
5. Emit domain events for all state changes
6. Update design documentation using `/arch-doc` command to validate and generate

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
- Agents execute in isolated containers with limited privileges — agent configs MUST have `requires_docker: true` in production
- `MultiProjectOrchestrator` MUST be the sole top-level orchestration entry point — started once at server startup, never bypassed
- REST API endpoints require `Authorization: Bearer <token>` — token generated by `SimpleTokenAuthManager` on startup, printed to console as `Authentication token: <jwt>`
- Resilience patterns MUST be centralized in infrastructure layer
- Adapters MUST remain pure (no resilience logic embedded)
- No silent error handling (all errors logged with exc_info=True)
- Simulation-only routes mount in `SimulationApplicationBootstrap`, NEVER in production `create_app()`
- **Application services implementing output ports MUST explicitly inherit the port ABC** - Do not rely on duck typing or `TYPE_CHECKING`-only imports. Examples: `MultiProjectOrchestrator` and `WorkflowOrchestrator` both inherit from their respective port interfaces (`IMultiProjectOrchestrator`, `IWorkflowOrchestrator`)

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

**Mock Adapters** (`src/codetoreum/adapters/testing/` and `src/codetoreum/adapters/primary/input_port_adapters/mock/`)
- 54 total adapters (mock + in-memory implementations): 35 in testing/, 19 in input port mocks
- MockLLMAdapter, MockBoardAdapter, MockReviewCycleAdapter, MockRepairCycleAdapter
- InMemoryEventStore, InMemoryStorageAdapter, InMemoryMetricsAdapter
- See `documentation/implementations/simulation/adapters.md` for complete reference

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

YAML scenario definitions live in `scenarios/` (dev_environment_repair, failure_recovery, planning_design_pipeline, planning_design_review_cycle, pr_feedback_child_issue, repair_cycle_test, review_cycle, sdlc_pipeline, smoke, stress_test).

See `documentation/implementations/simulation/scenarios.md` for detailed specifications.

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
- `documentation/implementations/simulation/scenarios.md` - All scenario specifications
- `documentation/implementations/simulation/adapters.md` - Mock adapter guide

## Key Documentation

**Essential Architecture Reading:**
1. `documentation/architecture/overview.md` - Architecture overview
2. `documentation/architecture/domain/models.md` - Domain model specifications (~95 classes)
3. `documentation/architecture/domain/events.md` - Domain event catalog (151 CodetoreumEvent subclasses)
4. `documentation/architecture/infrastructure/resilience.md` - Resilience patterns
5. `documentation/architecture/ports/output/` - Complete output port specifications (40 ports across 7 groups)

**Application & Services:**
- `documentation/architecture/application-services/services.md` - Application service designs (23 services)
- `documentation/architecture/application-services/event-handlers.md` - Event handler specifications
- `documentation/architecture/ports/input/` - Input port interface specifications
- `documentation/architecture/ports/output/` - Output port interface specifications

**Testing & Simulation:**
- `tests/simulation/README.md` - Simulation testing framework
- `tests/simulation/SCENARIO_FORMAT.md` - Scenario creation guide
- `documentation/implementations/simulation/adapters.md` - Mock adapter reference (53 adapters)
- `documentation/implementations/simulation/scenarios.md` - Scenario specifications

**Infrastructure:**
- `documentation/architecture/infrastructure/event-bus.md` - Event distribution architecture
- `documentation/architecture/infrastructure/observability.md` - Observability patterns
- `documentation/implementations/production-bootstrap.md` - Production bootstrap wiring

## Agents

Five specialized agents are available in `.claude/agents/`. Claude invokes them automatically when context matches; you can also name the agent explicitly in your request.

### `codetoreum-architect` — Architectural Authority
The authoritative reviewer for all architectural decisions in this project.

**Invoke when**:
- Writing a new adapter, port interface, domain event, or application service
- Reviewing code for hexagonal boundary compliance or resilience pattern placement
- Designing a new service and need guidance on where it fits among the 23 existing services
- Deciding where new logic belongs (domain vs. application vs. infrastructure)

**How**: Ask Claude to review, or phrase your request in terms of architecture — *"Is this adapter compliant?"*, *"Where should retry logic live?"*, *"Design a service for capability negotiation."*

### `arch-doc` — Documentation Management
Generates, validates, updates, and audits architecture documentation against templates.

**Invoke with `/arch-doc <intent> [target]`**:

| Intent | Example | Use when |
|--------|---------|----------|
| `generate` | `/arch-doc generate IBoardService` | Documenting a new port, adapter, event, or service |
| `validate` | `/arch-doc validate ports` | Checking doc coverage before a commit or PR |
| `update` | `/arch-doc update all signatures` | Syncing docs after interface changes |
| `diagram` | `/arch-doc diagram sequence workflow` | Creating or updating Mermaid diagrams |
| `audit` | `/arch-doc audit` | Full documentation coverage report |

The `arch-doc-validator` skill auto-validates on changes to `ports/`, `adapters/`, `domain/events/`, `application/`, and `documentation/architecture/`.

### `dr-architect` — DR Model Management
Handles all Documentation Robotics model tasks: adding elements, validating the model, running changesets, and reviewing drift. Modifies the model exclusively via the `dr` CLI (never writes YAML directly).

**Invoke when**: Adding architectural elements to `documentation-robotics/model/`, running DR validation, generating reports, or reviewing model changesets.

### `dr-extractor` — Code-to-DR Extraction
Analyzes source code and creates DR model entries with full source provenance (file references, symbol mappings).

**Invoke when**: Onboarding a new module or subsystem into the DR model; every element it creates includes traceability back to the source file.

### `dr-advisor` — DR Guidance
Strategic advice on DR modeling decisions — which layer to use, how to structure elements, how to resolve cross-layer relationship errors.

**Invoke when**: Uncertain about layer placement, getting validation errors you don't understand, or exploring modeling trade-offs.

---

*This project uses Claude Code for AI-assisted development and agent orchestration.*
