"""In-memory repair cycle adapter with event simulation for testing.

This module provides a mock implementation of IRepairCycle that simulates the repair
cycle without actual test execution or agent calls. It supports deterministic test
results and configurable failure scenarios for comprehensive simulation testing.

The mock adapter:
1. Tracks repair cycle state (iterations, failures, fixes)
2. Emits repair cycle domain events
3. Provides test helper methods for simulating different scenarios
4. Supports fast forward time manipulation via simulation infrastructure
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, List
import time

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
from codetoreum.ports.output.repair_cycle_service import (
    IRepairCycle,
    RepairCycleContext,
)

from .mock_event_emitter import MockEventEmitter


class MockRepairCycleAdapter(MockEventEmitter, IRepairCycle):
    """In-memory repair cycle adapter with event simulation.

    Provides a mock implementation of IRepairCycle that:
    1. Stores repair cycle state in memory
    2. Emits repair cycle domain events
    3. Provides test helper methods for simulation
    4. Supports deterministic test scenarios

    Intended for testing and simulation without actual test execution or agent
    collaboration (actual pytest/jest runs, actual agent calls, etc.).

    The adapter simulates realistic repair cycle behavior including:
    - Configurable test failures and fixes
    - Iteration tracking and circuit breaker limits
    - Fast-fail scenarios and error conditions
    - Checkpoint state tracking for resume capability

    Example:
        # Setup
        adapter = MockRepairCycleAdapter()
        adapter.current_project = "proj-1"

        # Configure test scenario
        adapter.add_test_scenario(
            test_type=RepairTestType.UNIT,
            initial_failures=3,
            passes_on_iteration=2,
        )

        # Subscribe to events
        events = []
        adapter.on("repair_cycle.started", events.append)

        # Execute repair cycle
        result = await adapter.execute(context)

        # Verify
        assert result.overall_success
        assert len(events) >= 2
    """

    def __init__(self) -> None:
        """Initialize the repair cycle adapter."""
        super().__init__()
        self._scenarios: Dict[str, "TestScenario"] = {}  # test_type -> scenario
        self._current_project: Optional[str] = None
        self._repair_state: Dict[str, any] = {}  # For state tracking
        self._test_type_index: Dict[str, int] = {}  # For tracking test type index

    # Configuration Methods

    def add_test_scenario(
        self,
        test_type: RepairTestType,
        initial_failures: int = 0,
        passes_on_iteration: Optional[int] = None,
        warnings: int = 0,
        failures_per_file: Optional[Dict[str, int]] = None,
    ) -> None:
        """Configure how a test type behaves during simulation.

        Allows detailed control over test execution, failures, and fixes for
        comprehensive scenario testing.

        Args:
            test_type: Type of test (UNIT, INTEGRATION, E2E)
            initial_failures: Number of failures in first iteration
            passes_on_iteration: Which iteration will have all tests pass (None = never)
            warnings: Number of warnings to generate
            failures_per_file: Map of file name to failure count per file

        Example:
            adapter.add_test_scenario(
                test_type=RepairTestType.UNIT,
                initial_failures=3,
                passes_on_iteration=2,
                failures_per_file={
                    "tests/unit/test_service.py": 2,
                    "tests/unit/test_repo.py": 1,
                }
            )
        """
        self._scenarios[test_type.value] = TestScenario(
            test_type=test_type,
            initial_failures=initial_failures,
            passes_on_iteration=passes_on_iteration,
            warnings=warnings,
            failures_per_file=failures_per_file or {},
        )

    @property
    def current_project(self) -> Optional[str]:
        """Get current project ID."""
        return self._current_project

    @current_project.setter
    def current_project(self, project_id: Optional[str]) -> None:
        """Set current project ID for event emission."""
        self._current_project = project_id

    # Core Repair Cycle Methods

    async def execute(self, context: RepairCycleContext) -> RepairCycleResult:
        """Execute complete repair cycle for all configured test types.

        Orchestrates the full test-fix-validate loop across all configured test
        types in sequence. For each test type, runs tests, analyzes failures,
        coordinates fixes, and validates until tests pass or circuit breaker triggers.

        Args:
            context: Repair cycle execution context with configuration

        Returns:
            RepairCycleResult with overall success and per-test-type results

        Raises:
            ValueError: If test_configs is empty
        """
        if not context.test_configs:
            raise ValueError("test_configs cannot be empty")

        start_time = time.time()
        cycle_start_timestamp = self._get_iso_timestamp()

        # Emit repair cycle started event
        if self._current_project is not None:
            self.emit(RepairCycleStartedEvent(
                type="repair_cycle.started",
                timestamp=cycle_start_timestamp,
                source="mock_repair_cycle",
                stage_name=context.stage_name,
                test_types=tuple(cfg.test_type for cfg in context.test_configs),
                pipeline_run_id=context.pipeline_run_id,
            ))

        # Execute each test type in sequence
        test_results: List[CycleResult] = []
        total_agent_calls = 0
        overall_success = True

        for test_type_index, test_config in enumerate(context.test_configs, start=1):
            self._test_type_index[test_config.test_type.value] = test_type_index

            # Check circuit breaker before starting test type
            if total_agent_calls >= context.max_total_agent_calls:
                if self._current_project is not None:
                    self.emit(RepairCycleFastFailEvent(
                        type="repair_cycle.fast_fail",
                        timestamp=self._get_iso_timestamp(),
                        source="mock_repair_cycle",
                        test_type=test_config.test_type,
                        reason="circuit_breaker_triggered",
                    ))
                break

            # Execute test type cycle
            cycle_result, calls_made = await self._execute_test_type_cycle(
                test_config=test_config,
                test_type_index=test_type_index,
                context=context,
                agent_calls_so_far=total_agent_calls,
            )

            test_results.append(cycle_result)
            total_agent_calls += calls_made

            # If this test type failed, stop cycling through remaining types
            if not cycle_result.passed:
                overall_success = False
                break

        # Emit cycle completed event (only if we have results)
        duration_seconds = time.time() - start_time
        if self._current_project is not None and test_results:
            self.emit(RepairCycleCompletedEvent(
                type="repair_cycle.completed",
                timestamp=cycle_start_timestamp,
                source="mock_repair_cycle",
                overall_success=overall_success,
                test_results=tuple(test_results),
                total_agent_calls=total_agent_calls,
                duration_seconds=duration_seconds,
                pipeline_run_id=context.pipeline_run_id,
            ))

        return RepairCycleResult(
            stage=context.stage_name,
            test_results=tuple(test_results),
            overall_success=overall_success,
            total_agent_calls=total_agent_calls,
            duration_seconds=duration_seconds,
            timestamp=cycle_start_timestamp,
        )

    async def run_tests(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RepairTestResult:
        """Execute tests for a specific test type.

        Simulates test execution for the given test type, returning deterministic
        results based on configured scenarios.

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            RepairTestResult with pass/fail counts and failure details
        """
        scenario = self._scenarios.get(config.test_type.value)
        if not scenario:
            # No scenario configured: all tests pass
            result = RepairTestResult(
                test_type=config.test_type,
                iteration=1,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All tests passed",
                timestamp=self._get_iso_timestamp(),
            )
        else:
            current_iteration = self._get_iteration_for_test_type(config.test_type)
            result = scenario.get_result_for_iteration(current_iteration)

        return result

    async def fix_failures_by_file(
        self,
        grouped_failures: Dict[str, Tuple[RepairTestFailure, ...]],
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Fix test failures grouped by file.

        Simulates the agent fixing failures for each file. Tracks which files
        have been fixed and emits events accordingly.

        Args:
            grouped_failures: Map of test file name to failures in that file
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Number of files fixed
        """
        test_type_index = self._test_type_index.get(config.test_type.value, 1)
        files_fixed = 0

        for file_path, failures in grouped_failures.items():
            if self._current_project is not None:
                self.emit(RepairCycleFileFixStartedEvent(
                    type="repair_cycle.file_fix_started",
                    timestamp=self._get_iso_timestamp(),
                    source="mock_repair_cycle",
                    test_file=file_path,
                    failure_count=len(failures),
                    test_type=config.test_type,
                    pipeline_run_id=context.pipeline_run_id,
                ))

            # Simulate agent fixing the file
            files_fixed += 1

            if self._current_project is not None:
                self.emit(RepairCycleFileFixCompletedEvent(
                    type="repair_cycle.file_fix_completed",
                    timestamp=self._get_iso_timestamp(),
                    source="mock_repair_cycle",
                    test_file=file_path,
                    failure_count=len(failures),
                    test_type=config.test_type,
                    success=True,
                    pipeline_run_id=context.pipeline_run_id,
                ))

        return files_fixed

    async def handle_warnings(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Review and fix warnings from test execution.

        Only called when tests pass, warnings exist, and review_warnings is True.
        Simulates the agent reviewing and addressing warnings.

        Args:
            test_result: Test result containing warnings
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Number of warning files reviewed
        """
        if not test_result.warning_list or not config.review_warnings:
            return 0

        test_type_index = self._test_type_index.get(config.test_type.value, 1)

        # Determine warning file (use first warning file if available)
        warning_file = ""
        if test_result.warning_list:
            warning_file = test_result.warning_list[0].file

        if self._current_project is not None:
            self.emit(RepairCycleWarningReviewStartedEvent(
                type="repair_cycle.warning_review_started",
                timestamp=self._get_iso_timestamp(),
                source="mock_repair_cycle",
                source_file=warning_file,
                warning_count=len(test_result.warning_list),
                test_type=config.test_type,
                warnings=test_result.warning_list,
            ))

        # Simulate agent reviewing warnings
        warnings_reviewed = len(test_result.warning_list)

        if self._current_project is not None:
            self.emit(RepairCycleWarningReviewCompletedEvent(
                type="repair_cycle.warning_review_completed",
                timestamp=self._get_iso_timestamp(),
                source="mock_repair_cycle",
                source_file=warning_file,
                warning_count=len(test_result.warning_list),
                test_type=config.test_type,
                success=True,
            ))

        return warnings_reviewed

    async def checkpoint(
        self,
        test_type: RepairTestType,
        iteration: int,
        context: RepairCycleContext,
    ) -> None:
        """Save repair cycle state for resume after failures.

        Called at checkpoint_interval iterations. For mock adapter, just
        stores state in memory.

        Args:
            test_type: Current test type being executed
            iteration: Current iteration number
            context: Repair cycle context
        """
        checkpoint_key = f"{context.pipeline_run_id}:{test_type.value}:{iteration}"
        self._repair_state[checkpoint_key] = {
            'test_type': test_type.value,
            'iteration': iteration,
            'timestamp': self._get_iso_timestamp(),
        }

    # Private Helper Methods

    async def _execute_test_type_cycle(
        self,
        test_config: RepairTestRunConfig,
        test_type_index: int,
        context: RepairCycleContext,
        agent_calls_so_far: int,
    ) -> Tuple[CycleResult, int]:
        """Execute full cycle for a single test type.

        Orchestrates the test-fix-validate loop for a single test type,
        updating iteration count and agent calls.

        Returns:
            Tuple of (CycleResult, number_of_agent_calls_made)
        """
        iterations = 0
        files_fixed = 0
        warnings_reviewed = 0
        agent_calls = 0
        cycle_passed = False
        error = None
        cycle_start = time.time()

        # Iterate up to max_iterations
        for iteration in range(1, test_config.max_iterations + 1):
            iterations = iteration

            # Run tests
            test_result = await self.run_tests(test_config, context)

            # Check if tests passed
            if test_result.failed == 0:
                cycle_passed = True

                # Handle warnings if configured
                if test_config.review_warnings and test_result.warnings > 0:
                    warnings_reviewed += await self.handle_warnings(
                        test_result, test_config, context
                    )
                    agent_calls += 1

                # Emit test cycle completed
                if self._current_project is not None:
                    self.emit(RepairCycleTestCycleCompletedEvent(
                        type="repair_cycle.test_cycle_completed",
                        timestamp=self._get_iso_timestamp(),
                        source="mock_repair_cycle",
                        test_type=test_config.test_type,
                        test_type_index=test_type_index,
                        passed=0,
                        test_cycle_iterations=iterations,
                        files_fixed=files_fixed,
                        warnings_reviewed=warnings_reviewed,
                        error=None,
                        duration_seconds=time.time() - cycle_start,
                        pipeline_run_id=context.pipeline_run_id,
                    ))

                break

            # Group failures by file and fix
            grouped_failures = self._group_failures_by_file(test_result.failures)
            files_fixed += await self.fix_failures_by_file(
                grouped_failures, test_config, context
            )
            agent_calls += 1

            # Check circuit breaker
            total_calls = agent_calls_so_far + agent_calls
            if total_calls >= context.max_total_agent_calls:
                if self._current_project is not None:
                    self.emit(RepairCycleFastFailEvent(
                        type="repair_cycle.fast_fail",
                        timestamp=self._get_iso_timestamp(),
                        source="mock_repair_cycle",
                        test_type=test_config.test_type,
                        reason="circuit_breaker_triggered",
                    ))
                error = "Circuit breaker triggered"
                break

            # Checkpoint at interval
            if iteration % context.checkpoint_interval == 0:
                await self.checkpoint(test_config.test_type, iteration, context)

        # If not passed after max iterations
        if not cycle_passed:
            if self._current_project is not None:
                self.emit(RepairCycleTestCycleCompletedEvent(
                    type="repair_cycle.test_cycle_completed",
                    timestamp=self._get_iso_timestamp(),
                    source="mock_repair_cycle",
                    test_type=test_config.test_type,
                    test_type_index=test_type_index,
                    passed=0,
                    test_cycle_iterations=iterations,
                    files_fixed=files_fixed,
                    warnings_reviewed=warnings_reviewed,
                    error=error,
                    duration_seconds=time.time() - cycle_start,
                    pipeline_run_id=context.pipeline_run_id,
                ))

        duration_seconds = time.time() - cycle_start

        # Get final result (if available)
        final_result = None
        if cycle_passed:
            final_result = await self.run_tests(test_config, context)

        cycle_result = CycleResult(
            test_type=test_config.test_type,
            passed=cycle_passed,
            iterations=iterations,
            final_result=final_result,
            error=error,
            files_fixed=files_fixed,
            warnings_reviewed=warnings_reviewed,
            duration_seconds=duration_seconds,
        )

        return cycle_result, agent_calls

    def _group_failures_by_file(
        self,
        failures: Tuple[RepairTestFailure, ...]
    ) -> Dict[str, Tuple[RepairTestFailure, ...]]:
        """Group test failures by file."""
        grouped: Dict[str, List[RepairTestFailure]] = {}
        for failure in failures:
            if failure.file not in grouped:
                grouped[failure.file] = []
            grouped[failure.file].append(failure)

        return {file: tuple(fs) for file, fs in grouped.items()}

    def _get_iteration_for_test_type(self, test_type: RepairTestType) -> int:
        """Get current iteration number for a test type."""
        key = f"iteration:{test_type.value}"
        current = self._repair_state.get(key, 0)
        self._repair_state[key] = current + 1
        return current + 1

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current time as ISO 8601 timestamp."""
        return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TestScenario:
    """Internal: Represents a configured test scenario for a test type."""

    test_type: RepairTestType
    initial_failures: int
    passes_on_iteration: Optional[int]
    warnings: int
    failures_per_file: Dict[str, int]

    def get_result_for_iteration(self, iteration: int) -> RepairTestResult:
        """Generate test result for given iteration."""
        # Determine if this iteration passes
        if (
            self.passes_on_iteration is not None
            and iteration >= self.passes_on_iteration
        ):
            # Tests pass from this iteration onward
            return self._create_passing_result(iteration)
        else:
            # Failures decrease as iterations progress
            failure_count = max(0, self.initial_failures - (iteration - 1))
            if failure_count == 0:
                return self._create_passing_result(iteration)
            else:
                return self._create_failing_result(iteration, failure_count)

    def _create_passing_result(self, iteration: int) -> RepairTestResult:
        """Create a passing test result."""
        warning_list = ()
        if self.warnings > 0:
            warning_list = tuple(
                RepairTestWarning(
                    file=f"src/module_{i}.py",
                    message=f"Warning {i}: Deprecation notice"
                )
                for i in range(self.warnings)
            )

        return RepairTestResult(
            test_type=self.test_type,
            iteration=iteration,
            passed=100,
            failed=0,
            warnings=self.warnings,
            failures=(),
            warning_list=warning_list,
            raw_output="All tests passed",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _create_failing_result(
        self,
        iteration: int,
        failure_count: int
    ) -> RepairTestResult:
        """Create a failing test result."""
        failures = []
        for i in range(failure_count):
            file_idx = i % len(self.failures_per_file) if self.failures_per_file else 0
            file_name = (
                list(self.failures_per_file.keys())[file_idx]
                if self.failures_per_file
                else f"tests/test_{i}.py"
            )
            failures.append(
                RepairTestFailure(
                    file=file_name,
                    test=f"test_case_{i}",
                    message=f"AssertionError: Expected value != actual (iteration {iteration})"
                )
            )

        return RepairTestResult(
            test_type=self.test_type,
            iteration=iteration,
            passed=100 - failure_count,
            failed=failure_count,
            warnings=0,
            failures=tuple(failures),
            warning_list=(),
            raw_output=f"{failure_count} tests failed",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
