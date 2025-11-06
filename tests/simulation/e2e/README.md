# E2E Test Suite for Simulation Mode

## Overview

This directory contains comprehensive end-to-end tests for the simulation mode testing infrastructure. These tests exercise the full UX layer (REST and WebSocket APIs) via FastAPI TestClient.

## Test Files

- **test_e2e_simple_workflow.py** - Basic 3-stage workflow execution (3 tests)
- **test_e2e_parallel_workflows.py** - Concurrent workflow execution (4 tests)
- **test_e2e_review_cycle.py** - Review feedback loops (4 tests)
- **test_e2e_execution_failure.py** - Error handling and retry logic (6 tests)
- **test_e2e_observability.py** - Metrics, events, WebSocket streaming (7 tests)

**Total: 24 E2E tests**

## Architecture

```
SimulationE2EClient (tests/simulation/e2e_client.py)
    │
    ├── REST API Methods
    │   ├── create_work_item()
    │   ├── trigger_workflow()
    │   ├── get_work_item_status()
    │   ├── get_executions()
    │   ├── get_metrics()
    │   └── get_events()
    │
    ├── WebSocket Methods
    │   ├── connect_websocket()
    │   └── WebSocketEventCollector
    │       ├── collect_event()
    │       ├── wait_for_event()
    │       └── assert_event_received()
    │
    └── Time Manipulation
        ├── advance_time()
        ├── advance_seconds()
        └── advance_minutes()
```

## Test Fixtures

### Core Fixtures (from conftest.py)

- **`simulation_bootstrap`** - Fully wired application stack
- **`simulation_app`** - FastAPI application instance
- **`simulation_seeder`** - Data seeding utility
- **`e2e_client`** - SimulationE2EClient instance

### Usage Example

```python
@pytest.mark.asyncio
@pytest.mark.simulation
async def test_example(e2e_client, simulation_seeder):
    # Seed test data
    await simulation_seeder.seed_default_scenario()

    # Create work item via REST API
    work_item = e2e_client.create_work_item(
        project_id="test-project",
        title="Test work item",
        description="Test description"
    )

    # Connect WebSocket
    ws_collector = e2e_client.connect_websocket(
        subscription_type="all_events",
        work_item_id=work_item["id"],
    )

    # Trigger workflow
    e2e_client.trigger_workflow(
        work_item_id=work_item["id"],
        workflow_id="test-workflow",
    )

    # Advance simulation time
    e2e_client.advance_time(timedelta(hours=1))

    # Wait for completion
    await e2e_client.wait_for_work_item_status(
        work_item_id=work_item["id"],
        expected_status="COMPLETED",
    )

    # Verify events received
    ws_collector.assert_event_received("workflow_completed")
```

## Integration Notes

### Current Implementation Status

The E2E test suite has been created based on the design specifications. However, some components may need adaptation based on the actual implementation:

#### 1. Data Seeding API

**Expected in tests:**
```python
project = await seeder.create_project(project_id="...", name="...")
agent = await seeder.create_agent(agent_id="...", name="...")
workflow = await seeder.create_workflow(workflow_id="...", name="...")
```

**Actual seeding API:**
```python
# Seeder uses fluent/chaining API and returns self, not dictionaries
await seeder.create_project(name="...", description="...")
await seeder.create_agents(count=3, capabilities=[...])  # plural!
await seeder.create_workflow(name="...", stages=[...])

# Projects, workflows, etc. are created with auto-generated IDs
# IDs are stored in seeder.created_items for tracking
```

**Adaptation needed:**
- Update tests to use chaining API
- Use `seed_default_scenario()` for simple cases
- Access created item IDs from `seeder.created_items` or query via API

#### 2. Mock Adapter Configuration

**Used in tests:**
```python
mock_llm.configure_failure_sequence([...])
mock_llm.configure_permanent_failure("...")
fake_container.configure_exit_code_sequence([...])
```

**Status:** These configuration methods may need to be added to mock adapters, or tests should be simplified to use the adapters' existing APIs.

#### 3. REST API Response Format

Tests assume certain response formats (e.g., work items as dictionaries with specific fields). Actual API responses may differ based on DTO/mapper implementations.

**Mitigation:**
- Check actual API endpoints in `src/codetoreum/adapters/primary/routers/`
- Update assertions to match actual response schemas

#### 4. WebSocket Event Format

Tests assume events have specific structures:
```python
{
    "type": "workflow_started",
    "data": {
        "work_item_id": "...",
        ...
    }
}
```

**Mitigation:**
- Verify actual WebSocket event format in `WebSocketAdapter`
- Update event type names and structure to match implementation

## Running the Tests

### Run All E2E Tests

```bash
pytest tests/simulation/e2e/ -v
```

### Run Specific Test File

```bash
pytest tests/simulation/e2e/test_e2e_simple_workflow.py -v
```

### Run Single Test

```bash
pytest tests/simulation/e2e/test_e2e_simple_workflow.py::test_simple_workflow_success -v
```

### Run with Coverage

```bash
pytest tests/simulation/e2e/ --cov=src/codetoreum/adapters/primary --cov-report=term-missing
```

## Performance Target

All 24 E2E tests should complete in **<30 seconds** when using the fast simulation config (100x speed multiplier).

## Test Coverage Goals

- **100% coverage of FastAPI routers** (`src/codetoreum/adapters/primary/routers/`)
- **All REST endpoints tested** (work items, workflows, agents, executions, metrics, events)
- **WebSocket functionality tested** (connection, subscription, event streaming)
- **Time manipulation verified** (simulation clock integration)

## Next Steps

1. **Adapt tests to actual seeding API** - Update test code to match `SimulationDataSeeder` implementation
2. **Verify mock adapter APIs** - Add missing configuration methods or simplify tests
3. **Check REST API schemas** - Update assertions to match actual DTOs
4. **Verify WebSocket events** - Match event types and structure to implementation
5. **Run tests** - Execute and fix any remaining issues
6. **Measure coverage** - Verify 100% router coverage goal

## Design Documents

- [Phase 3 Implementation Plan](../../../documentation/01_design/03_implementation_plan.md#phase-3-e2e-test-harness-7-days)
- [Simulation Architecture](../../../documentation/01_design/infrastructure/simulation_mode_architecture.md)

## Support

For issues or questions:
- Review actual adapter implementations in `src/codetoreum/adapters/testing/`
- Check router implementations in `src/codetoreum/adapters/primary/routers/`
- Consult seeding implementation in `src/codetoreum/infrastructure/simulation/seeding.py`
