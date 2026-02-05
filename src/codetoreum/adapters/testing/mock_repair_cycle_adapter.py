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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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
from codetoreum.domain.events.repair_cycle_events import (
    RepairCycleCheckpointFailedEvent,
    RepairCycleCompletedEvent,
    RepairCycleFileFixCompletedEvent,
    RepairCycleFileFixStartedEvent,
    RepairCycleFastFailEvent,
    RepairCycleResumedEvent,
    RepairCycleStartedEvent,
    RepairCycleTestCycleCompletedEvent,
    RepairCycleTestExecutionCompletedEvent,
    RepairCycleWarningReviewCompletedEvent,
    RepairCycleWarningReviewStartedEvent,
)
from codetoreum.ports.output.monitoring import MonitoringConfig, MonitoringStatus
from codetoreum.ports.output.repair_cycle_service import IRepairCycle, RepairCycleContext
from codetoreum.ports.output.repair_cycle_checkpoint_store import IRepairCycleCheckpointStore
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.infrastructure.error_ids import ErrorRegistry


logger = logging.getLogger(__name__)


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
        clock: Optional[SimulationClock] = None,
        checkpoint_store: Optional[IRepairCycleCheckpointStore] = None,
    ) -> None:
        """Initialize the repair cycle adapter with SimulationClock.

        Args:
            clock: SimulationClock instance for deterministic time advancement
            checkpoint_store: Optional checkpoint store for recovery testing
        """
        super().__init__()
        self._clock = clock or SimulationClock()
        self._checkpoint_store = checkpoint_store
        self._current_project: Optional[str] = None
        self._repair_state: Dict[str, Any] = {}
        self._test_type_index: Dict[str, int] = {}
        self.agent_call_count = 0
        self.max_total_agent_calls = 100
        self.event_log: List[Dict[str, Any]] = []
        self.test_results: Dict[RepairTestType, List[RepairTestResult]] = {}
        self.default_total_tests = 10  # Default total test count for generated results

        # State tracking for checkpoint/resume
        self.total_agent_calls = 0
        self.total_iterations = 0
        self._cycle_results: List[CycleResult] = []  # Accumulated test results
        self._elapsed_time = 0.0  # Total elapsed time
        self._files_fixed = 0  # Accumulated files fixed
        self._warnings_reviewed = 0  # Accumulated warnings reviewed

        # Interrupt simulation for testing checkpoint/resume
        self._interrupt_after_iteration: Optional[int] = None
        self._interrupt_test_type: Optional[RepairTestType] = None

        # Event system
        self._events: List[dict] = []
        self._event_handlers: Dict[str, List] = {}
        self._monitoring: Dict[str, MonitoringStatus] = {}
        self._handler_errors: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

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

    def set_interrupt_after_iteration(
        self,
        iteration: int,
        test_type: Optional[RepairTestType] = None
    ) -> None:
        """Configure adapter to simulate interruption after specified iteration.

        This simulates a container crash or system failure after completing
        the specified iteration, allowing testing of checkpoint/resume flow.

        Args:
            iteration: Iteration number after which to interrupt (1-based)
            test_type: Optional test type to interrupt during, or None for any
        """
        self._interrupt_after_iteration = iteration
        self._interrupt_test_type = test_type

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
                passed=7 if is_last else 7,
                failed=0 if is_last else 3,
                warnings=0,
                failures=() if is_last else (
                    RepairTestFailure(
                        file="test_example.py",
                        test=f"test_case_{i}_1",
                        message="Simulated failure"
                    ),
                    RepairTestFailure(
                        file="test_example.py",
                        test=f"test_case_{i}_2",
                        message="Simulated failure"
                    ),
                    RepairTestFailure(
                        file="test_example.py",
                        test=f"test_case_{i}_3",
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
                        test="test_always_fails_1",
                        message="Cannot be fixed"
                    ),
                    RepairTestFailure(
                        file="test_stubborn.py",
                        test="test_always_fails_2",
                        message="Cannot be fixed"
                    ),
                    RepairTestFailure(
                        file="test_stubborn.py",
                        test="test_always_fails_3",
                        message="Cannot be fixed"
                    ),
                ),
                warning_list=(),
                raw_output="",
                timestamp=self.clock.now().isoformat()
            ))
        self.test_results[test_type] = results

    def set_checkpoint_store(self, store: IRepairCycleCheckpointStore) -> None:
        """Set the checkpoint store (for testing)."""
        self._checkpoint_store = store

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
            raise ValueError("test_configs cannot be empty")

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
                    pipeline_run_id=context.pipeline_run_id,
                    test_type=checkpoint.test_type,
                    iteration=checkpoint.iteration,
                    elapsed_time=self._elapsed_time,
                    agent_calls_so_far=self.total_agent_calls,
                )
            )

            logger.info(
                f"Resumed repair cycle for {context.pipeline_run_id}: "
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

        cycle_results: List[CycleResult] = list(self._cycle_results)

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
                        self.emit(RepairCycleFastFailEvent(
                            type="repair_cycle.fast_fail",
                            timestamp=self.clock.now().isoformat(),
                            source="mock_repair_cycle",
                            test_type=config.test_type,
                            reason="cycle_failed",
                            pipeline_run_id=context.pipeline_run_id,
                        ))
                    break
        except Exception as e:
            logger.error(f"Error during repair cycle execution: {e}", exc_info=True, extra={"error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR})

        # Calculate overall success and duration
        overall_success = all(result.passed for result in cycle_results) if cycle_results else False
        end_time = self.clock.now()
        duration_seconds = (end_time - start_time).total_seconds()

        # Delete checkpoint on success
        if checkpoint and overall_success and self._checkpoint_store:
            try:
                await self._checkpoint_store.delete_checkpoint(context.pipeline_run_id)
            except Exception as e:
                logger.error(f"Failed to delete checkpoint: {e}", exc_info=True, extra={"error_id": ErrorRegistry.ERR_STORAGE_ERROR})

        # Emit cycle completed event (only if we have results)
        if self._current_project is not None and cycle_results:
            cycle_start_timestamp = start_time.isoformat()
            self.emit(RepairCycleCompletedEvent(
                type="repair_cycle.completed",
                timestamp=cycle_start_timestamp,
                source="mock_repair_cycle",
                overall_success=overall_success,
                test_results=tuple(cycle_results),
                total_agent_calls=self.total_agent_calls or self.agent_call_count,
                duration_seconds=duration_seconds,
                pipeline_run_id=context.pipeline_run_id,
            ))
            self._log_event({
                "type": "REPAIR_CYCLE_COMPLETED",
                "overall_success": overall_success,
            })

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
    ) -> Optional[RepairCycleCheckpoint]:
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
                    context.pipeline_run_id,
                    config.test_type.value,
                )

                if checkpoint:
                    logger.info(
                        f"Found checkpoint for {config.test_type.value} "
                        f"at iteration {checkpoint.iteration}"
                    )
                    return checkpoint

            return None
        except Exception as e:
            logger.error(f"Failed to retrieve checkpoint: {e}", exc_info=True, extra={"error_id": ErrorRegistry.ERR_STORAGE_ERROR})
            return None

    def _restore_checkpoint_state(self, checkpoint: RepairCycleCheckpoint) -> None:
        """Restore internal state from checkpoint with validation.

        Raises:
            ValueError: If checkpoint contains invalid data
        """
        # Validate numeric fields
        if checkpoint.total_agent_calls < 0:
            raise ValueError(
                f"Invalid checkpoint: total_agent_calls={checkpoint.total_agent_calls} must be >= 0"
            )

        if checkpoint.files_fixed < 0:
            raise ValueError(f"Invalid checkpoint: files_fixed must be >= 0")

        if checkpoint.warnings_reviewed < 0:
            raise ValueError(f"Invalid checkpoint: warnings_reviewed must be >= 0")

        if checkpoint.elapsed_seconds < 0:
            raise ValueError(f"Invalid checkpoint: elapsed_seconds must be >= 0")

        if checkpoint.iteration < 1:
            raise ValueError(f"Invalid checkpoint: iteration must be >= 1")

        # Validate test_type is valid enum
        try:
            RepairTestType(checkpoint.test_type)
        except ValueError as e:
            raise ValueError(
                f"Invalid checkpoint: test_type '{checkpoint.test_type}' is not valid"
            ) from e

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
                "pipeline_run_id": checkpoint.pipeline_run_id,
                "iteration": checkpoint.iteration,
            }
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
                        "handler": handler.__name__ if hasattr(handler, '__name__') else str(handler),
                        "error": str(e),
                        "timestamp": self.clock.now().isoformat(),
                    }
                    self._handler_errors.append(error_record)
                    logger.error(f"Error in event handler for {event_type}: {e}", exc_info=True, extra={"error_id": ErrorRegistry.ERR_HANDLER_EXECUTION})

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
        config: MonitoringConfig,
    ) -> MonitoringStatus:
        """Start monitoring (no-op for mock)."""
        status = MonitoringStatus(
            service_name="MockRepairCycleAdapter",
            is_running=True,
            timestamp=self.clock.now().isoformat(),
        )
        self._monitoring["default"] = status
        return status

    async def stop_monitoring(self) -> None:
        """Stop monitoring (no-op for mock)."""
        pass

    def get_all_events(self) -> List[dict]:
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

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            RepairTestResult with pass/fail counts and failure details
        """
        self.agent_call_count += 1
        self.total_agent_calls += 1
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
            self.total_agent_calls += 1
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
            self.total_agent_calls += 1
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
                    pipeline_run_id=context.pipeline_run_id,
                ))

                self.emit(RepairCycleWarningReviewCompletedEvent(
                    type="repair_cycle.warning_review_completed",
                    timestamp=self.clock.now().isoformat(),
                    source="mock_repair_cycle",
                    source_file=warning.file,
                    warning_count=1,
                    test_type=config.test_type,
                    success=True,
                    pipeline_run_id=context.pipeline_run_id,
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
        if not self._checkpoint_store:
            logger.debug(
                f"Checkpoint: project={context.pipeline_run_id}, "
                f"test_type={test_type}, iteration={iteration} (no store configured)"
            )
            return

        try:
            # Calculate expiration time (24 hours from now)
            now = self.clock.now()
            expires_at = (now + timedelta(hours=24)).isoformat()

            # Create checkpoint with accumulated state
            checkpoint = RepairCycleCheckpoint(
                pipeline_run_id=context.pipeline_run_id,
                test_type=test_type.value,
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
                f"Checkpoint saved: project={context.pipeline_run_id}, "
                f"test_type={test_type}, iteration={iteration}, "
                f"agent_calls={self.total_agent_calls}"
            )
        except Exception as e:
            logger.error(
                "Failed to save checkpoint - repair cycle may not be resumable",
                extra={
                    "pipeline_run_id": context.pipeline_run_id,
                    "test_type": test_type.value,
                    "iteration": iteration,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR},
                exc_info=True,
            )

            # Emit event so users/monitoring can be alerted
            self._emit_event(
                RepairCycleCheckpointFailedEvent(
                    type="repair_cycle.checkpoint_failed",
                    timestamp=self.clock.now().isoformat(),
                    source="mock_repair_cycle",
                    pipeline_run_id=context.pipeline_run_id,
                    test_type=test_type.value,
                    iteration=iteration,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    checkpoint_store_type=type(self._checkpoint_store).__name__ if self._checkpoint_store else "none",
                )
            )

    # Event log retrieval (FR-11.10)

    def get_all_events_log(self) -> List[Dict[str, Any]]:
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

    def get_handler_errors(self) -> List[Dict[str, Any]]:
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
            error_summary = "\n".join(
                f"  - {e['event_type']}: {e['error']}" for e in errors
            )
            raise AssertionError(
                f"Expected no handler errors, but found {len(errors)}:\n{error_summary}"
            )

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

    def assert_warnings_reviewed_count(self, test_type: RepairTestType, expected: int) -> None:
        """Assert test type reviewed expected number of warnings.

        Args:
            test_type: Type of test to check
            expected: Expected number of warnings reviewed

        Raises:
            AssertionError: If warning count doesn't match
        """
        events = self.get_events_by_type("TEST_CYCLE_COMPLETED")
        event = next(
            (e for e in events if e.get("test_type") == test_type.value),
            None
        )
        if not event:
            raise AssertionError(f"No completion event found for {test_type.value}")
        actual = event.get("warnings_reviewed", 0)
        if actual != expected:
            raise AssertionError(
                f"Expected {expected} warnings reviewed for {test_type.value}, "
                f"got {actual}"
            )

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
        event = next(
            (e for e in events if e.get("test_type") == test_type.value),
            None
        )
        if not event:
            raise AssertionError(f"No completion event found for {test_type.value}")

        final_warnings = event.get("final_warnings", 0)
        if final_warnings > 0:
            raise AssertionError(
                f"Expected no warning regression for {test_type.value}, "
                f"but found {final_warnings} warnings in final execution"
            )

    def assert_no_warning_reappearance(
        self,
        test_type: RepairTestType,
        original_warnings: Tuple[RepairTestWarning, ...]
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
        event = next(
            (e for e in events if e.get("test_type") == test_type.value),
            None
        )
        if not event:
            raise AssertionError(f"No completion event found for {test_type.value}")

        current_warnings = event.get("warning_list", ())

        if not original_warnings:
            return

        # Build set of original warning signatures (file, message)
        original_sigs = {
            (w.file, w.message) for w in original_warnings
        }

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
            raise AssertionError(
                f"Expected no warning reappearance for {test_type.value}, "
                f"but {len(reappeared)} warning(s) reappeared: {reappeared}"
            )

    def get_agent_call_count(self) -> int:
        """Return total agent calls made.

        Returns:
            Total number of agent calls
        """
        return self.total_agent_calls or self.agent_call_count

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

        self._log_event({
            "type": "TEST_CYCLE_STARTED",
            "test_type": config.test_type.value,
            "max_iterations": config.max_iterations
        })

        for iteration in range(1, config.max_iterations + 1):
            # Check circuit breaker
            if self.total_agent_calls >= context.max_total_agent_calls:
                if self._current_project is not None:
                    self.emit(RepairCycleFastFailEvent(
                        type="repair_cycle.fast_fail",
                        timestamp=self.clock.now().isoformat(),
                        source="mock_repair_cycle",
                        test_type=config.test_type,
                        reason="circuit_breaker_triggered",
                        pipeline_run_id=context.pipeline_run_id,
                    ))
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
                    warnings_reviewed += await self.handle_warnings(
                        test_result, config, context
                    )

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
                files_fixed += await self.fix_failures_by_file(
                    grouped, config, context
                )

            # Checkpoint at interval
            if iteration % context.checkpoint_interval == 0:
                await self.checkpoint(config.test_type, iteration, context)

            # Check for simulated interruption (for testing checkpoint/resume)
            if (self._interrupt_after_iteration is not None and
                iteration == self._interrupt_after_iteration and
                (self._interrupt_test_type is None or self._interrupt_test_type == config.test_type)):
                # Simulate interruption (e.g., container crash)
                logger.info(
                    f"Simulated interruption after iteration {iteration} "
                    f"for test_type={config.test_type.value}"
                )
                raise InterruptedError(
                    f"Simulated interruption after iteration {iteration} "
                    f"(checkpoint saved, testing resume functionality)"
                )

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
            "warnings_reviewed": warnings_reviewed,
            "final_warnings": last_test_result.warnings if last_test_result else 0,
            "warning_list": last_test_result.warning_list if last_test_result else (),
            "error": error
        })

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
