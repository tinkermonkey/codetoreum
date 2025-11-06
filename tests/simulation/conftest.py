"""Pytest fixtures for simulation testing."""

import pytest
from datetime import datetime, timezone
from typing import Generator

from fastapi import FastAPI

from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_metrics_adapter import (
    InMemoryMetricsAdapter,
)
from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.adapters.testing.mock_notifier_adapter import MockNotifierAdapter
from codetoreum.infrastructure.simulation import (
    SimulationClock,
    SimulationConfig,
    SimulationRunner,
)
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationApplicationBootstrap,
    SimulationAdapters,
    SimulationServices,
    SimulationPorts,
    SimulationInfrastructure,
)


@pytest.fixture
def simulation_clock() -> Generator[SimulationClock, None, None]:
    """
    Provide a simulation clock for tests.

    Yields:
        SimulationClock instance configured for fast execution
    """
    clock = SimulationClock(speed_multiplier=100.0)
    clock.start_at(datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
    yield clock


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
) -> Generator[SimulationApplicationBootstrap, None, None]:
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
    return simulation_bootstrap.app


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
    config.addinivalue_line(
        "markers",
        "simulation: mark test as a simulation test (fast, no external dependencies)"
    )
    config.addinivalue_line(
        "markers",
        "slow_simulation: mark test as a slow simulation (more realistic timing)"
    )
    config.addinivalue_line(
        "markers",
        "scenario: mark test as a predefined scenario test"
    )


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
):
    """
    Provide a simulation data seeder for E2E tests.

    Args:
        simulation_bootstrap: Bootstrap fixture

    Yields:
        SimulationDataSeeder instance ready for seeding test data

    Cleanup:
        Clears seeded data after test
    """
    from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder

    seeder = SimulationDataSeeder(simulation_bootstrap, track_items=True)
    yield seeder
    # Cleanup tracked items
    seeder.created_items.clear()


@pytest.fixture
async def e2e_client(
    simulation_app: FastAPI,
    simulation_bootstrap: SimulationApplicationBootstrap,
):
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
    # Cleanup
    client.client.__exit__(None, None, None)
