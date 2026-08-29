"""CI pipeline service port interface with event emission.

This interface defines contracts for CI pipeline integration, including
querying CI status for pull requests and running CI checks.

CI pipelines are vendor-agnostic abstractions over GitHub Actions, GitLab CI,
Jenkins, CircleCI, and other CI/CD platforms. Implementations may query
external CI systems or execute checks locally.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from .event_emitter import IEventEmitter
from .monitoring import IMonitoredService


class CICheckStatus(Enum):
    """Status of an individual CI check."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class CICheckResult:
    """Result of a single CI check execution.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        name: Name of the CI check (e.g., "unit-tests", "linting")
        status: Status of the check (PENDING, RUNNING, PASSED, FAILED, SKIPPED)
        conclusion: Detailed conclusion of the check result (None if check is still pending)
        url: URL to the check details in the external CI system (None if not available)
    """

    name: str
    status: CICheckStatus
    conclusion: str | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.name, str) or not self.name:
            msg = "name must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.status, CICheckStatus):
            msg = f"status must be a CICheckStatus instance, got {type(self.status)}"
            raise ValueError(msg)

        if self.conclusion is not None:
            if not isinstance(self.conclusion, str):
                msg = "conclusion must be a string or None"
                raise ValueError(msg)

        if self.url is not None:
            if not isinstance(self.url, str):
                msg = "url must be a string or None"
                raise ValueError(msg)


@dataclass(frozen=True)
class CIPipelineStatus:
    """Status of a CI pipeline for a pull request.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Check results are converted
    to a tuple for true immutability. Cross-field consistency is enforced: the counts
    (passed, failed, pending) must match the actual check results.

    Attributes:
        pr_id: Pull request identifier
        status: Overall pipeline status (PENDING, RUNNING, PASSED, FAILED, SKIPPED)
        check_results: Individual check results
        total_checks: Total number of checks in the pipeline
        passed: Number of checks that passed
        failed: Number of checks that failed
        pending: Number of checks still pending/running
        pipeline_url: URL to the CI pipeline run (if available)
    """

    pr_id: str
    status: CICheckStatus
    check_results: tuple[CICheckResult, ...]
    total_checks: int
    passed: int
    failed: int
    pending: int
    pipeline_url: str = ""

    def __post_init__(self) -> None:
        """Validate all fields at construction time and cross-field consistency."""
        if not isinstance(self.pr_id, str) or not self.pr_id:
            msg = "pr_id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.status, CICheckStatus):
            msg = f"status must be a CICheckStatus instance, got {type(self.status)}"
            raise ValueError(msg)

        # Coerce list to tuple for deep immutability
        if isinstance(self.check_results, list):
            object.__setattr__(self, "check_results", tuple(self.check_results))

        if not isinstance(self.check_results, tuple):
            msg = "check_results must be a list or tuple of CICheckResult instances"
            raise ValueError(msg)

        if not all(isinstance(result, CICheckResult) for result in self.check_results):
            msg = "all check_results must be CICheckResult instances"
            raise ValueError(msg)

        if not isinstance(self.total_checks, int) or self.total_checks < 0:
            msg = "total_checks must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.passed, int) or self.passed < 0:
            msg = "passed must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.failed, int) or self.failed < 0:
            msg = "failed must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.pending, int) or self.pending < 0:
            msg = "pending must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.pipeline_url, str):
            msg = "pipeline_url must be a string"
            raise ValueError(msg)

        # Cross-field consistency: validate that total_checks equals sum of status counts
        # Note: skipped checks don't contribute to passed/failed/pending, but are still in check_results
        skipped_results = sum(1 for r in self.check_results if r.status == CICheckStatus.SKIPPED)
        sum_of_counts = self.passed + self.failed + self.pending + skipped_results
        if self.total_checks != sum_of_counts:
            msg = f"total_checks ({self.total_checks}) must equal sum of status counts (passed={self.passed} + failed={self.failed} + pending={self.pending} + skipped={skipped_results} = {sum_of_counts})"
            raise ValueError(msg)

        # Validate that counts match the actual check_results from external system
        passed_results = sum(1 for r in self.check_results if r.status == CICheckStatus.PASSED)
        failed_results = sum(1 for r in self.check_results if r.status == CICheckStatus.FAILED)
        pending_results = sum(
            1 for r in self.check_results if r.status in (CICheckStatus.PENDING, CICheckStatus.RUNNING)
        )

        if self.passed != passed_results:
            msg = f"passed count ({self.passed}) does not match check_results ({passed_results} checks are PASSED)"
            raise ValueError(msg)

        if self.failed != failed_results:
            msg = f"failed count ({self.failed}) does not match check_results ({failed_results} checks are FAILED)"
            raise ValueError(msg)

        if self.pending != pending_results:
            msg = f"pending count ({self.pending}) does not match check_results ({pending_results} checks are PENDING/RUNNING)"
            raise ValueError(msg)


@dataclass(frozen=True)
class CIRunResult:
    """Result of CI check execution via the CI system.

    Represents the outcome of querying CI checks from an external CI system
    (GitHub Actions, GitLab CI, etc.) or executing checks in a local environment.
    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Check results are
    converted to a tuple for true immutability. Cross-field consistency is enforced:
    the passed boolean must match the actual check results.

    Attributes:
        passed: Boolean indicating whether all CI checks passed (True) or any failed (False)
        failed: Number of checks that failed
        check_results: Tuple of detailed results for each CI check
        failures: Tuple of failure descriptions from failed checks
        warnings: Tuple of non-fatal warnings from CI execution
        output: Full output/logs from CI execution or external CI system
    """

    passed: bool
    failed: int
    check_results: tuple[CICheckResult, ...]
    failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    output: str = ""

    def __post_init__(self) -> None:
        """Validate all fields at construction time and cross-field consistency."""
        if not isinstance(self.passed, bool):
            msg = "passed must be a boolean"
            raise ValueError(msg)

        if not isinstance(self.failed, int) or self.failed < 0:
            msg = "failed must be a non-negative integer"
            raise ValueError(msg)

        # Coerce list to tuple for deep immutability
        if isinstance(self.check_results, list):
            object.__setattr__(self, "check_results", tuple(self.check_results))

        if not isinstance(self.check_results, tuple):
            msg = "check_results must be a list or tuple of CICheckResult instances"
            raise ValueError(msg)

        if not all(isinstance(result, CICheckResult) for result in self.check_results):
            msg = "all check_results must be CICheckResult instances"
            raise ValueError(msg)

        # Coerce list to tuple for deep immutability
        if isinstance(self.failures, list):
            object.__setattr__(self, "failures", tuple(self.failures))

        if not isinstance(self.failures, tuple):
            msg = "failures must be a list or tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(f, str) for f in self.failures):
            msg = "all failures must be strings"
            raise ValueError(msg)

        # Coerce list to tuple for deep immutability
        if isinstance(self.warnings, list):
            object.__setattr__(self, "warnings", tuple(self.warnings))

        if not isinstance(self.warnings, tuple):
            msg = "warnings must be a list or tuple of strings"
            raise ValueError(msg)

        if not all(isinstance(w, str) for w in self.warnings):
            msg = "all warnings must be strings"
            raise ValueError(msg)

        if not isinstance(self.output, str):
            msg = "output must be a string"
            raise ValueError(msg)

        # Cross-field consistency: validate that passed boolean matches check_results
        failed_results = sum(1 for r in self.check_results if r.status == CICheckStatus.FAILED)

        if self.failed != failed_results:
            msg = f"failed count ({self.failed}) does not match check_results ({failed_results} checks are FAILED)"
            raise ValueError(msg)

        # Validate that passed boolean is consistent with failed count and pending/running checks
        pending_or_running = sum(
            1 for r in self.check_results if r.status in (CICheckStatus.PENDING, CICheckStatus.RUNNING)
        )

        if self.passed and self.failed != 0:
            msg = f"passed is True but failed count is {self.failed} (should be 0)"
            raise ValueError(msg)

        if self.passed and pending_or_running > 0:
            msg = f"passed is True but {pending_or_running} checks are still pending/running"
            raise ValueError(msg)

        # Allow passed=False with failed=0 only if there are pending/running checks
        if not self.passed and self.failed == 0 and pending_or_running == 0:
            msg = "passed is False but failed count is 0 and no checks are pending/running (should have failed checks or pending checks)"
            raise ValueError(msg)


class ICIPipelineService(IEventEmitter, IMonitoredService, ABC):
    """CI pipeline management with event emission and monitoring.

    Provides vendor-agnostic abstraction for CI systems (GitHub Actions, GitLab CI,
    Jenkins, CircleCI, etc.). Enables:
    1. Querying CI status for pull requests from external CI systems
    2. Executing CI checks via external systems or local containers
    3. Monitoring CI pipeline completion and status changes

    Implementations may vary: some adapters query external CI systems (e.g.,
    GitHub Actions), while others may execute checks locally. Consult the adapter
    documentation for specific behavior.

    Events emitted:
        - 'ci.pipeline_status_checked' → CIPipelineStatusCheckedEvent
                                        When PR CI status is queried
        - 'ci.run_started' → CIRunStartedEvent
                            When CI execution starts
        - 'ci.run_completed' → CIRunCompletedEvent
                              When CI execution completes

    Example:
        # Get PR CI status from external system
        status = await service.get_pr_ci_status("pr-456", "proj-123", 300)
        if status.status == CICheckStatus.PASSED:
            print(f"PR {status.pr_id} passed all checks ({status.passed}/{status.total_checks})")

        # Execute or query CI checks
        result = await service.run_ci_checks("proj-123", "/workspace", 600)
        if result.passed:
            print("All checks passed!")
        else:
            for check in result.check_results:
                if check.status == CICheckStatus.FAILED:
                    print(f"  - {check.name}: {check.conclusion}")
    """

    @abstractmethod
    async def get_pr_ci_status(self, pr_id: str, project_id: str, timeout_seconds: int = 300) -> CIPipelineStatus:
        """Query CI status for a pull request from external CI system.

        Retrieves the current status of CI checks for a PR from the external
        CI platform (GitHub Actions, GitLab CI, etc.). The results reflect
        the state of the PR's CI pipeline in the external system.

        Args:
            pr_id: Pull request identifier (e.g., "123")
            project_id: Project containing the PR
            timeout_seconds: How long to wait for CI status (default 300s / 5min)

        Returns:
            CIPipelineStatus: Current status of the PR's CI pipeline

        Raises:
            ResourceNotFoundError: PR doesn't exist
            ExternalServiceError: Service communication failure
            TimeoutError: CI status not available within timeout

        Events:
            Emits 'ci.pipeline_status_checked' event with query result
        """

    @abstractmethod
    async def run_ci_checks(self, project_id: str, working_directory: str, timeout_seconds: int = 600) -> CIRunResult:
        """Query or execute CI checks and return results.

        Runs CI checks by either executing them locally within the provided working
        directory (typically in a container with the project code mounted), or by
        querying an external CI system for CI status. The specific strategy depends
        on the adapter implementation. This allows validation of changes before
        pushing to the remote repository.

        Args:
            project_id: Project being checked
            working_directory: Working directory for the project. Adapters may use this as the execution root for local checks, or to resolve branch/PR context for remote CI queries.
            timeout_seconds: How long to allow check execution (default 600s / 10min)

        Returns:
            CIRunResult: Summary of check results with failures and warnings

        Raises:
            ResourceNotFoundError: Project doesn't exist
            ValidationError: Invalid working directory or check configuration
            ExternalServiceError: Service communication failure
            TimeoutError: CI checks didn't complete within timeout

        Events:
            Emits 'ci.run_started' event when execution begins
            Emits 'ci.run_completed' event when execution finishes
        """
