"""GitHub CI pipeline adapter for querying pull request CI status.

Implements ICIPipelineService interface for GitHub, supporting:
- PR CI status queries via GitHub GraphQL API
- Check run aggregation into pipeline status
- Event emission for CI operations
- Monitoring state lifecycle management
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from codetoreum.adapters.secondary.github_ticket_adapter import GitHubTicketAdapter
from codetoreum.domain.events.ci_pipeline_events import CIPipelineStatusCheckedEvent
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.http.github_graphql_client import (
    GitHubGraphQLClient,
)
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.ci_pipeline_service import (
    CICheckResult,
    CICheckStatus,
    CIPipelineStatus,
    CIRunResult,
    ICIPipelineService,
)
from codetoreum.ports.output.monitoring import (
    MonitoringConfig,
    MonitoringState,
    MonitoringStatus,
)

logger = logging.getLogger(__name__)


class GitHubCIPipelineAdapter(ICIPipelineService):
    """GitHub CI pipeline adapter for PR status queries.

    Provides CI status queries for GitHub pull requests using the GitHub GraphQL API.
    Aggregates check runs into a unified CIPipelineStatus for vendor-agnostic
    CI status representation.

    Example:
        adapter = GitHubCIPipelineAdapter(
            ticket_adapter=gh_ticket,
            graphql_client=gh_graphql
        )

        # Start monitoring
        await adapter.start_monitoring("proj-123", MonitoringConfig(...))

        # Get PR CI status from GitHub
        status = await adapter.get_pr_ci_status("123", "proj-123")
        if status.status == CICheckStatus.PASSED:
            print(f"PR {status.pr_id} all checks passed")

        # Stop monitoring
        await adapter.stop_monitoring("proj-123")
    """

    def __init__(
        self,
        ticket_adapter: GitHubTicketAdapter,
        graphql_client: GitHubGraphQLClient,
    ):
        """Initialize GitHub CI pipeline adapter.

        Args:
            ticket_adapter: GitHub ticket adapter for PR metadata and linking
            graphql_client: GitHub GraphQL client for check run queries
        """
        self._ticket_adapter = ticket_adapter
        self._graphql = graphql_client

        # Monitoring state per project
        self._monitoring: dict[str, MonitoringStatus] = {}

        # Event handlers by event type
        self._event_handlers: dict[str, list[Callable]] = {}

    # ===== IEventEmitter Implementation =====

    def on(self, event_type: str, handler: Callable) -> None:
        """Register event handler.

        Args:
            event_type: Type of event to listen for
            handler: Callable to invoke when event is emitted
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Callable) -> None:
        """Unregister event handler.

        Args:
            event_type: Type of event
            handler: Callable to remove
        """
        if event_type in self._event_handlers and handler in self._event_handlers[event_type]:
            self._event_handlers[event_type].remove(handler)

    def emit(self, event: Any) -> None:
        """Emit event to all registered handlers.

        Args:
            event: Event to emit
        """
        event_type = getattr(event, "type", None)
        if event_type not in self._event_handlers:
            return

        for handler in self._event_handlers[event_type]:
            try:
                handler(event)
            except Exception as e:
                logger.error(
                    f"Event handler failed for {event_type}: {e}",
                    exc_info=True,
                    extra={
                        "error_id": ErrorRegistry.ERR_HANDLER_EXECUTION,
                        "event_type": event_type,
                        "event_id": getattr(event, "event_id", None),
                        "handler": getattr(handler, "__name__", str(handler)),
                    },
                )

    # ===== IMonitoredService Implementation =====

    async def start_monitoring(self, project_id: str, config: MonitoringConfig) -> None:
        """Start monitoring CI status for a project.

        Args:
            project_id: Project to monitor
            config: Monitoring configuration
        """
        self._monitoring[project_id] = MonitoringStatus(
            state=MonitoringState.ACTIVE,
            project_id=project_id,
            started_at=datetime.now(UTC).isoformat(),
        )

        logger.info(f"Started monitoring CI status for project {project_id}")

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring CI status for a project.

        Args:
            project_id: Project to stop monitoring
        """
        if project_id in self._monitoring:
            old_status = self._monitoring[project_id]
            self._monitoring[project_id] = MonitoringStatus(
                state=MonitoringState.STOPPED,
                project_id=project_id,
                started_at=old_status.started_at,
                error_message=old_status.error_message,
            )

        logger.info(f"Stopped monitoring CI status for project {project_id}")

    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Get current monitoring status for a project.

        Args:
            project_id: Project to query

        Returns:
            Current monitoring status
        """
        if project_id in self._monitoring:
            return self._monitoring[project_id]

        return MonitoringStatus(
            state=MonitoringState.STOPPED,
            project_id=project_id,
        )

    # ===== Service Operations =====

    async def get_pr_ci_status(self, pr_id: str, project_id: str, timeout_seconds: int = 300) -> CIPipelineStatus:
        """Query CI status for a pull request from GitHub.

        Fetches the PR's check runs from GitHub and aggregates them into
        a unified CIPipelineStatus. Returns the overall status (pending,
        running, passed, failed, skipped) along with individual check results.

        Args:
            pr_id: Pull request number (e.g., "123")
            project_id: Project containing the PR
            timeout_seconds: How long to wait for CI status (default 300s / 5min)

        Returns:
            CIPipelineStatus: Current status of the PR's CI pipeline

        Raises:
            ValidationError: If pr_id or project_id are invalid
            ResourceNotFoundError: PR doesn't exist on GitHub
            AuthenticationError: Authentication failure (permanent)
            ExternalServiceError: GitHub API call failed (transient)

        Events:
            Emits 'ci.pipeline_status_checked' event with query result
        """
        # Validate inputs
        if not pr_id or not isinstance(pr_id, str):
            msg = "pr_id must be a non-empty string"
            raise ValidationError(msg)

        if not project_id or not isinstance(project_id, str):
            msg = "project_id must be a non-empty string"
            raise ValidationError(msg)

        # Convert pr_id to integer
        try:
            pr_number = int(pr_id)
        except ValueError as e:
            msg = f"pr_id must be numeric, got: {pr_id}"
            raise ValidationError(msg) from e

        try:
            # Fetch PR details including check runs from GitHub
            owner, repo = await self._get_owner_repo()

            # Query for PR details and associated check runs
            query = """
            query GetPullRequestCheckRuns($owner: String!, $repo: String!, $prNumber: Int!) {
              repository(owner: $owner, name: $repo) {
                pullRequest(number: $prNumber) {
                  id
                  number
                  commits(last: 1) {
                    nodes {
                      commit {
                        oid
                        checkSuites(first: 10) {
                          nodes {
                            status
                            conclusion
                            checkRuns(first: 50) {
                              nodes {
                                name
                                status
                                conclusion
                                detailsUrl
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """

            result = await self._graphql.execute(
                query,
                {"owner": owner, "repo": repo, "prNumber": pr_number},
            )

            # Parse the response
            pr_node = result.get("repository", {}).get("pullRequest")

            if not pr_node:
                raise ResourceNotFoundError("PullRequest", pr_id)

            # Extract and aggregate check runs
            check_results, overall_status, pipeline_url, status_counts = self._parse_check_runs(pr_node)

            # Create CI pipeline status
            ci_status = CIPipelineStatus(
                pr_id=pr_id,
                status=overall_status,
                check_results=tuple(check_results),
                total_checks=len(check_results),
                passed=status_counts["passed"],
                failed=status_counts["failed"],
                pending=status_counts["pending"] + status_counts["running"],
                pipeline_url=pipeline_url,
            )

            logger.info(f"Queried CI status for PR {pr_id}: {overall_status.value}")

            # Emit event asynchronously after successful CI status retrieval
            self._emit_event_safely(
                pr_id=pr_id,
                project_id=project_id,
                overall_status=overall_status,
                check_results=check_results,
            )

            return ci_status

        except (AuthenticationError, ResourceNotFoundError):
            # Permanent errors - log at error level and propagate
            logger.error(
                f"Permanent error querying CI status for PR {pr_id}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_EXTERNAL_SERVICE_ERROR,
                    "pr_id": pr_id,
                    "project_id": project_id,
                    "error_type": "permanent",
                },
            )
            raise
        except ExternalServiceError as e:
            # Transient errors - log at warning level and propagate
            logger.warning(
                f"Transient error querying CI status for PR {pr_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_EXTERNAL_SERVICE_ERROR,
                    "pr_id": pr_id,
                    "project_id": project_id,
                    "error_type": "transient",
                },
            )
            raise
        except Exception as e:
            # Unexpected errors - log critically
            logger.critical(
                f"Unexpected error querying CI status for PR {pr_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_EXTERNAL_SERVICE_ERROR,
                    "pr_id": pr_id,
                    "project_id": project_id,
                    "error_type": "unexpected",
                },
            )
            raise ExternalServiceError("GitHub", f"Failed to query PR CI status: {e}") from e

    async def run_ci_checks(self, project_id: str, working_directory: str, timeout_seconds: int = 600) -> CIRunResult:
        """Execute CI checks locally in a working directory.

        This method is not yet implemented. Use get_pr_ci_status to query CI status
        from GitHub.

        Args:
            project_id: Project being checked
            working_directory: Directory containing project code to check
            timeout_seconds: How long to allow check execution (default 600s / 10min)

        Returns:
            CIRunResult: Summary of check results with failures and warnings

        Raises:
            NotImplementedError: Feature not yet implemented
        """
        msg = "Local CI execution is not yet implemented. Use get_pr_ci_status to query CI status from GitHub."
        raise NotImplementedError(msg)

    # ===== Helper Methods =====

    def _emit_event_safely(
        self,
        pr_id: str,
        project_id: str,
        overall_status: CICheckStatus,
        check_results: list[CICheckResult],
    ) -> None:
        """Emit CI pipeline status checked event with error handling.

        Wraps event construction and emission in try/except to prevent failures
        from affecting the primary operation (CI status retrieval). Event emission
        failures are logged for diagnostics but don't propagate to the caller.

        Args:
            pr_id: Pull request ID
            project_id: Project ID
            overall_status: Overall CI pipeline status
            check_results: List of individual check results
        """
        try:
            self.emit(
                CIPipelineStatusCheckedEvent(
                    type="ci.pipeline_status_checked",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="github",
                    pr_id=pr_id,
                    project_id=project_id,
                    status=overall_status.value,
                    check_count=len(check_results),
                    passed_count=sum(1 for r in check_results if r.status == CICheckStatus.PASSED),
                    failed_count=sum(1 for r in check_results if r.status == CICheckStatus.FAILED),
                    pending_count=sum(
                        1 for r in check_results if r.status in (CICheckStatus.PENDING, CICheckStatus.RUNNING)
                    ),
                )
            )
        except Exception as emit_error:
            logger.error(
                f"Failed to emit CI pipeline status checked event for PR {pr_id}",
                extra={
                    "error_id": ErrorRegistry.ERR_EVENT_PUBLICATION_ERROR,
                    "pr_id": pr_id,
                    "project_id": project_id,
                    "emission_error": str(emit_error),
                },
                exc_info=True,
            )

    def _parse_check_runs(
        self, pr_node: dict[str, Any]
    ) -> tuple[list[CICheckResult], CICheckStatus, str, dict[str, int]]:
        """Parse check runs from GraphQL response into structured format.

        Aggregates check runs from all check suites on the PR's latest commit
        into a single list of CICheckResult objects and determines the overall
        pipeline status.

        Args:
            pr_node: PR node from GraphQL response

        Returns:
            Tuple of (check_results, overall_status, pipeline_url, status_counts)

        Raises:
            ExternalServiceError: If response format is invalid
        """
        check_results: list[CICheckResult] = []
        pipeline_url = ""

        try:
            commits = pr_node.get("commits", {}).get("nodes", [])
            if not commits:
                # No commits yet - treat as pending
                pr_number = pr_node.get("number", "unknown")
                logger.warning(
                    f"PR {pr_number} has no commits but is returning PENDING status",
                    extra={
                        "error_id": ErrorRegistry.ERR_INVALID_STATE,
                        "pr_number": pr_number,
                        "status": "PENDING",
                        "check_count": 0,
                    },
                )
                return (
                    [],
                    CICheckStatus.PENDING,
                    pipeline_url,
                    {
                        "pending": 0,
                        "running": 0,
                        "passed": 0,
                        "failed": 0,
                        "skipped": 0,
                    },
                )

            latest_commit = commits[0]

            # Collect all check runs from all check suites
            check_suites = latest_commit.get("commit", {}).get("checkSuites", {}).get("nodes", [])

            status_counts = {
                "pending": 0,
                "running": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
            }

            for suite in check_suites:
                check_runs = suite.get("checkRuns", {}).get("nodes", [])

                for run in check_runs:
                    name = run.get("name", "unnamed-check")
                    status_str = run.get("status", "QUEUED").lower()
                    conclusion = run.get("conclusion")
                    conclusion_str = conclusion.lower() if conclusion else ""
                    details_url = run.get("detailsUrl", "")

                    # Map GitHub status/conclusion to CICheckStatus
                    # First check status field, then branch on conclusion if completed
                    if status_str == "completed":
                        if conclusion_str in ("success", "neutral"):
                            ci_status = CICheckStatus.PASSED
                            status_counts["passed"] += 1
                        elif conclusion_str in ("failure", "timed_out", "action_required", "cancelled"):
                            ci_status = CICheckStatus.FAILED
                            status_counts["failed"] += 1
                        elif conclusion_str == "skipped":
                            ci_status = CICheckStatus.SKIPPED
                            status_counts["skipped"] += 1
                        else:
                            # Unknown conclusion - log warning and default to FAILED
                            logger.warning(
                                f"Unknown GitHub conclusion '{conclusion_str}' for check '{name}', defaulting to FAILED",
                                extra={
                                    "error_id": ErrorRegistry.ERR_EXTERNAL_SERVICE_ERROR,
                                    "check_name": name,
                                    "conclusion": conclusion_str,
                                    "status": status_str,
                                },
                            )
                            ci_status = CICheckStatus.FAILED
                            status_counts["failed"] += 1
                    elif status_str == "in_progress":
                        ci_status = CICheckStatus.RUNNING
                        status_counts["running"] += 1
                    elif status_str in ("queued", "requested", "waiting", "pending"):
                        ci_status = CICheckStatus.PENDING
                        status_counts["pending"] += 1
                    else:
                        # Unknown status - log warning and default to PENDING
                        logger.warning(
                            f"Unknown GitHub status '{status_str}' for check '{name}', defaulting to PENDING",
                            extra={
                                "error_id": ErrorRegistry.ERR_EXTERNAL_SERVICE_ERROR,
                                "check_name": name,
                                "status": status_str,
                                "conclusion": conclusion_str if conclusion_str else None,
                            },
                        )
                        ci_status = CICheckStatus.PENDING
                        status_counts["pending"] += 1

                    # Create check result
                    check_result = CICheckResult(
                        name=name,
                        status=ci_status,
                        conclusion=conclusion_str if conclusion_str else None,
                        url=details_url if details_url else None,
                    )
                    check_results.append(check_result)

                    # Store first URL as pipeline URL
                    if not pipeline_url and details_url:
                        pipeline_url = details_url

            # Determine overall status
            # Priority: FAILED > PENDING/RUNNING > PASSED > SKIPPED
            if status_counts["failed"] > 0:
                overall_status = CICheckStatus.FAILED
            elif status_counts["pending"] > 0 or status_counts["running"] > 0:
                overall_status = CICheckStatus.PENDING
            elif status_counts["passed"] > 0:
                overall_status = CICheckStatus.PASSED
            else:
                overall_status = CICheckStatus.SKIPPED

            return check_results, overall_status, pipeline_url, status_counts

        except (KeyError, TypeError, AttributeError) as e:
            raise ExternalServiceError("GitHub", f"Invalid check runs response format: {e!s}") from e

    async def _get_owner_repo(self) -> tuple[str, str]:
        """Get GitHub owner and repo from ticket adapter.

        Returns:
            Tuple of (owner, repo)

        Raises:
            ExternalServiceError: If unable to determine owner/repo
        """
        try:
            return self._ticket_adapter.get_owner_repo()
        except (ValueError, AttributeError) as e:
            msg = f"GitHub integration: {e}"
            raise ExternalServiceError("GitHub", msg) from e
