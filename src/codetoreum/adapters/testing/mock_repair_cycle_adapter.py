"""In-memory repair cycle adapter with event simulation for testing.

This module provides a mock implementation of IRepairCycle that simulates the repair
cycle without actual test execution or agent calls. It supports deterministic test
results and configurable failure scenarios for comprehensive simulation testing.

The mock adapter:
1. Tracks repair cycle state (iterations, failures, fixes)
2. Emits repair cycle domain events
3. Provides test helper methods for simulating different scenarios
4. Supports deterministic time manipulation via SimulationClock
5. Logs all events for assertion verification
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.repair_cycle_service import (
    IRepairCycle,
    RepairCycleContext,
)
from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter


class CircuitBreakerTripped(Exception):
    """Raised when max agent calls exceeded during repair cycle."""
    pass


class MockRepairCycleAdapter(MockEventEmitter, IRepairCycle):
    """Deterministic mock adapter for repair cycle simulation testing.

    Provides:
    - Configurable test result sequences per test type (FR-11.2)
    - Shorthand configuration methods (FR-11.3, FR-11.4)
    - SimulationClock integration for deterministic time (FR-11.5)
    - Clock advancement: 30s per test, 2min per fix, 1min per warning (FR-11.6-11.8)
    - Event logging with simulated timestamps (FR-11.9)
    - Event log retrieval methods (FR-11.10)
    - Assertion helpers for test verification (FR-12.1-12.7)
    - Circuit breaker support with max agent calls (FR-7.1-7.5)

    Example:
        # Setup with clock
        clock = SimulationClock()
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "proj-1"

        # Configure via sequence
        adapter.set_test_result_sequence(
            RepairTestType.UNIT,
            [result1, result2, result3]
        )

        # Or use shorthand
        adapter.set_iterations_until_success(RepairTestType.UNIT, 2)

        # Execute and verify
        result = await adapter.execute(context)
        adapter.assert_iteration_count(RepairTestType.UNIT, 2)
        adapter.assert_overall_success()
    """

    def __init__(self, clock: SimulationClock):
        """Initialize the repair cycle adapter with SimulationClock.

        Args:
            clock: SimulationClock instance for deterministic time advancement
        """
        super().__init__()
        self.clock = clock
        self._current_project: Optional[str] = None
        self._repair_state: Dict[str, Any] = {}
        self._test_type_index: Dict[str, int] = {}
        self.agent_call_count = 0
        self.max_total_agent_calls = 100
        self.event_log: List[Dict[str, Any]] = []
        self.test_results: Dict[RepairTestType, List[RepairTestResult]] = {}

    # Configuration methods (FR-11.2, FR-11.3, FR-11.4)

    def set_test_result_sequence(
        self,
        test_type: RepairTestType,
        results: List[RepairTestResult]
    ) -> None:
        """Configure exact test result sequence for a test type (FR-11.2).

        Args:
            test_type: Type of test (UNIT, INTEGRATION, E2E)
            results: List of test results in sequence order
        """
        self.test_results[test_type] = results

    def set_iterations_until_success(
        self,
        test_type: RepairTestType,
        iterations: int
    ) -> None:
        """Configure N iterations with last one succeeding (FR-11.3).

        Shorthand for configuring a gradual convergence scenario where
        failures decrease until the final iteration passes.

        Args:
            test_type: Type of test (UNIT, INTEGRATION, E2E)
            iterations: Number of iterations until success
        """
        results = []
        for i in range(1, iterations + 1):
            is_last = (i == iterations)
            results.append(RepairTestResult(
                test_type=test_type,
                iteration=i,
                passed=10 if is_last else 7,
                failed=0 if is_last else 3,
                warnings=0,
                failures=() if is_last else (
                    RepairTestFailure(
                        file="test_example.py",
                        test=f"test_case_{i}",
                        message="Simulated failure"
                    ),
                ),
                warning_list=(),
                raw_output="",
                timestamp=self.clock.now().isoformat()
            ))
        self.test_results[test_type] = results

    def set_always_fail(
        self,
        test_type: RepairTestType,
        max_iterations: int
    ) -> None:
        """Configure to always fail for max iterations (FR-11.4).

        Shorthand for configuring a scenario that never passes,
        simulating code that cannot be fixed within max iterations.

        Args:
            test_type: Type of test (UNIT, INTEGRATION, E2E)
            max_iterations: Maximum iterations before failure
        """
        results = []
        for i in range(1, max_iterations + 1):
            results.append(RepairTestResult(
                test_type=test_type,
                iteration=i,
                passed=7,
                failed=3,
                warnings=0,
                failures=(
                    RepairTestFailure(
                        file="test_stubborn.py",
                        test="test_always_fails",
                        message="Cannot be fixed"
                    ),
                ),
                warning_list=(),
                raw_output="",
                timestamp=self.clock.now().isoformat()
            ))
        self.test_results[test_type] = results

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
            CircuitBreakerTripped: If max agent calls exceeded
        """
        if not context.test_configs:
            raise ValueError("test_configs cannot be empty")

        start_time = self.clock.now()
        cycle_start_timestamp = start_time.isoformat()

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
            self._log_event({
                "type": "REPAIR_CYCLE_STARTED",
                "stage_name": context.stage_name,
            })

        # Execute each test type in sequence
        test_results: List[CycleResult] = []
        overall_success = True

        for test_type_index, test_config in enumerate(context.test_configs, start=1):
            self._test_type_index[test_config.test_type.value] = test_type_index

            # Check circuit breaker before starting test type
            if self.agent_call_count >= context.max_total_agent_calls:
                if self._current_project is not None:
                    self.emit(RepairCycleFastFailEvent(
                        type="repair_cycle.fast_fail",
                        timestamp=self.clock.now().isoformat(),
                        source="mock_repair_cycle",
                        test_type=test_config.test_type,
                        reason="circuit_breaker_triggered",
                    ))
                break

            # Execute test type cycle
            cycle_result = await self._run_test_cycle(
                config=test_config,
                context=context,
                test_type_index=test_type_index,
            )

            test_results.append(cycle_result)

            # If this test type failed, stop cycling through remaining types (fast-fail)
            if not cycle_result.passed:
                overall_success = False
                break

        # Emit cycle completed event (only if we have results)
        end_time = self.clock.now()
        duration_seconds = (end_time - start_time).total_seconds()

        if self._current_project is not None and test_results:
            self.emit(RepairCycleCompletedEvent(
                type="repair_cycle.completed",
                timestamp=cycle_start_timestamp,
                source="mock_repair_cycle",
                overall_success=overall_success,
                test_results=tuple(test_results),
                total_agent_calls=self.agent_call_count,
                duration_seconds=duration_seconds,
                pipeline_run_id=context.pipeline_run_id,
            ))
            self._log_event({
                "type": "REPAIR_CYCLE_COMPLETED",
                "overall_success": overall_success,
            })

        return RepairCycleResult(
            stage=context.stage_name,
            test_results=tuple(test_results),
            overall_success=overall_success,
            total_agent_calls=self.agent_call_count,
            duration_seconds=duration_seconds,
            timestamp=cycle_start_timestamp,
        )

    async def run_tests(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RepairTestResult:
        """Execute tests for a specific test type (FR-11.6).

        Clock advances 30 seconds per test execution.

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            RepairTestResult with pass/fail counts and failure details
        """
        self.agent_call_count += 1
        await self.clock.advance(timedelta(seconds=30))

        # Get configured result for this test type
        sequence = self.test_results.get(config.test_type, [])
        iteration = self._get_iteration_for_test_type(config.test_type)

        if iteration <= len(sequence):
            result = sequence[iteration - 1]
            # Create a new result with updated timestamp
            result = RepairTestResult(
                test_type=result.test_type,
                iteration=result.iteration,
                passed=result.passed,
                failed=result.failed,
                warnings=result.warnings,
                failures=result.failures,
                warning_list=result.warning_list,
                raw_output=result.raw_output,
                timestamp=self.clock.now().isoformat(),
            )
        else:
            # Default: success
            result = RepairTestResult(
                test_type=config.test_type,
                iteration=iteration,
                passed=10,
                failed=0,
                warnings=0,
                failures=(),
                warning_list=(),
                raw_output="All tests passed",
                timestamp=self.clock.now().isoformat(),
            )

        self._log_event({
            "type": "TEST_EXECUTION_COMPLETED",
            "test_type": config.test_type.value,
            "iteration": iteration,
            "passed": result.passed,
            "failed": result.failed
        })

        if self._current_project is not None:
            self.emit(RepairCycleTestExecutionCompletedEvent(
                type="repair_cycle.test_execution_completed",
                timestamp=self.clock.now().isoformat(),
                source="mock_repair_cycle",
                test_type=config.test_type,
                test_type_index=self._test_type_index.get(config.test_type.value, 1),
                test_cycle_iteration=iteration,
                passed=result.passed,
                failed=result.failed,
                warnings=result.warnings,
                has_failures=(result.failed > 0),
                failures=result.failures,
                pipeline_run_id=context.pipeline_run_id,
            ))

        return result

    async def fix_failures_by_file(
        self,
        grouped_failures: Dict[str, Tuple[RepairTestFailure, ...]],
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Fix failures grouped by file (FR-11.7).

        Clock advances 2 minutes per file fixed.

        Args:
            grouped_failures: Map of test file name to failures in that file
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Number of files fixed
        """
        fixed = 0

        for file_path, failures in grouped_failures.items():
            self.agent_call_count += 1
            await self.clock.advance(timedelta(minutes=2))

            if self._current_project is not None:
                self.emit(RepairCycleFileFixStartedEvent(
                    type="repair_cycle.file_fix_started",
                    timestamp=self.clock.now().isoformat(),
                    source="mock_repair_cycle",
                    test_file=file_path,
                    failure_count=len(failures),
                    test_type=config.test_type,
                    pipeline_run_id=context.pipeline_run_id,
                ))

                self.emit(RepairCycleFileFixCompletedEvent(
                    type="repair_cycle.file_fix_completed",
                    timestamp=self.clock.now().isoformat(),
                    source="mock_repair_cycle",
                    test_file=file_path,
                    failure_count=len(failures),
                    test_type=config.test_type,
                    success=True,
                    pipeline_run_id=context.pipeline_run_id,
                ))

            fixed += 1

        return fixed

    async def handle_warnings(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Review and fix warnings from test execution (FR-11.8).

        Clock advances 1 minute per warning file reviewed.

        Args:
            test_result: Test result containing warnings
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Number of warning files reviewed
        """
        if not test_result.warning_list or not config.review_warnings:
            return 0

        reviewed = 0

        for warning in test_result.warning_list:
            self.agent_call_count += 1
            await self.clock.advance(timedelta(minutes=1))

            if self._current_project is not None:
                self.emit(RepairCycleWarningReviewStartedEvent(
                    type="repair_cycle.warning_review_started",
                    timestamp=self.clock.now().isoformat(),
                    source="mock_repair_cycle",
                    source_file=warning.file,
                    warning_count=1,
                    test_type=config.test_type,
                    warnings=(warning,),
                ))

                self.emit(RepairCycleWarningReviewCompletedEvent(
                    type="repair_cycle.warning_review_completed",
                    timestamp=self.clock.now().isoformat(),
                    source="mock_repair_cycle",
                    source_file=warning.file,
                    warning_count=1,
                    test_type=config.test_type,
                    success=True,
                ))

            reviewed += 1

        return reviewed

    async def checkpoint(
        self,
        test_type: RepairTestType,
        iteration: int,
        context: RepairCycleContext,
    ) -> None:
        """Save repair cycle state for resume after failures.

        Args:
            test_type: Current test type being executed
            iteration: Current iteration number
            context: Repair cycle context
        """
        checkpoint_key = f"{context.pipeline_run_id}:{test_type.value}:{iteration}"
        self._repair_state[checkpoint_key] = {
            'test_type': test_type.value,
            'iteration': iteration,
            'timestamp': self.clock.now().isoformat(),
        }

        self._log_event({
            "type": "CHECKPOINT_SAVED",
            "test_type": test_type.value,
            "iteration": iteration
        })

    # Event log retrieval (FR-11.10)

    def get_all_events(self) -> List[Dict[str, Any]]:
        """Return all logged events.

        Returns:
            List of event dictionaries with timestamps
        """
        return list(self.event_log)

    def get_events_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """Return events of specific type.

        Args:
            event_type: Event type to filter by

        Returns:
            List of events matching the type
        """
        return [e for e in self.event_log if e.get("type") == event_type]

    # Assertion helpers (FR-12.1-12.7)

    def assert_iteration_count(self, test_type: RepairTestType, expected: int) -> None:
        """Assert test type took expected iterations.

        Args:
            test_type: Type of test to check
            expected: Expected number of iterations

        Raises:
            AssertionError: If iteration count doesn't match
        """
        events = self.get_events_by_type("TEST_CYCLE_COMPLETED")
        event = next(
            (e for e in events if e.get("test_type") == test_type.value),
            None
        )
        if not event:
            raise AssertionError(f"No completion event found for {test_type.value}")
        if event.get("iterations") != expected:
            raise AssertionError(
                f"Expected {expected} iterations for {test_type.value}, "
                f"got {event.get('iterations')}"
            )

    def assert_test_type_passed(self, test_type: RepairTestType) -> None:
        """Assert test type passed.

        Args:
            test_type: Type of test to check

        Raises:
            AssertionError: If test type didn't pass
        """
        events = self.get_events_by_type("TEST_CYCLE_COMPLETED")
        event = next(
            (e for e in events if e.get("test_type") == test_type.value),
            None
        )
        if not event or not event.get("passed"):
            raise AssertionError(f"Expected {test_type.value} to pass")

    def assert_test_type_failed(self, test_type: RepairTestType) -> None:
        """Assert test type failed.

        Args:
            test_type: Type of test to check

        Raises:
            AssertionError: If test type passed
        """
        events = self.get_events_by_type("TEST_CYCLE_COMPLETED")
        event = next(
            (e for e in events if e.get("test_type") == test_type.value),
            None
        )
        if not event or event.get("passed"):
            raise AssertionError(f"Expected {test_type.value} to fail")

    def assert_fast_fail(self, test_type: RepairTestType) -> None:
        """Assert fast-fail occurred after test type.

        Args:
            test_type: Type of test that should trigger fast-fail

        Raises:
            AssertionError: If fast-fail didn't occur
        """
        event = next(
            (e for e in self.event_log
             if e.get("type") == "REPAIR_CYCLE_FAST_FAIL"
             and e.get("test_type") == test_type.value),
            None
        )
        if not event:
            raise AssertionError(f"Expected fast-fail after {test_type.value}")

    def assert_overall_success(self) -> None:
        """Assert overall cycle succeeded.

        Raises:
            AssertionError: If cycle didn't succeed overall
        """
        event = next(
            (e for e in self.event_log
             if e.get("type") == "REPAIR_CYCLE_COMPLETED"),
            None
        )
        if not event or not event.get("overall_success"):
            raise AssertionError("Expected overall success")

    def assert_overall_failure(self) -> None:
        """Assert overall cycle failed.

        Raises:
            AssertionError: If cycle succeeded
        """
        event = next(
            (e for e in self.event_log
             if e.get("type") == "REPAIR_CYCLE_COMPLETED"),
            None
        )
        if not event or event.get("overall_success"):
            raise AssertionError("Expected overall failure")

    def get_agent_call_count(self) -> int:
        """Return total agent calls made.

        Returns:
            Total number of agent calls
        """
        return self.agent_call_count

    # Private helper methods

    async def _run_test_cycle(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
        test_type_index: int,
    ) -> CycleResult:
        """Execute full cycle for a single test type.

        Orchestrates the test-fix-validate loop for a single test type,
        updating iteration count and agent calls.

        Returns:
            CycleResult with outcomes and metrics
        """
        iteration = 0
        files_fixed = 0
        warnings_reviewed = 0
        cycle_passed = False
        error = None
        start_time = self.clock.now()

        self._log_event({
            "type": "TEST_CYCLE_STARTED",
            "test_type": config.test_type.value,
            "max_iterations": config.max_iterations
        })

        for iteration in range(1, config.max_iterations + 1):
            # Check circuit breaker
            if self.agent_call_count >= context.max_total_agent_calls:
                if self._current_project is not None:
                    self.emit(RepairCycleFastFailEvent(
                        type="repair_cycle.fast_fail",
                        timestamp=self.clock.now().isoformat(),
                        source="mock_repair_cycle",
                        test_type=config.test_type,
                        reason="circuit_breaker_triggered",
                    ))
                error = "Circuit breaker: max agent calls reached"
                break

            # Run tests
            test_result = await self.run_tests(config, context)

            # Check for success
            if test_result.failed == 0:
                cycle_passed = True

                # Handle warnings if configured
                if config.review_warnings and test_result.warnings > 0:
                    warnings_reviewed += await self.handle_warnings(
                        test_result, config, context
                    )

                    # Re-test after warning fixes
                    retest = await self.run_tests(config, context)
                    if retest.failed > 0:
                        # Warning fixes broke something, continue fixing
                        cycle_passed = False
                        # Fall through to fix failures again
                    else:
                        # Warnings fixed, success
                        break
                else:
                    # Success, no warnings to handle
                    break

            # Fix failures
            if not cycle_passed:
                grouped = self._group_failures_by_file(test_result.failures)
                files_fixed += await self.fix_failures_by_file(
                    grouped, config, context
                )

            # Checkpoint at interval
            if iteration % context.checkpoint_interval == 0:
                await self.checkpoint(config.test_type, iteration, context)

        # Emit test cycle completed
        if self._current_project is not None:
            self.emit(RepairCycleTestCycleCompletedEvent(
                type="repair_cycle.test_cycle_completed",
                timestamp=self.clock.now().isoformat(),
                source="mock_repair_cycle",
                test_type=config.test_type,
                test_type_index=test_type_index,
                passed=1 if cycle_passed else 0,
                test_cycle_iterations=iteration,
                files_fixed=files_fixed,
                warnings_reviewed=warnings_reviewed,
                error=error,
                duration_seconds=(self.clock.now() - start_time).total_seconds(),
                pipeline_run_id=context.pipeline_run_id,
            ))

        self._log_event({
            "type": "TEST_CYCLE_COMPLETED",
            "test_type": config.test_type.value,
            "passed": cycle_passed,
            "iterations": iteration,
            "error": error
        })

        duration_seconds = (self.clock.now() - start_time).total_seconds()

        return CycleResult(
            test_type=config.test_type,
            passed=cycle_passed,
            iterations=iteration,
            final_result=None,
            error=error,
            files_fixed=files_fixed,
            warnings_reviewed=warnings_reviewed,
            duration_seconds=duration_seconds,
        )

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

    def _log_event(self, event: Dict[str, Any]) -> None:
        """Log event with timestamp (FR-11.9)."""
        event["timestamp"] = self.clock.now().isoformat()
        self.event_log.append(event)
