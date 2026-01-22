"""Repair cycle service port interface.

This interface defines contracts for test-driven repair cycle orchestration,
where an agent iteratively fixes code until tests pass. Supports multiple
test types (UNIT, INTEGRATION, E2E) with fast-fail behavior and circuit
breaker enforcement.

Key features:
- Test sequencing: UNIT → INTEGRATION → E2E
- Fast-fail: Stops on first test type failure
- Circuit breaker: Limits total agent calls to prevent runaway loops
- File-by-file fixing: Groups failures by file, fixes iteratively
- Warning review: Optional post-pass warning review before completion
- Event emission: Complete audit trail of cycle progress
- Checkpointing: Periodic state saves for recovery after crashes
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from codetoreum.domain.repair_cycle_types import (
    RepairTestRunConfig,
    RepairTestResult,
    RepairTestFailure,
    RepairCycleResult,
)

from .event_emitter import IEventEmitter
from .monitoring import IMonitoredService, MonitoringConfig


# Type alias for context protocol
class RepairCycleContext:
    """Protocol for repair cycle execution context.

    This is a duck-typed interface (not a strict ABC) to allow flexible
    context implementations. All IRepairCycle implementations work with
    any context that provides these attributes.

    Attributes:
        stage_name: Name of the workflow stage (e.g., "fix_failures")
        pipeline_run_id: Unique identifier for this pipeline run
        test_configs: Tuple of RepairTestRunConfig for each test type to run
        agent_name: Name of the agent to execute for repairs
        max_total_agent_calls: Circuit breaker limit (max agent executions)
        checkpoint_interval: How often to save checkpoints (every N agent calls)
    """

    stage_name: str
    pipeline_run_id: str
    test_configs: Tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int


class IRepairCycle(IEventEmitter, IMonitoredService, ABC):
    """Repair cycle orchestration with event emission and monitoring.

    Provides test-driven repair cycle execution where an AI agent iteratively
    fixes code until tests pass. Orchestrates multiple test types in sequence
    (UNIT → INTEGRATION → E2E), with fast-fail on first failure and circuit
    breaker on agent call limits.

    Lifecycle:
        1. execute() called with context and test configs
        2. For each test type:
            - run_tests() executes tests, returns failures and warnings
            - fix_failures_by_file() calls agent to fix failures
            - Optional: handle_warnings() reviews warnings if test_result.failed == 0
            - checkpoint() saves state periodically
        3. Fast-fail: If tests fail at any iteration, execution stops
        4. Circuit breaker: If max_total_agent_calls exceeded, execution stops
        5. Returns RepairCycleResult with complete metrics

    Events emitted:
        - 'repair_cycle.started' → RepairCycleStartedEvent
                                 When cycle begins
        - 'repair_cycle.test_execution_completed' → RepairCycleTestExecutionCompletedEvent
                                                  After each test run
        - 'repair_cycle.test_cycle_completed' → RepairCycleTestCycleCompletedEvent
                                               When all iterations for a test type complete
        - 'repair_cycle.file_fix_started' → RepairCycleFileFixStartedEvent
                                           Before fixing a file's failures
        - 'repair_cycle.file_fix_completed' → RepairCycleFileFixCompletedEvent
                                             After fixing a file
        - 'repair_cycle.warning_review_started' → RepairCycleWarningReviewStartedEvent
                                                 Before reviewing warnings
        - 'repair_cycle.warning_review_completed' → RepairCycleWarningReviewCompletedEvent
                                                   After reviewing warnings
        - 'repair_cycle.fast_fail' → RepairCycleFastFailEvent
                                    When stopping early (test failure or circuit breaker)
        - 'repair_cycle.completed' → RepairCycleCompletedEvent
                                    At cycle end (success or with errors)

    Example:
        async with service as svc:
            # Configure monitoring
            await svc.start_monitoring(
                project_id="proj-123",
                config=MonitoringConfig(project_id="proj-123")
            )

            # Subscribe to events
            svc.on("repair_cycle.completed", handle_completion)

            # Create context
            context = RepairCycleContext(
                stage_name="fix_failures",
                pipeline_run_id="run-456",
                test_configs=(
                    RepairTestRunConfig(test_type=RepairTestType.UNIT),
                    RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
                ),
                agent_name="senior_engineer",
                max_total_agent_calls=100,
                checkpoint_interval=5,
            )

            # Execute repair cycle
            result = await svc.execute(context)
            if result.overall_success:
                print(f"All tests passed in {result.duration_seconds}s")
            else:
                print(f"Some tests failed after {result.total_agent_calls} agent calls")

            await svc.stop_monitoring("proj-123")

    Contract Requirements:
        - All return values must be immutable (frozen dataclasses)
        - All failures/warnings collections must be tuples (not lists)
        - Error handling must be consistent across implementations
        - Idempotency: Same inputs should produce equivalent results (allowing for timing)
        - State consistency: After errors, adapter state must remain valid
        - Concurrent access: Implementations should handle concurrent calls safely
    """

    # ==================== Core Orchestration Methods ====================

    @abstractmethod
    async def execute(self, context: RepairCycleContext) -> RepairCycleResult:
        """Execute complete repair cycle with all configured test types.

        Orchestrates the test-driven repair loop:
        1. For each configured test type (in order: UNIT, INTEGRATION, E2E):
            a. run_tests() to check current status
            b. If tests fail, call fix_failures_by_file() to repair
            c. If review_warnings=True and tests pass, call handle_warnings()
            d. Call checkpoint() at intervals
        2. Fast-fail: Stop test type sequence when tests fail
        3. Circuit breaker: Raise/return error if agent calls exceed limit
        4. Return comprehensive RepairCycleResult with all metrics

        Args:
            context: Repair cycle context with stage info, agent name, limits

        Returns:
            RepairCycleResult with test results, metrics, and completion status

        Raises:
            ValueError: If context is invalid or test configs malformed
            CircuitBreakerTripped: If max_total_agent_calls exceeded
            ExternalServiceError: If external service communication fails
            TimeoutError: If execution exceeds overall timeout

        Events emitted:
            - repair_cycle.started (at begin)
            - repair_cycle.test_execution_completed (after each test run)
            - repair_cycle.file_fix_started/completed (for each file fixed)
            - repair_cycle.test_cycle_completed (after all iterations for a test type)
            - repair_cycle.fast_fail (if stopping early)
            - repair_cycle.completed (at end, regardless of outcome)

        State Guarantees:
            - Idempotent: Same input context produces equivalent results
            - Consistent: State remains valid even if errors occur
            - Traceable: All events have pipeline_run_id for audit trail
        """
        pass

    # ==================== Test Execution Methods ====================

    @abstractmethod
    async def run_tests(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RepairTestResult:
        """Run tests for a specific test type.

        Executes tests (UNIT, INTEGRATION, or E2E) and returns results including:
        - Pass/fail/warning counts
        - Detailed failure information (file, test name, message)
        - Warning details for post-pass review
        - Raw test output for debugging

        Args:
            config: Test configuration (type, timeout, max_iterations)
            context: Repair cycle context

        Returns:
            RepairTestResult with comprehensive test outcome details

        Raises:
            ValueError: If config invalid (e.g., invalid test_type)
            TimeoutError: If test execution exceeds config.timeout
            ExternalServiceError: If test infrastructure unavailable

        Events emitted:
            - repair_cycle.test_execution_completed (after tests finish)

        Contract:
            - Returns RepairTestResult (immutable frozen dataclass)
            - failures tuple contains RepairTestFailure for each failure
            - warning_list tuple contains RepairTestWarning for each warning
            - If failed == 0, failures tuple is empty
            - iteration is 1-indexed (never 0)
            - timestamp is ISO 8601 format
        """
        pass

    # ==================== Failure Fixing Methods ====================

    @abstractmethod
    async def fix_failures_by_file(
        self,
        grouped_failures: Dict[str, Tuple[RepairTestFailure, ...]],
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Fix test failures by calling agent to modify files.

        Groups failures by file and calls the agent to fix each file,
        respecting max_file_iterations limit per file. Returns count of
        files successfully fixed.

        Args:
            grouped_failures: Dict mapping file path to tuple of failures in that file
            config: Test configuration (used for max_file_iterations)
            context: Repair cycle context (used for agent name, etc.)

        Returns:
            Number of files that were fixed (had all failures resolved)

        Raises:
            ValueError: If grouped_failures malformed
            CircuitBreakerTripped: If agent calls exceed context.max_total_agent_calls
            ExternalServiceError: If agent execution fails

        Events emitted:
            - repair_cycle.file_fix_started (before fixing each file)
            - repair_cycle.file_fix_completed (after fixing each file)

        Contract:
            - Returns non-negative integer
            - Respects config.max_file_iterations limit per file
            - If grouped_failures is empty, returns 0 (no error)
            - File-level idempotent: Fixing same file multiple times is safe
            - Tracks agent calls and enforces circuit breaker
        """
        pass

    # ==================== Warning Handling Methods ====================

    @abstractmethod
    async def handle_warnings(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Review and handle test warnings when tests have passed.

        Called only when:
        1. Tests have completed successfully (test_result.failed == 0)
        2. config.review_warnings is True
        3. test_result has non-empty warning_list

        Returns count of warnings reviewed.

        Args:
            test_result: Successful test result with warnings to review
            config: Test configuration (used for review_warnings flag)
            context: Repair cycle context

        Returns:
            Number of warnings reviewed

        Raises:
            ValueError: If test_result.failed != 0 (contract violation)
            ExternalServiceError: If warning review process fails

        Events emitted:
            - repair_cycle.warning_review_started (at begin)
            - repair_cycle.warning_review_completed (at end)

        Contract:
            - Returns non-negative integer
            - If config.review_warnings is False, returns 0
            - If test_result.warning_list is empty, returns 0 (no error)
            - Only called when test_result.failed == 0 (orchestrator enforces)
        """
        pass

    # ==================== State Management Methods ====================

    @abstractmethod
    async def checkpoint(
        self,
        test_type: str,
        iteration: int,
        context: RepairCycleContext,
    ) -> None:
        """Save repair cycle state checkpoint for recovery.

        Called periodically (every checkpoint_interval agent calls) to save
        cycle state to persistent storage. Allows recovery if container crashes
        before cycle completes.

        Args:
            test_type: Test type being executed
            iteration: Current iteration number
            context: Repair cycle context with all state

        Returns:
            None (void operation)

        Raises:
            PersistenceError: If checkpoint storage fails

        Events emitted:
            None (checkpointing is transparent)

        Contract:
            - Always succeeds or raises exception (no silent failures)
            - Idempotent: Multiple checkpoints for same iteration are safe
            - Does not modify context
            - Can be called multiple times without error
        """
        pass
