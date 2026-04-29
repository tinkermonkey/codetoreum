# Application Services Layer

The application services layer orchestrates domain logic and coordinates interactions with external systems through ports. It implements the use cases of the system — receiving commands from input ports, invoking domain logic, calling output ports, and emitting domain events.

## Contents

### services.md (Phase 5)
Catalog of 23 application services that orchestrate workflows:

Each service is responsible for one high-level business capability:

- **WorkflowOrchestrator** — Start and run workflows, manage stage transitions
- **AgentScheduler** — Queue agent executions, assign to containers
- **ExecutionService** — Manage agent execution lifecycle, capture output
- **ReviewService** — Manage code review cycles, collect feedback
- **BoardReconciliationService** — Sync board state with external systems
- **WorkspaceRouter** — Prepare container contexts, manage file mounts
- **ConversationalLoopOrchestrator** — Multi-turn agent dialogue
- **ContainerRecoveryService** — Handle container failures, restart agents
- **MultiProjectOrchestrator** — Coordinate workflows across projects
- **And 14 more...** (See services.md for complete list)

Each service documentation includes:
- Responsibility and use cases
- Dependencies (ports it uses)
- Key methods
- Events it emits
- Sequence diagram (if complex)

### event-handlers.md (Phase 5)
Catalog of 8 event handlers that react to domain events:

Event handlers implement reactive workflows — when a domain event occurs, handlers execute business logic:

- **BoardEventHandler** — Reacts to board state changes
- **WorkflowEventHandler** — Manages workflow state machines
- **ReviewEventHandler** — Coordinates review cycles
- **RepairEventHandler** — Triggers repair cycles on failures
- **ExecutionEventHandler** — Tracks agent execution
- **ContainerEventHandler** — Manages container lifecycle
- **NotificationEventHandler** — Sends notifications
- **AuditEventHandler** — Records audit trail

Each handler documentation includes:
- Events it subscribes to
- Reactions and side effects
- Domain events it emits
- Integration with application services

## Architecture

The application layer sits between:

- **Inbound**: Input ports (commands, queries from external clients)
- **Outbound**: Output ports (dependencies on external systems)
- **Core**: Domain layer (pure business logic, aggregates, events)

```
Input Ports ──→ Application Services ──→ Output Ports
                       ↓
                  Domain Layer
                   (Models, Events)
```

## Key Principles

1. **Orchestration**: Coordinate interactions between domain logic and external systems
2. **Event Emission**: All business state changes must emit domain events
3. **Async First**: All services use async/await for non-blocking execution
4. **No Business Logic**: Logic lives in domain; services coordinate
5. **Dependency Injection**: Port dependencies injected via constructor

## Transaction Semantics

Application services are transaction-safe through event sourcing:

1. Service executes domain operation (deterministic, idempotent)
2. Operation emits domain event
3. Event is persisted to event store (transactional)
4. Event is published to subscribers (eventually consistent)
5. External system adapters react and update state

## Phase Delivery

- **Phase 5**: Complete application service and event handler documentation
- **Phase 4+**: Services and handlers reference domain types and output ports

## See Also

- [Domain Layer](../domain/)
- [Port Layer](../ports/)
- [Infrastructure Layer](../infrastructure/)
