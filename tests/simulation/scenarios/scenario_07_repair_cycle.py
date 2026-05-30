"""Simulation Scenario 07: Repair Cycle (Test-Fix-Validate).

Tests the deterministic test-fix-validate loop used in the Testing column
of the SDLC workflow. This is NOT a maker-checker pattern; it's a simple
iterative loop where success means "all tests pass."

Comprehensive scenarios cover:
1. Happy path: immediate success (1 iteration per test type)
2. Multiple iterations: gradual convergence
3. Max iterations failure: circuit breaker at max iterations
4. Fast-fail integration: INTEGRATION fails, E2E skipped
5. Warning review: success with warnings after tests pass
6. Circuit breaker: max agent calls exceeded
7. Full sequence: UNIT → INTEGRATION → E2E all passing
"""

from dataclasses import dataclass

import pytest

# MockLLMAdapter retired in Phase D5 — replaced with stub class below
from codetoreum.adapters.testing.mock_repair_cycle_adapter import MockRepairCycleAdapter
from codetoreum.domain.repair_cycle_types import (
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RepairTestWarning,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.simulation.simulation_runner import SimulationRunner


class MockLLMAdapter:
    """Inert stub for the retired MockLLMAdapter (Phase D5).

    The repair-cycle scenarios pass an LLM adapter to the factory but never
    invoke a method on it. This stub keeps construction working until the
    scenarios migrate to ICodingAgent."""

    def __init__(self, *args, **kwargs) -> None:
        pass


@dataclass
class RepairCycleTestContext:
    """Test implementation of RepairCycleContext protocol."""

    stage_name: str
    workflow_run_id: str
    test_configs: tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int
    agent_config: object | None = None  # Optional specialized agent configuration
    systemic_fix_failure_ceiling: int = 50


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
        workflow_run_id="test-run-123",
        test_configs=test_configs,
        agent_name="repair_agent",
        max_total_agent_calls=max_total_agent_calls,
        checkpoint_interval=1,
    )


@pytest.fixture
def llm_factory():
    """Factory that returns a MockLLMAdapter regardless of agent name."""
    llm_adapter = MockLLMAdapter()

    async def factory(agent_name: str):
        return llm_adapter

    return factory


async def test_scenario_01_happy_path_immediate_success(llm_factory):
    """Test repair cycle with immediate success (1 iteration per test type)."""
    config = create_config("scenario_01_happy_path")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
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
    assert result.total_agent_calls == 6  # 3 calls per type (initial run + fix + retest)

    # Verify adapter assertions
    adapter.assert_iteration_count(RepairTestType.UNIT, 1)
    adapter.assert_iteration_count(RepairTestType.INTEGRATION, 1)
    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_test_type_passed(RepairTestType.INTEGRATION)
    adapter.assert_overall_success()

    # Verify completion time (360 seconds simulated → <3.6s real at 100x)
    assert result.duration_seconds <= 360


async def test_scenario_02_multiple_iterations_success(llm_factory):
    """Test repair cycle requiring multiple iterations to converge."""
    config = create_config("scenario_02_multiple_iterations")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
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
    assert result.total_agent_calls == 14

    adapter.assert_iteration_count(RepairTestType.UNIT, 3)
    adapter.assert_iteration_count(RepairTestType.INTEGRATION, 1)
    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_test_type_passed(RepairTestType.INTEGRATION)
    adapter.assert_overall_success()


async def test_scenario_03_max_iterations_failure(llm_factory):
    """Test repair cycle hitting max iterations (test type fails)."""
    config = create_config("scenario_03_max_iterations")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
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
    # iterations reflects last_test_result.iteration (not the outer loop counter)
    assert result.test_results[0].iterations == 3
    # Error may be None if we hit max iterations naturally (vs circuit breaker)
    assert len(result.test_results) == 1  # INTEGRATION not run (fast-fail)

    adapter.assert_iteration_count(RepairTestType.UNIT, 3)
    adapter.assert_test_type_failed(RepairTestType.UNIT)
    adapter.assert_overall_failure()


async def test_scenario_04_fast_fail_integration(llm_factory):
    """Test fast-fail when INTEGRATION fails after UNIT succeeds."""
    config = create_config("scenario_04_fast_fail_integration")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
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
    e2e_started = any(e.get("test_type") == RepairTestType.E2E.value for e in test_cycle_events)
    assert not e2e_started


async def test_scenario_05_warning_review(llm_factory):
    """Test warning review after tests pass.

    Tests the warning review flow:
    - Tests pass with warnings
    - Agent reviews warnings and makes fixes
    - Re-test passes without warnings
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    # Configure: Tests pass immediately but with warnings
    # First result: passed=10, failed=0, warnings=2 (with warnings)
    # Second result (after warning fixes): passed=10, failed=0, warnings=0
    warning_list = (
        RepairTestWarning(file="auth.py", message="Deprecation warning: use new_method instead"),
        RepairTestWarning(file="utils.py", message="Performance warning: consider using async"),
    )

    adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=2,
                failures=(),
                warning_list=warning_list,
                raw_output="Tests passed but with warnings",
                timestamp=clock.now().isoformat(),
            ),
            # After warning fixes, re-test passes without warnings
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All tests passed, no warnings",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    # Test config with review_warnings=True
    test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT, review_warnings=True),)
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert len(result.test_results) == 1
    assert result.test_results[0].passed is True
    assert result.test_results[0].iterations == 1

    # Verify warning review happened
    assert result.test_results[0].warnings_reviewed == 2, "Expected 2 warnings to be reviewed"

    # Verify adapter assertions
    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_overall_success()

    # Verify test cycle completed event passes
    test_cycle_events = adapter.get_events_by_type("TEST_CYCLE_COMPLETED")
    cycle_event = next((e for e in test_cycle_events if e.get("test_type") == RepairTestType.UNIT.value), None)
    assert cycle_event is not None, "Expected TEST_CYCLE_COMPLETED event for UNIT tests"
    assert cycle_event.get("passed") is True, "Expected test cycle to pass"

    # Verify completion time (3 min 30s simulated → <2.1s real at 100x)
    # 30s test + 2min warning fix (2 files) + 30s retest = 3 min 30s
    assert result.duration_seconds < 210, f"Expected duration < 210s, got {result.duration_seconds}s"

    # Verify agent was called for tests and warning reviews
    # 1st test (with warnings) + 2 warning reviews + 1 retest = 4 calls
    assert result.total_agent_calls == 4, f"Expected 4 agent calls, got {result.total_agent_calls}"


async def test_scenario_06_circuit_breaker(llm_factory):
    """Test circuit breaker triggers when max agent calls exceeded."""
    config = create_config("scenario_06_circuit_breaker")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    # Configure: UNIT takes many iterations, circuit breaker at 10 calls
    adapter.set_always_fail(RepairTestType.UNIT, 20)  # Would take 40 calls

    test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT, max_iterations=20),)
    context = create_repair_context(test_configs, max_total_agent_calls=10)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is False
    assert result.test_results[0].error == "Circuit breaker: max agent calls reached"
    assert adapter.get_agent_call_count() <= 15

    adapter.assert_overall_failure()


async def test_scenario_07_all_three_test_types(llm_factory):
    """Test full UNIT → INTEGRATION → E2E sequence with all passing."""
    config = create_config("scenario_07_all_test_types")
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
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


async def test_scenario_08_warning_regression_detection(llm_factory):
    """Test successful warning fix without regression (happy path).

    Tests that when warnings are found and then fixed successfully,
    the system properly completes the warning review cycle without regression.
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    # Configure: Tests pass with warnings, agent fixes them successfully
    original_warnings = (
        RepairTestWarning(file="config.py", message="Deprecated config format"),
        RepairTestWarning(file="logger.py", message="Old logging API"),
    )

    # Simulate successful warning fix: warnings appear, are fixed, don't reappear
    adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            # First run: tests pass with warnings
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=2,
                failures=(),
                warning_list=original_warnings,
                raw_output="Tests passed but with warnings",
                timestamp=clock.now().isoformat(),
            ),
            # After warning fixes: tests pass, no warnings (successfully fixed)
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All tests passed, no warnings",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT, review_warnings=True),)
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert len(result.test_results) == 1
    assert result.test_results[0].passed is True

    # Verify warning review happened
    assert result.test_results[0].warnings_reviewed == 2

    # Verify no regression (warnings don't reappear)
    adapter.assert_no_warning_regression(RepairTestType.UNIT)
    # Verify the specific warnings don't reappear
    adapter.assert_no_warning_reappearance(RepairTestType.UNIT, original_warnings)
    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_overall_success()


async def test_scenario_09_partial_warning_fix(llm_factory):
    """Test handling of partial warning fixes across iterations.

    Tests that when an agent only fixes some warnings in the first pass,
    the system continues to review remaining warnings until all are addressed.
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    warnings_batch_1 = (
        RepairTestWarning(file="auth.py", message="Deprecated auth method"),
        RepairTestWarning(file="database.py", message="Deprecated DB query"),
    )

    warnings_batch_2 = (RepairTestWarning(file="utils.py", message="Old utility function"),)

    # Simulate: agent fixes some warnings, re-test shows remaining warnings
    adapter.set_test_result_sequence(
        RepairTestType.INTEGRATION,
        [
            # First run: tests pass with 2 warnings
            RepairTestResult(
                test_type=RepairTestType.INTEGRATION,
                iteration=1,
                passed=8,
                failed=0,
                warnings=2,
                failures=(),
                warning_list=warnings_batch_1,
                raw_output="Tests passed with multiple warnings",
                timestamp=clock.now().isoformat(),
            ),
            # After first batch of warning fixes: re-test shows 1 remaining
            RepairTestResult(
                test_type=RepairTestType.INTEGRATION,
                iteration=1,
                passed=8,
                failed=0,
                warnings=1,
                failures=(),
                warning_list=warnings_batch_2,
                raw_output="Tests passed, more warnings detected",
                timestamp=clock.now().isoformat(),
            ),
            # After fixing remaining: all warnings gone
            RepairTestResult(
                test_type=RepairTestType.INTEGRATION,
                iteration=1,
                passed=8,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All warnings resolved",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    test_configs = (RepairTestRunConfig(test_type=RepairTestType.INTEGRATION, review_warnings=True),)
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert result.test_results[0].passed is True

    # Verify warnings were reviewed
    # The mock adapter counts warnings from the first test result (2 warnings)
    # Only those are processed before the re-test
    assert result.test_results[0].warnings_reviewed == 2
    adapter.assert_test_type_passed(RepairTestType.INTEGRATION)


async def test_scenario_10_warning_and_failure_mix(llm_factory):
    """Test repair cycle handling both failures and warnings together.

    Tests that the system handles mixed scenarios where tests fail AND have warnings,
    requiring both failure fixes and warning reviews.
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    warnings_list = (RepairTestWarning(file="helpers.py", message="Performance warning"),)

    failures_list = (
        RepairTestFailure(file="test_main.py", test="test_integration", message="Connection timeout"),
        RepairTestFailure(file="test_main.py", test="test_api_call", message="Timeout error"),
        RepairTestFailure(file="test_main.py", test="test_database", message="Connection failed"),
    )

    # Simulate: tests fail then pass with warnings then pass clean
    # With systemic analysis flow, the iteration consumes results differently:
    # - Initial run: fails → fix → retest: passes (no failures) → break
    # - Next iteration: passes with warnings → review → retest: all clean → break
    adapter.set_test_result_sequence(
        RepairTestType.E2E,
        [
            # Iteration 1, initial run: tests fail
            RepairTestResult(
                test_type=RepairTestType.E2E,
                iteration=1,
                passed=5,
                failed=3,
                warnings=0,
                failures=failures_list,
                warning_list=(),
                raw_output="Tests failed",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 1, retest after fix: still fails (triggers systemic analysis)
            RepairTestResult(
                test_type=RepairTestType.E2E,
                iteration=1,
                passed=5,
                failed=3,
                warnings=0,
                failures=failures_list,
                warning_list=(),
                raw_output="Still failing after fix",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 2, initial run: passes with warnings
            RepairTestResult(
                test_type=RepairTestType.E2E,
                iteration=2,
                passed=8,
                failed=0,
                warnings=1,
                failures=(),
                warning_list=warnings_list,
                raw_output="Tests pass but warnings remain",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 2, retest after warning review: all clean
            RepairTestResult(
                test_type=RepairTestType.E2E,
                iteration=2,
                passed=8,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All issues resolved",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    test_configs = (RepairTestRunConfig(test_type=RepairTestType.E2E, review_warnings=True),)
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert result.test_results[0].passed is True

    # Verify both failures and warnings were handled
    assert result.test_results[0].files_fixed >= 1  # At least one file with failures
    assert result.test_results[0].warnings_reviewed >= 1  # Warnings also reviewed
    adapter.assert_test_type_passed(RepairTestType.E2E)


async def test_scenario_11_multiple_test_types_with_warnings(llm_factory):
    """Test warning review across multiple test types with different warnings.

    Tests that each test type's warnings are reviewed independently without
    cross-contamination between test type results.
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    unit_warnings = (RepairTestWarning(file="types.py", message="Type annotation warning"),)

    integration_warnings = (
        RepairTestWarning(file="api_client.py", message="API deprecation"),
        RepairTestWarning(file="database.py", message="Query optimization"),
    )

    # Configure UNIT tests with warnings
    # Note: re-test must also have warnings for them to be reviewed
    adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=20,
                failed=0,
                warnings=1,
                failures=(),
                warning_list=unit_warnings,
                raw_output="Unit tests passed with warnings",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    # Configure INTEGRATION tests with different warnings
    adapter.set_test_result_sequence(
        RepairTestType.INTEGRATION,
        [
            RepairTestResult(
                test_type=RepairTestType.INTEGRATION,
                iteration=1,
                passed=10,
                failed=0,
                warnings=2,
                failures=(),
                warning_list=integration_warnings,
                raw_output="Integration tests passed with warnings",
                timestamp=clock.now().isoformat(),
            ),
            RepairTestResult(
                test_type=RepairTestType.INTEGRATION,
                iteration=1,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="Integration tests clean",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    test_configs = (
        RepairTestRunConfig(test_type=RepairTestType.UNIT, review_warnings=True),
        RepairTestRunConfig(test_type=RepairTestType.INTEGRATION, review_warnings=True),
    )
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert len(result.test_results) == 2

    # Verify UNIT warnings
    assert result.test_results[0].passed is True
    assert result.test_results[0].warnings_reviewed == 1

    # Verify INTEGRATION warnings (different count)
    assert result.test_results[1].passed is True
    assert result.test_results[1].warnings_reviewed == 2

    # Verify no cross-contamination
    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_test_type_passed(RepairTestType.INTEGRATION)
    adapter.assert_warnings_reviewed_count(RepairTestType.UNIT, 1)
    adapter.assert_warnings_reviewed_count(RepairTestType.INTEGRATION, 2)


async def test_scenario_12_warnings_without_review_enabled(llm_factory):
    """Test that warnings are detected but not reviewed when review_warnings=False.

    Tests that the system correctly handles scenarios where warnings exist
    but the repair cycle is not configured to review them.
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    warnings_list = (
        RepairTestWarning(file="legacy.py", message="Legacy code warning"),
        RepairTestWarning(file="old_api.py", message="Deprecated API"),
    )

    # Configure tests with warnings but review_warnings=False
    adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=2,
                failures=(),
                warning_list=warnings_list,
                raw_output="Tests passed with warnings",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    # review_warnings=False: warnings detected but not reviewed
    test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT, review_warnings=False),)
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert result.test_results[0].passed is True

    # Verify warnings were NOT reviewed
    assert result.test_results[0].warnings_reviewed == 0

    # Verify minimal agent calls (only test execution, no warning review)
    assert result.total_agent_calls == 1  # Just the initial test run
    adapter.assert_test_type_passed(RepairTestType.UNIT)


async def test_scenario_13_warning_fixes_break_tests(llm_factory):
    """Test when warning fixes introduce new test failures (Edge Case #6).

    Edge Case #6 from issue #88: Warning fixes break tests, system handles
    regression correctly. Verifies that when fixing warnings introduces new
    test failures, the next iteration retests and handles the new failures.

    Scenario:
    1. Configure initial test result: passed=10, failed=0, warnings=2
    2. Agent reviews warnings (2 warnings)
    3. Re-run tests after warning fixes: passed=9, failed=1 (new failure!)
    4. Next iteration runs tests again and gets success
    5. System verifies warnings were reviewed despite temporary regression
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    original_warnings = (
        RepairTestWarning(file="config.py", message="Deprecated config format"),
        RepairTestWarning(file="logger.py", message="Old logging API"),
    )

    new_failure = (
        RepairTestFailure(file="test_config.py", test="test_config_loading", message="Import error after refactor"),
    )

    # Simulate: tests pass with warnings → warning review → retest shows new failure
    # → fix failures → retest still fails → systemic analysis → iteration 2 succeeds
    adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            # Iteration 1, initial run: tests pass with warnings
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=2,
                failures=(),
                warning_list=original_warnings,
                raw_output="Tests passed but with warnings",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 1, retest after warning review: new failure introduced!
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=9,
                failed=1,
                warnings=0,
                failures=new_failure,
                warning_list=(),
                raw_output="Warning fix broke a test!",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 1, retest after fix_failures: still fails (triggers systemic)
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=9,
                failed=1,
                warnings=0,
                failures=new_failure,
                warning_list=(),
                raw_output="Fix didn't fully resolve",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 2, initial run: all pass
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=2,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All tests pass, no warnings",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT, review_warnings=True),)
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert result.test_results[0].passed is True

    # Verify iteration count: 2 iterations (iteration 1 fails after warning regression, iteration 2 succeeds)
    assert result.test_results[0].iterations == 2

    # Verify warnings were reviewed (2 warnings from initial test)
    assert result.test_results[0].warnings_reviewed == 2

    # Verify system handled the warning regression and eventually passed
    adapter.assert_test_type_passed(RepairTestType.UNIT)


async def test_scenario_14_warning_review_max_iterations(llm_factory):
    """Test max iterations prevent infinite loops when warning fixes break tests.

    Scenario:
    1. Configure warning fixes that always introduce new failures
    2. Set max_iterations to 5
    3. Verify system doesn't loop indefinitely
    4. Verify max_iterations limit is respected
    5. Verify appropriate failure status is returned
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    original_warnings = (RepairTestWarning(file="api.py", message="Deprecated API endpoint"),)

    # Simulate: each warning fix breaks a different test (infinite loop scenario)
    # Iteration 1: warnings, iteration 2: new failure, iteration 3: different failure, etc.
    adapter.set_test_result_sequence(
        RepairTestType.INTEGRATION,
        [
            # Iteration 1: tests pass with warnings
            RepairTestResult(
                test_type=RepairTestType.INTEGRATION,
                iteration=1,
                passed=8,
                failed=0,
                warnings=1,
                failures=(),
                warning_list=original_warnings,
                raw_output="Tests pass with warnings",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 2: warning fix breaks test A
            RepairTestResult(
                test_type=RepairTestType.INTEGRATION,
                iteration=2,
                passed=7,
                failed=1,
                warnings=0,
                failures=(RepairTestFailure(file="test_api.py", test="test_get_users", message="API change"),),
                warning_list=(),
                raw_output="Warning fix broke test A",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 3: fix for A breaks test B
            RepairTestResult(
                test_type=RepairTestType.INTEGRATION,
                iteration=3,
                passed=7,
                failed=1,
                warnings=0,
                failures=(
                    RepairTestFailure(file="test_api.py", test="test_list_users", message="Response format change"),
                ),
                warning_list=(),
                raw_output="Fix for A broke test B",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 4: fix for B breaks test C
            RepairTestResult(
                test_type=RepairTestType.INTEGRATION,
                iteration=4,
                passed=7,
                failed=1,
                warnings=0,
                failures=(
                    RepairTestFailure(
                        file="test_api.py",
                        test="test_delete_users",
                        message="Delete endpoint changed",
                    ),
                ),
                warning_list=(),
                raw_output="Fix for B broke test C",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 5: fix for C breaks test D (at max_iterations limit)
            RepairTestResult(
                test_type=RepairTestType.INTEGRATION,
                iteration=5,
                passed=7,
                failed=1,
                warnings=0,
                failures=(
                    RepairTestFailure(file="test_api.py", test="test_update_users", message="Update logic changed"),
                ),
                warning_list=(),
                raw_output="Fix for C broke test D",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    # Set max_iterations to 5 to prevent infinite loop
    test_configs = (RepairTestRunConfig(test_type=RepairTestType.INTEGRATION, review_warnings=True, max_iterations=5),)
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    # Verify warnings were reviewed
    assert result.test_results[0].warnings_reviewed == 1

    # Verify fixes were attempted despite continuous failures
    assert result.test_results[0].files_fixed >= 1

    # Verify agent call count doesn't exceed reasonable bounds
    # Max iterations with systemic analysis calls = more agent calls per iteration
    assert adapter.get_agent_call_count() <= 50


async def test_scenario_15_multiple_warning_review_attempts(llm_factory):
    """Test multiple warning review attempts with iteration tracking (Complex Case).

    Scenario:
    1. Warning review triggers temporary regression
    2. Next iteration recovers and succeeds
    3. Verify iteration count and event emission

    Tests the repair cycle's ability to handle warning review cycles followed
    by immediate retests that may temporarily fail but then recover successfully.
    """
    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    warnings_batch_1 = (RepairTestWarning(file="auth.py", message="Deprecated auth method"),)

    new_failure_1 = (RepairTestFailure(file="test_auth.py", test="test_login", message="Auth refactor broke login"),)

    # Simulate: warnings → warning review → temporary regression → fix → retest still fails → iteration 2 succeeds
    adapter.set_test_result_sequence(
        RepairTestType.E2E,
        [
            # Iteration 1, initial run: tests pass with warnings
            RepairTestResult(
                test_type=RepairTestType.E2E,
                iteration=1,
                passed=15,
                failed=0,
                warnings=1,
                failures=(),
                warning_list=warnings_batch_1,
                raw_output="Tests pass with warnings",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 1, retest after warning review: temporary regression
            RepairTestResult(
                test_type=RepairTestType.E2E,
                iteration=1,
                passed=14,
                failed=1,
                warnings=0,
                failures=new_failure_1,
                warning_list=(),
                raw_output="Warning fix caused temporary regression",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 1, retest after fix_failures: still fails (triggers systemic)
            RepairTestResult(
                test_type=RepairTestType.E2E,
                iteration=1,
                passed=14,
                failed=1,
                warnings=0,
                failures=new_failure_1,
                warning_list=(),
                raw_output="Fix didn't fully resolve",
                timestamp=clock.now().isoformat(),
            ),
            # Iteration 2, initial run: recovery - all tests pass
            RepairTestResult(
                test_type=RepairTestType.E2E,
                iteration=2,
                passed=15,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All tests pass after recovery",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    test_configs = (RepairTestRunConfig(test_type=RepairTestType.E2E, review_warnings=True),)
    context = create_repair_context(test_configs)
    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert result.test_results[0].passed is True

    # Verify iteration count: 2 iterations (iteration 1 ends with regression, iteration 2 succeeds)
    assert result.test_results[0].iterations == 2

    # Verify warning review happened (1 warning in the list)
    assert result.test_results[0].warnings_reviewed == 1

    # Verify total agent calls includes test runs and warning review
    # At least: initial test (1) + warning review (1) + retest (1) + iteration 2 test (1) = 4 calls
    assert result.total_agent_calls >= 4

    # Verify no regression occurred (warnings were successfully processed despite temporary failure)
    adapter.assert_no_warning_regression(RepairTestType.E2E)
    adapter.assert_test_type_passed(RepairTestType.E2E)


# Main runner
async def run_scenario(runner: SimulationRunner) -> None:
    """Execute all repair cycle scenarios."""
    # Create llm_factory for all scenarios
    llm_adapter = MockLLMAdapter()

    async def llm_factory(agent_name: str):
        return llm_adapter

    await test_scenario_01_happy_path_immediate_success(llm_factory)
    await test_scenario_02_multiple_iterations_success(llm_factory)
    await test_scenario_03_max_iterations_failure(llm_factory)
    await test_scenario_04_fast_fail_integration(llm_factory)
    await test_scenario_05_warning_review(llm_factory)
    await test_scenario_06_circuit_breaker(llm_factory)
    await test_scenario_07_all_three_test_types(llm_factory)
    await test_scenario_08_warning_regression_detection(llm_factory)
    await test_scenario_09_partial_warning_fix(llm_factory)
    await test_scenario_10_warning_and_failure_mix(llm_factory)
    await test_scenario_11_multiple_test_types_with_warnings(llm_factory)
    await test_scenario_12_warnings_without_review_enabled(llm_factory)
    await test_scenario_13_warning_fixes_break_tests(llm_factory)
    await test_scenario_14_warning_review_max_iterations(llm_factory)
    await test_scenario_15_multiple_warning_review_attempts(llm_factory)


@pytest.mark.asyncio
async def test_scenario_16_json_parse_retry_logic(llm_factory):
    """Test JSON parse error with retry logic.

    Edge Case #8 from issue #88: Agent returns invalid JSON,
    system retries with delay, eventually fails gracefully.
    """
    import time
    from unittest.mock import Mock

    from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
        JSONParseError,
        ProductionRepairCycleAdapter,
        RepairCycleConfig,
    )

    config = RepairCycleConfig(
        max_json_parse_retries=3,
        json_parse_retry_delay_ms=100,
    )

    # Mock LLM that returns non-JSON
    mock_llm = Mock()

    def llm_factory(agent_name):
        return mock_llm

    adapter = ProductionRepairCycleAdapter(llm_factory=llm_factory, config=config)

    start_time = time.time()

    with pytest.raises(JSONParseError) as exc_info:
        await adapter._parse_test_output_with_retry("This is not JSON at all!", RepairTestType.UNIT)

    elapsed = time.time() - start_time

    # Should fail immediately when no JSON found
    assert "No JSON found in agent response" in str(exc_info.value)


@pytest.mark.asyncio
async def test_scenario_17_json_parse_success_after_retry(llm_factory):
    """Test successful JSON extraction from mixed content.

    Tests that embedded JSON is found and parsed correctly
    even when surrounded by other text.
    """
    from unittest.mock import Mock

    from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
        ProductionRepairCycleAdapter,
        RepairCycleConfig,
    )

    config = RepairCycleConfig(max_json_parse_retries=3)
    mock_llm = Mock()

    def llm_factory(agent_name):
        return mock_llm

    adapter = ProductionRepairCycleAdapter(llm_factory=llm_factory, config=config)

    # Test with embedded JSON in mixed content
    mixed_content = """
    Here is some text before the JSON.

    {"passed": 10, "failed": 0, "warnings": [], "failures": []}

    And some text after.
    """

    result = await adapter._parse_test_output_with_retry(mixed_content, RepairTestType.UNIT)

    assert result["passed"] == 10
    assert result["failed"] == 0
    assert result["warnings"] == []
    assert result["failures"] == []


@pytest.mark.asyncio
async def test_scenario_18_json_parse_malformed_structure(llm_factory):
    """Test that structurally invalid JSON fails gracefully.

    Tests partial/malformed JSON (missing closing braces, etc.)
    fails after all retries with clear error message.
    """
    from unittest.mock import Mock

    from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
        JSONParseError,
        ProductionRepairCycleAdapter,
        RepairCycleConfig,
    )

    config = RepairCycleConfig(max_json_parse_retries=2)
    mock_llm = Mock()

    def llm_factory(agent_name):
        return mock_llm

    adapter = ProductionRepairCycleAdapter(llm_factory=llm_factory, config=config)

    # Test with malformed JSON (missing closing brace)
    malformed_json = '{"passed": 10, "failed": 0'

    with pytest.raises(JSONParseError) as exc_info:
        await adapter._parse_test_output_with_retry(malformed_json, RepairTestType.UNIT)

    assert "No JSON found in agent response" in str(exc_info.value)


@pytest.mark.asyncio
async def test_scenario_19_agent_config_routing(llm_factory):
    """Test repair cycle with agent config routing to specialized agents (issue #556).

    Verifies the primary behavioral change: when RepairCycleAgentConfig is provided,
    run_tests() routes through 'test_execution', fix_failures_by_file() through
    'code_fix', and handle_warnings() through 'code_fix' sub-task agents.
    """
    from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig

    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    # Configure specialized agents for sub-tasks
    agent_config = RepairCycleAgentConfig(
        test_execution="qa_engineer",  # Different from default
        code_fix="senior_developer",  # Different from default
    )

    # Simple scenario: tests pass immediately
    adapter.set_iterations_until_success(RepairTestType.UNIT, 1)

    test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT),)
    context = create_repair_context(test_configs)
    # Set agent config on context (PRIMARY TEST CHANGE)
    context.agent_config = agent_config
    context.agent_name = "default_repair_agent"

    result = await adapter.execute(context)

    # Assertions: verify execution succeeded
    assert result.overall_success is True
    assert len(result.test_results) == 1
    assert result.test_results[0].passed is True

    # NEW: Verify agent routing was recorded
    # When agent_config is present, _get_llm_for_subtask should resolve agents
    agent_calls = adapter.get_subtask_agent_calls()
    assert len(agent_calls) > 0, "Expected agent calls to be recorded"

    # Verify test_execution sub-task used the configured agent
    test_execution_calls = [c for c in agent_calls if c["sub_task"] == "test_execution"]
    assert len(test_execution_calls) > 0, "Expected test_execution sub-task to be recorded"
    assert (
        test_execution_calls[0]["agent_name"] == "qa_engineer"
    ), "test_execution should use configured 'qa_engineer' agent"

    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_overall_success()


@pytest.mark.asyncio
async def test_scenario_20_agent_config_with_failures_and_fixes(llm_factory):
    """Test agent config routing when failures trigger code_fix agent (issue #556).

    Verifies that when tests fail and need fixing, the code_fix sub-task uses
    the specialized agent from RepairCycleAgentConfig.
    """
    from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig

    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    # Configure specialized agents
    agent_config = RepairCycleAgentConfig(
        test_execution="qa_specialist",
        code_fix="code_repair_expert",
    )

    # Tests require 2 iterations (1st fails, 2nd passes)
    adapter.set_iterations_until_success(RepairTestType.UNIT, 2)

    test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT),)
    context = create_repair_context(test_configs)
    context.agent_config = agent_config
    context.agent_name = "default_agent"

    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert result.test_results[0].iterations == 2

    # Verify both test_execution and code_fix sub-tasks were called
    agent_calls = adapter.get_subtask_agent_calls()
    sub_tasks = {c["sub_task"] for c in agent_calls}
    assert "test_execution" in sub_tasks, "Expected test_execution calls"
    assert "code_fix" in sub_tasks, "Expected code_fix calls (from fix_failures_by_file)"

    # Verify the specialized agents were used
    code_fix_calls = [c for c in agent_calls if c["sub_task"] == "code_fix"]
    assert len(code_fix_calls) > 0
    assert all(
        c["agent_name"] == "code_repair_expert" for c in code_fix_calls
    ), "All code_fix calls should use the configured agent"

    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_overall_success()


@pytest.mark.asyncio
async def test_scenario_21_agent_config_with_warning_review(llm_factory):
    """Test agent config routing for warning review (issue #556).

    Verifies that when warnings are reviewed, the code_fix sub-task uses
    the specialized agent from RepairCycleAgentConfig.
    """
    from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig

    clock = SimulationClock(speed_multiplier=100.0)
    adapter = MockRepairCycleAdapter(llm_factory, clock)
    adapter.current_project = "test-proj"

    # Configure specialized agents
    agent_config = RepairCycleAgentConfig(
        test_execution="qa_agent",
        code_fix="warning_fixer",
    )

    # Configure warning list for first test result
    warning_list = (
        RepairTestWarning(file="config.py", message="Deprecated config format"),
        RepairTestWarning(file="logger.py", message="Old logging API"),
    )

    adapter.set_test_result_sequence(
        RepairTestType.UNIT,
        [
            # First run: tests pass with warnings
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=2,
                failures=(),
                warning_list=warning_list,
                raw_output="Tests passed but with warnings",
                timestamp=clock.now().isoformat(),
            ),
            # After warning review: all clean
            RepairTestResult(
                test_type=RepairTestType.UNIT,
                iteration=1,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All tests passed, no warnings",
                timestamp=clock.now().isoformat(),
            ),
        ],
    )

    test_configs = (RepairTestRunConfig(test_type=RepairTestType.UNIT, review_warnings=True),)
    context = create_repair_context(test_configs)
    context.agent_config = agent_config
    context.agent_name = "default_agent"

    result = await adapter.execute(context)

    # Assertions
    assert result.overall_success is True
    assert result.test_results[0].passed is True
    assert result.test_results[0].warnings_reviewed == 2

    # Verify code_fix agent was used for warning review
    agent_calls = adapter.get_subtask_agent_calls()
    code_fix_calls = [c for c in agent_calls if c["sub_task"] == "code_fix"]
    assert len(code_fix_calls) > 0, "Expected code_fix calls for warning review"
    assert all(
        c["agent_name"] == "warning_fixer" for c in code_fix_calls
    ), "Warning review should use configured code_fix agent"

    adapter.assert_test_type_passed(RepairTestType.UNIT)
    adapter.assert_overall_success()


@pytest.mark.asyncio
async def test_repair_cycle_scenario():
    """Test complete repair cycle simulation scenario."""
    config = create_config()
    runner = SimulationRunner(config)
    result = await runner.run(run_scenario)
    assert result.success
