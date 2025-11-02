"""Pytest fixtures for simulation testing."""

import pytest
from datetime import datetime, timezone
from typing import Generator

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
