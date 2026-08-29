"""Mock CI pipeline adapter for testing and simulation.

This module provides a complete in-memory implementation of ICIPipelineService
for use in simulation tests and integration tests. The adapter provides a
configuration API for pre-setting outcomes and assertion helpers for verifying
CI interactions.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from codetoreum.domain.events.ci_pipeline_events import (
    CIPipelineStatusCheckedEvent,
    CIRunCompletedEvent,
    CIRunStartedEvent,
)
from codetoreum.ports.output.ci_pipeline_service import (
    CICheckResult,
    CICheckStatus,
    CIPipelineStatus,
    CIRunResult,
    ICIPipelineService,
)
from codetoreum.ports.output.event_emitter import IEventEmitter, NullEventEmitter
from codetoreum.ports.output.monitoring import (
    MonitoringConfig,
    MonitoringState,
    MonitoringStatus,
)

if TYPE_CHECKING:
    from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock

logger = logging.getLogger(__name__)


class MockCIPipelineAdapter(ICIPipelineService):
    """Mock CI pipeline service for testing.

    Provides a complete in-memory implementation of ICIPipelineService that:
    1. Stores configured CI outcomes for PRs and projects
    2. Returns pre-configured status and results without external calls
    3. Tracks CI status checks and run executions for assertion verification
    4. Emits domain events on CI operations
    5. Maintains monitoring state for lifecycle management
    6. Integrates with SimulationClock for deterministic time in tests

    Intended for testing and simulation without external CI systems
    (GitHub Actions, GitLab CI, Jenkins, etc.).

    Example:
        # Setup
        adapter = MockCIPipelineAdapter()
        adapter.set_pr_ci_failing("pr-123", failure_count=2)

        # Get configured status
        status = await adapter.get_pr_ci_status("pr-123", "proj-1")
        assert status.status == CICheckStatus.FAILED
        assert sum(1 for r in status.check_results if r.status == CICheckStatus.FAILED) == 2

        # Verify interaction
        adapter.assert_pr_ci_checked("pr-123")

        # Run local CI checks
        await adapter.run_ci_checks("proj-1", "/workspace")

        # Verify run was executed
        adapter.assert_ci_run_executed("proj-1")
    """

    def __init__(self, event_emitter: IEventEmitter | None = None, clock: "SimulationClock | None" = None) -> None:
        """Initialize the mock CI pipeline adapter.

        Args:
            event_emitter: Optional IEventEmitter for emitting domain events
            clock: Optional SimulationClock for deterministic time in tests
                   If provided, timestamps use simulation clock; otherwise uses wall clock
        """
        self._event_emitter = event_emitter or NullEventEmitter()
        self._clock = clock

        # Configuration storage for PR CI status
        # pr_id -> {"status": CICheckStatus, "failed_count": int, "pending_count": int}
        self._pr_ci_config: dict[str, dict] = {}

        # Configuration storage for project CI runs
        # project_id -> {"passed": bool, "failures": list[str]}
        self._project_ci_config: dict[str, dict] = {}

        # Call history for assertions - tracks full call history per key
        # pr_id -> list of CIPipelineStatus results (allows call count and return value assertions)
        self._pr_ci_checks: dict[str, list[CIPipelineStatus]] = {}
        # project_id -> list of CIRunResult results (allows call count and return value assertions)
        self._ci_run_calls: dict[str, list[CIRunResult]] = {}

        # Monitoring state
        self._monitoring: dict[str, MonitoringStatus] = {}  # project_id -> status

        # Thread safety
        self._lock = asyncio.Lock()

        # Local event listeners (for IEventEmitter interface)
        self._event_listeners: dict[str, list] = {}  # Event type -> list of handlers

    # ===== IEventEmitter Implementation =====

    def on(self, event_type: str, handler) -> None:
        """Register event listener.

        Args:
            event_type: Type of event to subscribe to
            handler: Callback function that accepts a CodetoreumEvent parameter
        """
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(handler)

    def off(self, event_type: str, handler) -> None:
        """Unregister event listener.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove
        """
        if event_type in self._event_listeners:
            self._event_listeners[event_type] = [h for h in self._event_listeners[event_type] if h != handler]

    def emit(self, event) -> None:
        """Emit event to all registered listeners and event emitter.

        Emits to both:
        1. Local event listeners (for backwards compatibility)
        2. Event emitter (for domain event publishing to event bus)

        Args:
            event: CodetoreumEvent instance to emit
        """
        event_type = getattr(event, "type", event.__class__.__name__)

        # Emit to local listeners - let exceptions propagate for test visibility
        if event_type in self._event_listeners:
            for handler in self._event_listeners[event_type]:
                handler(event)

        # Emit to event emitter if provided (for event bus subscription)
        if self._event_emitter:
            self._event_emitter.emit(event)

    # ===== Configuration API =====

    def set_pr_ci_passing(self, pr_id: str) -> None:
        """Configure a PR to have passing CI status.

        Args:
            pr_id: Pull request ID

        Example:
            adapter.set_pr_ci_passing("pr-123")
        """
        self._pr_ci_config[pr_id] = {
            "status": CICheckStatus.PASSED,
            "failed_count": 0,
            "pending_count": 0,
        }

    def set_pr_ci_failing(self, pr_id: str, failure_count: int) -> None:
        """Configure a PR to have failing CI status.

        Args:
            pr_id: Pull request ID
            failure_count: Number of checks that failed

        Example:
            adapter.set_pr_ci_failing("pr-123", failure_count=2)
        """
        self._pr_ci_config[pr_id] = {
            "status": CICheckStatus.FAILED,
            "failed_count": failure_count,
            "pending_count": 0,
        }

    def set_pr_ci_pending(self, pr_id: str, pending_count: int) -> None:
        """Configure a PR to have pending CI status.

        Args:
            pr_id: Pull request ID
            pending_count: Number of checks that are pending

        Example:
            adapter.set_pr_ci_pending("pr-123", pending_count=3)
        """
        self._pr_ci_config[pr_id] = {
            "status": CICheckStatus.PENDING,
            "failed_count": 0,
            "pending_count": pending_count,
        }

    def set_ci_run_passing(self, project_id: str) -> None:
        """Configure a project to have passing CI run results.

        Args:
            project_id: Project ID

        Example:
            adapter.set_ci_run_passing("proj-1")
        """
        self._project_ci_config[project_id] = {
            "passed": True,
            "failures": [],
        }

    def set_ci_run_failing(self, project_id: str, failures: list[str]) -> None:
        """Configure a project to have failing CI run results.

        Args:
            project_id: Project ID
            failures: List of failure descriptions

        Example:
            adapter.set_ci_run_failing("proj-1", ["lint: line too long", "tests: timeout"])
        """
        self._project_ci_config[project_id] = {
            "passed": False,
            "failures": failures,
        }

    # ===== Assertion Helpers =====

    def assert_pr_ci_checked(self, pr_id: str) -> None:
        """Assert that PR CI status was checked at least once.

        Args:
            pr_id: Pull request ID

        Raises:
            AssertionError: If PR CI status was never checked

        Example:
            await adapter.get_pr_ci_status("pr-123", "proj-1")
            adapter.assert_pr_ci_checked("pr-123")
        """
        if pr_id not in self._pr_ci_checks:
            msg = f"Expected PR {pr_id} CI status to have been checked, but it was never checked"
            raise AssertionError(msg)

    def assert_ci_run_executed(self, project_id: str) -> None:
        """Assert that CI run was executed at least once for project.

        Args:
            project_id: Project ID

        Raises:
            AssertionError: If CI run was never executed for project

        Example:
            await adapter.run_ci_checks("proj-1", "/workspace")
            adapter.assert_ci_run_executed("proj-1")
        """
        if project_id not in self._ci_run_calls:
            msg = f"Expected CI run to have been executed for project {project_id}, but it was never executed"
            raise AssertionError(msg)

    def assert_no_failures(self, pr_id: str) -> None:
        """Assert that PR has no CI failures.

        Args:
            pr_id: Pull request ID

        Raises:
            AssertionError: If PR is configured with failures

        Example:
            adapter.set_pr_ci_passing("pr-123")
            adapter.assert_no_failures("pr-123")
        """
        config = self._pr_ci_config.get(pr_id)
        if config and config["status"] == CICheckStatus.FAILED:
            msg = f"Expected PR {pr_id} to have no failures, " f"but {config['failed_count']} checks are failing"
            raise AssertionError(msg)

    def assert_pr_ci_checked_count(self, pr_id: str, expected_count: int) -> None:
        """Assert that PR CI status was checked a specific number of times.

        Args:
            pr_id: Pull request ID
            expected_count: Expected number of checks

        Raises:
            AssertionError: If actual count doesn't match expected

        Example:
            await adapter.get_pr_ci_status("pr-123", "proj-1")
            await adapter.get_pr_ci_status("pr-123", "proj-1")  # Check again
            adapter.assert_pr_ci_checked_count("pr-123", 2)
        """
        actual_count = len(self._pr_ci_checks.get(pr_id, []))
        if actual_count != expected_count:
            msg = f"Expected PR {pr_id} CI status to have been checked {expected_count} times, but was checked {actual_count} times"
            raise AssertionError(msg)

    def assert_ci_run_executed_count(self, project_id: str, expected_count: int) -> None:
        """Assert that CI run was executed a specific number of times for project.

        Args:
            project_id: Project ID
            expected_count: Expected number of executions

        Raises:
            AssertionError: If actual count doesn't match expected

        Example:
            await adapter.run_ci_checks("proj-1", "/workspace")
            await adapter.run_ci_checks("proj-1", "/workspace")  # Run again
            adapter.assert_ci_run_executed_count("proj-1", 2)
        """
        actual_count = len(self._ci_run_calls.get(project_id, []))
        if actual_count != expected_count:
            msg = f"Expected CI run to have been executed {expected_count} times for project {project_id}, but was executed {actual_count} times"
            raise AssertionError(msg)

    def get_pr_ci_status_history(self, pr_id: str) -> list[CIPipelineStatus]:
        """Get full history of CIPipelineStatus results for a PR.

        Returns all return values from calls to get_pr_ci_status() for this PR,
        allowing verification of return values, call sequences, and status changes.

        Args:
            pr_id: Pull request ID

        Returns:
            List of CIPipelineStatus objects in call order (empty if never checked)

        Example:
            await adapter.get_pr_ci_status("pr-123", "proj-1")
            await adapter.get_pr_ci_status("pr-123", "proj-1")
            history = adapter.get_pr_ci_status_history("pr-123")
            assert len(history) == 2
            assert history[0].status == CICheckStatus.PASSED
            assert history[1].status == CICheckStatus.FAILED
        """
        return self._pr_ci_checks.get(pr_id, []).copy()

    def get_ci_run_result_history(self, project_id: str) -> list[CIRunResult]:
        """Get full history of CIRunResult results for a project.

        Returns all return values from calls to run_ci_checks() for this project,
        allowing verification of return values, call sequences, and result changes.

        Args:
            project_id: Project ID

        Returns:
            List of CIRunResult objects in call order (empty if never executed)

        Example:
            await adapter.run_ci_checks("proj-1", "/workspace")
            await adapter.run_ci_checks("proj-1", "/workspace")
            history = adapter.get_ci_run_result_history("proj-1")
            assert len(history) == 2
            assert history[0].failed == 0
            assert history[1].failed == 1
        """
        return self._ci_run_calls.get(project_id, []).copy()

    # ===== Service Operations =====

    async def get_pr_ci_status(self, pr_id: str, project_id: str, timeout_seconds: int = 300) -> CIPipelineStatus:
        """Query CI status for a pull request.

        Returns pre-configured status if set, otherwise defaults to passing status.
        Emits CIPipelineStatusCheckedEvent.

        Args:
            pr_id: Pull request identifier
            project_id: Project containing the PR
            timeout_seconds: Timeout (for interface compatibility, not used)

        Returns:
            CIPipelineStatus: Current status of the PR's CI pipeline

        Events:
            Emits 'ci.pipeline_status_checked' event with query result
        """
        # Get configured status or default to passing
        config = self._pr_ci_config.get(
            pr_id,
            {
                "status": CICheckStatus.PASSED,
                "failed_count": 0,
                "pending_count": 0,
            },
        )

        status = config["status"]
        failed_count = config.get("failed_count", 0)
        pending_count = config.get("pending_count", 0)

        # Create check results based on counts
        check_results = []

        # Add failed checks
        for i in range(failed_count):
            check_results.append(
                CICheckResult(
                    name=f"check-{i}",
                    status=CICheckStatus.FAILED,
                    conclusion="failure",
                    url=f"https://ci.example.com/pr/{pr_id}/check/{i}",
                )
            )

        # Add pending checks
        for i in range(pending_count):
            check_results.append(
                CICheckResult(
                    name=f"check-pending-{i}",
                    status=CICheckStatus.PENDING,
                    conclusion=None,
                    url=f"https://ci.example.com/pr/{pr_id}/check-pending/{i}",
                )
            )

        # Add passing check if there are no failures or pending
        if not check_results:
            check_results.append(
                CICheckResult(
                    name="check-0",
                    status=CICheckStatus.PASSED,
                    conclusion="success",
                    url=f"https://ci.example.com/pr/{pr_id}/check/0",
                )
            )

        # Determine counts for aggregation
        passed_count = len([r for r in check_results if r.status == CICheckStatus.PASSED])
        total_checks = len(check_results)

        # Create the CI pipeline status
        ci_status = CIPipelineStatus(
            pr_id=pr_id,
            status=status,
            check_results=tuple(check_results),
            total_checks=total_checks,
            passed=passed_count,
            failed=failed_count,
            pending=pending_count,
            pipeline_url=f"https://ci.example.com/pr/{pr_id}",
        )

        # Track call history under lock
        async with self._lock:
            if pr_id not in self._pr_ci_checks:
                self._pr_ci_checks[pr_id] = []
            self._pr_ci_checks[pr_id].append(ci_status)

        # Emit event outside lock
        event = CIPipelineStatusCheckedEvent(
            type="ci.pipeline_status_checked",
            pr_id=pr_id,
            project_id=project_id,
            status=status.value,
            check_count=len(check_results),
            passed_count=len([r for r in check_results if r.status == CICheckStatus.PASSED]),
            failed_count=failed_count,
            pending_count=len([r for r in check_results if r.status in (CICheckStatus.PENDING, CICheckStatus.RUNNING)]),
            timestamp=self._get_iso_timestamp(),
            source="mock",
        )
        self.emit(event)

        return ci_status

    async def run_ci_checks(self, project_id: str, working_directory: str, timeout_seconds: int = 600) -> CIRunResult:
        """Execute CI checks locally in a working directory.

        Returns pre-configured results if set, otherwise defaults to passing result.
        Emits CIRunStartedEvent and CIRunCompletedEvent.

        Args:
            project_id: Project being checked
            working_directory: Directory containing project code to check
            timeout_seconds: Timeout (for interface compatibility, not used)

        Returns:
            CIRunResult: Summary of check results with failures and warnings

        Events:
            Emits 'ci.run_started' event when execution begins
            Emits 'ci.run_completed' event when execution finishes
        """
        workflow_run_id = str(uuid4())

        # Emit run started event
        started_event = CIRunStartedEvent(
            type="ci.run_started",
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
            checks_planned=0,  # Mock doesn't know checks planned ahead of time
            timestamp=self._get_iso_timestamp(),
            source="mock",
        )
        self.emit(started_event)

        # Get configured results or default to passing
        config = self._project_ci_config.get(
            project_id,
            {
                "passed": True,
                "failures": [],
            },
        )

        failures = config.get("failures", [])
        all_passed = config.get("passed", True)

        # Create check results
        check_results = []
        if all_passed:
            # Create a single passing check
            check_results.append(
                CICheckResult(
                    name="all-tests",
                    status=CICheckStatus.PASSED,
                    conclusion="success",
                    url="https://ci.example.com/run/all-tests",
                )
            )
            output = "All checks passed"
        else:
            # Create check results for each failure
            for i, failure in enumerate(failures):
                check_results.append(
                    CICheckResult(
                        name=f"check-{i}",
                        status=CICheckStatus.FAILED,
                        conclusion="failure",
                        url=f"https://ci.example.com/run/check-{i}",
                    )
                )
            output = "Failed checks:\n" + "\n".join(failures)

        # Count results for creation
        passed_count = sum(1 for r in check_results if r.status == CICheckStatus.PASSED)
        failed_count = sum(1 for r in check_results if r.status == CICheckStatus.FAILED)

        # Create result with new schema
        result = CIRunResult(
            passed=(failed_count == 0),
            failed=failed_count,
            check_results=tuple(check_results),
            failures=tuple(failures),
            output=output,
        )

        # Track call history under lock
        async with self._lock:
            if project_id not in self._ci_run_calls:
                self._ci_run_calls[project_id] = []
            self._ci_run_calls[project_id].append(result)

        # Emit run completed event
        check_count = len(check_results)
        pending_count = sum(1 for r in check_results if r.status in (CICheckStatus.PENDING, CICheckStatus.RUNNING))

        completed_event = CIRunCompletedEvent(
            type="ci.run_completed",
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            check_count=check_count,
            passed_count=passed_count,
            failure_count=failed_count,
            pending_count=pending_count,
            warning_count=len(result.warnings),
            output=result.output,
            timestamp=self._get_iso_timestamp(),
            source="mock",
        )
        self.emit(completed_event)

        return result

    # ===== Monitoring Lifecycle (IMonitoredService) =====

    async def start_monitoring(self, project_id: str, config: MonitoringConfig) -> None:
        """Begin monitoring for changes.

        Args:
            project_id: Project to monitor
            config: Monitoring configuration
        """
        async with self._lock:
            self._monitoring[project_id] = MonitoringStatus(
                state=MonitoringState.ACTIVE,
                project_id=project_id,
                started_at=self._get_iso_timestamp(),
            )

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring for changes.

        Args:
            project_id: Project to stop monitoring
        """
        async with self._lock:
            if project_id in self._monitoring:
                status = self._monitoring[project_id]
                stopped_status = MonitoringStatus(
                    state=MonitoringState.STOPPED,
                    project_id=status.project_id,
                    started_at=status.started_at,
                    error_message=status.error_message,
                )
                self._monitoring[project_id] = stopped_status

    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Query current monitoring state.

        Args:
            project_id: Project to query status for

        Returns:
            MonitoringStatus with current state
        """
        async with self._lock:
            return self._monitoring.get(
                project_id,
                MonitoringStatus(state=MonitoringState.STOPPED, project_id=project_id),
            )

    # ===== Helper Methods =====

    def _get_iso_timestamp(self) -> str:
        """Get current time as ISO 8601 timestamp."""
        if self._clock:
            return self._clock.now().isoformat()
        return datetime.now(UTC).isoformat()

    # ===== Test Helper Methods =====

    def clear(self) -> None:
        """Clear all configuration and call history for cleanup.

        Useful between test cases to reset state.

        Example:
            adapter.clear()
        """
        self._pr_ci_config.clear()
        self._project_ci_config.clear()
        self._pr_ci_checks.clear()
        self._ci_run_calls.clear()
        self._monitoring.clear()

    def get_pr_ci_calls(self) -> list[str]:
        """Get list of PR IDs that had CI status checked.

        Returns:
            List of PR IDs (order not guaranteed)

        Example:
            await adapter.get_pr_ci_status("pr-1", "proj-1")
            await adapter.get_pr_ci_status("pr-2", "proj-1")
            calls = adapter.get_pr_ci_calls()
            assert "pr-1" in calls
            assert "pr-2" in calls
        """
        return list(self._pr_ci_checks.keys())

    def get_ci_run_calls(self) -> list[str]:
        """Get list of project IDs that had CI runs executed.

        Returns:
            List of project IDs (order not guaranteed)

        Example:
            await adapter.run_ci_checks("proj-1", "/workspace")
            await adapter.run_ci_checks("proj-2", "/workspace")
            calls = adapter.get_ci_run_calls()
            assert "proj-1" in calls
            assert "proj-2" in calls
        """
        return list(self._ci_run_calls.keys())
