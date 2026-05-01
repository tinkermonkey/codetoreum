# Simulation Implementation Overview

## Summary

The Simulation Implementation is a complete, working system that demonstrates all architecture tier port contracts using deterministic mock adapters and in-memory services. It is NOT a test harness or simplified version — it exercises the full work coordination pipeline with real domain logic, real application services, and real event flows.

**Key characteristics:**
- 54 total mock adapters (36 output port + 18 input port) implementing the same contracts as production
- Domain layer, application services, and event flows identical to production
- Deterministic responses (no randomness, configurable via YAML)
- Time controlled via SimulationClock (10-100x speed multiplier)
- In-memory storage (no database, Redis, or external services required)
- Complete event audit trail via event sourcing for debugging
- 100x faster execution than real-time

## Authoritative Documentation

For comprehensive usage, implementation details, and testing guidance, refer to the authoritative testing framework documentation:

📖 **[`tests/simulation/README.md`](../../../tests/simulation/README.md)** — Complete framework reference

This file covers:
- Framework overview and key features
- Execution model (all services always active)
- Bootstrap phases (6-phase wiring sequence)
- Quick start and running tests
- Directory structure and components
- Predefined scenarios and writing custom scenarios
- Assertion helpers and debugging tools
- Best practices and performance targets
- Troubleshooting guide

## Related Documentation

- **[Bootstrap Wiring](./bootstrap-wiring.md)** — 6-phase bootstrap sequence with detailed diagrams
- **[Adapters Reference](./adapters.md)** — Complete mapping of all 54 adapters
- **[Scenarios Reference](./scenarios.md)** — All scenario definitions and configurations
- **[Implementations Overview](../README.md)** — All implementation tiers
- **[Architecture: Ports](../../architecture/ports/)** — Port interface specifications
- **[Architecture: Domain](../../architecture/domain/)** — Domain models and events
