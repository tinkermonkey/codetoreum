# Ports Layer

The ports layer defines contracts (interfaces) that separate the core domain and application logic from external systems. Ports follow the hexagonal architecture pattern: input ports represent system boundaries for inbound requests, output ports represent system boundaries for outbound dependencies.

## Architecture

Input and output ports are logical separations:

- **Input Ports** (Inbound): Commands, queries, and services that external clients invoke
- **Output Ports** (Outbound): Contracts for dependencies the system relies on

Both sets use Python Abstract Base Classes (ABCs) with type-annotated methods. Adapters implement these ports to connect to real or mock external systems.

## Port Organization

With 63 total port interfaces (21 input + 42 output), individual files per port would create navigational overhead. Instead, ports are grouped by **functional domain** — related interfaces that address the same problem area.

> Count verified 2026-08-12 via exhaustive port ABC scan (`src/codetoreum/ports/input/` and `src/codetoreum/ports/output/`). Recount when ports are added or removed.

This strategy:
- Keeps related interfaces together for context
- Reduces directory fragmentation
- Matches the organization of existing reference documentation
- Creates 6 input files + 7 output files = 13 total port documentation files

### Why This Approach?

- **Cohesion**: Ports within a group typically change together (e.g., review-related interfaces)
- **Traceability**: Cross-references between related ports are explicit in a single file
- **Diagrams**: One diagram per group shows port relationships and their implementations
- **Maintainability**: 13 files is a navigable documentation surface

## Contents

### [input/](./input/)
**21 input port interfaces** across 6 documentation files:

1. **agent-management.md** — Agent command/query operations
2. **work-item-management.md** — Work item and task operations
3. **workflow-management.md** — Workflow definition and execution
4. **execution-management.md** — Agent execution and orchestration
5. **configuration.md** — System configuration and metrics
6. **system-services.md** — Authentication, audit, workspace operations

Each input port documentation file includes:
- Purpose and responsibility
- Interface definition (ABC with type signatures)
- Methods table
- Events this port's operations may trigger
- Error contracts
- Available adapters (mock implementations)
- Class diagram

### [output/](./output/)
**44 output port interfaces** across 7 documentation files:

1. **core-system.md** — Fundamental operations (tickets, VCS, containers, coding agent)
2. **board-management.md** — Project board operations
3. **code-review.md** — Pull request and review lifecycle
4. **work-coordination.md** — Work item coordination and workflow
5. **infrastructure-services.md** — Event distribution, storage, metrics, tracing
6. **domain-services.md** — Bot identity, agent execution, configuration
7. **lifecycle-services.md** — Repair cycles, container recovery, system analysis

Each output port documentation file includes:
- Purpose and responsibility
- Interface definition (ABC with type signatures)
- Methods table
- Events operations may trigger
- Error contracts
- Production, secondary, and testing adapters
- Class diagram

## CQRS Pattern

The port interfaces follow Command Query Responsibility Segregation (CQRS) at the port level:

- **Command Ports** (mutation): IWorkItemCommandPort, IWorkflowCommandPort, etc.
- **Query Ports** (read): IWorkItemQueryPort, IWorkflowQueryPort, etc.

This separation is architectural — it doesn't imply separate physical stores or event logs. Rather, it clarifies intent at the interface boundary.

## Port Design Principles

1. **Vendor Agnostic**: Ports hide external system details behind clean interfaces
2. **Single Responsibility**: Each port has a focused concern area
3. **Event-Driven**: Domain services emit events for state changes
4. **Pure Contracts**: No implementation logic in port definitions
5. **Immutable Parameters**: Complex parameters use `Mapping` for immutability
6. **Clear Error Boundaries**: Custom exceptions define port contract violations
7. **Async-First**: All port methods are async to support distributed systems
8. **Type-Safe**: Full type hints for clarity and IDE support

## Event Emission from Ports

Ports that extend `IEventEmitter` publish domain events following this pattern:

```python
class MyService(IEventEmitter, ABC):
    """Service with event emission."""

    async def my_operation(self) -> Result:
        """Perform operation and emit event."""
        # ... business logic ...

        # Emit event for state change
        event = MyStateChangedEvent(...)
        await self.emit("my.state.changed", event)

        return result
```

Events are immutable dataclasses with complete audit information.

## Port Composition

Complex services compose multiple ports at the adapter level:

- **IBranchResolutionService**: Composes `ITicketSystem` + `IVersionControlService`
- **ICodeReviewService**: Wraps VCS pull request operations
- **IBoardService**: Manages board and work item state

Composition happens in adapters, not in port definitions, keeping ports pure and focused.

## Adapter Mapping

Each port documentation file includes an "Adapter Implementations" section listing all known adapters that implement that port. Adapters are categorized as:

- **Production**: Real external system implementations (GitHub, Docker, Redis, etc.)
- **Secondary**: Alternative production implementations for different platforms
- **Testing/Mock**: In-memory or mock implementations for simulation and unit testing

This mapping ensures that every adapter is documented and traceable to its port(s).

### Key Adapter Categories

**Primary Adapters** (Input Port Implementations):
- FastAPI route handlers that receive HTTP requests
- Webhook handlers for external system callbacks
- Mock implementations for simulation (`MockAgentCommandAdapter`, `MockWorkflowCommandAdapter`, etc.)

**Secondary Adapters** (Output Port Implementations):
- **GitHub**: `GitHubTicketAdapter`, `GitHubBoardAdapter`, `GitHubCodeReviewAdapter`, `GitHubDiscussionAdapter`, `GitHubCIPipelineAdapter`
- **Docker**: `DockerContainerAdapter`, `DockerContainerRecoveryAdapter`
- **Git**: `GitRepositoryAdapter`
- **Elasticsearch**: `ElasticsearchEventStore`
- **Redis**: `RedisPubSubAdapter` (for messaging)
- **Prometheus**: `PrometheusMetricsAdapter`
- **Claude**: `ClaudeCodeAdapter` (coding agent)
- **Branch Resolution**: `BranchResolutionAdapter`
- **Environment Repair**: `ProductionEnvironmentRepairAdapter`
- **Repair Cycles**: `ProductionRepairCycleAdapter`

**Testing Adapters** (Simulation and Unit Testing):
- `InMemoryEventStore`
- `MockBoardAdapter`
- `MockContainerAdapter`
- `MockClaudeCodeAdapter` (replaces the prior `MockLLMAdapter`)
- ~25+ total mock/in-memory adapters for comprehensive simulation testing

> `InMemoryStorage` retires with the `IStorage` port — see the coding-agent port redesign (DEF-015 in `bootstrap/ARCHITECTURE.md`).
