"""Mock repair cycle adapter for testing and simulation.

Provides an in-memory implementation of IRepairCycle for testing repair cycle
orchestration logic without external services.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    RepairCycleContext,
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
from codetoreum.ports.output.monitoring import MonitoringConfig, MonitoringStatus
from codetoreum.ports.output.repair_cycle_service import IRepairCycle
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock

logger = logging.getLogger(__name__)


class MockRepairCycleAdapter(IRepairCycle):
    """Mock in-memory implementation of IRepairCycle for testing.

    Features:
    - Configurable iterations until success per test type
    - Deterministic test results for reproducible testing
    - Event emission tracking for verification
    - State tracking (agent calls, iterations, files fixed)
    - Support for simulation mode with fixed clock

    Usage in tests:
        adapter = MockRepairCycleAdapter(clock)
        adapter.current_project = "test-proj"
        adapter.set_iterations_until_success(RepairTestType.UNIT, 1)

        result = await adapter.execute(context)
        assert result.overall_success
    """

    def __init__(self, clock: Optional[SimulationClock] = None) -> None:
        """Initialize mock adapter.

        Args:
            clock: Optional SimulationClock for time control in tests
        """
        self._clock = clock or SimulationClock()
        self._events: List[dict] = []
        self._event_handlers: Dict[str, List] = {}
        self._monitoring: Dict[str, MonitoringStatus] = {}
        self._lock = threading.Lock()

        # Configuration for test behavior
        self._iterations_until_success: Dict[str, int] = {}  # test_type -> iterations_count
        self._failures_per_type: Dict[str, Tuple[RepairTestFailure, ...]] = {}
        self._warnings_per_type: Dict[str, Tuple[RepairTestWarning, ...]] = {}

        # State tracking
        self.current_project: Optional[str] = None
        self.total_agent_calls = 0
        self.total_iterations = 0

    def set_iterations_until_success(self, test_type: RepairTestType, iterations: int) -> None:
        """Configure how many iterations until tests pass.

        Args:
            test_type: Test type (UNIT, INTEGRATION, E2E)
            iterations: Number of iterations before success (>= 1)
        """
        self._iterations_until_success[test_type.value] = max(1, iterations)

    def set_failures(self, test_type: RepairTestType, failures: Tuple[RepairTestFailure, ...]) -> None:
        """Configure failures for a test type.

        Args:
            test_type: Test type
            failures: Tuple of failures to return
        """
        self._failures_per_type[test_type.value] = failures

    def set_warnings(self, test_type: RepairTestType, warnings: Tuple[RepairTestWarning, ...]) -> None:
        """Configure warnings for a test type.

        Args:
            test_type: Test type
            warnings: Tuple of warnings to return
        """
        self._warnings_per_type[test_type.value] = warnings

    def get_all_events(self) -> List[dict]:
        """Get all emitted events."""
        with self._lock:
            return list(self._events)

    def _emit_event(self, event_type: str, event: object) -> None:
        """Emit an event and call handlers."""
        with self._lock:
            event_dict = {
                "type": event_type,
                "event": event,
                "timestamp": self._clock.now().isoformat(),
            }
            self._events.append(event_dict)

        # Call handlers
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler for {event_type}: {e}")

    # ==================== IEventEmitter Implementation ====================

    def on(self, event_type: str, handler) -> None:
        """Register event handler."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def off(self, event_type: str, handler) -> None:
        """Unregister event handler."""
        if event_type in self._event_handlers:
            try:
                self._event_handlers[event_type].remove(handler)
            except ValueError:
                pass

    def emit(self, event) -> None:
        """Emit an event to all subscribers."""
        # Get event type from the event
        event_type = getattr(event, "type", "unknown")
        self._emit_event(event_type, event)

    # ==================== IMonitoredService Implementation ====================

    async def start_monitoring(
        self,
        project_id: str,
        config: MonitoringConfig,
    ) -> None:
        """Start monitoring (no-op for mock)."""
        with self._lock:
            self._monitoring[project_id] = MonitoringStatus(
                project_id=project_id,
                is_monitoring=True,
                last_check=self._clock.now().isoformat(),
                error_count=0,
            )

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring (no-op for mock)."""
        with self._lock:
            if project_id in self._monitoring:
                self._monitoring[project_id] = MonitoringStatus(
                    project_id=project_id,
                    is_monitoring=False,
                    last_check=self._clock.now().isoformat(),
                    error_count=0,
                )

    async def get_monitoring_status(self, project_id: str) -> Optional[MonitoringStatus]:
        """Get monitoring status."""
        with self._lock:
            return self._monitoring.get(project_id)

    # ==================== IRepairCycle Implementation ====================

    async def execute(self, context: RepairCycleContext) -> RepairCycleResult:
        """Execute complete repair cycle."""
        start_time = self._clock.now()
        self.total_agent_calls = 0
        self.total_iterations = 0

        # Emit start event
        self._emit_event(
            "repair_cycle.started",
            RepairCycleStartedEvent(
                type="repair_cycle.started",
                timestamp=self._clock.now().isoformat(),
                source="mock",
                pipeline_run_id=context.pipeline_run_id,
                stage_name=context.stage_name,
                agent_name=context.agent_name,
            )
        )

        cycle_results: List[CycleResult] = []

        # Execute each test type in order
        try:
            for config in context.test_configs:
                cycle_result = await self._execute_test_cycle(config, context)
                cycle_results.append(cycle_result)

                # Fast-fail if tests didn't pass
                if not cycle_result.passed:
                    self._emit_event(
                        "repair_cycle.fast_fail",
                        RepairCycleFastFailEvent(
                            type="repair_cycle.fast_fail",
                            timestamp=self._clock.now().isoformat(),
                            source="mock",
                            pipeline_run_id=context.pipeline_run_id,
                            reason="test_failed",
                            test_type=config.test_type.value,
                        )
                    )
                    break

                # Check circuit breaker
                if self.total_agent_calls >= context.max_total_agent_calls:
                    self._emit_event(
                        "repair_cycle.fast_fail",
                        RepairCycleFastFailEvent(
                            type="repair_cycle.fast_fail",
                            timestamp=self._clock.now().isoformat(),
                            source="mock",
                            pipeline_run_id=context.pipeline_run_id,
                            reason="circuit_breaker",
                            test_type=config.test_type.value,
                        )
                    )
                    break
        except Exception as e:
            logger.error(f"Error during repair cycle execution: {e}")

        # Calculate overall success and duration
        overall_success = all(result.passed for result in cycle_results) if cycle_results else False
        duration = (self._clock.now() - start_time).total_seconds()

        # Create result
        result = RepairCycleResult(
            stage=context.stage_name,
            test_results=tuple(cycle_results),
            overall_success=overall_success,
            total_agent_calls=self.total_agent_calls,
            duration_seconds=duration,
            timestamp=self._clock.now().isoformat(),
        )

        # Emit completion event
        self._emit_event(
            "repair_cycle.completed",
            RepairCycleCompletedEvent(
                type="repair_cycle.completed",
                timestamp=self._clock.now().isoformat(),
                source="mock",
                pipeline_run_id=context.pipeline_run_id,
                stage_name=context.stage_name,
                overall_success=overall_success,
                total_iterations=self.total_iterations,
                total_agent_calls=self.total_agent_calls,
                duration_seconds=duration,
            )
        )

        return result

    async def _execute_test_cycle(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> CycleResult:
        """Execute tests for one test type until success or max iterations."""
        start_time = self._clock.now()
        iterations = 0
        files_fixed = 0
        warnings_reviewed = 0
        final_result = None
        error = None

        iterations_needed = self._iterations_until_success.get(config.test_type.value, 1)

        try:
            # Run iterations until success or max reached
            for iteration in range(1, config.max_iterations + 1):
                iterations = iteration

                # Run tests
                test_result = await self.run_tests(config, context)
                final_result = test_result

                self._emit_event(
                    "repair_cycle.test_execution_completed",
                    RepairCycleTestExecutionCompletedEvent(
                        type="repair_cycle.test_execution_completed",
                        timestamp=self._clock.now().isoformat(),
                        source="mock",
                        pipeline_run_id=context.pipeline_run_id,
                        test_type=config.test_type.value,
                        iteration=iteration,
                        passed_count=test_result.passed,
                        failed_count=test_result.failed,
                        warnings_count=test_result.warnings,
                    )
                )

                # If tests passed
                if test_result.failed == 0:
                    # Handle warnings if configured
                    if config.review_warnings and test_result.warning_list:
                        warnings_reviewed = await self.handle_warnings(test_result, config, context)

                    # Success!
                    break

                # Failures - fix them if not last iteration
                if iteration < config.max_iterations:
                    grouped_failures = self._group_failures(test_result.failures)
                    files_fixed += await self.fix_failures_by_file(grouped_failures, config, context)

        except Exception as e:
            error = str(e)
            logger.error(f"Error in test cycle for {config.test_type}: {e}")

        # Emit test cycle completed event
        self._emit_event(
            "repair_cycle.test_cycle_completed",
            RepairCycleTestCycleCompletedEvent(
                type="repair_cycle.test_cycle_completed",
                timestamp=self._clock.now().isoformat(),
                source="mock",
                pipeline_run_id=context.pipeline_run_id,
                test_type=config.test_type.value,
                passed=final_result is not None and final_result.failed == 0,
                iterations=iterations,
                files_fixed=files_fixed,
            )
        )

        self.total_iterations += iterations

        duration = (self._clock.now() - start_time).total_seconds()

        return CycleResult(
            test_type=config.test_type,
            passed=final_result is not None and final_result.failed == 0,
            iterations=iterations,
            final_result=final_result,
            error=error,
            files_fixed=files_fixed,
            warnings_reviewed=warnings_reviewed,
            duration_seconds=duration,
        )

    async def run_tests(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RepairTestResult:
        """Run tests for a specific test type."""
        test_type_str = config.test_type.value

        # Get configured failures/warnings or defaults
        failures = self._failures_per_type.get(test_type_str, ())
        warnings = self._warnings_per_type.get(test_type_str, ())

        # If tests should pass on this iteration
        iterations_needed = self._iterations_until_success.get(test_type_str, 1)
        iteration_count = len([e for e in self._events if "iteration" in str(e)])

        # Determine if this iteration passes
        should_pass = iteration_count >= iterations_needed - 1

        if should_pass:
            failures = ()
            warnings = self._warnings_per_type.get(test_type_str, ())

        return RepairTestResult(
            test_type=config.test_type,
            iteration=1,  # Mock always reports iteration 1
            passed=len(failures),
            failed=len(failures),
            warnings=len(warnings),
            failures=failures,
            warning_list=warnings,
            raw_output="Mock test output",
            timestamp=self._clock.now().isoformat(),
        )

    async def fix_failures_by_file(
        self,
        grouped_failures: Dict[str, Tuple[RepairTestFailure, ...]],
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Fix failures by file."""
        if not grouped_failures:
            return 0

        files_fixed = 0

        for file_path, failures in grouped_failures.items():
            if not failures:
                continue

            # Emit file fix started
            self._emit_event(
                "repair_cycle.file_fix_started",
                RepairCycleFileFixStartedEvent(
                    type="repair_cycle.file_fix_started",
                    timestamp=self._clock.now().isoformat(),
                    source="mock",
                    pipeline_run_id=context.pipeline_run_id,
                    file_path=file_path,
                    failure_count=len(failures),
                )
            )

            # Count as agent call
            self.total_agent_calls += 1

            # Mock: assume file is fixed
            files_fixed += 1

            # Emit file fix completed
            self._emit_event(
                "repair_cycle.file_fix_completed",
                RepairCycleFileFixCompletedEvent(
                    type="repair_cycle.file_fix_completed",
                    timestamp=self._clock.now().isoformat(),
                    source="mock",
                    pipeline_run_id=context.pipeline_run_id,
                    file_path=file_path,
                    fixed=True,
                    iterations_used=1,
                )
            )

        return files_fixed

    async def handle_warnings(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Handle test warnings."""
        if not config.review_warnings or not test_result.warning_list:
            return 0

        # Emit warning review started
        self._emit_event(
            "repair_cycle.warning_review_started",
            RepairCycleWarningReviewStartedEvent(
                type="repair_cycle.warning_review_started",
                timestamp=self._clock.now().isoformat(),
                source="mock",
                pipeline_run_id=context.pipeline_run_id,
                test_type=test_result.test_type.value,
                warning_count=len(test_result.warning_list),
            )
        )

        warnings_reviewed = len(test_result.warning_list)

        # Emit warning review completed
        self._emit_event(
            "repair_cycle.warning_review_completed",
            RepairCycleWarningReviewCompletedEvent(
                type="repair_cycle.warning_review_completed",
                timestamp=self._clock.now().isoformat(),
                source="mock",
                pipeline_run_id=context.pipeline_run_id,
                test_type=test_result.test_type.value,
                warnings_reviewed=warnings_reviewed,
            )
        )

        return warnings_reviewed

    async def checkpoint(
        self,
        test_type: str,
        iteration: int,
        context: RepairCycleContext,
    ) -> None:
        """Save checkpoint (no-op for mock)."""
        # Mock checkpoint - just log it
        logger.debug(
            f"Checkpoint: project={context.pipeline_run_id}, "
            f"test_type={test_type}, iteration={iteration}"
        )

    @staticmethod
    def _group_failures(failures: Tuple[RepairTestFailure, ...]) -> Dict[str, Tuple[RepairTestFailure, ...]]:
        """Group failures by file."""
        groups: Dict[str, List[RepairTestFailure]] = {}
        for failure in failures:
            if failure.file not in groups:
                groups[failure.file] = []
            groups[failure.file].append(failure)
        return {k: tuple(v) for k, v in groups.items()}
