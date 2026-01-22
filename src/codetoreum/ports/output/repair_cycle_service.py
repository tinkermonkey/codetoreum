"""Repair cycle service port interface for iterative test-driven code fixing.

This interface defines contracts for managing repair cycles, which automate the
process of iteratively executing tests, identifying failures and warnings, and
coordinating fixes until tests pass or circuit breakers trigger.

Repair cycles are vendor-agnostic abstractions over test execution frameworks
(pytest, jest, vitest, mocha, etc.) and code repair processes. They represent
multi-stage test-driven repair operations that span multiple agent executions.

The repair cycle manages:
1. Test execution (UNIT → INTEGRATION → E2E in strict order)
2. Failure/warning analysis
3. Agent coordination for fixes
4. Checkpoint management for resumability
5. Circuit breaker enforcement (max agent calls)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple

from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    RepairCycleResult,
    RepairCycleStageConfig,
    RepairTestFailure,
    RepairTestResult,
    RepairTestType,
    RepairTestWarning,
)

from .event_emitter import IEventEmitter
from .monitoring import IMonitoredService, MonitoringConfig


@dataclass(frozen=True)
class RepairCycleStatus:
    """Current status of a repair cycle.

    Immutable snapshot of repair cycle state at a point in time.

    Attributes:
        cycle_id: Unique identifier for this repair cycle
        project_id: Associated project
        stage_name: Name of the workflow stage (e.g., "fix_failures")
        state: Current lifecycle state (PENDING, IN_PROGRESS, COMPLETED, FAILED, ABORTED)
        test_type_index: Current test type index (0=UNIT, 1=INTEGRATION, 2=E2E)
        test_type_count: Total test types to execute
        current_iteration: Current iteration number for the test type
        max_iterations: Maximum iterations allowed for current test type
        agent_call_count: Number of agent calls made so far
        max_agent_calls: Circuit breaker limit for total agent calls
        started_at: ISO 8601 timestamp when cycle started
        completed_at: ISO 8601 timestamp when cycle completed (None if in progress)
        checkpoint_iteration: Last iteration where state was checkpointed
    """

    cycle_id: str
    project_id: str
    stage_name: str
    state: str  # PENDING | IN_PROGRESS | COMPLETED | FAILED | ABORTED
    test_type_index: int
    test_type_count: int
    current_iteration: int
    max_iterations: int
    agent_call_count: int
    max_agent_calls: int
    started_at: str
    completed_at: Optional[str] = None
    checkpoint_iteration: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate status after initialization."""
        if not self.cycle_id:
            raise ValueError("cycle_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.stage_name:
            raise ValueError("stage_name is required")
        if self.test_type_index < 0:
            raise ValueError("test_type_index must be >= 0")
        if self.current_iteration < 0:
            raise ValueError("current_iteration must be >= 0")
        if self.agent_call_count < 0:
            raise ValueError("agent_call_count must be >= 0")


@dataclass(frozen=True)
class TestExecutionRequest:
    """Request to execute a single test type.

    Immutable request for executing tests within a repair cycle.

    Attributes:
        cycle_id: Repair cycle to execute tests for
        test_type: Type of test to execute (UNIT, INTEGRATION, E2E)
        iteration: Iteration number for this test type
        timeout: Timeout in seconds for test execution
        container_id: Container to execute tests in
    """

    cycle_id: str
    test_type: RepairTestType
    iteration: int
    timeout: int
    container_id: str

    def __post_init__(self) -> None:
        """Validate request after initialization."""
        if not self.cycle_id:
            raise ValueError("cycle_id is required")
        if self.iteration < 1:
            raise ValueError("iteration must be >= 1")
        if self.timeout <= 0:
            raise ValueError("timeout must be > 0")
        if not self.container_id:
            raise ValueError("container_id is required")


@dataclass(frozen=True)
class FixRequest:
    """Request to fix failures in specific file(s).

    Immutable request for agent to fix identified test failures.

    Attributes:
        cycle_id: Repair cycle to fix for
        test_file: Test file that failed
        test_type: Type of test that failed
        failures: List of failures to fix
        iteration: Iteration number for this fix attempt
        container_id: Container to execute fixes in
    """

    cycle_id: str
    test_file: str
    test_type: RepairTestType
    failures: Tuple[RepairTestFailure, ...]
    iteration: int
    container_id: str

    def __post_init__(self) -> None:
        """Validate request after initialization."""
        if not self.cycle_id:
            raise ValueError("cycle_id is required")
        if not self.test_file:
            raise ValueError("test_file is required")
        if not self.failures:
            raise ValueError("failures must not be empty")
        if self.iteration < 1:
            raise ValueError("iteration must be >= 1")
        if not self.container_id:
            raise ValueError("container_id is required")


@dataclass(frozen=True)
class WarningReviewRequest:
    """Request to review and fix warnings.

    Immutable request for agent to review and address test warnings.

    Attributes:
        cycle_id: Repair cycle to review warnings for
        source_file: Source file where warnings occurred
        test_type: Type of test that generated warnings
        warnings: List of warnings to review
        iteration: Iteration number for this review
        container_id: Container to execute review in
    """

    cycle_id: str
    source_file: str
    test_type: RepairTestType
    warnings: Tuple[RepairTestWarning, ...]
    iteration: int
    container_id: str

    def __post_init__(self) -> None:
        """Validate request after initialization."""
        if not self.cycle_id:
            raise ValueError("cycle_id is required")
        if not self.source_file:
            raise ValueError("source_file is required")
        if not self.warnings:
            raise ValueError("warnings must not be empty")
        if self.iteration < 1:
            raise ValueError("iteration must be >= 1")
        if not self.container_id:
            raise ValueError("container_id is required")


class IRepairCycleService(IEventEmitter, IMonitoredService, ABC):
    """Repair cycle management with event emission and project-wide monitoring.

    Provides vendor-agnostic abstraction for test-driven repair cycles, enabling:
    1. Querying repair cycle status and test results
    2. Starting repair cycles with configuration
    3. Executing tests and analyzing results
    4. Coordinating agent-based fixes for failures/warnings
    5. Managing checkpoints for long-running cycles
    6. Enforcing circuit breakers (max agent calls)
    7. Monitoring project for repair cycle events

    Repair cycles execute in strict order:
    - Test types: UNIT → INTEGRATION → E2E
    - For each test type: Test → Analyze → Fix → Validate (iterate)

    Events emitted:
        - 'repair_cycle.started' → RepairCycleStartedEvent
                                  When repair cycle begins
        - 'repair_cycle.test_execution_started' → RepairCycleTestExecutionStartedEvent
                                                 Before test execution
        - 'repair_cycle.test_execution_completed' → RepairCycleTestExecutionCompletedEvent
                                                   After test execution with results
        - 'repair_cycle.fix_cycle_started' → RepairCycleFixCycleStartedEvent
                                            When fix cycle starts after failures
        - 'repair_cycle.file_fix_started' → RepairCycleFileFixStartedEvent
                                           Before fixing specific file
        - 'repair_cycle.file_fix_completed' → RepairCycleFileFixCompletedEvent
                                             After fixing specific file
        - 'repair_cycle.warning_review_started' → RepairCycleWarningReviewStartedEvent
                                                 Before reviewing warnings
        - 'repair_cycle.warning_review_completed' → RepairCycleWarningReviewCompletedEvent
                                                   After warning review
        - 'repair_cycle.test_cycle_completed' → RepairCycleTestCycleCompletedEvent
                                               When test type cycle completes
        - 'repair_cycle.fast_fail' → RepairCycleFastFailEvent
                                    When circuit breaker triggers
        - 'repair_cycle.completed' → RepairCycleCompletedEvent
                                    When entire repair cycle finishes

    Example:
        async with service as svc:
            # Start monitoring for repair cycle events
            await svc.start_monitoring(
                project_id="proj-123",
                config=MonitoringConfig(project_id="proj-123")
            )

            # Subscribe to repair cycle events
            svc.on("repair_cycle.completed", handle_cycle_complete)

            # Start a repair cycle with configuration
            config = RepairCycleStageConfig(
                name="fix_failures",
                test_configs=(
                    RepairTestRunConfig(RepairTestType.UNIT, timeout=900),
                    RepairTestRunConfig(RepairTestType.INTEGRATION, timeout=1800),
                )
            )
            cycle_id = await svc.start_repair_cycle(
                project_id="proj-123",
                config=config,
                container_id="container-456",
                pipeline_run_id="pipeline-789"
            )

            # Monitor repair cycle progress
            status = await svc.get_repair_cycle_status(cycle_id)
            while status.state == "IN_PROGRESS":
                status = await svc.get_repair_cycle_status(cycle_id)
                # Wait and check again

            # Get final results
            result = await svc.get_repair_cycle_result(cycle_id)
            if result.overall_success:
                print("All tests passed!")
            else:
                print(f"Failed: {result.test_results}")

            # Stop monitoring
            await svc.stop_monitoring("proj-123")
    """

    # Query Operations

    @abstractmethod
    async def get_repair_cycle_status(self, cycle_id: str) -> RepairCycleStatus:
        """Get current status of a repair cycle.

        Returns the current state snapshot of the repair cycle, including
        progress (test type, iteration), agent call counts, and timing.

        Args:
            cycle_id: ID of repair cycle to query

        Returns:
            RepairCycleStatus: Current status snapshot

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def get_test_results(
        self, cycle_id: str, test_type: Optional[RepairTestType] = None
    ) -> List[RepairTestResult]:
        """Retrieve test results from a repair cycle.

        Returns all test results executed so far in the repair cycle.
        If test_type is specified, returns only results for that test type.

        Args:
            cycle_id: ID of repair cycle
            test_type: Optional test type filter (UNIT, INTEGRATION, E2E)

        Returns:
            List[RepairTestResult]: Test results (may be empty if no tests executed yet)

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def get_cycle_result(self, cycle_id: str) -> Optional[RepairCycleResult]:
        """Get final result from completed repair cycle.

        Returns the complete final result of a repair cycle, including
        results for all test types executed. Only available after cycle completes.

        Args:
            cycle_id: ID of repair cycle

        Returns:
            RepairCycleResult if cycle completed, None if still in progress or failed

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def get_checkpoint(self, cycle_id: str, iteration: int) -> Optional[dict]:
        """Get saved checkpoint state from repair cycle.

        Retrieves saved state at a specific checkpoint iteration for potential resume.

        Args:
            cycle_id: ID of repair cycle
            iteration: Checkpoint iteration number

        Returns:
            Dictionary containing checkpoint state, or None if not found

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    # Command Operations

    @abstractmethod
    async def start_repair_cycle(
        self,
        project_id: str,
        config: RepairCycleStageConfig,
        container_id: str,
        pipeline_run_id: str,
    ) -> str:
        """Start a new repair cycle.

        Initiates a repair cycle with the provided configuration. The cycle will
        execute test types in order (UNIT → INTEGRATION → E2E) according to the
        test_configs in the configuration.

        Args:
            project_id: Project to run repair cycle for
            config: RepairCycleStageConfig with test configurations
            container_id: Container to run tests/fixes in
            pipeline_run_id: Pipeline execution ID for tracing

        Returns:
            str: ID of the created repair cycle

        Raises:
            ValidationError: Configuration invalid
            ResourceNotFoundError: Project or container doesn't exist
            ExternalServiceError: Service communication failure

        Events:
            Emits 'repair_cycle.started' event
        """
        pass

    @abstractmethod
    async def execute_test(self, request: TestExecutionRequest) -> RepairTestResult:
        """Execute a single test type in repair cycle.

        Runs the specified test type for the repair cycle iteration,
        returning all passed/failed/warning counts and details.

        Args:
            request: TestExecutionRequest with test type and container

        Returns:
            RepairTestResult: Results from test execution

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            InvalidStateError: Repair cycle not in correct state for test execution
            TimeoutError: Test execution exceeded timeout
            ExternalServiceError: Service communication failure

        Events:
            Emits 'repair_cycle.test_execution_started' event
            Emits 'repair_cycle.test_execution_completed' event
        """
        pass

    @abstractmethod
    async def coordinate_fix(
        self,
        request: FixRequest,
        agent_executor: "IAgentExecutor",  # noqa: F821
    ) -> bool:
        """Coordinate agent fix for identified test failures.

        Requests agent to fix the specified test failures, then validates
        by re-running tests. Returns success if failures resolved.

        Args:
            request: FixRequest with failures to fix
            agent_executor: Agent executor to coordinate fix with

        Returns:
            bool: True if failures fixed, False if still failing

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            InvalidStateError: Repair cycle not in correct state
            PermissionError: Agent cannot execute fixes
            ExternalServiceError: Service communication failure

        Events:
            Emits 'repair_cycle.file_fix_started' event
            Emits 'repair_cycle.file_fix_completed' event
        """
        pass

    @abstractmethod
    async def coordinate_warning_review(
        self,
        request: WarningReviewRequest,
        agent_executor: "IAgentExecutor",  # noqa: F821
    ) -> bool:
        """Coordinate agent review and fix of warnings.

        Requests agent to review the specified warnings and address them,
        then validates by re-running tests. Returns success if warnings resolved.

        Args:
            request: WarningReviewRequest with warnings to review
            agent_executor: Agent executor to coordinate review with

        Returns:
            bool: True if warnings addressed, False otherwise

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            InvalidStateError: Repair cycle not in correct state
            PermissionError: Agent cannot execute review
            ExternalServiceError: Service communication failure

        Events:
            Emits 'repair_cycle.warning_review_started' event
            Emits 'repair_cycle.warning_review_completed' event
        """
        pass

    @abstractmethod
    async def record_test_cycle_result(
        self, cycle_id: str, test_type: RepairTestType, result: CycleResult
    ) -> None:
        """Record the final result for a test type cycle.

        Saves the aggregated result after all iterations for a test type complete.

        Args:
            cycle_id: Repair cycle to record result for
            test_type: Test type that completed
            result: CycleResult with aggregated metrics

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            InvalidStateError: Repair cycle not in correct state
            ExternalServiceError: Service communication failure

        Events:
            Emits 'repair_cycle.test_cycle_completed' event
        """
        pass

    @abstractmethod
    async def abort_cycle(self, cycle_id: str, reason: str) -> None:
        """Abort a running repair cycle.

        Stops the repair cycle immediately with the specified reason
        (e.g., circuit breaker triggered, manual abort).

        Args:
            cycle_id: Repair cycle to abort
            reason: Reason for abort

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            InvalidStateError: Repair cycle already completed
            ExternalServiceError: Service communication failure

        Events:
            Emits 'repair_cycle.fast_fail' event if circuit breaker
        """
        pass

    @abstractmethod
    async def complete_cycle(self, cycle_id: str, result: RepairCycleResult) -> None:
        """Mark repair cycle as complete with final result.

        Records the final result and marks the cycle as completed.

        Args:
            cycle_id: Repair cycle to complete
            result: RepairCycleResult with final metrics and results

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            InvalidStateError: Repair cycle already completed
            ExternalServiceError: Service communication failure

        Events:
            Emits 'repair_cycle.completed' event
        """
        pass

    @abstractmethod
    async def save_checkpoint(
        self, cycle_id: str, iteration: int, state: dict
    ) -> None:
        """Save checkpoint state at iteration.

        Saves state for potential resumption at this checkpoint.

        Args:
            cycle_id: Repair cycle to save checkpoint for
            iteration: Iteration number
            state: State dictionary to save

        Raises:
            ResourceNotFoundError: Repair cycle doesn't exist
            ValidationError: State dictionary invalid
            ExternalServiceError: Service communication failure
        """
        pass
