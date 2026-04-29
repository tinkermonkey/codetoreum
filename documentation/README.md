# Codetoreum Documentation

This directory contains the complete architecture and implementation documentation for the Codetoreum platform. The documentation is organized into three tiers:

## Structure

### [architecture/](./architecture/)
Implementation-agnostic architecture specification covering the hexagonal layers, domain models, port interfaces, application services, and infrastructure patterns. This tier describes *what* the system does and *how* it's organized.

### [implementations/](./implementations/)
Concrete implementations that fulfill the architecture tier contracts. Currently includes the simulation system (complete mock implementation for testing and development). Future implementations may include production configurations.

### [templates/](./templates/)
Template definitions and enforcement rules that specify required sections for each type of documentation file. Used by the documentation validation agent to ensure consistency and completeness.

## Getting Started

- **Architects & Design Review**: Start with [architecture/README.md](./architecture/)
- **Implementation Details**: See [implementations/README.md](./implementations/)
- **Adding Documentation**: Review [templates/README.md](./templates/) for enforcement rules and template definitions
- **API Reference**: Look for port documentation in `architecture/ports/`

## Key Concepts

- **Port Interfaces**: Defined in `architecture/ports/`. Input ports (system inbound) and output ports (system outbound).
- **Domain Models**: Pure business logic in `architecture/domain/`. Events, entities, and value objects.
- **Adapters**: Implementations listed in port documentation. Primary (mock input), secondary (production external services), testing (for simulation).
- **Application Services**: Orchestration layer in `architecture/application-services/`.

## Naming Conventions

All documentation files use lowercase-hyphenated naming (e.g., `comprehensive-ports-reference.md`). README.md files are exceptions and use standard capitalization.
