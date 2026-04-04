"""Unit tests for MockEnvironmentRepairAdapter.

Verifies that:
1. Default behavior succeeds on first attempt
2. Configurable rebuild result sequences work
3. Configurable verification result sequences work
4. SimulationClock integration for deterministic timing
5. Both rebuild and verify can be configured independently
6. Result exhaustion (sequence runs out) falls back to defaults
7. Events are emitted correctly with all required fields
8. Clock is advanced by result duration for each operation
"""

from datetime import timedelta

import pytest

from codetoreum.adapters.testing.mock_environment_repair_adapter import (
    MockEnvironmentRepairAdapter,
)
from codetoreum.adapters.testing.capturing_mock_event_emitter import CapturingMockEventEmitter
from codetoreum.domain.events.repair_cycle_events import (
    EnvironmentRebuildCompletedEvent,
    EnvironmentRebuildStartedEvent,
    EnvironmentVerificationCompletedEvent,
    EnvironmentVerificationStartedEvent,
)
from codetoreum.domain.repair_cycle_types import (
    RebuildResult,
    RepairTestRunConfig,
    RepairTestType,
    VerificationResult,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.repair_cycle_service import RepairCycleContext
from unittest.mock import MagicMock

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def simulation_clock():
    """Create a simulation clock for deterministic timing."""
    # Use a very fast speed multiplier (1000x) to prevent test timeouts
    return SimulationClock(speed_multiplier=1000.0)


@pytest.fixture
def mock_event_emitter():
    """Create a mock event emitter."""
    return CapturingMockEventEmitter()


@pytest.fixture
def test_context():
    """Create a test repair cycle context."""
    context = MagicMock(spec=RepairCycleContext)
    context.workflow_run_id = "run-123"
    context.iteration = 1
    return context


@pytest.fixture
def test_config():
    """Create a test run configuration."""
    return RepairTestRunConfig(
        test_type=RepairTestType.UNIT,
        timeout=900,
        max_iterations=5,
        review_warnings=True,
    )


# ============================================================================
# rebuild_environment() Default Behavior Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rebuild_environment_default_success(
    simulation_clock, test_context, test_config
):
    """Test rebuild succeeds by default on first attempt."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock)

    result = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    assert result.success is True
    assert len(result.actions_taken) == 2
    assert result.error is None
    assert result.duration_seconds > 0


@pytest.mark.asyncio
async def test_rebuild_environment_default_with_events(
    simulation_clock, mock_event_emitter, test_context, test_config
):
    """Test rebuild emits events with correct structure."""
    adapter = MockEnvironmentRepairAdapter(
        clock=simulation_clock, event_emitter=mock_event_emitter
    )

    result = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    assert result.success is True

    # Verify events
    events = mock_event_emitter.get_events()
    assert len(events) == 2

    assert isinstance(events[0], EnvironmentRebuildStartedEvent)
    assert events[0].workflow_run_id == "run-123"
    assert events[0].test_type == RepairTestType.UNIT
    assert events[0].iteration == 1
    assert events[0].source == "mock_environment_repair"

    assert isinstance(events[1], EnvironmentRebuildCompletedEvent)
    assert events[1].workflow_run_id == "run-123"
    assert events[1].test_type == RepairTestType.UNIT
    assert events[1].iteration == 1
    assert events[1].success is True
    assert len(events[1].actions_taken) == 2


# ============================================================================
# rebuild_environment() Configurable Sequence Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rebuild_environment_failure_then_success(
    simulation_clock, mock_event_emitter, test_context, test_config
):
    """Test rebuild with failure followed by success in sequence."""
    adapter = MockEnvironmentRepairAdapter(
        clock=simulation_clock, event_emitter=mock_event_emitter
    )

    # Configure sequence: fail, then succeed
    failure_result = RebuildResult(
        success=False,
        duration_seconds=10.0,
        actions_taken=("attempt_install",),
        error="Missing dependency X",
    )
    success_result = RebuildResult(
        success=True,
        duration_seconds=20.0,
        actions_taken=("install_x", "configure"),
        error=None,
    )
    adapter.set_rebuild_results([failure_result, success_result])

    # First call should fail
    result1 = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )
    assert result1.success is False
    assert result1.error == "Missing dependency X"

    # Second call should succeed
    result2 = await adapter.rebuild_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )
    assert result2.success is True
    assert len(result2.actions_taken) == 2


@pytest.mark.asyncio
async def test_rebuild_environment_multiple_failures(
    simulation_clock, test_context, test_config
):
    """Test rebuild with multiple failures in sequence."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock)

    results = [
        RebuildResult(
            success=False,
            duration_seconds=5.0,
            actions_taken=(),
            error="Attempt 1 failed",
        ),
        RebuildResult(
            success=False,
            duration_seconds=5.0,
            actions_taken=(),
            error="Attempt 2 failed",
        ),
        RebuildResult(
            success=True,
            duration_seconds=15.0,
            actions_taken=("fix",),
            error=None,
        ),
    ]
    adapter.set_rebuild_results(results)

    # First attempt
    r1 = await adapter.rebuild_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert r1.success is False

    # Second attempt
    r2 = await adapter.rebuild_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert r2.success is False

    # Third attempt
    r3 = await adapter.rebuild_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert r3.success is True


@pytest.mark.asyncio
async def test_rebuild_environment_exhaustion_falls_back_to_default(
    simulation_clock, test_context, test_config
):
    """Test rebuild falls back to default when sequence is exhausted."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock)

    # Configure only one result
    adapter.set_rebuild_results(
        [
            RebuildResult(
                success=False,
                duration_seconds=5.0,
                actions_taken=(),
                error="First attempt failed",
            )
        ]
    )

    # First call returns configured result
    result1 = await adapter.rebuild_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert result1.success is False

    # Second call (sequence exhausted) falls back to default success
    result2 = await adapter.rebuild_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert result2.success is True


# ============================================================================
# verify_environment() Default Behavior Tests
# ============================================================================


@pytest.mark.asyncio
async def test_verify_environment_default_healthy(
    simulation_clock, test_context, test_config
):
    """Test verify returns healthy by default on first attempt."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock)

    result = await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    assert result.healthy is True
    assert len(result.checks_passed) == 3
    assert len(result.checks_failed) == 0
    assert result.duration_seconds > 0


@pytest.mark.asyncio
async def test_verify_environment_default_with_events(
    simulation_clock, mock_event_emitter, test_context, test_config
):
    """Test verify emits events with correct structure."""
    adapter = MockEnvironmentRepairAdapter(
        clock=simulation_clock, event_emitter=mock_event_emitter
    )

    result = await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )

    assert result.healthy is True

    # Verify events
    events = mock_event_emitter.get_events()
    assert len(events) == 2

    assert isinstance(events[0], EnvironmentVerificationStartedEvent)
    assert events[0].workflow_run_id == "run-123"
    assert events[0].test_type == RepairTestType.UNIT
    assert events[0].iteration == 1
    assert events[0].source == "mock_environment_repair"

    assert isinstance(events[1], EnvironmentVerificationCompletedEvent)
    assert events[1].workflow_run_id == "run-123"
    assert events[1].test_type == RepairTestType.UNIT
    assert events[1].iteration == 1
    assert events[1].healthy is True
    assert len(events[1].checks_passed) == 3
    assert len(events[1].checks_failed) == 0


# ============================================================================
# verify_environment() Configurable Sequence Tests
# ============================================================================


@pytest.mark.asyncio
async def test_verify_environment_unhealthy_then_healthy(
    simulation_clock, mock_event_emitter, test_context, test_config
):
    """Test verify with unhealthy followed by healthy in sequence."""
    adapter = MockEnvironmentRepairAdapter(
        clock=simulation_clock, event_emitter=mock_event_emitter
    )

    # Configure sequence: unhealthy, then healthy
    unhealthy_result = VerificationResult(
        healthy=False,
        checks_passed=("deps_installed",),
        checks_failed=("env_vars_set", "services_running"),
        duration_seconds=5.0,
    )
    healthy_result = VerificationResult(
        healthy=True,
        checks_passed=("deps_installed", "env_vars_set", "services_running"),
        checks_failed=(),
        duration_seconds=5.0,
    )
    adapter.set_verification_results([unhealthy_result, healthy_result])

    # First call should be unhealthy
    result1 = await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )
    assert result1.healthy is False
    assert len(result1.checks_failed) == 2

    # Second call should be healthy
    result2 = await adapter.verify_environment(
        project="test-project",
        config=test_config,
        context=test_context,
    )
    assert result2.healthy is True
    assert len(result2.checks_failed) == 0


@pytest.mark.asyncio
async def test_verify_environment_multiple_unhealthy(
    simulation_clock, test_context, test_config
):
    """Test verify with multiple unhealthy checks in sequence."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock)

    results = [
        VerificationResult(
            healthy=False,
            checks_passed=(),
            checks_failed=("all_failed",),
            duration_seconds=3.0,
        ),
        VerificationResult(
            healthy=False,
            checks_passed=("deps",),
            checks_failed=("env_vars",),
            duration_seconds=3.0,
        ),
        VerificationResult(
            healthy=True,
            checks_passed=("deps", "env_vars"),
            checks_failed=(),
            duration_seconds=3.0,
        ),
    ]
    adapter.set_verification_results(results)

    # First attempt
    r1 = await adapter.verify_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert r1.healthy is False

    # Second attempt
    r2 = await adapter.verify_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert r2.healthy is False

    # Third attempt
    r3 = await adapter.verify_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert r3.healthy is True


@pytest.mark.asyncio
async def test_verify_environment_exhaustion_falls_back_to_default(
    simulation_clock, test_context, test_config
):
    """Test verify falls back to default when sequence is exhausted."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock)

    # Configure only one result
    adapter.set_verification_results(
        [
            VerificationResult(
                healthy=False,
                checks_passed=(),
                checks_failed=("all",),
                duration_seconds=5.0,
            )
        ]
    )

    # First call returns configured result
    result1 = await adapter.verify_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert result1.healthy is False

    # Second call (sequence exhausted) falls back to default healthy
    result2 = await adapter.verify_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert result2.healthy is True


# ============================================================================
# SimulationClock Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rebuild_advances_clock_by_duration(simulation_clock, test_context, test_config):
    """Test rebuild advances clock by result duration."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock)

    # Configure result with specific duration
    adapter.set_rebuild_results(
        [RebuildResult(success=True, duration_seconds=42.0, actions_taken=(), error=None)]
    )

    initial_time = simulation_clock.now()

    await adapter.rebuild_environment(
        project="test-project", config=test_config, context=test_context
    )

    final_time = simulation_clock.now()
    elapsed = (final_time - initial_time).total_seconds()

    assert abs(elapsed - 42.0) < 0.1  # Allow small floating point error


@pytest.mark.asyncio
async def test_verify_advances_clock_by_duration(simulation_clock, test_context, test_config):
    """Test verify advances clock by result duration."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock)

    # Configure result with specific duration
    adapter.set_verification_results(
        [
            VerificationResult(
                healthy=True,
                checks_passed=(),
                checks_failed=(),
                duration_seconds=17.5,
            )
        ]
    )

    initial_time = simulation_clock.now()

    await adapter.verify_environment(
        project="test-project", config=test_config, context=test_context
    )

    final_time = simulation_clock.now()
    elapsed = (final_time - initial_time).total_seconds()

    assert abs(elapsed - 17.5) < 0.1  # Allow small floating point error


@pytest.mark.asyncio
async def test_multiple_operations_advance_clock_cumulatively(
    simulation_clock, test_context, test_config
):
    """Test that multiple operations advance clock cumulatively."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock)

    adapter.set_rebuild_results(
        [
            RebuildResult(success=True, duration_seconds=10.0, actions_taken=(), error=None),
            RebuildResult(success=True, duration_seconds=20.0, actions_taken=(), error=None),
        ]
    )
    adapter.set_verification_results(
        [
            VerificationResult(healthy=True, checks_passed=(), checks_failed=(), duration_seconds=5.0),
            VerificationResult(healthy=True, checks_passed=(), checks_failed=(), duration_seconds=5.0),
        ]
    )

    initial_time = simulation_clock.now()

    # First rebuild (10s)
    await adapter.rebuild_environment(
        project="test-project", config=test_config, context=test_context
    )

    # First verify (5s)
    await adapter.verify_environment(
        project="test-project", config=test_config, context=test_context
    )

    # Second rebuild (20s)
    await adapter.rebuild_environment(
        project="test-project", config=test_config, context=test_context
    )

    # Second verify (5s)
    await adapter.verify_environment(
        project="test-project", config=test_config, context=test_context
    )

    final_time = simulation_clock.now()
    total_elapsed = (final_time - initial_time).total_seconds()

    # Total: 10 + 5 + 20 + 5 = 40 seconds
    assert abs(total_elapsed - 40.0) < 0.1


# ============================================================================
# Independent Configuration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rebuild_and_verify_configured_independently(
    simulation_clock, test_context, test_config
):
    """Test that rebuild and verify sequences are independent."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock)

    # Configure rebuild to always fail
    adapter.set_rebuild_results(
        [
            RebuildResult(
                success=False,
                duration_seconds=5.0,
                actions_taken=(),
                error="Always fails",
            )
        ]
    )

    # Configure verify to always succeed
    adapter.set_verification_results(
        [
            VerificationResult(
                healthy=True,
                checks_passed=("all",),
                checks_failed=(),
                duration_seconds=5.0,
            )
        ]
    )

    # Rebuild should fail
    rebuild_result = await adapter.rebuild_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert rebuild_result.success is False

    # Verify should succeed (independent configuration)
    verify_result = await adapter.verify_environment(
        project="test-project", config=test_config, context=test_context
    )
    assert verify_result.healthy is True


# ============================================================================
# No Event Emitter Tests
# ============================================================================


@pytest.mark.asyncio
async def test_rebuild_without_event_emitter(simulation_clock, test_context, test_config):
    """Test rebuild works without event emitter."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock, event_emitter=None)

    result = await adapter.rebuild_environment(
        project="test-project", config=test_config, context=test_context
    )

    assert result.success is True


@pytest.mark.asyncio
async def test_verify_without_event_emitter(simulation_clock, test_context, test_config):
    """Test verify works without event emitter."""
    adapter = MockEnvironmentRepairAdapter(clock=simulation_clock, event_emitter=None)

    result = await adapter.verify_environment(
        project="test-project", config=test_config, context=test_context
    )

    assert result.healthy is True
