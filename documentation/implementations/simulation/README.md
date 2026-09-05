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

### [overview.md](./overview.md)

Overview of the Simulation Implementation as a complete port contract implementation:

- How it fulfills all architecture contracts with mock adapters
- Configuration and behavior of 57 adapters
- Time control (100x fast-forward) and determinism
- Purpose, architecture, quick start guide
- Limitations and integration pattern

### [adapters.md](./adapters.md)

Complete reference for all 57 adapters:

- **37 Testing Adapters**: Mock implementations of output ports (InMemoryTicketAdapter, MockClaudeCodeAdapter, FakeContainerAdapter, etc.)
- **2 Secondary Adapters**: In-memory identity service and event emitter
- **18 Input Port Adapters**: HTTP endpoint wrappers (MockOrchestrationCommand, MockWorkItem, etc.)
- Full mapping table with port interface → adapter class → file path
- Adapter organization and characteristics
- Testing patterns and integration
- `MockClaudeCodeAdapter` design notes (default 5-event ledger, `script` override hook)

### [bootstrap-wiring.md](./bootstrap-wiring.md)

Complete bootstrap documentation with diagrams:

- **6-Phase Bootstrap Sequence**: Engine → Infrastructure → Adapters → Services → Input Ports → FastAPI
- **Level 4 Mermaid Flowchart**: Detailed wiring diagram with all phases
- **Dependency Graphs**: Adapter and service dependency relationships
- **Configuration Options**: Python and YAML configuration examples
- **Degraded Mode Support**: Graceful degradation for optional phases

### [scenarios.md](./scenarios.md)

Complete scenario reference and catalog:

- **10 Scenario Directories**: smoke, sdlc_pipeline, review_cycle, failure_recovery, repair_cycle_test, stress_test, planning_design_pipeline, planning_design_review_cycle, pr_feedback_child_issue, dev_environment_repair
- **80 YAML Files**: 8 files per scenario (external + orchestrator subdirectories)
- **YAML Schema**: Complete documentation of projects.yaml, workflows.yaml, agents.yaml, etc.
- **Loading & Execution**: Programmatic loading, CLI, and test integration examples
- **Best Practices**: Speed multiplier selection, work item counts, agent configuration

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

| Aspect        | Simulation             | Production             |
| ------------- | ---------------------- | ---------------------- |
| Ticket System | InMemoryTicketAdapter  | GitHubTicketAdapter    |
| Container     | FakeContainerAdapter   | DockerContainerAdapter |
| Coding Agent  | MockClaudeCodeAdapter  | ClaudeCodeAdapter      |
| Event Store   | InMemoryEventStore     | RedisEventStore        |
| Configuration | InMemoryConfigStore    | DatabaseConfigStore    |
| Speed         | 100x faster            | Real-time              |

## Using the Simulation

See `overview.md` for detailed setup and usage.

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

## See Also

- [Implementations Overview](../README.md)
- [Architecture: Domain Layer](../../architecture/domain/)
- [Architecture: Ports](../../architecture/ports/)
