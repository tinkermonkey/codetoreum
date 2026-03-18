"""Pytest fixtures for simulation testing."""

from collections.abc import AsyncGenerator, Callable, Coroutine, Generator
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi import FastAPI

# Set default timeout for all simulation tests to prevent hanging indefinitely
pytestmark = pytest.mark.timeout(60)

from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_metrics_adapter import (
    InMemoryMetricsAdapter,
)
from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.adapters.testing.mock_notifier_adapter import MockNotifierAdapter
from codetoreum.domain.events import WorkItemColumnChanged
from codetoreum.infrastructure.simulation import (
    SimulationClock,
    SimulationConfig,
    SimulationRunner,
)
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
    SimulationInfrastructure,
    SimulationPorts,
    SimulationServices,
)
from codetoreum.ports.output.agent_executor import IAgentExecutor

# ====================================================================================
# Shared Test Utilities (Scenario Tests)
# ====================================================================================


class MockAgentExecutor(IAgentExecutor):
    """Mock agent executor for unit tests constructing BoardColumnEventHandler instances.

    IMPORTANT: This is a simple execution tracking mock for isolated unit tests only.
    It does NOT support execution delays or the full execution pipeline. Tests that
    construct their own BoardColumnEventHandler instances (e.g., board_automation_scenario_*.py)
    should use this class.

    For tests using SimulationApplicationBootstrap, the executor is ExecutionServiceAgentExecutor,
    which provides the full execution chain with execution delay support. Do not confuse this
    simple mock with the production-strength MockAgentExecutor in
    src/codetoreum/adapters/testing/mock_agent_executor.py.

    Attributes:
        _executions: Record of all agent executions for test assertions
    """

    def __init__(self):
        """Initialize the mock agent executor."""
        self._executions: list[dict] = []
        self._lock = __import__("threading").Lock()

    async def execute(self, work_item_id: str, agent_id: str, board_id: str | None = None) -> None:
        """Record agent execution.

        Args:
            work_item_id: ID of work item being processed
            agent_id: ID of agent being executed
            board_id: ID of the board containing the work item (optional)
        """
        with self._lock:
            self._executions.append(
                {
                    "work_item_id": work_item_id,
                    "agent_id": agent_id,
                    "board_id": board_id,
                    "timestamp": datetime.now(tz=UTC),
                }
            )

    def was_triggered(self, agent_id: str, work_item_id: str) -> bool:
        """Check if agent was triggered for work item.

        Args:
            agent_id: Agent ID to check
            work_item_id: Work item ID to check

        Returns:
            True if agent was triggered for this work item
        """
        with self._lock:
            return any(e["agent_id"] == agent_id and e["work_item_id"] == work_item_id for e in self._executions)

    def get_execution_count(self, agent_id: str) -> int:
        """Get total execution count for an agent.

        Args:
            agent_id: Agent ID to check

        Returns:
            Number of times this agent was executed
        """
        with self._lock:
            return sum(1 for e in self._executions if e["agent_id"] == agent_id)

    def set_completion_handler(
        self,
        callback: Callable[[str, str, bool], Coroutine[Any, Any, None]],
        default_board_id: str,
    ) -> None:
        """Wire completion callback for agent execution.

        This is a no-op in the mock implementation since MockAgentExecutor
        does not actually execute agents or invoke callbacks.

        Args:
            callback: Async function(work_item_id, board_id, success) invoked when execution completes
            default_board_id: Board ID to pass to callback when none is provided to execute()
        """
        # No-op: mock executor does not actually execute or invoke callbacks

    def clear(self) -> None:
        """Clear execution history."""
        with self._lock:
            self._executions.clear()


def create_column_changed_event(
    work_item_id: str,
    project_id: str,
    board_id: str,
    from_column: str,
    to_column: str,
    moved_by: str = "human",
) -> WorkItemColumnChanged:
    """Helper to create a column changed event with proper payload dict.

    Args:
        work_item_id: ID of the work item
        project_id: ID of the project
        board_id: ID of the board
        from_column: Source column name
        to_column: Destination column name
        moved_by: Who moved the item (default: "human")

    Returns:
        WorkItemColumnChanged event with proper payload
    """
    return WorkItemColumnChanged(
        aggregate_id=work_item_id,
        payload={
            "work_item_id": work_item_id,
            "project_id": project_id,
            "board_id": board_id,
            "from_column": from_column,
            "to_column": to_column,
            "moved_by": moved_by,
        },
    )


@pytest.fixture
def simulation_clock() -> SimulationClock:
    """
    Provide a simulation clock for tests.

    Yields:
        SimulationClock instance configured for fast execution
    """
    clock = SimulationClock(speed_multiplier=100.0)
    clock.start_at(datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC))
    return clock


@pytest.fixture
def mock_llm() -> Generator[MockLLMAdapter, None, None]:
    """
    Provide a mock LLM adapter.

    Yields:
        MockLLMAdapter instance
    """
    adapter = MockLLMAdapter(
        default_response="Mock LLM response",
        delay_seconds=0.0,
    )
    yield adapter
    adapter.clear_conversations()
    adapter.reset_stats()


@pytest.fixture
def fake_container() -> Generator[FakeContainerAdapter, None, None]:
    """
    Provide a fake container adapter.

    Yields:
        FakeContainerAdapter instance
    """
    adapter = FakeContainerAdapter(
        default_exit_code=0,
        default_stdout="Container execution completed",
        execution_delay=0.0,
    )
    yield adapter
    adapter.clear()


@pytest.fixture
def in_memory_metrics() -> Generator[InMemoryMetricsAdapter, None, None]:
    """
    Provide an in-memory metrics adapter.

    Yields:
        InMemoryMetricsAdapter instance
    """
    adapter = InMemoryMetricsAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def mock_notifier() -> Generator[MockNotifierAdapter, None, None]:
    """
    Provide a mock notifier adapter.

    Yields:
        MockNotifierAdapter instance
    """
    adapter = MockNotifierAdapter(send_delay=0.0)
    yield adapter
    adapter.clear()


@pytest.fixture
def fast_simulation_config() -> SimulationConfig:
    """
    Provide a fast simulation configuration.

    Returns:
        SimulationConfig optimized for speed (100x multiplier)
    """
    return SimulationConfig.create_fast_config(
        scenario_name="test_scenario",
        speed_multiplier=100.0,
    )


@pytest.fixture
def realistic_simulation_config() -> SimulationConfig:
    """
    Provide a realistic simulation configuration.

    Returns:
        SimulationConfig with realistic timings (10x multiplier)
    """
    return SimulationConfig.create_realistic_config(
        scenario_name="test_scenario",
        speed_multiplier=10.0,
    )


@pytest.fixture
def simulation_runner(
    fast_simulation_config: SimulationConfig,
) -> Generator[SimulationRunner, None, None]:
    """
    Provide a simulation runner.

    Args:
        fast_simulation_config: Fast simulation configuration fixture

    Yields:
        SimulationRunner instance
    """
    runner = SimulationRunner(fast_simulation_config)
    yield runner
    # Cleanup
    runner.clear_captured_data()


@pytest.fixture
def custom_simulation_runner():
    """
    Factory fixture for creating custom simulation runners.

    Returns:
        Function that creates SimulationRunner with custom config
    """

    def _create_runner(config: SimulationConfig) -> SimulationRunner:
        return SimulationRunner(config)

    return _create_runner


# ====================================================================================
# Phase 1 Bootstrap Fixtures (NEW)
# ====================================================================================


@pytest.fixture
async def simulation_bootstrap(
    fast_simulation_config: SimulationConfig,
) -> AsyncGenerator[SimulationApplicationBootstrap, None]:
    """
    Provide a fully set up simulation bootstrap.

    Args:
        fast_simulation_config: Fast simulation configuration fixture

    Yields:
        SimulationApplicationBootstrap instance with app ready for testing

    Cleanup:
        Tears down all resources after test
    """
    bootstrap = SimulationApplicationBootstrap(fast_simulation_config)
    await bootstrap.setup()
    yield bootstrap
    await bootstrap.teardown()


@pytest.fixture
async def simulation_app(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> FastAPI:
    """
    Provide the FastAPI application from simulation bootstrap.

    Args:
        simulation_bootstrap: Bootstrap fixture

    Returns:
        FastAPI application ready for testing
    """
    if not simulation_bootstrap.app:
        raise RuntimeError("Bootstrap app not initialized")
    # Cast needed because bootstrap.py has ignore_errors in mypy config,
    # making app typed as Any despite runtime type being FastAPI | None
    return cast("FastAPI", simulation_bootstrap.app)


@pytest.fixture
async def simulation_adapters(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> SimulationAdapters:
    """
    Provide all simulation adapters.

    Args:
        simulation_bootstrap: Bootstrap fixture

    Returns:
        SimulationAdapters container with all 9 mock adapters
    """
    if not simulation_bootstrap.adapters:
        raise RuntimeError("Bootstrap adapters not initialized")
    return simulation_bootstrap.adapters


@pytest.fixture
async def simulation_services(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> SimulationServices:
    """
    Provide all application services.

    Args:
        simulation_bootstrap: Bootstrap fixture

    Returns:
        SimulationServices container with all 8 application services
    """
    if not simulation_bootstrap.services:
        raise RuntimeError("Bootstrap services not initialized")
    return simulation_bootstrap.services


@pytest.fixture
async def simulation_ports(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> SimulationPorts:
    """
    Provide all input/output ports.

    Args:
        simulation_bootstrap: Bootstrap fixture

    Returns:
        SimulationPorts container with all port implementations
    """
    if not simulation_bootstrap.ports:
        raise RuntimeError("Bootstrap ports not initialized")
    return simulation_bootstrap.ports


@pytest.fixture
async def simulation_infrastructure(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> SimulationInfrastructure:
    """
    Provide infrastructure components.

    Args:
        simulation_bootstrap: Bootstrap fixture

    Returns:
        SimulationInfrastructure with event bus, clock, logger
    """
    if not simulation_bootstrap.infrastructure:
        raise RuntimeError("Bootstrap infrastructure not initialized")
    return simulation_bootstrap.infrastructure


# Markers for categorizing simulation tests


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "simulation: mark test as a simulation test (fast, no external dependencies)")
    config.addinivalue_line("markers", "slow_simulation: mark test as a slow simulation (more realistic timing)")
    config.addinivalue_line("markers", "scenario: mark test as a predefined scenario test")


# Hooks for simulation test collection and execution


def pytest_collection_modifyitems(config, items):
    """
    Modify test collection to add markers automatically.

    Args:
        config: Pytest configuration
        items: Collected test items
    """
    for item in items:
        # Auto-mark tests in simulation directory
        if "simulation" in str(item.fspath):
            if "scenario" not in item.keywords:
                item.add_marker(pytest.mark.simulation)

            # Mark slow simulations
            if "slow" in item.name or "realistic" in item.name:
                item.add_marker(pytest.mark.slow_simulation)


# ====================================================================================
# Phase 3 E2E Test Fixtures (NEW)
# ====================================================================================


@pytest.fixture
async def simulation_seeder(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> AsyncGenerator:
    """
    Provide a simulation data seeder for E2E tests.

    This seeder populates domain objects (Agent, WorkItem) required for
    ExecutionServiceAgentExecutor to function properly in end-to-end tests.

    Args:
        simulation_bootstrap: Bootstrap fixture

    Yields:
        SimulationDataSeeder instance ready for seeding test data

    Cleanup:
        Clears seeded data after test
    """
    from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder

    adapters = simulation_bootstrap.adapters
    seeder = SimulationDataSeeder(
        simulation_bootstrap,
        track_items=True,
        agent_repository=adapters.agent_repository,
        work_item_service=adapters.work_item_service,
    )
    yield seeder
    # Cleanup tracked items
    seeder.created_items.clear()


@pytest.fixture
async def e2e_client(
    simulation_app: FastAPI,
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> AsyncGenerator:
    """
    Provide an E2E test client for simulation testing.

    Args:
        simulation_app: FastAPI app fixture
        simulation_bootstrap: Bootstrap fixture

    Yields:
        SimulationE2EClient instance ready for E2E testing

    Cleanup:
        Closes test client connections
    """
    from tests.simulation.e2e_client import SimulationE2EClient

    client = SimulationE2EClient(simulation_app, simulation_bootstrap)
    yield client
    # Cleanup - properly close the client to release socket resources
    client.close()


# ====================================================================================
# Scenario 06 Test Data Fixtures
# ====================================================================================

# Test project constants
SCENARIO_06_TEST_PROJECT = "test-project"
SCENARIO_06_TEST_BOARD = "test-board"
SCENARIO_06_MAKER_AGENT = "senior_software_engineer"
SCENARIO_06_REVIEWER_AGENT = "code_reviewer"
SCENARIO_06_DEFAULT_MAX_ITERATIONS = 5


@pytest.fixture
def scenario_06_test_config() -> dict:
    """
    Provide standard test configuration for Scenario 06 tests.

    Returns:
        Dictionary with test constants for consistency
    """
    return {
        "project_id": SCENARIO_06_TEST_PROJECT,
        "board_id": SCENARIO_06_TEST_BOARD,
        "maker_agent": SCENARIO_06_MAKER_AGENT,
        "reviewer_agent": SCENARIO_06_REVIEWER_AGENT,
        "max_iterations": SCENARIO_06_DEFAULT_MAX_ITERATIONS,
    }
