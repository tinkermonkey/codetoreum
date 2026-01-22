"""Domain types for the repair cycle service.

This module defines all domain types used by the IRepairCycle service:
- Test configuration and results
- Failure and warning details
- Cycle completion results
- Overall repair cycle outcomes

All types are frozen (immutable) dataclasses for audit integrity and to prevent
accidental state mutations. Validations are performed in __post_init__ methods.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple
from datetime import datetime, timezone


# ============================================================================
# Enums
# ============================================================================


class RepairTestType(Enum):
    """Types of tests in the repair cycle sequence."""

    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"

    def __str__(self) -> str:
        """Return string representation."""
        return self.value


# ============================================================================
# Configuration Types
# ============================================================================


@dataclass(frozen=True)
class RepairTestRunConfig:
    """Configuration for running a specific test type in repair cycle.

    Attributes:
        test_type: Type of test to run (UNIT, INTEGRATION, or E2E)
        timeout: Timeout in seconds for test execution (default 900)
        max_iterations: Maximum iterations to repair failures before giving up
        review_warnings: Whether to review test warnings after passing
        max_file_iterations: Max iterations per file when fixing failures
    """

    test_type: RepairTestType
    timeout: int = 900
    max_iterations: int = 5
    review_warnings: bool = True
    max_file_iterations: int = 3

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not isinstance(self.test_type, RepairTestType):
            raise ValueError("test_type must be a RepairTestType enum value")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        if self.max_file_iterations <= 0:
            raise ValueError("max_file_iterations must be positive")


# ============================================================================
# Test Result Types
# ============================================================================


@dataclass(frozen=True)
class RepairTestFailure:
    """Single test failure in a test run.

    Attributes:
        file: Source file containing the failed test
        test: Test name or identifier
        message: Failure message or error output
    """

    file: str
    test: str
    message: str

    def __post_init__(self) -> None:
        """Validate failure fields."""
        if not self.file or not self.file.strip():
            raise ValueError("file cannot be empty")
        if not self.test or not self.test.strip():
            raise ValueError("test cannot be empty")
        if not self.message or not self.message.strip():
            raise ValueError("message cannot be empty")


@dataclass(frozen=True)
class RepairTestWarning:
    """Single warning from a test run.

    Attributes:
        file: Source file with the warning
        message: Warning message
    """

    file: str
    message: str

    def __post_init__(self) -> None:
        """Validate warning fields."""
        if not self.file or not self.file.strip():
            raise ValueError("file cannot be empty")
        if not self.message or not self.message.strip():
            raise ValueError("message cannot be empty")


@dataclass(frozen=True)
class RepairTestResult:
    """Results from running a specific test type once.

    Attributes:
        test_type: Type of test that was run
        iteration: Iteration number (1-indexed, never 0)
        passed: Number of passing tests
        failed: Number of failing tests
        warnings: Number of test warnings
        failures: Tuple of RepairTestFailure details (immutable)
        warning_list: Tuple of RepairTestWarning details (immutable)
        raw_output: Raw test output/logs
        timestamp: ISO 8601 timestamp of test execution
    """

    test_type: RepairTestType
    iteration: int
    passed: int
    failed: int
    warnings: int
    failures: Tuple[RepairTestFailure, ...]
    warning_list: Tuple[RepairTestWarning, ...]
    raw_output: str
    timestamp: str

    def __post_init__(self) -> None:
        """Validate result fields."""
        if self.iteration < 1:
            raise ValueError("iteration must be >= 1 (1-indexed)")
        if self.passed < 0:
            raise ValueError("passed count cannot be negative")
        if self.failed < 0:
            raise ValueError("failed count cannot be negative")
        if self.warnings < 0:
            raise ValueError("warnings count cannot be negative")
        if not isinstance(self.failures, tuple):
            raise ValueError("failures must be a tuple (immutable)")
        if not isinstance(self.warning_list, tuple):
            raise ValueError("warning_list must be a tuple (immutable)")


# ============================================================================
# Cycle Result Types
# ============================================================================


@dataclass(frozen=True)
class CycleResult:
    """Result of executing a single test type cycle (possibly multiple iterations).

    Attributes:
        test_type: Type of test that was executed
        passed: Whether all tests passed in this cycle
        iterations: Number of iterations executed
        final_result: The final RepairTestResult (may be None if error occurred)
        error: Error message if cycle failed (None if successful)
        files_fixed: Number of files fixed during this cycle
        warnings_reviewed: Number of warnings reviewed
        duration_seconds: Total time spent on this test type
    """

    test_type: RepairTestType
    passed: bool
    iterations: int
    final_result: Optional["RepairTestResult"]
    error: Optional[str]
    files_fixed: int
    warnings_reviewed: int
    duration_seconds: float

    def __post_init__(self) -> None:
        """Validate cycle result fields."""
        if self.iterations < 0:
            raise ValueError("iterations cannot be negative")
        if self.files_fixed < 0:
            raise ValueError("files_fixed cannot be negative")
        if self.warnings_reviewed < 0:
            raise ValueError("warnings_reviewed cannot be negative")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")


@dataclass(frozen=True)
class RepairCycleResult:
    """Final result of an entire repair cycle execution.

    Attributes:
        stage: Name of the workflow stage (e.g., "fix_failures")
        test_results: Tuple of CycleResult for each test type executed
        overall_success: Whether all tests passed
        total_agent_calls: Total number of agent executions
        duration_seconds: Total time for entire cycle
        timestamp: ISO 8601 timestamp of cycle completion
    """

    stage: str
    test_results: Tuple[CycleResult, ...]
    overall_success: bool
    total_agent_calls: int
    duration_seconds: float
    timestamp: str

    def __post_init__(self) -> None:
        """Validate cycle result fields."""
        if not self.stage or not self.stage.strip():
            raise ValueError("stage cannot be empty")
        if not isinstance(self.test_results, tuple):
            raise ValueError("test_results must be a tuple (immutable)")
        if self.total_agent_calls < 0:
            raise ValueError("total_agent_calls cannot be negative")
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")


# ============================================================================
# Context (mutable, passed by reference)
# ============================================================================


@dataclass
class RepairCycleContext:
    """Context for repair cycle execution (mutable, passed by reference).

    This is NOT frozen - it's a mutable context object passed between services.

    Attributes:
        stage_name: Name of the workflow stage
        pipeline_run_id: Unique identifier for this pipeline run
        test_configs: Tuple of RepairTestRunConfig for each test type
        agent_name: Name of the agent to execute
        max_total_agent_calls: Maximum total agent calls before circuit breaker
        checkpoint_interval: How often to checkpoint state
    """

    stage_name: str
    pipeline_run_id: str
    test_configs: Tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int
