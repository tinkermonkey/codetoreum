# Domain Layer

The domain layer contains pure business logic, independent of any technology or framework. It defines the core concepts of the Codetoreum platform through entities, value objects, events, and domain services.

## Contents

### models.md (Phase 3)
Catalog of domain model classes — entities and value objects that represent core business concepts. Covers 67 classes across 16 source files:

- **Aggregate Roots**: WorkItem, Agent, Workflow, AgentExecution, ReviewCycle, RepairCycle
- **Domain Entities**: PipelineStage, QueuePosition, ReviewFeedback, ConversationMessage, etc.
- **Value Objects**: Status enums, configuration objects, identifiers
- **Invariants & Validators**: Business rule constraints enforced at model boundaries

### events.md (Phase 3)
Catalog of domain events — immutable records of state changes that occurred in the system. Covers 167 event classes across 19 source files, partitioned by bounded context:

- **Work Item Events**: Column transitions, creation, completion
- **Board Events**: Board reconciliation, state synchronization
- **Review Events**: Review cycle creation, feedback, completion
- **Repair Events**: Repair cycle state changes
- **Execution Events**: Agent execution lifecycle
- **Repository Events**: Git operations
- **Other Events**: Lock acquisition, notifications, etc.

Each event includes:
- Immutable (frozen) dataclass definition
- Serialization format for event store persistence
- Causality chain (what triggered the event)
- Affected aggregates (which domain objects changed)

## Key Principles

1. **Purity**: Domain layer has zero external dependencies (no I/O, no framework code)
2. **Immutability**: Events are frozen dataclasses. Domain models enforce invariants.
3. **Event Sourcing**: All state changes emit events for audit trail and replay
4. **Behavior-Driven**: Models capture business rules, not just data structures

## Relationship to Other Layers

- **Application Services** orchestrate domain models and emit domain events
- **Port Interfaces** accept domain objects as parameters and return domain results
- **Adapters** translate domain models to/from external system representations

## Phase Delivery

- **Phase 3**: Complete domain model and event catalog with diagrams
- **Phase 4+**: Ports and services reference domain types
