"""Simulation Scenario 07: Repair Cycle (Test-Fix-Validate).

Tests the deterministic test-fix-validate loop used in the Testing column
of the SDLC workflow. This is NOT a maker-checker pattern; it's a simple
iterative loop where success means "all tests pass."

Comprehensive scenarios cover:
1. Happy path: immediate success (1 iteration per test type)
2. Multiple iterations: gradual convergence
3. Max iterations failure: circuit breaker at max iterations
4. Fast-fail integration: INTEGRATION fails, E2E skipped
5. Warning review: success with warnings after tests pass (TODO)
6. Circuit breaker: max agent calls exceeded
7. Full sequence: UNIT → INTEGRATION → E2E all passing
"""

import pytest
from dataclasses import dataclass
from typing import Tuple

from codetoreum.domain.repair_cycle_types import (
    RepairTestType,
    RepairTestRunConfig,
)
from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.simulation.simulation_runner import SimulationRunner
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock


@dataclass
class RepairCycleTestContext:
    """Test implementation of RepairCycleContext protocol."""

    stage_name: str
    pipeline_run_id: str
    test_configs: Tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int


def create_config(scenario_name: str = "scenario_07_repair_cycle") -> SimulationConfig:
    """Create configuration for repair cycle scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name=scenario_name,
        speed_multiplier=100.0,
    )
    config.scenario_description = (
        "Repair cycle test-fix-validate loop with sequential test types, "
        "fast-fail behavior, and optional warning review"
    )
    return config


def create_repair_context(
    test_configs: tuple,
    stage_name: str = "testing",
    max_total_agent_calls: int = 100,
) -> RepairCycleTestContext:
    """Create repair cycle context from config."""
    return RepairCycleTestContext(
        stage_name=stage_name,
        pipeline_run_id="test-run-123",
        test_configs=test_configs,
        agent_name="repair_agent",
        max_total_agent_calls=max_total_agent_calls,
        checkpoint_interval=1,
    )


async def test_scenario_01_happy_path_immediate_success():
    """Test repair cycle with immediate success (1 iteration per test type)."""
    config = create_config("scenario_01_happy_path")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(clock)
    adapter.current_project = "test-proj"

    # Configure: both test types pass immediately
    adapter.set_iterations_until_success(RepairTestType.UNIT, 1)
    adapter.set_iterations_until_success(RepairTestType.INTEGRATION, 1)

    # Execute
    test_configs = (
        RepairTestRunConfig(test_type=RepairTestType.UNIT),
        RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
    )
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert len(result.test_results) == 2
    assert result.test_results[0].passed is True
    assert result.test_results[0].iterations == 1
    assert result.test_results[1].passed is True
    assert result.test_results[1].iterations == 1
    assert result.total_agent_calls == 2  # 1 test run per type

    # Verify adapter assertions
    adapter.assert_iteration_count(RepairTestType.UNIT, 1)
    adapter.assert_iteration_count(RepairTestType.INTEGRATION, 1)
    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_test_type_passed(RepairTestType.INTEGRATION)
    adapter.assert_overall_success()

    # Verify completion time (180 seconds simulated → <1.8s real at 100x)
    assert result.duration_seconds < 180


async def test_scenario_02_multiple_iterations_success():
    """Test repair cycle requiring multiple iterations to converge."""
    config = create_config("scenario_02_multiple_iterations")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(clock)
    adapter.current_project = "test-proj"

    # Configure: UNIT takes 3 iterations, INTEGRATION takes 1
    adapter.set_iterations_until_success(RepairTestType.UNIT, 3)
    adapter.set_iterations_until_success(RepairTestType.INTEGRATION, 1)

    test_configs = (
        RepairTestRunConfig(test_type=RepairTestType.UNIT),
        RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
    )
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert result.test_results[0].iterations == 3
    assert result.test_results[1].iterations == 1
    # Agent calls: 3 tests + 2 fixes for UNIT, 1 test for INTEGRATION = 6
    assert result.total_agent_calls == 6

    adapter.assert_iteration_count(RepairTestType.UNIT, 3)
    adapter.assert_iteration_count(RepairTestType.INTEGRATION, 1)
    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_test_type_passed(RepairTestType.INTEGRATION)
    adapter.assert_overall_success()


async def test_scenario_03_max_iterations_failure():
    """Test repair cycle hitting max iterations (test type fails)."""
    config = create_config("scenario_03_max_iterations")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(clock)
    adapter.current_project = "test-proj"

    # Configure: UNIT always fails (5 iterations), INTEGRATION not run
    adapter.set_always_fail(RepairTestType.UNIT, 5)

    test_configs = (
        RepairTestRunConfig(test_type=RepairTestType.UNIT, max_iterations=5),
        RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
    )
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is False
    assert result.test_results[0].passed is False
    assert result.test_results[0].iterations == 5
    # Error may be None if we hit max iterations naturally (vs circuit breaker)
    assert len(result.test_results) == 1  # INTEGRATION not run (fast-fail)

    adapter.assert_iteration_count(RepairTestType.UNIT, 5)
    adapter.assert_test_type_failed(RepairTestType.UNIT)
    adapter.assert_overall_failure()


async def test_scenario_04_fast_fail_integration():
    """Test fast-fail when INTEGRATION fails after UNIT succeeds."""
    config = create_config("scenario_04_fast_fail_integration")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(clock)
    adapter.current_project = "test-proj"

    # Configure: UNIT passes, INTEGRATION fails, E2E not run
    adapter.set_iterations_until_success(RepairTestType.UNIT, 1)
    adapter.set_always_fail(RepairTestType.INTEGRATION, 3)

    test_configs = (
        RepairTestRunConfig(test_type=RepairTestType.UNIT),
        RepairTestRunConfig(test_type=RepairTestType.INTEGRATION, max_iterations=3),
        RepairTestRunConfig(test_type=RepairTestType.E2E),
    )
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is False
    assert result.test_results[0].passed is True
    assert result.test_results[1].passed is False
    assert len(result.test_results) == 2  # E2E not run (fast-fail)

    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_test_type_failed(RepairTestType.INTEGRATION)
    adapter.assert_overall_failure()

    # Verify E2E never started
    test_cycle_events = adapter.get_events_by_type("TEST_CYCLE_STARTED")
    e2e_started = any(
        e.get("test_type") == RepairTestType.E2E.value for e in test_cycle_events
    )
    assert not e2e_started


async def test_scenario_05_warning_review():
    """Test warning review after tests pass."""
    # TODO: Implement after establishing warning configuration in test results
    pass


async def test_scenario_06_circuit_breaker():
    """Test circuit breaker triggers when max agent calls exceeded."""
    config = create_config("scenario_06_circuit_breaker")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(clock)
    adapter.current_project = "test-proj"

    # Configure: UNIT takes many iterations, circuit breaker at 10 calls
    adapter.set_always_fail(RepairTestType.UNIT, 20)  # Would take 40 calls

    test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT, max_iterations=20),)
    context = create_repair_context(test_configs, max_total_agent_calls=10)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is False
    assert result.test_results[0].error == "Circuit breaker: max agent calls reached"
    assert adapter.get_agent_call_count() <= 10

    adapter.assert_overall_failure()


async def test_scenario_07_all_three_test_types():
    """Test full UNIT → INTEGRATION → E2E sequence with all passing."""
    config = create_config("scenario_07_all_test_types")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(clock)
    adapter.current_project = "test-proj"

    # Configure: all three types pass, some with multiple iterations
    adapter.set_iterations_until_success(RepairTestType.UNIT, 2)
    adapter.set_iterations_until_success(RepairTestType.INTEGRATION, 1)
    adapter.set_iterations_until_success(RepairTestType.E2E, 2)

    test_configs = (
        RepairTestRunConfig(test_type=RepairTestType.UNIT),
        RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
        RepairTestRunConfig(test_type=RepairTestType.E2E),
    )
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert len(result.test_results) == 3
    assert result.test_results[0].iterations == 2  # UNIT
    assert result.test_results[1].iterations == 1  # INTEGRATION
    assert result.test_results[2].iterations == 2  # E2E

    adapter.assert_iteration_count(RepairTestType.UNIT, 2)
    adapter.assert_iteration_count(RepairTestType.INTEGRATION, 1)
    adapter.assert_iteration_count(RepairTestType.E2E, 2)
    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_test_type_passed(RepairTestType.INTEGRATION)
    adapter.assert_test_type_passed(RepairTestType.E2E)
    adapter.assert_overall_success()


# Main runner
async def run_scenario(runner: SimulationRunner) -> None:
    """Execute all repair cycle scenarios."""
    await test_scenario_01_happy_path_immediate_success()
    await test_scenario_02_multiple_iterations_success()
    await test_scenario_03_max_iterations_failure()
    await test_scenario_04_fast_fail_integration()
    # await test_scenario_05_warning_review()  # TODO
    await test_scenario_06_circuit_breaker()
    await test_scenario_07_all_three_test_types()


@pytest.mark.asyncio
async def test_repair_cycle_scenario():
    """Test complete repair cycle simulation scenario."""
    config = create_config()
    runner = SimulationRunner(config)
    result = await runner.run(run_scenario)
    assert result.success
