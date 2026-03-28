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
6. Supports checkpoint/resume for long-running cycles
"""

import logging
import threading
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter

if TYPE_CHECKING:
    from codetoreum.ports.output.llm_provider import ILLMProvider

from codetoreum.domain.events.repair_cycle_events import (
    RepairCycleCheckpointFailedEvent,
    RepairCycleCompletedEvent,
    RepairCycleFastFailEvent,
    RepairCycleFileFixCompletedEvent,
    RepairCycleFileFixStartedEvent,
    RepairCycleResumedEvent,
    RepairCycleStartedEvent,
    RepairCycleTestCycleCompletedEvent,
    RepairCycleTestExecutionCompletedEvent,
    RepairCycleWarningReviewCompletedEvent,
    RepairCycleWarningReviewStartedEvent,
)
from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    RepairCycleCheckpoint,
    RepairCycleResult,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    RepairTestWarning,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.monitoring import (
    MonitoringConfig,
    MonitoringState,
    MonitoringStatus,
)
from codetoreum.ports.output.repair_cycle_checkpoint_store import (
    IRepairCycleCheckpointStore,
)
from codetoreum.ports.output.repair_cycle_service import (
    IRepairCycle,
    RepairCycleContext,
)

logger = logging.getLogger(__name__)


class CircuitBreakerTripped(Exception):
    """Raised when max agent calls exceeded during repair cycle."""


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
    - Checkpoint/resume for long-running cycles

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

    def __init__(
        self,
        llm_factory: "Callable[[str], ILLMProvider]",
        clock: SimulationClock | None = None,
        checkpoint_store: IRepairCycleCheckpointStore | None = None,
        container_adapter: "Any | None" = None,
    ) -> None:
        """Initialize the repair cycle adapter with SimulationClock.

        Args:
            llm_factory: Factory for creating LLM providers for agents. Takes agent name
                        and returns an ILLMProvider instance. Enables behavioral parity with
                        production adapter's agent selection and LLM instantiation.
            clock: SimulationClock instance for deterministic time advancement
            checkpoint_store: Optional checkpoint store for recovery testing
            container_adapter: Optional container adapter for causal linking (FR-2/US-2.4).
                             If provided, the adapter will use actual container test results
                             instead of pre-configured sequences. This enables integration
                             between test execution and repair cycle decisions.
        """
        super().__init__()
        self._llm_factory = llm_factory
        self._clock = clock or SimulationClock()
        self._checkpoint_store = checkpoint_store
        self._container_adapter = container_adapter
        self._current_project: str | None = None
        self._repair_state: dict[str, Any] = {}
        self._test_type_index: dict[str, int] = {}
        self.agent_call_count = 0
        self.max_total_agent_calls = 100
        self.event_log: list[dict[str, Any]] = []
        self.test_results: dict[RepairTestType, list[RepairTestResult]] = {}
        self.default_total_tests = 10  # Default total test count for generated results

        # State tracking for checkpoint/resume
        self.total_agent_calls = 0
        self.total_iterations = 0
        self._cycle_results: list[CycleResult] = []  # Accumulated test results
        self._elapsed_time = 0.0  # Total elapsed time
        self._files_fixed = 0  # Accumulated files fixed
        self._warnings_reviewed = 0  # Accumulated warnings reviewed

        # Interrupt simulation for testing checkpoint/resume
        self._interrupt_after_iteration: int | None = None
        self._interrupt_test_type: RepairTestType | None = None

        # Event system
        self._events: list[dict] = []
        self._event_handlers: dict[str, list] = {}
        self._monitoring: dict[str, MonitoringStatus] = {}
        self._handler_errors: list[dict[str, Any]] = []
        self._lock = threading.Lock()

        # Agent selection tracking
        self._subtask_agent_calls: list[dict[str, Any]] = []

    @property
    def clock(self) -> SimulationClock:
        """Private property for internal clock access.

        This property provides internal access to the simulation clock for timing
        operations within the adapter. External code should not access this.
        """
        return self._clock

    # Configuration methods (FR-11.2, FR-11.3, FR-11.4)

    def set_test_result_sequence(self, test_type: RepairTestType, results: list[RepairTestResult]) -> None:
        """Configure exact test result sequence for a test type (FR-11.2).

        Args:
            test_type: Type of test (UNIT, INTEGRATION, E2E)
            results: List of test results in sequence order
        """
        self.test_results[test_type] = results

    def set_interrupt_after_iteration(self, iteration: int, test_type: RepairTestType | None = None) -> None:
        """Configure adapter to simulate interruption after specified iteration.

        This simulates a container crash or system failure after completing
        the specified iteration, allowing testing of checkpoint/resume flow.

        Args:
            iteration: Iteration number after which to interrupt (1-based)
            test_type: Optional test type to interrupt during, or None for any
        """
        self._interrupt_after_iteration = iteration
        self._interrupt_test_type = test_type

    def set_iterations_until_success(self, test_type: RepairTestType, iterations: int) -> None:
        """Configure N iterations with last one succeeding (FR-11.3).

        Shorthand for configuring a gradual convergence scenario where
        failures decrease until the final iteration passes.

        Args:
            test_type: Type of test (UNIT, INTEGRATION, E2E)
            iterations: Number of iterations until success
        """
        results = []
        for i in range(1, iterations + 1):
            is_last = i == iterations
            results.append(
                RepairTestResult(
                    test_type=test_type,
                    iteration=i,
                    passed=7 if is_last else 7,
                    failed=0 if is_last else 3,
                    warnings=0,
                    failures=(
                        ()
                        if is_last
                        else (
                            RepairTestFailure(
                                file="test_example.py",
                                test=f"test_case_{i}_1",
                                message="Simulated failure",
                            ),
                            RepairTestFailure(
                                file="test_example.py",
                                test=f"test_case_{i}_2",
                                message="Simulated failure",
                            ),
                            RepairTestFailure(
                                file="test_example.py",
                                test=f"test_case_{i}_3",
                                message="Simulated failure",
                            ),
                        )
                    ),
                    warning_list=(),
                    raw_output="",
                    timestamp=self.clock.now().isoformat(),
                )
            )
        self.test_results[test_type] = results

    def set_always_fail(self, test_type: RepairTestType, max_iterations: int) -> None:
        """Configure to always fail for max iterations (FR-11.4).

        Shorthand for configuring a scenario that never passes,
        simulating code that cannot be fixed within max iterations.

        Args:
            test_type: Type of test (UNIT, INTEGRATION, E2E)
            max_iterations: Maximum iterations before failure
        """
        results = []
        for i in range(1, max_iterations + 1):
            results.append(
                RepairTestResult(
                    test_type=test_type,
                    iteration=i,
                    passed=7,
                    failed=3,
                    warnings=0,
                    failures=(
                        RepairTestFailure(
                            file="test_stubborn.py",
                            test="test_always_fails_1",
                            message="Cannot be fixed",
                        ),
                        RepairTestFailure(
                            file="test_stubborn.py",
                            test="test_always_fails_2",
                            message="Cannot be fixed",
                        ),
                        RepairTestFailure(
                            file="test_stubborn.py",
                            test="test_always_fails_3",
                            message="Cannot be fixed",
                        ),
                    ),
                    warning_list=(),
                    raw_output="",
                    timestamp=self.clock.now().isoformat(),
                )
            )
        self.test_results[test_type] = results

    def set_checkpoint_store(self, store: IRepairCycleCheckpointStore) -> None:
        """Set the checkpoint store (for testing)."""
        self._checkpoint_store = store

    @property
    def current_project(self) -> str | None:
        """Get current project ID."""
        return self._current_project

    @current_project.setter
    def current_project(self, project_id: str | None) -> None:
        """Set current project ID for event emission."""
        self._current_project = project_id

    # Core Repair Cycle Methods

    async def execute(self, context: RepairCycleContext) -> RepairCycleResult:
        """Execute complete repair cycle, resuming from checkpoint if available.

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
            msg = "test_configs cannot be empty"
            raise ValueError(msg)

        # Try to resume from checkpoint
        checkpoint = await self.try_resume_from_checkpoint(context)

        if checkpoint:
            # Restore state from checkpoint
            self._restore_checkpoint_state(checkpoint)
            start_time = self.clock.now() - timedelta(seconds=self._elapsed_time)

            # Emit resume event
            self._emit_event(
                "repair_cycle.resumed",
                RepairCycleResumedEvent(
                    type="repair_cycle.resumed",
                    timestamp=self.clock.now().isoformat(),
                    source="mock",
                    workflow_run_id=context.workflow_run_id,
                    test_type=checkpoint.test_type,
                    iteration=checkpoint.iteration,
                    elapsed_time=self._elapsed_time,
                    agent_calls_so_far=self.total_agent_calls,
                ),
            )

            logger.info(
                f"Resumed repair cycle for {context.workflow_run_id}: "
                f"iteration={checkpoint.iteration}, agent_calls={self.total_agent_calls}"
            )
        else:
            start_time = self.clock.now()
            self.total_agent_calls = 0
            self.agent_call_count = 0
            self.total_iterations = 0
            self._cycle_results = []
            self._elapsed_time = 0.0
            self._files_fixed = 0
            self._warnings_reviewed = 0

            # Emit start event
            cycle_start_timestamp = start_time.isoformat()
            if self._current_project is not None:
                self.emit(
                    RepairCycleStartedEvent(
                        type="repair_cycle.started",
                        timestamp=cycle_start_timestamp,
                        source="mock_repair_cycle",
                        stage_name=context.stage_name,
                        test_types=tuple(cfg.test_type for cfg in context.test_configs),
                        workflow_run_id=context.workflow_run_id,
                    )
                )
                self._log_event(
                    {
                        "type": "REPAIR_CYCLE_STARTED",
                        "stage_name": context.stage_name,
                    }
                )

        cycle_results: list[CycleResult] = list(self._cycle_results)

        # Execute each test type in order
        try:
            for config in context.test_configs:
                # Skip test types already completed (from checkpoint)
                if any(r.test_type == config.test_type and r.passed for r in cycle_results):
                    continue

                cycle_result = await self._run_test_cycle(
                    config=config,
                    context=context,
                )

                # Find and replace or append result
                existing_idx = next(
                    (i for i, r in enumerate(cycle_results) if r.test_type == config.test_type),
                    -1,
                )
                if existing_idx >= 0:
                    cycle_results[existing_idx] = cycle_result
                else:
                    cycle_results.append(cycle_result)

                # If this test type failed, stop cycling through remaining types (fast-fail)
                if not cycle_result.passed:
                    if self._current_project is not None:
                        self.emit(
                            RepairCycleFastFailEvent(
                                type="repair_cycle.fast_fail",
                                timestamp=self.clock.now().isoformat(),
                                source="mock_repair_cycle",
                                test_type=config.test_type,
                                reason="cycle_failed",
                                workflow_run_id=context.workflow_run_id,
                            )
                        )
                    break
        except Exception as e:
            logger.error(
                f"Error during repair cycle execution: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR},
            )

        # Calculate overall success and duration
        overall_success = all(result.passed for result in cycle_results) if cycle_results else False
        end_time = self.clock.now()
        duration_seconds = (end_time - start_time).total_seconds()

        # Delete checkpoint on success
        if checkpoint and overall_success and self._checkpoint_store:
            try:
                await self._checkpoint_store.delete_checkpoint(context.workflow_run_id)
            except Exception as e:
                logger.error(
                    f"Failed to delete checkpoint: {e}",
                    exc_info=True,
                    extra={"error_id": ErrorRegistry.ERR_STORAGE_ERROR},
                )

        # Emit cycle completed event (only if we have results)
        if self._current_project is not None and cycle_results:
            cycle_start_timestamp = start_time.isoformat()
            self.emit(
                RepairCycleCompletedEvent(
                    type="repair_cycle.completed",
                    timestamp=cycle_start_timestamp,
                    source="mock_repair_cycle",
                    overall_success=overall_success,
                    test_results=tuple(cycle_results),
                    total_agent_calls=self.total_agent_calls or self.agent_call_count,
                    duration_seconds=duration_seconds,
                    workflow_run_id=context.workflow_run_id,
                )
            )
            self._log_event(
                {
                    "type": "REPAIR_CYCLE_COMPLETED",
                    "overall_success": overall_success,
                }
            )

        return RepairCycleResult(
            stage=context.stage_name,
            test_results=tuple(cycle_results),
            overall_success=overall_success,
            total_agent_calls=self.total_agent_calls or self.agent_call_count,
            duration_seconds=duration_seconds,
            timestamp=cycle_start_timestamp if self._current_project else start_time.isoformat(),
        )

    async def try_resume_from_checkpoint(
        self,
        context: RepairCycleContext,
    ) -> RepairCycleCheckpoint | None:
        """Try to resume from an existing checkpoint.

        Returns:
            Checkpoint if one exists and is valid, None otherwise
        """
        if not self._checkpoint_store:
            return None

        try:
            # Check all test types for checkpoints
            for config in context.test_configs:
                checkpoint = await self._checkpoint_store.get_checkpoint(
                    context.workflow_run_id,
                    config.test_type.value,
                )

                if checkpoint:
                    logger.info(f"Found checkpoint for {config.test_type.value} at iteration {checkpoint.iteration}")
                    return checkpoint

            return None
        except Exception as e:
            logger.error(
                f"Failed to retrieve checkpoint: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_STORAGE_ERROR},
            )
            return None

    def _restore_checkpoint_state(self, checkpoint: RepairCycleCheckpoint) -> None:
        """Restore internal state from checkpoint with validation.

        Raises:
            ValueError: If checkpoint contains invalid data
        """
        # Validate numeric fields
        if checkpoint.total_agent_calls < 0:
            msg = f"Invalid checkpoint: total_agent_calls={checkpoint.total_agent_calls} must be >= 0"
            raise ValueError(msg)

        if checkpoint.files_fixed < 0:
            msg = "Invalid checkpoint: files_fixed must be >= 0"
            raise ValueError(msg)

        if checkpoint.warnings_reviewed < 0:
            msg = "Invalid checkpoint: warnings_reviewed must be >= 0"
            raise ValueError(msg)

        if checkpoint.elapsed_seconds < 0:
            msg = "Invalid checkpoint: elapsed_seconds must be >= 0"
            raise ValueError(msg)

        if checkpoint.iteration < 1:
            msg = "Invalid checkpoint: iteration must be >= 1"
            raise ValueError(msg)

        # Validate test_type is valid enum
        try:
            RepairTestType(checkpoint.test_type)
        except ValueError as e:
            msg = f"Invalid checkpoint: test_type '{checkpoint.test_type}' is not valid"
            raise ValueError(msg) from e

        # All validations passed, restore state atomically
        with self._lock:
            self.total_agent_calls = checkpoint.total_agent_calls
            self.agent_call_count = checkpoint.total_agent_calls
            self._files_fixed = checkpoint.files_fixed
            self._warnings_reviewed = checkpoint.warnings_reviewed
            self._elapsed_time = checkpoint.elapsed_seconds
            self._cycle_results = list(checkpoint.test_results)

        logger.info(
            "Checkpoint state restored and validated",
            extra={
                "workflow_run_id": checkpoint.workflow_run_id,
                "iteration": checkpoint.iteration,
            },
        )

    def _emit_event(self, event_type: str, event: object) -> None:
        """Emit an event and call handlers."""
        with self._lock:
            event_dict = {
                "type": event_type,
                "event": event,
                "timestamp": self.clock.now().isoformat(),
            }
            self._events.append(event_dict)

        # Call handlers
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    error_record = {
                        "event_type": event_type,
                        "handler": handler.__name__ if hasattr(handler, "__name__") else str(handler),
                        "error": str(e),
                        "timestamp": self.clock.now().isoformat(),
                    }
                    self._handler_errors.append(error_record)
                    logger.error(
                        f"Error in event handler for {event_type}: {e}",
                        exc_info=True,
                        extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION},
                    )

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

    async def start_monitoring(self, project_id: str, config: MonitoringConfig) -> None:
        """Begin monitoring for changes.

        Args:
            project_id: Project to monitor
            config: Monitoring configuration
        """
        status = MonitoringStatus(
            state=MonitoringState.ACTIVE,
            project_id=project_id,
            started_at=self.clock.now().isoformat(),
        )
        with self._lock:
            self._monitoring[project_id] = status

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring for changes.

        Args:
            project_id: Project to stop monitoring
        """
        with self._lock:
            if project_id in self._monitoring:
                self._monitoring[project_id].state = MonitoringState.STOPPED

    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Query current monitoring state.

        Args:
            project_id: Project to query status for

        Returns:
            MonitoringStatus with current state
        """
        with self._lock:
            return self._monitoring.get(
                project_id,
                MonitoringStatus(state=MonitoringState.STOPPED, project_id=project_id),
            )

    def get_all_events(self) -> list[dict]:
        """Get all emitted events."""
        with self._lock:
            return list(self._events)

    async def run_tests(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RepairTestResult:
        """Execute tests for a specific test type (FR-11.6).

        Clock advances 30 seconds per test execution.

        Uses container adapter test results if available (causal linking FR-2/US-2.4),
        otherwise falls back to pre-configured sequences.

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            RepairTestResult with pass/fail counts and failure details
        """
        # Resolve and record which agent is executing this sub-task
        _, agent_name = self._resolve_and_record_agent("test_execution", context)

        self.agent_call_count += 1
        self.total_agent_calls += 1
        await self.clock.advance(timedelta(seconds=30))

        iteration = self._get_iteration_for_test_type(config.test_type)

        # Try to use container adapter results (causal linking FR-2/US-2.4)
        container_result = self._extract_test_result_from_container(config.test_type, iteration)
        if container_result:
            result = container_result
        else:
            # Fallback to pre-configured sequences (backward compatibility)
            sequence = self.test_results.get(config.test_type, [])

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
                # Default: success - passed = total - failed
                default_failed = 0
                default_passed = self.default_total_tests - default_failed
                result = RepairTestResult(
                    test_type=config.test_type,
                    iteration=iteration,
                    passed=default_passed,
                    failed=default_failed,
                    warnings=0,
                    failures=(),
                    warning_list=(),
                    raw_output="All tests passed",
                    timestamp=self.clock.now().isoformat(),
                )

        self._log_event(
            {
                "type": "TEST_EXECUTION_COMPLETED",
                "test_type": config.test_type.value,
                "iteration": iteration,
                "passed": result.passed,
                "failed": result.failed,
            }
        )

        if self._current_project is not None:
            self.emit(
                RepairCycleTestExecutionCompletedEvent(
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
                    agent_name=agent_name,
                    workflow_run_id=context.workflow_run_id,
                )
            )

        return result

    async def fix_failures_by_file(
        self,
        grouped_failures: dict[str, tuple[RepairTestFailure, ...]],
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
            # Resolve and record which agent is executing this sub-task
            _, agent_name = self._resolve_and_record_agent("code_fix", context)

            self.agent_call_count += 1
            self.total_agent_calls += 1
            await self.clock.advance(timedelta(minutes=2))

            if self._current_project is not None:
                self.emit(
                    RepairCycleFileFixStartedEvent(
                        type="repair_cycle.file_fix_started",
                        timestamp=self.clock.now().isoformat(),
                        source="mock_repair_cycle",
                        test_file=file_path,
                        failure_count=len(failures),
                        test_type=config.test_type,
                        agent_name=agent_name,
                        workflow_run_id=context.workflow_run_id,
                    )
                )

                self.emit(
                    RepairCycleFileFixCompletedEvent(
                        type="repair_cycle.file_fix_completed",
                        timestamp=self.clock.now().isoformat(),
                        source="mock_repair_cycle",
                        test_file=file_path,
                        failure_count=len(failures),
                        test_type=config.test_type,
                        agent_name=agent_name,
                        success=True,
                        workflow_run_id=context.workflow_run_id,
                    )
                )

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
            # Resolve and record which agent is executing this sub-task
            _, agent_name = self._resolve_and_record_agent("code_fix", context)

            self.agent_call_count += 1
            self.total_agent_calls += 1
            await self.clock.advance(timedelta(minutes=1))

            if self._current_project is not None:
                self.emit(
                    RepairCycleWarningReviewStartedEvent(
                        type="repair_cycle.warning_review_started",
                        timestamp=self.clock.now().isoformat(),
                        source="mock_repair_cycle",
                        source_file=warning.file,
                        warning_count=1,
                        test_type=config.test_type,
                        warnings=(warning,),
                        agent_name=agent_name,
                        workflow_run_id=context.workflow_run_id,
                    )
                )

                self.emit(
                    RepairCycleWarningReviewCompletedEvent(
                        type="repair_cycle.warning_review_completed",
                        timestamp=self.clock.now().isoformat(),
                        source="mock_repair_cycle",
                        source_file=warning.file,
                        warning_count=1,
                        test_type=config.test_type,
                        agent_name=agent_name,
                        success=True,
                        workflow_run_id=context.workflow_run_id,
                    )
                )

            reviewed += 1

        return reviewed

    async def analyze_systemic_issues(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> str:
        """Mock implementation: return simulated systemic analysis.

        Args:
            test_result: Test result containing failures to analyze
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Analysis summary string
        """
        if not test_result.failures:
            return ""

        # Track agent call
        self.agent_call_count += 1
        self.total_agent_calls += 1

        # Simulate analysis response
        analysis = f"Systemic issues detected in {len(test_result.failures)} failures"

        logger.info(
            "Mock systemic analysis completed",
            extra={
                "workflow_run_id": context.workflow_run_id,
                "failure_count": len(test_result.failures),
            },
            exc_info=False,
        )

        return analysis

    async def apply_systemic_fixes(
        self,
        analysis_summary: str,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Mock implementation: simulate systemic fix application.

        Args:
            analysis_summary: Summary from systemic analysis
            test_result: Test result that triggered the analysis
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if fixes were successfully applied
        """
        if not analysis_summary:
            return False

        # Track agent call
        self.agent_call_count += 1
        self.total_agent_calls += 1

        logger.info(
            "Mock systemic fixes applied",
            extra={
                "workflow_run_id": context.workflow_run_id,
                "test_type": config.test_type.value,
            },
            exc_info=False,
        )

        return True

    async def rebuild_environment(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Mock implementation: simulate environment rebuild.

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if environment was successfully rebuilt
        """
        # Track agent call
        self.agent_call_count += 1
        self.total_agent_calls += 1

        logger.info(
            "Mock environment rebuild completed",
            extra={
                "workflow_run_id": context.workflow_run_id,
                "test_type": config.test_type.value,
            },
            exc_info=False,
        )

        return True

    async def verify_environment(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Mock implementation: simulate environment verification.

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if environment verification passed
        """
        # Track agent call
        self.agent_call_count += 1
        self.total_agent_calls += 1

        logger.info(
            "Mock environment verification completed",
            extra={
                "workflow_run_id": context.workflow_run_id,
                "test_type": config.test_type.value,
                "ready": True,
            },
            exc_info=False,
        )

        return True

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
        if not self._checkpoint_store:
            logger.debug(
                f"Checkpoint: project={context.workflow_run_id}, "
                f"test_type={test_type}, iteration={iteration} (no store configured)"
            )
            return

        try:
            # Calculate expiration time (24 hours from now)
            now = self.clock.now()
            expires_at = (now + timedelta(hours=24)).isoformat()

            # Create checkpoint with accumulated state
            checkpoint = RepairCycleCheckpoint(
                workflow_run_id=context.workflow_run_id,
                test_type=test_type,
                iteration=iteration,
                total_agent_calls=self.total_agent_calls,
                files_fixed=self._files_fixed,
                warnings_reviewed=self._warnings_reviewed,
                elapsed_seconds=self._elapsed_time,
                test_results=tuple(self._cycle_results),
                timestamp=now.isoformat(),
                expires_at=expires_at,
            )

            # Save to store
            await self._checkpoint_store.save_checkpoint(checkpoint)

            logger.debug(
                f"Checkpoint saved: project={context.workflow_run_id}, "
                f"test_type={test_type}, iteration={iteration}, "
                f"agent_calls={self.total_agent_calls}"
            )
        except Exception as e:
            logger.error(
                "Failed to save checkpoint - repair cycle may not be resumable",
                extra={
                    "workflow_run_id": context.workflow_run_id,
                    "test_type": test_type.value,
                    "iteration": iteration,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR,
                },
                exc_info=True,
            )

            # Emit event so users/monitoring can be alerted
            checkpoint_failed_event = RepairCycleCheckpointFailedEvent(
                type="repair_cycle.checkpoint_failed",
                timestamp=self.clock.now().isoformat(),
                source="mock_repair_cycle",
                workflow_run_id=context.workflow_run_id,
                test_type=test_type,
                iteration=iteration,
                error_type=type(e).__name__,
                error_message=str(e),
                checkpoint_store_type=type(self._checkpoint_store).__name__ if self._checkpoint_store else "none",
            )
            self._emit_event("repair_cycle.checkpoint_failed", checkpoint_failed_event)

    # Event log retrieval (FR-11.10)

    def get_all_events_log(self) -> list[dict[str, Any]]:
        """Return all logged events.

        Returns:
            List of event dictionaries with timestamps
        """
        return list(self.event_log)

    def get_events_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Return events of specific type.

        Args:
            event_type: Event type to filter by

        Returns:
            List of events matching the type
        """
        return [e for e in self.event_log if e.get("type") == event_type]

    def get_handler_errors(self) -> list[dict[str, Any]]:
        """Get all handler errors that occurred during repair cycle."""
        with self._lock:
            return list(self._handler_errors)

    def assert_no_handler_errors(self) -> None:
        """Assert no event handler errors occurred.

        Raises:
            AssertionError: If any handler errors were recorded
        """
        errors = self.get_handler_errors()
        if errors:
            error_summary = "\n".join(f"  - {e['event_type']}: {e['error']}" for e in errors)
            msg = f"Expected no handler errors, but found {len(errors)}:\n{error_summary}"
            raise AssertionError(msg)

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
        event = next((e for e in events if e.get("test_type") == test_type.value), None)
        if not event:
            msg = f"No completion event found for {test_type.value}"
            raise AssertionError(msg)
        if event.get("iterations") != expected:
            msg = f"Expected {expected} iterations for {test_type.value}, got {event.get('iterations')}"
            raise AssertionError(msg)

    def assert_test_type_passed(self, test_type: RepairTestType) -> None:
        """Assert test type passed.

        Args:
            test_type: Type of test to check

        Raises:
            AssertionError: If test type didn't pass
        """
        events = self.get_events_by_type("TEST_CYCLE_COMPLETED")
        event = next((e for e in events if e.get("test_type") == test_type.value), None)
        if not event or not event.get("passed"):
            msg = f"Expected {test_type.value} to pass"
            raise AssertionError(msg)

    def assert_test_type_failed(self, test_type: RepairTestType) -> None:
        """Assert test type failed.

        Args:
            test_type: Type of test to check

        Raises:
            AssertionError: If test type passed
        """
        events = self.get_events_by_type("TEST_CYCLE_COMPLETED")
        event = next((e for e in events if e.get("test_type") == test_type.value), None)
        if not event or event.get("passed"):
            msg = f"Expected {test_type.value} to fail"
            raise AssertionError(msg)

    def assert_fast_fail(self, test_type: RepairTestType) -> None:
        """Assert fast-fail occurred after test type.

        Args:
            test_type: Type of test that should trigger fast-fail

        Raises:
            AssertionError: If fast-fail didn't occur
        """
        event = next(
            (
                e
                for e in self.event_log
                if e.get("type") == "REPAIR_CYCLE_FAST_FAIL" and e.get("test_type") == test_type.value
            ),
            None,
        )
        if not event:
            msg = f"Expected fast-fail after {test_type.value}"
            raise AssertionError(msg)

    def assert_overall_success(self) -> None:
        """Assert overall cycle succeeded.

        Raises:
            AssertionError: If cycle didn't succeed overall
        """
        event = next((e for e in self.event_log if e.get("type") == "REPAIR_CYCLE_COMPLETED"), None)
        if not event or not event.get("overall_success"):
            msg = "Expected overall success"
            raise AssertionError(msg)

    def assert_overall_failure(self) -> None:
        """Assert overall cycle failed.

        Raises:
            AssertionError: If cycle succeeded
        """
        event = next((e for e in self.event_log if e.get("type") == "REPAIR_CYCLE_COMPLETED"), None)
        if not event or event.get("overall_success"):
            msg = "Expected overall failure"
            raise AssertionError(msg)

    def assert_warnings_reviewed_count(self, test_type: RepairTestType, expected: int) -> None:
        """Assert test type reviewed expected number of warnings.

        Args:
            test_type: Type of test to check
            expected: Expected number of warnings reviewed

        Raises:
            AssertionError: If warning count doesn't match
        """
        events = self.get_events_by_type("TEST_CYCLE_COMPLETED")
        event = next((e for e in events if e.get("test_type") == test_type.value), None)
        if not event:
            msg = f"No completion event found for {test_type.value}"
            raise AssertionError(msg)
        actual = event.get("warnings_reviewed", 0)
        if actual != expected:
            msg = f"Expected {expected} warnings reviewed for {test_type.value}, got {actual}"
            raise AssertionError(msg)

    def assert_no_warning_regression(self, test_type: RepairTestType) -> None:
        """Assert test type completed without new warnings appearing.

        Verifies final test execution had 0 warnings, indicating no
        regression introduced during the repair cycle.

        Args:
            test_type: Type of test to check

        Raises:
            AssertionError: If warnings were found in final execution
        """
        events = self.get_events_by_type("TEST_CYCLE_COMPLETED")
        event = next((e for e in events if e.get("test_type") == test_type.value), None)
        if not event:
            msg = f"No completion event found for {test_type.value}"
            raise AssertionError(msg)

        final_warnings = event.get("final_warnings", 0)
        if final_warnings > 0:
            msg = (
                f"Expected no warning regression for {test_type.value}, "
                f"but found {final_warnings} warnings in final execution"
            )
            raise AssertionError(msg)

    def assert_no_warning_reappearance(
        self, test_type: RepairTestType, original_warnings: tuple[RepairTestWarning, ...]
    ) -> None:
        """Assert previously fixed warnings didn't reappear.

        Compares final test execution warnings against original warnings
        that should have been fixed, ensuring none reappeared.

        Args:
            test_type: Type of test to check
            original_warnings: Warnings that were originally present and fixed

        Raises:
            AssertionError: If any original warnings reappeared
        """
        events = self.get_events_by_type("TEST_CYCLE_COMPLETED")
        event = next((e for e in events if e.get("test_type") == test_type.value), None)
        if not event:
            msg = f"No completion event found for {test_type.value}"
            raise AssertionError(msg)

        current_warnings = event.get("warning_list", ())

        if not original_warnings:
            return

        # Build set of original warning signatures (file, message)
        original_sigs = {(w.file, w.message) for w in original_warnings}

        # Check if any current warnings match original ones
        reappeared = []
        for current_warning in current_warnings:
            if isinstance(current_warning, dict):
                sig = (current_warning.get("file", ""), current_warning.get("message", ""))
            else:
                sig = (current_warning.file, current_warning.message)

            if sig in original_sigs:
                reappeared.append(sig)

        if reappeared:
            msg = (
                f"Expected no warning reappearance for {test_type.value}, "
                f"but {len(reappeared)} warning(s) reappeared: {reappeared}"
            )
            raise AssertionError(msg)

    def get_agent_call_count(self) -> int:
        """Return total agent calls made.

        Returns:
            Total number of agent calls
        """
        return self.total_agent_calls or self.agent_call_count

    def get_subtask_agent_calls(self) -> list[dict[str, Any]]:
        """Get all recorded sub-task agent calls.

        Returns a list of recorded agent selections for each sub-task invocation.
        Each record contains the sub_task name, resolved agent_name, and timestamp.

        Returns:
            List of agent call records with keys: sub_task, agent_name, timestamp
        """
        with self._lock:
            return list(self._subtask_agent_calls)

    def assert_subtask_used_agent(self, sub_task: str, expected_agent: str) -> None:
        """Assert that a sub-task used the specified agent.

        Checks the most recent call for the specified sub-task and verifies
        it used the expected agent. Raises AssertionError if no calls were
        recorded for the sub-task or if the agent name doesn't match.

        Args:
            sub_task: The sub-task name to check
            expected_agent: The expected agent name

        Raises:
            AssertionError: If no calls recorded or agent name doesn't match
        """
        with self._lock:
            calls = [c for c in self._subtask_agent_calls if c["sub_task"] == sub_task]

        if not calls:
            msg = f"No calls recorded for sub_task '{sub_task}'"
            raise AssertionError(msg)

        actual = calls[-1]["agent_name"]  # Check most recent call
        if actual != expected_agent:
            msg = (
                f"Sub-task '{sub_task}': expected agent '{expected_agent}', got '{actual}'"
            )
            raise AssertionError(msg)

    # Private helper methods

    async def _run_test_cycle(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
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
        test_type_index = len(self._cycle_results) + 1
        last_test_result = None

        self._log_event(
            {
                "type": "TEST_CYCLE_STARTED",
                "test_type": config.test_type.value,
                "max_iterations": config.max_iterations,
            }
        )

        for iteration in range(1, config.max_iterations + 1):
            # Check circuit breaker
            if self.total_agent_calls >= context.max_total_agent_calls:
                if self._current_project is not None:
                    self.emit(
                        RepairCycleFastFailEvent(
                            type="repair_cycle.fast_fail",
                            timestamp=self.clock.now().isoformat(),
                            source="mock_repair_cycle",
                            test_type=config.test_type,
                            reason="circuit_breaker_triggered",
                            workflow_run_id=context.workflow_run_id,
                        )
                    )
                error = "Circuit breaker: max agent calls reached"
                break

            # Run tests
            test_result = await self.run_tests(config, context)
            last_test_result = test_result

            # Check for success
            if test_result.failed == 0:
                cycle_passed = True

                # Handle warnings if configured
                if config.review_warnings and test_result.warnings > 0:
                    warnings_reviewed += await self.handle_warnings(test_result, config, context)

                    # Re-test after warning fixes
                    retest = await self.run_tests(config, context)
                    last_test_result = retest
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
                files_fixed += await self.fix_failures_by_file(grouped, config, context)

            # Checkpoint at interval
            if iteration % context.checkpoint_interval == 0:
                await self.checkpoint(config.test_type, iteration, context)

            # Check for simulated interruption (for testing checkpoint/resume)
            if (
                self._interrupt_after_iteration is not None
                and iteration == self._interrupt_after_iteration
                and (self._interrupt_test_type is None or self._interrupt_test_type == config.test_type)
            ):
                # Simulate interruption (e.g., container crash)
                logger.info(
                    f"Simulated interruption after iteration {iteration} for test_type={config.test_type.value}"
                )
                msg = (
                    f"Simulated interruption after iteration {iteration} "
                    f"(checkpoint saved, testing resume functionality)"
                )
                raise InterruptedError(msg)

        # Emit test cycle completed
        if self._current_project is not None:
            self.emit(
                RepairCycleTestCycleCompletedEvent(
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
                    workflow_run_id=context.workflow_run_id,
                )
            )

        self._log_event(
            {
                "type": "TEST_CYCLE_COMPLETED",
                "test_type": config.test_type.value,
                "passed": cycle_passed,
                "iterations": iteration,
                "warnings_reviewed": warnings_reviewed,
                "final_warnings": last_test_result.warnings if last_test_result else 0,
                "warning_list": last_test_result.warning_list if last_test_result else (),
                "error": error,
            }
        )

        duration_seconds = (self.clock.now() - start_time).total_seconds()
        self._elapsed_time += duration_seconds

        result = CycleResult(
            test_type=config.test_type,
            passed=cycle_passed,
            iterations=iteration,
            final_result=last_test_result if cycle_passed else None,
            error=error,
            files_fixed=files_fixed,
            warnings_reviewed=warnings_reviewed,
            duration_seconds=duration_seconds,
        )

        self._cycle_results.append(result)
        self._files_fixed += files_fixed
        self._warnings_reviewed += warnings_reviewed

        return result

    def _group_failures_by_file(
        self, failures: tuple[RepairTestFailure, ...]
    ) -> dict[str, tuple[RepairTestFailure, ...]]:
        """Group test failures by file."""
        grouped: dict[str, list[RepairTestFailure]] = {}
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

    def _get_test_type_for_command(self, command: str) -> RepairTestType | None:
        """Determine test type from command string.

        Maps common test commands to their test types:
        - pytest tests/unit -> UNIT
        - pytest tests/integration -> INTEGRATION
        - pytest tests/e2e -> E2E
        - unittest tests.unit -> UNIT
        etc.

        Args:
            command: The test command to analyze

        Returns:
            RepairTestType if recognized, None otherwise
        """
        command_lower = command.lower()

        # Check for test type indicators in command
        if any(pattern in command_lower for pattern in ["tests/unit", "test_unit", "unittest", "tests/unit.*py"]):
            return RepairTestType.UNIT
        if any(pattern in command_lower for pattern in ["tests/integration", "test_integration", "integration"]):
            return RepairTestType.INTEGRATION
        if any(pattern in command_lower for pattern in ["tests/e2e", "test_e2e", "e2e", "end.to.end"]):
            return RepairTestType.E2E

        return None

    def _extract_test_result_from_container(self, test_type: RepairTestType, iteration: int) -> RepairTestResult | None:
        """Extract test result from container execution output (FR-2/US-2.4).

        This method implements causal linking between container test execution and repair
        cycle decisions. It attempts to retrieve actual test results from the container
        adapter and parse them into RepairTestResult format.

        The method correlates container execution results by test type to ensure we're
        analyzing the right test results for the requested test_type.

        Args:
            test_type: Type of test (UNIT, INTEGRATION, E2E)
            iteration: Current iteration number

        Returns:
            RepairTestResult if container execution data is available, None otherwise
        """
        if not self._container_adapter:
            return None

        try:
            # Access command history via public method to avoid private attribute fragility
            # Note: FakeContainerAdapter._command_history is internal but we need it for now
            # TODO: Add public get_command_history() method to IContainer interface
            if not hasattr(self._container_adapter, "_command_history"):
                return None

            # Search for container executions matching the requested test_type
            for container_id, executions in self._container_adapter._command_history.items():
                if not executions:
                    continue

                # Find executions for the matching test type
                for execution in executions:
                    # Determine test type from the command
                    command_test_type = self._get_test_type_for_command(execution.command)

                    # Skip if this execution's test type doesn't match what we're looking for
                    if command_test_type != test_type:
                        continue

                    # Found a matching test type - parse the result
                    stdout = execution.stdout.lower() if execution.stdout else ""
                    stderr = execution.stderr.lower() if execution.stderr else ""
                    combined_output = (execution.stdout or "") + (execution.stderr or "")

                    # Analyze container output for test metrics
                    passed = failed = 0
                    failures = []

                    # Check for test failure patterns in output
                    if "failed" in stdout or "failed" in stderr or execution.exit_code != 0:
                        # Parse failure information
                        failure_lines = [
                            line
                            for line in combined_output.split("\n")
                            if "test" in line.lower() and ("fail" in line.lower() or "error" in line.lower())
                        ]

                        failed = len(failure_lines) if failure_lines else 1

                        # Extract failure details
                        for line in failure_lines:
                            failures.append(
                                RepairTestFailure(
                                    file="test_container.py",
                                    test=line[:100],
                                    message=line[100:200] if len(line) > 100 else "Container test failed",
                                )
                            )
                    else:
                        # No failures detected
                        passed = self.default_total_tests
                        failed = 0

                    # Create result from container execution
                    return RepairTestResult(
                        test_type=test_type,
                        iteration=iteration,
                        passed=passed if failed == 0 else max(0, self.default_total_tests - failed),
                        failed=failed,
                        warnings=0,
                        failures=tuple(failures),
                        warning_list=(),
                        raw_output=execution.stdout or "",
                        timestamp=self.clock.now().isoformat(),
                    )

            # No matching test type found in container history
            return None

        except Exception as e:
            logger.debug(
                f"Failed to extract test results from container adapter: {e}",
                exc_info=True,
            )
            return None

    def _log_event(self, event: dict[str, Any]) -> None:
        """Log event with timestamp (FR-11.9)."""
        event["timestamp"] = self.clock.now().isoformat()
        self.event_log.append(event)

    def _resolve_and_record_agent(
        self,
        sub_task: str,
        context: RepairCycleContext,
    ) -> tuple["ILLMProvider", str]:
        """Resolve agent for a sub-task and return its LLM provider.

        Resolves the agent name based on agent_config if available, otherwise
        uses the default context agent name. Calls the llm_factory with the resolved
        agent name to obtain the configured ILLMProvider, ensuring behavioral parity
        with the production adapter's agent selection and LLM instantiation.
        Records the selection in the subtask agent calls log for later assertion.

        Args:
            sub_task: The sub-task name (e.g., "test_execution", "code_fix")
            context: Repair cycle context with optional agent_config

        Returns:
            Tuple of (ILLMProvider instance for the resolved agent, resolved agent name)
        """
        agent_name = (
            context.agent_config.resolve_agent(sub_task, context.agent_name)
            if context.agent_config
            else context.agent_name
        )

        # Call factory to obtain ILLMProvider for the resolved agent.
        # This enforces the contract that llm_factory returns ILLMProvider
        # and validates production wiring correctness.
        llm_provider = self._llm_factory(agent_name)

        with self._lock:
            self._subtask_agent_calls.append(
                {
                    "sub_task": sub_task,
                    "agent_name": agent_name,
                    "llm_provider": llm_provider,
                    "timestamp": self.clock.now().isoformat(),
                }
            )

        return llm_provider, agent_name
