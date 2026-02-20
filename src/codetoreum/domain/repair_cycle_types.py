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
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


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
            raise ValueError("file is required")
        if not self.test:
            raise ValueError("test is required")
        if not self.message:
            raise ValueError("message is required")


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
            raise ValueError("file is required")
        if not self.message:
            raise ValueError("message is required")


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
    failures: Tuple[RepairTestFailure, ...]  # Immutable tuple
    warning_list: Tuple[RepairTestWarning, ...]  # Immutable tuple
    raw_output: str
    timestamp: str

    def __post_init__(self) -> None:
        """Validate result after initialization."""
        if self.iteration < 1:
            raise ValueError("iteration must be >= 1")
        if self.passed < 0:
            raise ValueError("passed must be >= 0")
        if self.failed < 0:
            raise ValueError("failed must be >= 0")
        if self.warnings < 0:
            raise ValueError("warnings must be >= 0")
        if not self.timestamp:
            raise ValueError("timestamp is required")

        # Consistency check: failed count must match failures list length
        if len(self.failures) != self.failed:
            raise ValueError(
                f"failed count mismatch: {len(self.failures)} failures in list "
                f"but failed={self.failed}"
            )

        # Consistency check: warnings count must match warning_list length
        if len(self.warning_list) != self.warnings:
            raise ValueError(
                f"warnings count mismatch: {len(self.warning_list)} warnings in list "
                f"but warnings={self.warnings}"
            )


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
    final_result: Optional[RepairTestResult]
    error: Optional[str]
    files_fixed: int
    warnings_reviewed: int
    duration_seconds: float

    def __post_init__(self) -> None:
        """Validate cycle result after initialization."""
        if self.iterations < 0:
            raise ValueError("iterations must be >= 0")
        if self.files_fixed < 0:
            raise ValueError("files_fixed must be >= 0")
        if self.warnings_reviewed < 0:
            raise ValueError("warnings_reviewed must be >= 0")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be >= 0")

        # Consistency check: passed state must align with final_result/error
        if self.passed and self.final_result is None:
            raise ValueError(
                "passed=True but final_result is None (expected successful test result)"
            )
        if self.passed and self.error is not None:
            raise ValueError(
                f"passed=True but error is set: '{self.error}' (contradiction)"
            )

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
    test_results: Tuple[CycleResult, ...]  # Immutable tuple
    overall_success: bool
    total_agent_calls: int
    duration_seconds: float
    timestamp: str

    def __post_init__(self) -> None:
        """Validate cycle result after initialization."""
        if not self.stage:
            raise ValueError("stage is required")
        if self.total_agent_calls < 0:
            raise ValueError("total_agent_calls must be >= 0")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be >= 0")
        if not self.timestamp:
            raise ValueError("timestamp is required")

        # Consistency check: overall_success must match all test results
        if self.test_results:
            all_passed = all(r.passed for r in self.test_results)
            if self.overall_success and not all_passed:
                failed_types = [r.test_type.value for r in self.test_results if not r.passed]
                raise ValueError(
                    f"overall_success=True but some test types failed: {failed_types}"
                )
            if not self.overall_success and all_passed:
                raise ValueError(
                    "overall_success=False but all test results passed (inconsistency)"
                )
        else:
            # Empty test_results with overall_success=True is suspicious but may be valid
            # (e.g., no tests configured). Log warning but don't raise.
            if self.overall_success:
                logger.warning(
                    "overall_success=True but test_results is empty",
                    extra={"stage": self.stage}
                )


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
            raise ValueError("timeout must be > 0")
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be > 0")
        if self.max_file_iterations <= 0:
            raise ValueError("max_file_iterations must be > 0")


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
    test_results: Tuple[CycleResult, ...]
    timestamp: str
    expires_at: str

    def __post_init__(self) -> None:
        """Validate checkpoint fields."""
        if not self.workflow_run_id or not self.workflow_run_id.strip():
            raise ValueError("workflow_run_id cannot be empty")
        if not isinstance(self.test_type, RepairTestType):
            raise ValueError("test_type must be a RepairTestType enum")
        if self.iteration < 1:
            raise ValueError("iteration must be >= 1 (1-indexed)")
        if self.total_agent_calls < 0:
            raise ValueError("total_agent_calls cannot be negative")
        if self.files_fixed < 0:
            raise ValueError("files_fixed cannot be negative")
        if self.warnings_reviewed < 0:
            raise ValueError("warnings_reviewed cannot be negative")
        if self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds cannot be negative")
        if not isinstance(self.test_results, tuple):
            raise ValueError("test_results must be a tuple (immutable)")


@dataclass(frozen=True)
class RepairCycleStageConfig:
    """Configuration for entire repair cycle stage.

    Immutable configuration for a complete repair cycle stage, defining:
    - Which test types to run (and in what order)
    - Overall constraints and circuit breakers
    - Checkpointing strategy for long-running cycles

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Collections stored as immutable Tuples instead of Lists.

    Attributes:
        name: Stage name (e.g., "fix_failures", "fix_warnings")
        test_configs: Immutable tuple of RepairTestRunConfig objects
                      Defines test types and settings in execution order
        agent_name: Name of agent to use (default "senior_software_engineer")
        max_total_agent_calls: Circuit breaker - abort cycle if exceeded
        checkpoint_interval: Save state every N iterations for resumability
    """

    name: str
    test_configs: Tuple[RepairTestRunConfig, ...]  # Sequential test types
    agent_name: str = "senior_software_engineer"
    max_total_agent_calls: int = 100  # Circuit breaker
    checkpoint_interval: int = 5  # Save state every N iterations

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.name:
            raise ValueError("name is required")
        if not self.test_configs:
            raise ValueError("test_configs must not be empty")
        if self.max_total_agent_calls <= 0:
            raise ValueError("max_total_agent_calls must be > 0")
        if self.checkpoint_interval <= 0:
            raise ValueError("checkpoint_interval must be > 0")
