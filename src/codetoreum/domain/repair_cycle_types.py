"""Repair cycle domain types and value objects.

Establishes the foundational domain model for the repair cycle, including enums,
value objects, and configuration types. All types are immutable (frozen dataclasses)
following the pure domain layer pattern with no external dependencies.

The repair cycle automates iterative testing and fixing:
1. Executes tests in order: UNIT → INTEGRATION → E2E
2. For each test type, runs up to max_iterations cycles of:
   - Execute test
   - If failures, agent fixes issues
   - If warnings and review_warnings=True, agent reviews and fixes
   - Validate fixes by re-running tests
3. Tracks results, failures, and warnings at each stage
4. Provides configuration for timeout, max iterations, and circuit breakers

**Immutability Pattern**: All types use @dataclass(frozen=True) for immutability:
- Frozen dataclasses are hashable and thread-safe
- Tuples instead of lists for collection fields
- All fields are read-only after construction
- Attempting to modify raises FrozenInstanceError
- Events represent immutable facts in the audit trail

Reference: review_events.py for event sourcing immutability patterns
"""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Systemic fix dispatch threshold: maximum failures before falling back to file-level fixes.
# When CODE_DEFECT + cross_cutting=True has more than this many failures, the repair cycle
# falls back to fix_failures_by_file() to prevent overwhelming the systemic fix agent.
SYSTEMIC_FIX_FAILURE_CEILING = 50


class FailureClassification(str, Enum):
    """Classification of the root cause of test failures.

    Enables systemic analysis to categorize failures and dispatch to appropriate
    handling strategy without wasting agent calls on unfixable problems.

    **Enum Values:**
    - CODE_DEFECT: Issue is in the source code (traditional fix path)
    - ENVIRONMENT_ISSUE: Environment setup problem (rebuild/verify path)
    - TRANSIENT_FAILURE: Temporary failure, likely to pass on retry (no fix)
    - DEPENDENCY_ISSUE: External dependency problem (systemic fix path)
    - CONFIGURATION_ISSUE: Configuration error (systemic fix path)

    **Serialization**: Inherits from `str, Enum` for direct JSON serialization
    without `.value` access.
    """

    CODE_DEFECT = "code_defect"
    ENVIRONMENT_ISSUE = "environment_issue"
    TRANSIENT_FAILURE = "transient_failure"
    DEPENDENCY_ISSUE = "dependency_issue"
    CONFIGURATION_ISSUE = "configuration_issue"


class RepairTestType(Enum):
    """Test types in execution order.

    The repair cycle must execute test types in strict order:
    1. UNIT - Unit tests (fastest, most isolated)
    2. INTEGRATION - Integration tests (medium speed, component interaction)
    3. E2E - End-to-end tests (slowest, full system validation)

    This ordering ensures fast feedback on basic issues before running slower tests.
    """

    UNIT = "UNIT"
    INTEGRATION = "INTEGRATION"
    E2E = "E2E"


@dataclass(frozen=True)
class RepairTestFailure:
    """Represents a single test failure.

    Immutable record of a test failure with location and details.

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Attempting to modify any field raises FrozenInstanceError.

    Attributes:
        file: Test file name (e.g., "test_auth.py")
        test: Test function/method name (e.g., "test_login_success")
        message: Failure message from test output
    """

    file: str  # Test file name
    test: str  # Test function/method name
    message: str  # Failure message

    def __post_init__(self) -> None:
        """Validate failure after initialization."""
        if not self.file:
            msg = "file is required"
            raise ValueError(msg)
        if not self.test:
            msg = "test is required"
            raise ValueError(msg)
        if not self.message:
            msg = "message is required"
            raise ValueError(msg)


@dataclass(frozen=True)
class RepairTestWarning:
    """Represents a single test warning.

    Immutable record of a warning found during testing (e.g., deprecation warning,
    performance warning).

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Attempting to modify any field raises FrozenInstanceError.

    Attributes:
        file: Source file name where warning occurred (e.g., "auth.py")
        message: Warning message
    """

    file: str  # Source file name
    message: str  # Warning message

    def __post_init__(self) -> None:
        """Validate warning after initialization."""
        if not self.file:
            msg = "file is required"
            raise ValueError(msg)
        if not self.message:
            msg = "message is required"
            raise ValueError(msg)


@dataclass(frozen=True)
class RepairTestResult:
    """Result from a single test execution.

    Immutable record of executing a test type in a single iteration.
    Captures test counts, failures, warnings, and raw output.

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Collections stored as immutable Tuples instead of Lists.

    Attributes:
        test_type: Type of test executed (UNIT, INTEGRATION, E2E)
        iteration: Iteration number (1-based) within the test cycle
        passed: Number of tests that passed
        failed: Number of tests that failed
        warnings: Number of warnings found
        failures: Immutable tuple of RepairTestFailure objects
        warning_list: Immutable tuple of RepairTestWarning objects
        raw_output: Raw test execution output (for debugging)
        timestamp: ISO 8601 timestamp when test executed
    """

    test_type: RepairTestType
    iteration: int
    passed: int
    failed: int
    warnings: int
    failures: tuple[RepairTestFailure, ...]  # Immutable tuple
    warning_list: tuple[RepairTestWarning, ...]  # Immutable tuple
    raw_output: str
    timestamp: str

    def __post_init__(self) -> None:
        """Validate result after initialization."""
        if self.iteration < 1:
            msg = "iteration must be >= 1"
            raise ValueError(msg)
        if self.passed < 0:
            msg = "passed must be >= 0"
            raise ValueError(msg)
        if self.failed < 0:
            msg = "failed must be >= 0"
            raise ValueError(msg)
        if self.warnings < 0:
            msg = "warnings must be >= 0"
            raise ValueError(msg)
        if not self.timestamp:
            msg = "timestamp is required"
            raise ValueError(msg)

        # Consistency check: failed count must match failures list length
        if len(self.failures) != self.failed:
            msg = f"failed count mismatch: {len(self.failures)} failures in list but failed={self.failed}"
            raise ValueError(msg)

        # Consistency check: warnings count must match warning_list length
        if len(self.warning_list) != self.warnings:
            msg = f"warnings count mismatch: {len(self.warning_list)} warnings in list but warnings={self.warnings}"
            raise ValueError(msg)


@dataclass(frozen=True)
class CycleResult:
    """Result from a complete test type cycle (all iterations).

    Immutable record of executing all iterations for a single test type,
    including the final result, error details, and metrics.

    **Immutability**: Frozen dataclass - all fields read-only after construction.

    Attributes:
        test_type: Type of test that was cycled (UNIT, INTEGRATION, E2E)
        passed: True if all tests passed by final iteration
        iterations: Number of iterations executed for this test type
        final_result: Final RepairTestResult object, None if failed before completion
        error: Error message if cycle failed, None if successful
        files_fixed: Number of unique files fixed during this cycle
        warnings_reviewed: Number of warnings reviewed and addressed
        duration_seconds: Total time spent on this test type cycle
    """

    test_type: RepairTestType
    passed: bool
    iterations: int
    final_result: RepairTestResult | None
    error: str | None
    files_fixed: int
    warnings_reviewed: int
    duration_seconds: float

    def __post_init__(self) -> None:
        """Validate cycle result after initialization."""
        if self.iterations < 0:
            msg = "iterations must be >= 0"
            raise ValueError(msg)
        if self.files_fixed < 0:
            msg = "files_fixed must be >= 0"
            raise ValueError(msg)
        if self.warnings_reviewed < 0:
            msg = "warnings_reviewed must be >= 0"
            raise ValueError(msg)
        if self.duration_seconds < 0:
            msg = "duration_seconds must be >= 0"
            raise ValueError(msg)

        # Consistency check: passed state must align with final_result/error
        if self.passed and self.final_result is None:
            msg = "passed=True but final_result is None (expected successful test result)"
            raise ValueError(msg)
        if self.passed and self.error is not None:
            msg = f"passed=True but error is set: '{self.error}' (contradiction)"
            raise ValueError(msg)

        # Note: passed=False with final_result is allowed (failed but completed)
        # Note: passed=False with error is the expected failure case


@dataclass(frozen=True)
class RepairCycleResult:
    """Overall result from complete repair cycle (all test types).

    Immutable record of the entire repair cycle execution, containing results
    for each test type executed in sequence (UNIT → INTEGRATION → E2E).

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Collections stored as immutable Tuples instead of Lists.

    Attributes:
        stage: Name of the workflow stage (e.g., "fix_failures", "fix_warnings")
        test_results: Immutable tuple of CycleResult objects for each test type executed
        overall_success: True if all test types passed
        total_agent_calls: Total number of agent calls made during entire cycle
        duration_seconds: Total time spent on entire repair cycle
        timestamp: ISO 8601 timestamp when cycle started
    """

    stage: str
    test_results: tuple[CycleResult, ...]  # Immutable tuple
    overall_success: bool
    total_agent_calls: int
    duration_seconds: float
    timestamp: str

    def __post_init__(self) -> None:
        """Validate cycle result after initialization."""
        if not self.stage:
            msg = "stage is required"
            raise ValueError(msg)
        if self.total_agent_calls < 0:
            msg = "total_agent_calls must be >= 0"
            raise ValueError(msg)
        if self.duration_seconds < 0:
            msg = "duration_seconds must be >= 0"
            raise ValueError(msg)
        if not self.timestamp:
            msg = "timestamp is required"
            raise ValueError(msg)

        # Consistency check: overall_success must match all test results
        if self.test_results:
            all_passed = all(r.passed for r in self.test_results)
            if self.overall_success and not all_passed:
                failed_types = [r.test_type.value for r in self.test_results if not r.passed]
                msg = f"overall_success=True but some test types failed: {failed_types}"
                raise ValueError(msg)
            if not self.overall_success and all_passed:
                msg = "overall_success=False but all test results passed (inconsistency)"
                raise ValueError(msg)
        # Empty test_results with overall_success=True is suspicious but may be valid
        # (e.g., no tests configured). Log warning but don't raise.
        elif self.overall_success:
            logger.warning("overall_success=True but test_results is empty", extra={"stage": self.stage})


@dataclass(frozen=True)
class RepairTestRunConfig:
    """Configuration for a single test type run.

    Immutable configuration controlling how a single test type (UNIT, INTEGRATION, E2E)
    is executed within the repair cycle.

    **Immutability**: Frozen dataclass - all fields read-only after construction.

    Attributes:
        test_type: Type of test to run (UNIT, INTEGRATION, E2E)
        timeout: Timeout in seconds for a single test execution (default 900s = 15min)
        max_iterations: Maximum iterations to attempt (test-fix-validate cycles)
        review_warnings: Whether to review and fix warnings in addition to failures
        max_file_iterations: Maximum times to attempt fixing a single file before giving up
    """

    test_type: RepairTestType
    timeout: int = 900  # Timeout in seconds
    max_iterations: int = 5  # Max test-fix-validate iterations
    review_warnings: bool = True  # Whether to review/fix warnings
    max_file_iterations: int = 3  # Max times to attempt fixing a single file

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.timeout <= 0:
            msg = "timeout must be > 0"
            raise ValueError(msg)
        if self.max_iterations <= 0:
            msg = "max_iterations must be > 0"
            raise ValueError(msg)
        if self.max_file_iterations <= 0:
            msg = "max_file_iterations must be > 0"
            raise ValueError(msg)


@dataclass(frozen=True)
class RepairCycleAgentConfig:
    """Maps repair cycle sub-tasks to specific agents.

    Immutable configuration that optionally assigns specialized agents to repair cycle
    sub-tasks. All fields are optional; None means fall back to the stage's default
    agent (specified in RepairCycleStageConfig).

    Sub-task names correspond to the operations performed by ProductionRepairCycleAdapter:
    - test_execution: Runs tests and parses results
    - code_fix: Fixes code-level test failures
    - systemic_analysis: Classifies failure root causes
    - systemic_fix: Applies cross-cutting fixes
    - env_rebuild: Rebuilds test environment
    - env_verification: Verifies rebuilt environment

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Attempting to modify any field raises FrozenInstanceError.

    **Backward Compatibility**: All fields default to None. When a RepairCycleAgentConfig
    is absent or a specific sub-task is None, the stage's agent_name is used as fallback.

    Attributes:
        test_execution: Optional agent name for test execution sub-task
        code_fix: Optional agent name for code fixing sub-task
        systemic_analysis: Optional agent name for systemic analysis sub-task
        systemic_fix: Optional agent name for systemic fix sub-task
        env_rebuild: Optional agent name for environment rebuild sub-task
        env_verification: Optional agent name for environment verification sub-task
    """

    # Known sub-task names (canonical source for validation)
    KNOWN_SUB_TASKS = frozenset(
        [
            "test_execution",
            "code_fix",
            "systemic_analysis",
            "systemic_fix",
            "env_rebuild",
            "env_verification",
        ]
    )

    test_execution: str | None = None
    code_fix: str | None = None
    systemic_analysis: str | None = None
    systemic_fix: str | None = None
    env_rebuild: str | None = None
    env_verification: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # No validations needed: all fields are optional strings or None
        # The resolve_agent method validates sub_task names at call time

    def resolve_agent(self, sub_task: str, default: str) -> str:
        """Return configured agent for sub_task, or default if not set.

        Implements the fallback chain for agent resolution:
        1. Validates sub_task name against KNOWN_SUB_TASKS
        2. If this config has a non-None value for the sub_task, return it
        3. Otherwise, return the default (typically from RepairCycleStageConfig.agent_name)

        Args:
            sub_task: Name of the repair cycle sub-task (must be one of KNOWN_SUB_TASKS)
            default: Fallback agent name if not configured for this sub-task

        Returns:
            The agent name to use for this sub-task

        Raises:
            ValueError: If sub_task is not a known sub-task name
        """
        if sub_task not in self.KNOWN_SUB_TASKS:
            msg = f"sub_task must be one of {sorted(self.KNOWN_SUB_TASKS)}, got '{sub_task}'"
            raise ValueError(msg)

        agent = getattr(self, sub_task, None)
        return agent if agent is not None else default


@dataclass(frozen=True)
class RepairCycleCheckpoint:
    """Checkpoint state for repair cycle recovery.

    Saved periodically during execution to allow resuming after crashes.
    All fields are immutable for audit integrity.

    Attributes:
        workflow_run_id: Unique identifier for this workflow run
        test_type: Current test type being executed (RepairTestType enum for type safety)
        iteration: Current iteration number (1-indexed)
        total_agent_calls: Number of agent calls so far
        files_fixed: Number of files fixed so far
        warnings_reviewed: Number of warnings reviewed so far
        elapsed_seconds: Time already spent on this cycle
        test_results: Completed test results for each test type
        timestamp: ISO 8601 timestamp of checkpoint creation
        expires_at: ISO 8601 timestamp when checkpoint should expire (24 hours)
    """

    workflow_run_id: str
    test_type: RepairTestType
    iteration: int
    total_agent_calls: int
    files_fixed: int
    warnings_reviewed: int
    elapsed_seconds: float
    test_results: tuple[CycleResult, ...]
    timestamp: str
    expires_at: str

    def __post_init__(self) -> None:
        """Validate checkpoint fields."""
        if not self.workflow_run_id or not self.workflow_run_id.strip():
            msg = "workflow_run_id cannot be empty"
            raise ValueError(msg)
        if not isinstance(self.test_type, RepairTestType):
            msg = "test_type must be a RepairTestType enum"
            raise ValueError(msg)
        if self.iteration < 1:
            msg = "iteration must be >= 1 (1-indexed)"
            raise ValueError(msg)
        if self.total_agent_calls < 0:
            msg = "total_agent_calls cannot be negative"
            raise ValueError(msg)
        if self.files_fixed < 0:
            msg = "files_fixed cannot be negative"
            raise ValueError(msg)
        if self.warnings_reviewed < 0:
            msg = "warnings_reviewed cannot be negative"
            raise ValueError(msg)
        if self.elapsed_seconds < 0:
            msg = "elapsed_seconds cannot be negative"
            raise ValueError(msg)
        if not isinstance(self.test_results, tuple):
            msg = "test_results must be a tuple (immutable)"
            raise ValueError(msg)


@dataclass(frozen=True)
class RepairCycleStageConfig:
    """Configuration for entire repair cycle stage.

    Immutable configuration for a complete repair cycle stage, defining:
    - Which test types to run (and in what order)
    - Overall constraints and circuit breakers
    - Checkpointing strategy for long-running cycles
    - Optional specialized agent assignments

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Collections stored as immutable Tuples instead of Lists.

    Attributes:
        name: Stage name (e.g., "fix_failures", "fix_warnings")
        test_configs: Immutable tuple of RepairTestRunConfig objects
                      Defines test types and settings in execution order
        agent_name: Name of agent to use (default "senior_software_engineer")
        max_total_agent_calls: Circuit breaker - abort cycle if exceeded
        checkpoint_interval: Save state every N iterations for resumability
        agent_config: Optional RepairCycleAgentConfig for agent specialization. None means
                      fall back to agent_name. Supports assigning specialized agents to
                      specific repair cycle sub-tasks.
    """

    name: str
    test_configs: tuple[RepairTestRunConfig, ...]  # Sequential test types
    agent_name: str = "senior_software_engineer"
    max_total_agent_calls: int = 100  # Circuit breaker
    checkpoint_interval: int = 5  # Save state every N iterations
    agent_config: RepairCycleAgentConfig | None = None  # Optional specialized agents

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.name:
            msg = "name is required"
            raise ValueError(msg)
        if not self.test_configs:
            msg = "test_configs must not be empty"
            raise ValueError(msg)
        if self.max_total_agent_calls <= 0:
            msg = "max_total_agent_calls must be > 0"
            raise ValueError(msg)
        if self.checkpoint_interval <= 0:
            msg = "checkpoint_interval must be > 0"
            raise ValueError(msg)


@dataclass(frozen=True)
class SystemicAnalysisResult:
    """Result of systemic analysis classifying the root cause of test failures.

    Immutable record of failure classification, enabling repair cycle orchestration
    to dispatch to the correct handling strategy (code fix, environment rebuild,
    dependency fix, or transient retry).

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Attempting to modify any field raises FrozenInstanceError.

    Attributes:
        classification: Root cause category (FailureClassification enum)
        confidence: Confidence in classification (0.0-1.0)
        reasoning: Explanation of classification decision
        affected_files: Immutable tuple of file names affected by the issue
        recommended_action: Recommended remediation step for this classification
        cross_cutting: Whether the failure indicates a cross-cutting root cause (default: False)
    """

    classification: FailureClassification
    confidence: float
    reasoning: str
    affected_files: tuple[str, ...]  # Immutable tuple
    recommended_action: str
    cross_cutting: bool = False

    def __post_init__(self) -> None:
        """Validate analysis result after initialization."""
        if not isinstance(self.classification, FailureClassification):
            msg = "classification must be a FailureClassification"
            raise ValueError(msg)
        if not 0.0 <= self.confidence <= 1.0:
            msg = "confidence must be between 0.0 and 1.0"
            raise ValueError(msg)
        if not self.reasoning:
            msg = "reasoning is required"
            raise ValueError(msg)
        if not self.recommended_action:
            msg = "recommended_action is required"
            raise ValueError(msg)


@dataclass(frozen=True)
class AnalysisContext:
    """Context for systemic failure analysis.

    Immutable record of context needed to classify failures, including prior
    attempts and classifications for escalation support.

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Collections stored as immutable Tuples instead of Lists.

    Attributes:
        work_item_id: Identifier of the work item being repaired
        iteration: Current iteration number in the repair cycle
        workflow_run_id: Identifier of the workflow run
        prior_fix_attempts: Immutable tuple of descriptions of prior fix attempts
        prior_classifications: Immutable tuple of prior classification results
                              (for escalation and re-classification)
    """

    work_item_id: str
    iteration: int
    workflow_run_id: str
    prior_fix_attempts: tuple[str, ...] = ()  # Immutable tuple
    prior_classifications: tuple[SystemicAnalysisResult, ...] = ()  # Immutable tuple

    def __post_init__(self) -> None:
        """Validate analysis context after initialization."""
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        if self.iteration < 0:
            msg = "iteration must be non-negative"
            raise ValueError(msg)


@dataclass(frozen=True)
class SystemicFixResult:
    """Result of a systemic fix operation addressing a cross-cutting root cause.

    Immutable record of a holistic fix attempt that addresses a failure pattern
    affecting multiple files with a shared root cause (e.g., API contract change,
    configuration update, dependency version bump).

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Attempting to modify any field raises FrozenInstanceError.

    Attributes:
        success: Whether the systemic fix successfully addressed the root cause
        files_modified: List of file paths modified by the systemic fix
        root_cause_addressed: Description of what root cause was addressed
        duration_seconds: Time taken to apply the systemic fix (non-negative)
    """

    success: bool
    files_modified: list[str]
    root_cause_addressed: str
    duration_seconds: float

    def __post_init__(self) -> None:
        """Validate systemic fix result after initialization."""
        if not isinstance(self.files_modified, list):
            object.__setattr__(self, "files_modified", list(self.files_modified))
        if self.duration_seconds < 0:
            msg = "duration_seconds must be non-negative"
            raise ValueError(msg)
