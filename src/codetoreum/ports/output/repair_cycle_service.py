"""Repair cycle port interface for iterative test-driven code fixing.

This interface defines contracts for the repair cycle, which automates the
process of iteratively executing tests, identifying failures and warnings, and
coordinating fixes until tests pass or circuit breakers trigger.

The repair cycle is a deterministic test-fix-validate loop used in the
configured repair cycle stage of the SDLC workflow. It executes test types sequentially (UNIT →
INTEGRATION → E2E) with fast-fail behavior.

For each test type:
1. Run tests
2. Group failures by file
3. Fix each file
4. Re-run tests
5. Repeat until tests pass or max iterations reached
6. Optionally review warnings after success
"""

from typing import Protocol

from codetoreum.domain.repair_cycle_types import (
    RepairCycleResult,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
)


class RepairCycleContext(Protocol):
    """Context for repair cycle execution.

    Protocol defining the execution context passed to repair cycle operations.
    Provides configuration and state information for the repair cycle.

    Attributes:
        stage_name: Name of the workflow stage (e.g., "fix_failures")
        workflow_run_id: Unique identifier for the workflow run
        work_item_id: Unique identifier for the work item being repaired (issue/task)
        test_configs: Tuple of RepairTestRunConfig for each test type
        agent_name: Name of agent executing repairs
        max_total_agent_calls: Maximum total agent calls allowed (circuit breaker)
        checkpoint_interval: Iteration interval for checkpointing (e.g., every 5 iterations)
    """

    stage_name: str
    workflow_run_id: str
    work_item_id: str
    test_configs: tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int


class IRepairCycle(Protocol):
    """Port interface for repair cycle operations.

    The repair cycle is a deterministic test-fix-validate loop used in the
    configured repair cycle stage of the SDLC workflow. It executes test types sequentially
    (UNIT → INTEGRATION → E2E) with fast-fail behavior.

    For each test type:
    1. Run tests
    2. Group failures by file
    3. Fix each file
    4. Re-run tests
    5. Repeat until tests pass or max iterations reached
    6. Optionally review warnings after success

    Raises:
        CircuitBreakerOpenError: When max_total_agent_calls exceeded
        TimeoutError: When test execution exceeds timeout
        JSONParseError: When agent returns invalid JSON (after retries)
    """

    async def execute(self, context: RepairCycleContext) -> RepairCycleResult:
        """Execute complete repair cycle for all configured test types.

        Orchestrates the full test-fix-validate loop across all configured test
        types (UNIT, INTEGRATION, E2E) in sequence. For each test type, runs
        tests, analyzes failures, coordinates fixes via agent, and validates
        until tests pass or circuit breaker triggers.

        Args:
            context: Repair cycle execution context with configuration

        Returns:
            RepairCycleResult with overall success status and per-test-type results

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        ...

    async def run_tests(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RepairTestResult:
        """Execute tests for a specific test type.

        Runs the test framework (pytest, jest, etc.) for the specified test type,
        collecting pass/fail counts, failure details, and warnings.

        Args:
            config: Test run configuration (timeout, max iterations, etc.)
            context: Repair cycle context

        Returns:
            RepairTestResult with pass/fail counts and failure details

        Raises:
            TimeoutError: When test execution exceeds timeout
            JSONParseError: When agent returns invalid JSON (after retries)
        """
        ...

    async def fix_failures_by_file(
        self,
        grouped_failures: dict[str, tuple[RepairTestFailure, ...]],
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Fix test failures grouped by file.

        Iterates through files with failures, coordinating agent-based fixes
        for each file. Agents analyze failure details and implement fixes,
        then tests are re-run to validate.

        Args:
            grouped_failures: Map of test file name to failures in that file
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Number of files fixed (may be less than input if some fail)

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        ...

    async def handle_warnings(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> int:
        """Review and fix warnings from test execution.

        Only called when:
        - Tests pass (0 failures)
        - Warnings exist
        - config.review_warnings is True

        Coordinates with agent to review and address warnings.

        Args:
            test_result: Test result containing warnings
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Number of warning files reviewed

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        ...

    async def checkpoint(
        self,
        test_type: RepairTestType,
        iteration: int,
        context: RepairCycleContext,
    ) -> None:
        """Save repair cycle state for resume after failures.

        Called at checkpoint_interval iterations (e.g., every 5 iterations).
        Saves sufficient state to resume from this point if cycle is interrupted.

        Args:
            test_type: Current test type being executed
            iteration: Current iteration number
            context: Repair cycle context
        """
        ...
