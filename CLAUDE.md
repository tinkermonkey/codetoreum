# Codetoreum - AI Agent Orchestration Platform

## Project Overview

Codetoreum is an AI agent orchestration platform that automates software development workflows using specialized AI agents. The system integrates with GitHub for work item management and uses Claude Code for agent execution in containerized environments.

**IMPORTANT**: Design documentation for the new Gen 2 architecture is located in the `documentation/01_design/` directory. If a specific design document was not specified for a task, refer to that directory for the relevant design details.

## Architecture

**Gen 2 Design**: Hexagonal Architecture with Event Sourcing
- **Domain Layer**: Pure business logic (WorkItem, Agent, Workflow, etc.)
- **Application Layer**: Orchestration services (WorkflowOrchestrator, ExecutionService, etc.)
- **Ports**: Clean interfaces between core and external systems
- **Adapters**: Swappable implementations (production + mock/simulation)
- **Event Store**: Complete audit trail and replay capability

## Key Design Principles

1. **Testability**: Full end-to-end testing without external services via simulation mode
2. **Observability**: Event sourcing provides complete audit trail
3. **Extensibility**: Plugin architecture for ticket systems and LLM providers
4. **Ease of Configuration**: Web-based UI with database storage (replacing YAML)

## Project Structure

```
codetoreum/
├── documentation/
│   ├── 00_legacy/           # Gen 1 system documentation
│   └── 01_design/           # Gen 2 design specifications
│       ├── 01_design_changes.md
│       ├── 02_high_level_arch.md
│       ├── 03_implementation_plan.md
│       ├── domains/         # Domain model designs
│       ├── application_services/
│       ├── input_ports/     # Inbound port interfaces
│       ├── output_ports/    # Outbound port interfaces
│       ├── primary_adapters/    # Inbound adapters
│       ├── secondary_adapters/  # Outbound adapters
│       ├── events/          # Event catalog
│       ├── infrastructure/  # Cross-cutting infrastructure
│       └── external_systems/    # External system integration specs
└── src/                     # Implementation
│   ├── domain/              # Core business logic
│   ├── application/         # Application services
│   ├── ports/              # Port interfaces
│   ├── adapters/           # Adapter implementations
│   │   ├── primary/        # Inbound adapters
│   │   └── secondary/      # Outbound adapters
│   └── infrastructure/     # Cross-cutting concerns
├── tests/
│   ├── unit/
│   ├── integration/
│   └── simulation/
```

## Core Concepts

### Domain Models (Pure Business Logic)
- **WorkItem**: Unit of work (issue, task, etc.)
- **Agent**: Specialized AI agent with specific capabilities
- **AgentExecution**: Instance of agent working on a work item
- **Workflow**: Multi-stage pipeline with stage transitions
- **PipelineStage**: Individual stage in workflow with entry conditions
- **ReviewCycle**: Maker-checker review process with feedback loops

### Application Services (Orchestration)
- **WorkflowOrchestrator**: Coordinates workflow execution
- **AgentScheduler**: Queues and schedules agent executions
- **ExecutionService**: Manages agent execution lifecycle
- **ReviewService**: Handles review cycles and feedback
- **WorkspaceRouter**: Manages container workspaces and file mounting

### Port Interfaces (Contracts)
- **ITicketSystem**: Abstract ticket system (GitHub, Jira, Markdown, etc.)
- **ILLMProvider**: Abstract LLM provider (Claude Code, Aider, GPT-4, etc.)
- **IContainer**: Container runtime abstraction
- **IRepository**: Git repository operations
- **IEventStore**: Event sourcing storage
- **IStorage**: Artifact storage (local, etc.)

### Infrastructure Layer (Cross-cutting Concerns)
- **Resilience Patterns**: Circuit breakers, rate limiting, retries, timeouts
  - Applied via decorators that wrap adapters
  - Centralized implementation, reusable across all external integrations
  - Production and mock implementations for simulation testing
- **Event Store**: Elasticsearch + Redis for event sourcing
- **Configuration Store**: Database-backed config with versioning and search
- **Observability**: Metrics, logging, tracing, auditing

### Adapters (Implementations)
**Production**: GitHubTicketAdapter, ClaudeCodeAdapter, DockerContainerAdapter
**Testing/Simulation**: InMemoryTicketAdapter, MockLLMAdapter, FakeContainerAdapter

## Important Design Changes (Gen 1 → Gen 2)

### Containerized Agent Context
- Context written to files and mounted into container
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
- Database-backed configuration with web UI
  - Project settings
  - Workflow definitions
  - Agent configurations
  - Environment variables

## Testing Strategy

### Test Pyramid
- **Unit Tests**: Domain models (100% coverage target)
- **Integration Tests**: Application services with mock adapters (90% coverage)
- **Simulation Tests**: Full workflows with deterministic mock responses
- **Contract Tests**: Verify adapters conform to port interfaces
- **Performance Tests**: Load and stress testing

### Simulation Mode
- Time manipulation (fast-forward simulation)
- Deterministic LLM responses
- No external service dependencies
- Event replay for debugging
- 10-100x faster than real execution

## Key Documentation

### Essential Reading
1. `documentation/01_design/02_high_level_arch.md` - Architecture overview
2. `documentation/01_design/03_implementation_plan.md` - Detailed implementation plan
3. `documentation/01_design/01_design_changes.md` - Key design changes

### Gen 1 Legacy System
- `documentation/00_legacy/README.md` - Complete Gen 1 system analysis
- `documentation/00_legacy/01_components_and_layers.md` - 150+ components
- `documentation/00_legacy/04_containerization_architecture.md` - Docker-in-Docker deep dive

### Design Specifications
- `domains/` - Domain model specifications (WorkItem, Agent, Workflow, etc.)
- `application_services/` - Application service designs
- `input_ports/` and `output_ports/` - Port interface specifications
- `primary_adapters/` and `secondary_adapters/` - Adapter designs
- `infrastructure/` - Cross-cutting infrastructure (resilience, observability)
- `events/` - Domain event catalog

## Technology Stack

- **Language**: Python 3.11+
- **Web Framework**: FastAPI (REST + WebSocket APIs)
- **ORM**: SQLAlchemy
- **Databases**: PostgreSQL (configuration), Redis (event store)
- **Container Runtime**: Docker
- **Testing**: pytest, pytest-asyncio, testcontainers
- **Monitoring**: Prometheus, Grafana, Jaeger (OpenTelemetry)
- **Frontend**: React or Vue (configuration dashboard)
- **LLM Integration**: Claude Code API/CLI (primary), pluggable for others

## External Systems

- **GitHub**: Issues, project boards, pull requests
- **Claude API**: LLM provider for agent execution
- **Docker**: Container runtime for isolated agent execution
- **Redis**: Event store, task queue, caching
- **Elasticsearch**: Metrics storage (legacy, may be replaced)

## Development Workflow

1. **Local Development**: Docker Compose with mock adapters
2. **Simulation Testing**: Fast end-to-end tests without external services
3. **Staging**: Production-like environment with real services
4. **Production**: Full deployment with monitoring and alerting

## Working with Claude on This Project

### When Adding New Features
1. Review relevant design docs in `documentation/01_design/`
2. Check if domain models, ports, or adapters need updates
3. Follow hexagonal architecture patterns
4. Write tests first (domain layer) or alongside (application layer)
5. Update design documentation to match implementation

### When Debugging
1. Check event store for audit trail
2. Use event replay to reproduce issues
3. Review relevant flow documentation in `documentation/00_legacy/03_information_flow_patterns.md` (Gen 1)
4. Check adapter implementations for external system issues

### When Refactoring
1. Maintain port interfaces (contracts)
2. Update adapters as needed
3. Ensure tests still pass (especially simulation tests)
4. Update documentation

### Key Constraints
- Domain layer MUST have no external dependencies
- All external interactions through port interfaces
- All state changes must emit domain events
- Configuration must be database-backed
- Agents execute in isolated containers with limited privileges
- Resilience patterns (circuit breakers, rate limiting, etc.) MUST be centralized in infrastructure layer
- Adapters MUST remain pure (no resilience logic embedded in adapter code)

## Contact & Resources

- **Design Docs**: `documentation/01_design/`
- **Legacy System Docs**: `documentation/00_legacy/`
- **Implementation Plan**: `documentation/01_design/03_implementation_plan.md`
- **Architecture Overview**: `documentation/01_design/02_high_level_arch.md`
- **Resilience Infrastructure**: `documentation/01_design/infrastructure/resilience_infrastructure_design.md`

---

*This project uses Claude Code for AI-assisted development and agent orchestration.*
