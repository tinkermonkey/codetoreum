# Codetroeum

An AI-powered software development orchestration system built with hexagonal architecture, enabling autonomous code generation, testing, and deployment through configurable workflows.

## 📚 Documentation Structure

### Core Architecture
- [System Architecture Overview](docs/architecture/00-system-architecture.md) - High-level architecture and patterns
- [Hexagonal Architecture Guide](docs/architecture/01-hexagonal-architecture.md) - Detailed hexagonal design
- [Event Sourcing & CQRS](docs/architecture/02-event-sourcing-cqrs.md) - Event-driven patterns
- [Testing Strategy](docs/architecture/03-testing-strategy.md) - Comprehensive testing approach

### Component Documentation

#### Input Layer
- [Input Ports Overview](docs/components/input-ports/00-overview.md)
- Individual port specifications in `docs/components/input-ports/`

#### Domain Layer
- [Domain Models Overview](docs/components/domain/00-overview.md)
- Individual domain models in `docs/components/domain/`

#### Application Services
- [Services Overview](docs/components/services/00-overview.md)
- Individual service specifications in `docs/components/services/`

#### Output Layer
- [Output Ports Overview](docs/components/output-ports/00-overview.md)
- Individual port specifications in `docs/components/output-ports/`

#### Adapters
- [Primary Adapters Overview](docs/components/adapters/primary/00-overview.md)
- [Secondary Adapters Overview](docs/components/adapters/secondary/00-overview.md)

### Configuration & Deployment
- [Configuration Management](docs/configuration/00-configuration-management.md)
- [Deployment Guide](docs/deployment/00-deployment-guide.md)
- [Migration Strategy](docs/migration/00-migration-strategy.md)

## 🚀 Quick Start

1. Review the [System Architecture](docs/architecture/00-system-architecture.md)
2. Understand the [Hexagonal Architecture](docs/architecture/01-hexagonal-architecture.md)
3. Explore the [Component Documentation](docs/components/)
4. Check the [Testing Strategy](docs/architecture/03-testing-strategy.md)

## 🎯 Design Principles

1. **Hexagonal Architecture** - Clear separation between business logic and external dependencies
2. **Event Sourcing** - All state changes captured as events for replay and audit
3. **Dependency Injection** - All dependencies injected through interfaces
4. **Domain-Driven Design** - Core domain models independent of infrastructure
5. **CQRS Pattern** - Separate command and query responsibilities
6. **Testability First** - Every component designed for isolation testing
7. **Simulation Mode** - Full system testing without external dependencies

## 📖 License

[License information to be added]
