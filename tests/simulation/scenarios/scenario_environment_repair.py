"""Simulation Scenario: Environment Repair (Rebuild and Verify).

Tests the environment repair service for handling ENVIRONMENT_ISSUE classification
during the repair cycle. The scenario covers:

1. Environment rebuild: Re-provisioning dependencies after systemic fixes
2. Environment verification: Validating that the rebuilt environment is healthy
3. Retry loop: Rebuilding and verifying until environment is ready
4. Test rerun: Running tests again after environment repair

This scenario demonstrates the full environment issue resolution path:
ENVIRONMENT_ISSUE classification → rebuild → verify → rerun tests
"""

from dataclasses import dataclass

import pytest

from codetoreum.adapters.testing.mock_environment_repair_adapter import (
    MockEnvironmentRepairAdapter,
)
from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.domain.repair_cycle_types import (
    RebuildResult,
    RepairTestRunConfig,
    RepairTestType,
    VerificationResult,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig


@dataclass
class RepairCycleTestContext:
    """Test implementation of RepairCycleContext protocol."""

    stage_name: str
    workflow_run_id: str
    test_configs: tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int
    agent_config: object | None = None
    systemic_fix_failure_ceiling: int = 50
    iteration: int = 0


def create_config(scenario_name: str = "scenario_environment_repair") -> SimulationConfig:
    """Create configuration for environment repair scenario."""
    config = SimulationConfig.create_fast_config(
        scenario_name=scenario_name,
        speed_multiplier=100.0,
    )
    config.scenario_description = (
        "Environment repair rebuild and verification with test rerun " "for ENVIRONMENT_ISSUE failures"
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
        workflow_run_id="test-run-env-repair",
        test_configs=test_configs,
        agent_name="repair_agent",
        max_total_agent_calls=max_total_agent_calls,
        checkpoint_interval=1,
        iteration=0,
    )


@pytest.fixture
async def mock_environment_repair():
    """Create a mock environment repair adapter."""
    clock = SimulationClock(speed_multiplier=100.0)
    return MockEnvironmentRepairAdapter(clock)


async def test_environment_repair_successful_rebuild_and_verify(
    mock_environment_repair,
):
    """Test successful environment rebuild and verification.

    Verifies that:
    1. rebuild_environment succeeds
    2. verify_environment succeeds
    """
    # Setup
    test_config = RepairTestRunConfig(test_type=RepairTestType.UNIT)
    context = create_repair_context((test_config,))

    # Execute rebuild
    rebuild_result = await mock_environment_repair.rebuild_environment(
        project="test-project",
        config=test_config,
        context=context,
    )

    # Verify rebuild succeeded
    assert rebuild_result.success is True
    assert rebuild_result.duration_seconds > 0
    assert len(rebuild_result.actions_taken) > 0
    assert rebuild_result.error is None

    # Execute verification
    verify_result = await mock_environment_repair.verify_environment(
        project="test-project",
        config=test_config,
        context=context,
    )

    # Verify verification succeeded
    assert verify_result.healthy is True
    assert verify_result.duration_seconds > 0
    assert len(verify_result.checks_passed) > 0
    assert len(verify_result.checks_failed) == 0


async def test_environment_repair_with_mock_repair_cycle(
    mock_environment_repair,
):
    """Test environment repair integrated with mock repair cycle.

    Verifies that the environment repair service can be used by the
    mock repair cycle adapter for ENVIRONMENT_ISSUE classification.
    """

    # Setup repair cycle with environment repair service
    async def llm_factory(agent_name: str):
        from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter

        return MockLLMAdapter()

    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(
        llm_factory,
        clock,
        environment_repair_service=mock_environment_repair,
    )
    adapter.current_project = "test-proj"

    # Configure test to pass immediately
    adapter.set_iterations_until_success(RepairTestType.UNIT, 1)

    # Execute repair cycle
    test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT),)
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Verify repair cycle succeeded
    assert result.overall_success is True
    assert len(result.test_results) == 1
    assert result.test_results[0].passed is True


async def test_environment_repair_configurable_results():
    """Test that environment repair results can be configured.

    Verifies that the mock adapter supports configurable rebuild
    and verification sequences for testing different scenarios.
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockEnvironmentRepairAdapter(clock)

    # Configure custom results
    rebuild_success = RebuildResult(
        success=True,
        duration_seconds=20.0,
        actions_taken=("install_packages", "setup_env"),
        error=None,
    )
    rebuild_failure = RebuildResult(
        success=False,
        duration_seconds=10.0,
        actions_taken=(),
        error="Failed to install packages",
    )
    adapter.set_rebuild_results([rebuild_failure, rebuild_success])

    verify_success = VerificationResult(
        healthy=True,
        checks_passed=("deps_ok", "config_ok"),
        checks_failed=(),
        duration_seconds=5.0,
    )
    adapter.set_verification_results([verify_success])

    # Setup context
    test_config = RepairTestRunConfig(test_type=RepairTestType.UNIT)
    context = create_repair_context((test_config,))

    # First rebuild should fail
    result1 = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=context,
    )
    assert result1.success is False
    assert "Failed to install packages" in result1.error

    # Second rebuild should succeed
    result2 = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=context,
    )
    assert result2.success is True

    # Verification should succeed
    verify_result = await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=context,
    )
    assert verify_result.healthy is True


async def test_environment_repair_defaults_to_success():
    """Test that mock adapter defaults to success when no results configured.

    Verifies the default behavior: rebuild succeeds with standard actions,
    verification succeeds with standard checks.
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockEnvironmentRepairAdapter(clock)

    test_config = RepairTestRunConfig(test_type=RepairTestType.UNIT)
    context = create_repair_context((test_config,))

    # Use defaults (no configuration)
    rebuild_result = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=context,
    )
    assert rebuild_result.success is True

    verify_result = await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=context,
    )
    assert verify_result.healthy is True
