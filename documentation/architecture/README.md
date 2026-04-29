# Architecture Tier

The architecture tier contains the implementation-agnostic specification of the Codetoreum platform. It describes the hexagonal architecture layers, business logic, contracts, and orchestration patterns.

## Contents

### [domain/](./domain/)
Pure domain logic layer. Contains definitions for entity models, value objects, domain events, and domain services. This is the system's core — independent of any external technology choices.

- **models.md** (Phase 3): Catalog of 67 domain model classes across 16 files
- **events.md** (Phase 3): Catalog of 167 domain event classes with event flow diagrams

### [ports/](./ports/)
Port interfaces (contracts) that define system boundaries. Input ports represent inbound commands and queries. Output ports represent outbound dependencies.

#### [ports/input/](./ports/input/)
Inbound ports (APIs for commands, queries, services). Grouped by functional domain. 19 input port interfaces across 6 documentation files.

#### [ports/output/](./ports/output/)
Outbound ports (contracts for external system dependencies). Grouped by functional domain. 40 output port interfaces across 7 documentation files.

### [application-services/](./application-services/)
Application services layer. Orchestrates domain logic and coordinates interactions with external systems through ports. Includes application services and event handlers.

- **services.md** (Phase 5): 23 application services
- **event-handlers.md** (Phase 5): 8 event handlers with wiring diagram

### [infrastructure/](./infrastructure/)
Infrastructure and cross-cutting concerns. Event bus, resilience patterns, observability, and other foundational systems.

- **event-bus.md** (Phase 5): Event persistence, distribution, and replay
- **resilience.md** (Phase 5): Circuit breakers, rate limiting, retries, and decorators
- **observability.md** (Phase 5): Structured logging, metrics, tracing, audit trail

## Hexagonal Architecture Diagram

The system follows a hexagonal (ports & adapters) architecture with five layers:

1. **Domain Layer** (core): Pure business logic
2. **Application Layer**: Orchestration and service coordination
3. **Ports** (boundaries): Input and output contracts
4. **Adapters** (implementations): Primary (mock input), secondary (external), testing (simulation)
5. **Infrastructure** (cross-cutting): Event bus, resilience, observability

See **overview.md** (Phase 3) for the detailed architecture diagram and narrative.

## Phase Delivery

- **Phase 1**: Directory structure and templates (complete)
- **Phase 3**: Domain layer documentation
- **Phase 4**: Port contracts (input and output)
- **Phase 5**: Application services and infrastructure
- **Phase 8**: Validation and gap analysis

## Documentation Standards

All architecture tier documentation follows templates defined in `../../templates/`. Each documentation file includes:

- YAML frontmatter indicating which template it follows
- Markdown headings matching required sections from the template
- Mermaid diagrams where specified
- Code examples and cross-references to source

See `../../templates/README.md` for template enforcement rules.
