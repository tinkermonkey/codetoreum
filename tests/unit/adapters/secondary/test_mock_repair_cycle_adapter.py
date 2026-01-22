"""Tests for MockRepairCycleAdapter.

Comprehensive tests for the mock repair cycle adapter, verifying:
1. Core repair cycle execution methods
2. Event emission behavior
3. Test scenario configuration
4. Error handling and edge cases
5. State tracking and checkpointing
"""

import pytest
from datetime import datetime, timezone

from codetoreum.adapters.secondary.mock_repair_cycle_adapter import (
    MockRepairCycleAdapter,
)
from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    RepairCycleResult,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RepairTestWarning,
)
from codetoreum.domain.events.repair_cycle_events import (
    RepairCycleCompletedEvent,
    RepairCycleFileFixCompletedEvent,
    RepairCycleFileFixStartedEvent,
    RepairCycleFastFailEvent,
    RepairCycleStartedEvent,
    RepairCycleTestCycleCompletedEvent,
    RepairCycleTestExecutionCompletedEvent,
    RepairCycleWarningReviewCompletedEvent,
    RepairCycleWarningReviewStartedEvent,
)


class MockRepairCycleContext:
    """Mock implementation of RepairCycleContext for testing."""

    def __init__(
        self,
        stage_name: str = "fix_failures",
        pipeline_run_id: str = "pipeline_123",
        test_configs: tuple = None,
        agent_name: str = "senior_software_engineer",
        max_total_agent_calls: int = 100,
        checkpoint_interval: int = 5,
    ):
        self.stage_name = stage_name
        self.pipeline_run_id = pipeline_run_id
        self.test_configs = test_configs or (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=900,
                max_iterations=3,
                review_warnings=True,
            ),
        )
        self.agent_name = agent_name
        self.max_total_agent_calls = max_total_agent_calls
        self.checkpoint_interval = checkpoint_interval


class TestMockRepairCycleAdapterInitialization:
    """Tests for adapter initialization."""

    def test_initialization(self):
        """Verify adapter initializes correctly."""
        adapter = MockRepairCycleAdapter()
        assert adapter.current_project is None
        assert len(adapter._scenarios) == 0
        assert len(adapter._repair_state) == 0

    def test_project_property(self):
        """Verify current_project property works."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"
        assert adapter.current_project == "proj-1"

        adapter.current_project = None
        assert adapter.current_project is None


class TestTestScenarioConfiguration:
    """Tests for test scenario configuration."""

    def test_add_simple_scenario(self):
        """Verify adding a simple test scenario."""
        adapter = MockRepairCycleAdapter()
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=3,
            passes_on_iteration=2,
        )

        assert RepairTestType.UNIT.value in adapter._scenarios
        scenario = adapter._scenarios[RepairTestType.UNIT.value]
        assert scenario.initial_failures == 3
        assert scenario.passes_on_iteration == 2

    def test_add_scenario_with_failures_per_file(self):
        """Verify scenario with per-file failure distribution."""
        adapter = MockRepairCycleAdapter()
        failures_per_file = {
            "tests/unit/test_service.py": 2,
            "tests/unit/test_repo.py": 1,
        }
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=3,
            passes_on_iteration=2,
            failures_per_file=failures_per_file,
        )

        scenario = adapter._scenarios[RepairTestType.UNIT.value]
        assert scenario.failures_per_file == failures_per_file

    def test_add_scenario_with_warnings(self):
        """Verify scenario with warning configuration."""
        adapter = MockRepairCycleAdapter()
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=0,
            passes_on_iteration=1,
            warnings=3,
        )

        scenario = adapter._scenarios[RepairTestType.UNIT.value]
        assert scenario.warnings == 3

    def test_multiple_scenarios(self):
        """Verify adding multiple test scenarios."""
        adapter = MockRepairCycleAdapter()
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=2,
            passes_on_iteration=1,
        )
        adapter.add_test_scenario(
            test_type=RepairTestType.INTEGRATION,
            initial_failures=1,
            passes_on_iteration=2,
        )

        assert len(adapter._scenarios) == 2
        assert RepairTestType.UNIT.value in adapter._scenarios
        assert RepairTestType.INTEGRATION.value in adapter._scenarios


class TestRunTests:
    """Tests for run_tests method."""

    @pytest.mark.asyncio
    async def test_run_tests_no_scenario_passes(self):
        """Verify tests pass when no scenario configured."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
        )
        context = MockRepairCycleContext()

        result = await adapter.run_tests(config, context)

        assert result.test_type == RepairTestType.UNIT
        assert result.failed == 0
        assert result.passed == 10
        assert len(result.failures) == 0

    @pytest.mark.asyncio
    async def test_run_tests_with_scenario_failures(self):
        """Verify tests respect scenario failure configuration."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=3,
            passes_on_iteration=2,
        )

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
        )
        context = MockRepairCycleContext()

        # First iteration should fail
        result1 = await adapter.run_tests(config, context)
        assert result1.failed == 3
        assert len(result1.failures) == 3

        # Second iteration should pass
        result2 = await adapter.run_tests(config, context)
        assert result2.failed == 0
        assert len(result2.failures) == 0

    @pytest.mark.asyncio
    async def test_run_tests_with_warnings(self):
        """Verify warnings are included in test results."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=0,
            passes_on_iteration=1,
            warnings=2,
        )

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )
        context = MockRepairCycleContext()

        result = await adapter.run_tests(config, context)
        assert result.warnings == 2
        assert len(result.warning_list) == 2

    @pytest.mark.asyncio
    async def test_run_tests_no_event_without_project(self):
        """Verify run_tests doesn't emit event when project not set."""
        adapter = MockRepairCycleAdapter()
        # current_project is None by default

        events = []
        adapter.on("repair_cycle.test_execution_completed", events.append)

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
        )
        context = MockRepairCycleContext()

        result = await adapter.run_tests(config, context)

        # No events because project is not set
        assert len(events) == 0
        assert result.test_type == RepairTestType.UNIT


class TestFixFailuresByFile:
    """Tests for fix_failures_by_file method."""

    @pytest.mark.asyncio
    async def test_fix_failures_empty(self):
        """Verify fixing empty failure list."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
        )
        context = MockRepairCycleContext()

        files_fixed = await adapter.fix_failures_by_file({}, config, context)
        assert files_fixed == 0

    @pytest.mark.asyncio
    async def test_fix_failures_single_file(self):
        """Verify fixing failures in a single file."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        failures = (
            RepairTestFailure(
                file="tests/unit/test_service.py",
                test="test_create",
                message="AssertionError: Expected 201, got 400"
            ),
            RepairTestFailure(
                file="tests/unit/test_service.py",
                test="test_update",
                message="AssertionError: Expected 200, got 404"
            ),
        )
        grouped_failures = {"tests/unit/test_service.py": failures}

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
        )
        context = MockRepairCycleContext()

        files_fixed = await adapter.fix_failures_by_file(
            grouped_failures, config, context
        )
        assert files_fixed == 1

    @pytest.mark.asyncio
    async def test_fix_failures_multiple_files(self):
        """Verify fixing failures across multiple files."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        grouped_failures = {
            "tests/unit/test_service.py": (
                RepairTestFailure(
                    file="tests/unit/test_service.py",
                    test="test_create",
                    message="Error 1"
                ),
            ),
            "tests/unit/test_repo.py": (
                RepairTestFailure(
                    file="tests/unit/test_repo.py",
                    test="test_get",
                    message="Error 2"
                ),
            ),
        }

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
        )
        context = MockRepairCycleContext()

        files_fixed = await adapter.fix_failures_by_file(
            grouped_failures, config, context
        )
        assert files_fixed == 2

    @pytest.mark.asyncio
    async def test_fix_failures_emits_events(self):
        """Verify fix_failures_by_file emits start and completion events."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        start_events = []
        complete_events = []
        adapter.on("repair_cycle.file_fix_started", start_events.append)
        adapter.on("repair_cycle.file_fix_completed", complete_events.append)

        grouped_failures = {
            "tests/unit/test_service.py": (
                RepairTestFailure(
                    file="tests/unit/test_service.py",
                    test="test_create",
                    message="Error"
                ),
            ),
        }

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
        )
        context = MockRepairCycleContext()

        await adapter.fix_failures_by_file(grouped_failures, config, context)

        assert len(start_events) == 1
        assert len(complete_events) == 1
        assert isinstance(start_events[0], RepairCycleFileFixStartedEvent)
        assert isinstance(complete_events[0], RepairCycleFileFixCompletedEvent)


class TestHandleWarnings:
    """Tests for handle_warnings method."""

    @pytest.mark.asyncio
    async def test_handle_warnings_no_warnings(self):
        """Verify no action when no warnings."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All pass",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
            review_warnings=True,
        )
        context = MockRepairCycleContext()

        warnings_reviewed = await adapter.handle_warnings(test_result, config, context)
        assert warnings_reviewed == 0

    @pytest.mark.asyncio
    async def test_handle_warnings_review_disabled(self):
        """Verify no action when review_warnings is False."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=2,
            failures=(),
            warning_list=(
                RepairTestWarning(file="src/service.py", message="Deprecation"),
                RepairTestWarning(file="src/repo.py", message="Performance"),
            ),
            raw_output="All pass",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
            review_warnings=False,
        )
        context = MockRepairCycleContext()

        warnings_reviewed = await adapter.handle_warnings(test_result, config, context)
        assert warnings_reviewed == 0

    @pytest.mark.asyncio
    async def test_handle_warnings_with_warnings(self):
        """Verify handling of warnings."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=2,
            failures=(),
            warning_list=(
                RepairTestWarning(file="src/service.py", message="Deprecation"),
                RepairTestWarning(file="src/repo.py", message="Performance"),
            ),
            raw_output="All pass",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
            review_warnings=True,
        )
        context = MockRepairCycleContext()

        warnings_reviewed = await adapter.handle_warnings(test_result, config, context)
        # Should process warnings even without events (can fail gracefully if project not properly set up)
        assert warnings_reviewed == 2

    @pytest.mark.asyncio
    async def test_handle_warnings_emits_events(self):
        """Verify handle_warnings emits review events."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        started_events = []
        completed_events = []
        adapter.on("repair_cycle.warning_review_started", started_events.append)
        adapter.on("repair_cycle.warning_review_completed", completed_events.append)

        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=1,
            failures=(),
            warning_list=(
                RepairTestWarning(file="src/service.py", message="Deprecation"),
            ),
            raw_output="All pass",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
            review_warnings=True,
        )
        context = MockRepairCycleContext()

        await adapter.handle_warnings(test_result, config, context)

        assert len(started_events) == 1
        assert len(completed_events) == 1


class TestCheckpoint:
    """Tests for checkpoint method."""

    @pytest.mark.asyncio
    async def test_checkpoint_creates_state(self):
        """Verify checkpoint saves state."""
        adapter = MockRepairCycleAdapter()
        context = MockRepairCycleContext()

        await adapter.checkpoint(RepairTestType.UNIT, 5, context)

        checkpoint_key = f"{context.pipeline_run_id}:UNIT:5"
        assert checkpoint_key in adapter._repair_state
        assert adapter._repair_state[checkpoint_key]["iteration"] == 5

    @pytest.mark.asyncio
    async def test_checkpoint_multiple_test_types(self):
        """Verify checkpoint for different test types."""
        adapter = MockRepairCycleAdapter()
        context = MockRepairCycleContext()

        await adapter.checkpoint(RepairTestType.UNIT, 3, context)
        await adapter.checkpoint(RepairTestType.INTEGRATION, 2, context)

        assert f"{context.pipeline_run_id}:UNIT:3" in adapter._repair_state
        assert f"{context.pipeline_run_id}:INTEGRATION:2" in adapter._repair_state


class TestExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_all_tests_pass(self):
        """Verify successful repair cycle execution."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=0,
            passes_on_iteration=1,
        )

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=3,
        )
        context = MockRepairCycleContext(test_configs=(config,))

        result = await adapter.execute(context)

        assert isinstance(result, RepairCycleResult)
        assert result.overall_success
        assert result.stage == "fix_failures"
        assert len(result.test_results) == 1

    @pytest.mark.asyncio
    async def test_execute_multiple_test_types(self):
        """Verify execution of multiple test types in sequence."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=0,
            passes_on_iteration=1,
        )
        adapter.add_test_scenario(
            test_type=RepairTestType.INTEGRATION,
            initial_failures=0,
            passes_on_iteration=1,
        )

        configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=900,
                max_iterations=3,
            ),
            RepairTestRunConfig(
                test_type=RepairTestType.INTEGRATION,
                timeout=900,
                max_iterations=3,
            ),
        )
        context = MockRepairCycleContext(test_configs=configs)

        result = await adapter.execute(context)

        assert result.overall_success
        assert len(result.test_results) == 2

    @pytest.mark.asyncio
    async def test_execute_stops_on_failure(self):
        """Verify execution stops when a test type fails."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=5,  # Will never pass with 1 iteration
            passes_on_iteration=None,  # Never passes
        )
        adapter.add_test_scenario(
            test_type=RepairTestType.INTEGRATION,
            initial_failures=0,
            passes_on_iteration=1,
        )

        configs = (
            RepairTestRunConfig(
                test_type=RepairTestType.UNIT,
                timeout=900,
                max_iterations=1,
            ),
            RepairTestRunConfig(
                test_type=RepairTestType.INTEGRATION,
                timeout=900,
                max_iterations=3,
            ),
        )
        context = MockRepairCycleContext(test_configs=configs)

        result = await adapter.execute(context)

        assert not result.overall_success
        # Should have stopped after UNIT failed
        assert len(result.test_results) == 1

    @pytest.mark.asyncio
    async def test_execute_emits_events(self):
        """Verify execute emits all required events."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        started_events = []
        completed_events = []
        adapter.on("repair_cycle.started", started_events.append)
        adapter.on("repair_cycle.completed", completed_events.append)

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )
        context = MockRepairCycleContext(test_configs=(config,))

        await adapter.execute(context)

        assert len(started_events) == 1
        assert len(completed_events) == 1
        assert isinstance(started_events[0], RepairCycleStartedEvent)
        assert isinstance(completed_events[0], RepairCycleCompletedEvent)

    @pytest.mark.asyncio
    async def test_execute_with_circuit_breaker_at_zero_calls(self):
        """Verify execute respects circuit breaker limit."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=5,
            passes_on_iteration=None,
        )

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )
        context = MockRepairCycleContext(
            test_configs=(config,),
            max_total_agent_calls=0,  # Circuit breaker immediately
        )

        result = await adapter.execute(context)

        # Circuit breaker should prevent execution (no tests run)
        assert len(result.test_results) == 0
        # Overall success is True because nothing failed (nothing ran)
        assert result.overall_success

    @pytest.mark.asyncio
    async def test_execute_no_project_no_events(self):
        """Verify no events emitted when current_project is None."""
        adapter = MockRepairCycleAdapter()
        # current_project is None by default

        started_events = []
        adapter.on("repair_cycle.started", started_events.append)

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )
        context = MockRepairCycleContext(test_configs=(config,))

        result = await adapter.execute(context)

        # Execute still works, but no events emitted
        assert result is not None
        assert len(started_events) == 0


class TestEventEmission:
    """Tests for event emission behavior."""

    @pytest.mark.asyncio
    async def test_event_subscription(self):
        """Verify event subscription works."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        events = []
        adapter.on("repair_cycle.started", events.append)

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )
        context = MockRepairCycleContext(test_configs=(config,))

        await adapter.execute(context)

        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_event_unsubscription(self):
        """Verify event unsubscription works."""
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        events = []
        handler = events.append
        adapter.on("repair_cycle.started", handler)
        adapter.off("repair_cycle.started", handler)

        config = RepairTestRunConfig(
            test_type=RepairTestType.UNIT,
            timeout=900,
            max_iterations=1,
        )
        context = MockRepairCycleContext(test_configs=(config,))

        await adapter.execute(context)

        assert len(events) == 0


class TestStateTracking:
    """Tests for internal state tracking."""

    @pytest.mark.asyncio
    async def test_iteration_tracking(self):
        """Verify iteration counting is tracked."""
        adapter = MockRepairCycleAdapter()

        iter1 = adapter._get_iteration_for_test_type(RepairTestType.UNIT)
        iter2 = adapter._get_iteration_for_test_type(RepairTestType.UNIT)
        iter3 = adapter._get_iteration_for_test_type(RepairTestType.UNIT)

        assert iter1 == 1
        assert iter2 == 2
        assert iter3 == 3

    def test_failure_grouping(self):
        """Verify failures are grouped correctly by file."""
        adapter = MockRepairCycleAdapter()

        failures = (
            RepairTestFailure(
                file="test_service.py",
                test="test_1",
                message="Error 1"
            ),
            RepairTestFailure(
                file="test_repo.py",
                test="test_2",
                message="Error 2"
            ),
            RepairTestFailure(
                file="test_service.py",
                test="test_3",
                message="Error 3"
            ),
        )

        grouped = adapter._group_failures_by_file(failures)

        assert len(grouped) == 2
        assert len(grouped["test_service.py"]) == 2
        assert len(grouped["test_repo.py"]) == 1
