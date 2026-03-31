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
    FailureClassification,
    RepairCycleAgentConfig,
    RepairCycleResult,
    RepairTestFailure,
    RepairTestResult,
    RepairTestRunConfig,
    RepairTestType,
    SystemicAnalysisResult,
    SystemicFixResult,
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
        agent_config: Optional RepairCycleAgentConfig for agent specialization. None means
                      fall back to stage's default agent (agent_name). Supports assigning
                      specialized agents to specific repair cycle sub-tasks.
        iteration: Current iteration number in the repair cycle (for analysis context)
        prior_fix_attempts: Immutable tuple of descriptions of prior fix attempts
                           (for escalation and re-classification)
        prior_classifications: Immutable tuple of prior classification results
                              (for escalation and re-classification)
    """

    stage_name: str
    workflow_run_id: str
    work_item_id: str
    test_configs: tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int
    agent_config: RepairCycleAgentConfig | None
    iteration: int
    prior_fix_attempts: tuple[str, ...]
    prior_classifications: tuple


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

    async def analyze_systemic_issues(
        self,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> str:
        """Analyze failure root causes at systemic level.

        Classifies test failures to identify systemic patterns that affect
        multiple tests or require cross-cutting fixes.

        Args:
            test_result: Test result containing failures to analyze
            config: Test run configuration
            context: Repair cycle context

        Returns:
            Analysis summary from the agent

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        ...

    async def apply_systemic_fixes(
        self,
        analysis_summary: str,
        test_result: RepairTestResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Apply cross-cutting fixes based on systemic analysis.

        Uses the systemic analysis to apply fixes that address root causes
        affecting multiple tests. These are broader fixes beyond file-level
        changes, such as architecture adjustments or dependency updates.

        Args:
            analysis_summary: Summary from systemic analysis
            test_result: Test result that triggered the analysis
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if fixes were successfully applied

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        ...

    async def fix_failures_systemically(
        self,
        failures: tuple[RepairTestFailure, ...],
        analysis_result: SystemicAnalysisResult,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> SystemicFixResult:
        """Apply a coordinated holistic fix addressing the root cause across all affected files.

        Unlike fix_failures_by_file(), this method issues a single agent invocation
        presenting all failures together with the root cause context from systemic analysis.
        Use when analysis_result.cross_cutting is True.

        Args:
            failures: Immutable tuple of test failures to address
            analysis_result: Systemic analysis result with root cause and affected files
            config: Test run configuration
            context: Repair cycle context

        Returns:
            SystemicFixResult indicating whether the holistic fix succeeded and which
            files were modified

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        ...

    async def rebuild_environment(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Rebuild test environment after systemic fixes.

        Coordinates with the env_rebuild agent to rebuild the test environment
        after systemic fixes, ensuring dependencies and configuration are
        properly updated.

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if environment was successfully rebuilt

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        ...

    async def verify_environment(
        self,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> bool:
        """Verify that rebuilt environment is ready for testing.

        Coordinates with the env_verification agent to verify that the
        rebuilt environment is properly configured and ready for test execution.

        Args:
            config: Test run configuration
            context: Repair cycle context

        Returns:
            True if environment verification passed

        Raises:
            CircuitBreakerOpenError: When circuit breaker is open
        """
        ...

    async def checkpoint(
        self,
        test_type: RepairTestType,
        iteration: int,
        context: RepairCycleContext,
    ) -> bool:
        """Save repair cycle state for resume after failures.

        Called at checkpoint_interval iterations (e.g., every 5 iterations).
        Saves sufficient state to resume from this point if cycle is interrupted.

        Args:
            test_type: Current test type being executed
            iteration: Current iteration number
            context: Repair cycle context

        Returns:
            True if checkpoint saved successfully, False otherwise
        """
        ...
