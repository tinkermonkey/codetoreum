# Simulation Implementation

The simulation system is a complete, working implementation of Codetoreum using mock adapters and in-memory services. It demonstrates the architecture in action without external dependencies.

## Purpose

The simulation implementation serves multiple purposes:

- **Testing & Validation**: Run complete workflows with deterministic behavior
- **Development**: Fast feedback loop without external service dependencies
- **Scenario Testing**: Exercise specific workflows with controlled inputs
- **Debugging**: Complete event audit trail for post-mortem analysis
- **Documentation**: The simulation demonstrates how adapters are wired and how components interact

## Key Features

- **Fast Time** (100x speed multiplier): Simulations complete in seconds instead of minutes
- **Deterministic**: Same input always produces same output (no flakiness)
- **No External Dependencies**: All services are mocked (GitHub, Docker, Claude, etc.)
- **Event Sourcing**: Complete audit trail of all state changes
- **Scenario-Based**: Predefined workflows test different system paths
- **In-Memory**: No database or external storage required

## Contents

### overview.md (Phase 6)
Overview of the simulation system:
- How it fulfills the architecture contracts
- Configuration and behavior
- Time control and determinism
- Quick start guide

### adapters.md (Phase 6)
Complete list of 53 adapters:
- 35 testing adapters (mock implementations of output ports)
- 18 mock input port adapters (for HTTP/API simulation)
- Each adapter's source file and role

### bootstrap-wiring.md (Phase 6)
How adapters are instantiated and wired:
- 6-phase bootstrap sequence
- Adapter instantiation with dependencies
- Configuration injection
- Wiring diagram

### scenarios.md (Phase 6)
Predefined scenario tests:
- 10 scenario directories
- 28 YAML scenario files
- Scenario format and creation guide
- How to run scenarios

## Architecture

The simulation implementation uses the same architecture as production:

```
Input Ports (Mock) ──→ Application Services ──→ Output Ports (Mock)
                              ↓
                         Domain Layer
                    (Real models, events)
                              ↓
                        Event Bus (Real)
                              ↓
                        Observability (Real)
```

Everything is real except the adapters — which are mocks. This means:
- Real domain logic is exercised
- Real business rules are validated
- Real event flows are tested
- Mocks are completely transparent

## Key Components

- **SimulationConfig**: Configuration for simulation behavior
- **SimulationRunner**: Orchestrates scenario execution
- **SimulationClock**: Manages time (fast-forward, advance)
- **Mock Adapters**: Implement all output ports
- **In-Memory Event Store**: Persists events for replay
- **Bootstrap**: Wires simulation adapters together

## Comparison with Production

| Aspect | Simulation | Production |
|---|---|---|
| Ticket System | MockTicketAdapter | GitHubTicketAdapter |
| Container | FakeContainerAdapter | DockerContainerAdapter |
| LLM | MockLLMAdapter | ClaudeCodeAdapter |
| Event Store | InMemoryEventStore | RedisEventStore |
| Configuration | InMemoryConfigStore | DatabaseConfigStore |
| Speed | 100x faster | Real-time |

## Using the Simulation

See `overview.md` (Phase 6) for detailed setup and usage.

Quick example:
```python
config = SimulationConfig.create_fast_config("test_workflow")
runner = SimulationRunner(config)

async def scenario(sim):
    # Trigger actions, advance time, make assertions
    await sim.advance_time(timedelta(minutes=5))
    sim.assert_event_occurred("WorkflowStarted")

result = await runner.run(scenario)
assert result.success
```

## Phase Delivery

- **Phase 6**: Complete simulation implementation documentation
- **adapters.md** — All 53 adapters listed and mapped
- **bootstrap-wiring.md** — 6-phase bootstrap with diagrams
- **scenarios.md** — All scenarios documented

## See Also

- [Implementations Overview](../README.md)
- [Architecture: Domain Layer](../../architecture/domain/)
- [Architecture: Ports](../../architecture/ports/)
