"""GitHub pull request code review adapter with event emission.

Implements ICodeReviewService interface for GitHub pull requests, supporting:
- PR status queries via GraphQL API
- Code review status determination (open, approved, changes_requested, merged, closed)
- Review comments retrieval and code review feedback analysis
- PR approval or request for changes via GraphQL mutations
- Change detection via webhooks or adaptive polling
- Event emission for review status changes and comment additions
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from codetoreum.adapters.secondary.github_ticket_adapter import GitHubTicketAdapter
from codetoreum.domain.events.adapter_events import now_iso
from codetoreum.domain.events.discussion_events import Comment
from codetoreum.domain.events.review_events import (
    ReviewCommentAddedEvent,
    ReviewStatusChangedEvent,
)
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
from codetoreum.ports.output.code_review_service import (
    Approval,
    CodeReview,
    CodeReviewStatus,
    ICodeReviewService,
    ReviewComment,
)
from codetoreum.ports.output.monitoring import (
    MonitoringConfig,
    MonitoringState,
    MonitoringStatus,
)

logger = logging.getLogger(__name__)


class GitHubCodeReviewAdapter(ICodeReviewService):
    """GitHub pull request code review adapter with event emission.

    Provides code review management and change detection for GitHub PRs.
    Supports both webhook-based (real-time) and polling-based (fallback) change detection.

    Detection mechanisms:
    - Webhook: Subscribe to pull_request_review and pull_request events
    - Polling: Periodically query open PRs for status changes (60s intervals)
    - Adaptive intervals: Back off during low-activity periods, burst during high-activity

    Example:
        adapter = GitHubCodeReviewAdapter(
            ticket_adapter=gh_ticket,
            graphql_client=gh_graphql,
            webhook_enabled=True
        )

        # Start monitoring for PR status changes
        await adapter.start_monitoring("proj-123", MonitoringConfig(...))

        # Subscribe to events
        adapter.on("review.status_changed", on_status_change)

        # Approve a PR or request changes
        await adapter.approve(pr_id)
        await adapter.request_changes(pr_id, "Please fix X")

        # Stop monitoring
        await adapter.stop_monitoring("proj-123")
    """

    def __init__(
        self,
        ticket_adapter: GitHubTicketAdapter,
        graphql_client: GitHubGraphQLClient,
        webhook_enabled: bool = True,
    ):
        """Initialize GitHub code review adapter.

        Args:
            ticket_adapter: GitHub ticket adapter for issue metadata and linking
            graphql_client: GitHub GraphQL client for PR queries and mutations
            webhook_enabled: If False, use polling fallback for change detection
        """
        self._ticket_adapter = ticket_adapter
        self._graphql = graphql_client
        self._webhook_enabled = webhook_enabled

        # Monitoring state per project
        self._monitoring: dict[str, MonitoringStatus] = {}
        self._polling_tasks: dict[str, asyncio.Task] = {}

        # Event handlers by event type
        self._event_handlers: dict[str, list[Callable]] = {}

        # State tracking for polling-based change detection
        self._last_known_status: dict[str, CodeReviewStatus] = {}  # pr_id -> status
        self._work_item_reviews: dict[str, str] = {}  # work_item_id -> pr_id

        # Polling configuration
        self._polling_intervals: dict[str, float] = {}  # project_id -> interval
        self._activity_counters: dict[str, int] = {}  # project_id -> change count

    # IEventEmitter implementation

    def on(self, event_type: str, handler: Callable) -> None:
        """Register event handler.

        Args:
            event_type: Type of event to listen for
            handler: Callable to invoke when event is emitted

        Raises:
            ValueError: If event_type is invalid or handler is not callable
        """
        if not isinstance(handler, Callable):
            msg = f"handler must be callable, got {type(handler)}"
            raise ValueError(msg)

        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Callable) -> None:
        """Unregister event handler.

        Args:
            event_type: Type of event
            handler: Callable to remove

        Raises:
            ValueError: If handler was not previously subscribed
        """
        if event_type in self._event_handlers and handler in self._event_handlers[event_type]:
            self._event_handlers[event_type].remove(handler)
        else:
            msg = f"Handler not subscribed to {event_type}"
            raise ValueError(msg)

    def emit(self, event: Any) -> None:
        """Emit event to all registered handlers.

        Handler failures are logged at ERROR level with full stack traces but do not
        prevent other handlers from executing. This allows event processing to continue
        while ensuring failures are visible in logs for monitoring and debugging.

        Critical exceptions like asyncio.CancelledError and KeyboardInterrupt are
        never suppressed - they propagate immediately to the caller. Only application-
        level exceptions (ValueError, TypeError, and other Exception subclasses) are
        caught and logged.

        Args:
            event: Event to emit (should be CodetoreumEvent or subclass)

        Raises:
            asyncio.CancelledError: If a handler is cancelled
            KeyboardInterrupt: If interrupted by user (via BaseException, not caught)
            SystemExit: If system exit is requested (via BaseException, not caught)
        """
        event_type = getattr(event, "type", None)
        if event_type not in self._event_handlers:
            return

        failures = []
        for handler in self._event_handlers[event_type]:
            handler_name = getattr(handler, "__name__", str(handler))
            try:
                handler(event)
            except asyncio.CancelledError:
                # Never suppress cancellation - propagate immediately
                raise
            except (ValueError, TypeError) as e:
                # Expected validation errors from handlers
                logger.error(
                    f"Handler {handler_name} validation error for {event_type}: {e}",
                    exc_info=True,
                    extra={
                        "event_type": event_type,
                        "handler": handler_name,
                        "error_id": ErrorRegistry.ERR_VALIDATION_FAILED
                    }
                )
                failures.append((handler, e))
            except Exception as e:
                # Unexpected errors - critical issue
                logger.error(
                    f"Unexpected error in handler {handler_name} for {event_type}: {e}",
                    exc_info=True,
                    extra={
                        "event_type": event_type,
                        "handler": handler_name,
                        "error_id": ErrorRegistry.ERR_HANDLER_EXECUTION
                    }
                )
                failures.append((handler, e))

        if failures:
            logger.error(
                f"Event emission for {event_type} completed with {len(failures)} handler failure(s)",
                extra={
                    "event_type": event_type,
                    "failure_count": len(failures),
                    "error_id": ErrorRegistry.ERR_HANDLER_EXECUTION
                }
            )

    # IMonitoredService implementation

    async def start_monitoring(
        self, project_id: str, config: MonitoringConfig
    ) -> None:
        """Start monitoring for PR status changes.

        Initializes monitoring for the given project. If webhook_enabled is False,
        starts polling-based change detection with adaptive intervals.

        Args:
            project_id: Project to monitor for PR changes
            config: Monitoring configuration (poll_interval_seconds, etc.)

        Raises:
            ValidationError: If project_id is invalid or config is malformed
        """
        if not project_id:
            msg = "project_id is required"
            raise ValidationError(msg)

        self._monitoring[project_id] = MonitoringStatus(
            state=MonitoringState.ACTIVE,
            project_id=project_id,
            started_at=datetime.now(UTC).isoformat(),
        )

        # Initialize polling configuration
        self._polling_intervals[project_id] = float(
            config.poll_interval_seconds or 60
        )
        self._activity_counters[project_id] = 0

        # Start polling if webhooks disabled
        if not self._webhook_enabled:
            self._polling_tasks[project_id] = asyncio.create_task(
                self._poll_review_changes(project_id)
            )
            logger.info(
                f"Started polling for PR changes in {project_id} "
                f"(interval: {self._polling_intervals[project_id]}s)"
            )

    async def stop_monitoring(self, project_id: str) -> None:
        """Stop monitoring for PR status changes.

        Cancels any polling tasks and marks the project as no longer monitored.

        Args:
            project_id: Project to stop monitoring

        Raises:
            ValidationError: If project_id is invalid
            ResourceNotFoundError: If not currently monitoring this project
        """
        if not project_id:
            msg = "project_id is required"
            raise ValidationError(msg)

        if project_id not in self._monitoring:
            msg = "project"
            raise ResourceNotFoundError(msg, project_id)

        # Cancel polling task if running
        if project_id in self._polling_tasks:
            task = self._polling_tasks[project_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self._polling_tasks[project_id]

        # Mark as stopped
        if project_id in self._monitoring:
            self._monitoring[project_id].state = MonitoringState.STOPPED

        logger.info(f"Stopped monitoring project {project_id} for PR changes")

    async def get_monitoring_status(self, project_id: str) -> MonitoringStatus:
        """Query current monitoring state.

        Args:
            project_id: Project to query status for

        Returns:
            MonitoringStatus with current state and metadata

        Raises:
            ValidationError: If project_id is invalid
        """
        if not project_id:
            msg = "project_id is required"
            raise ValidationError(msg)

        if project_id in self._monitoring:
            return self._monitoring[project_id]

        return MonitoringStatus(
            state=MonitoringState.STOPPED,
            project_id=project_id,
        )

    # Query Operations

    async def get_review_for_work_item(
        self, work_item_id: str
    ) -> CodeReview | None:
        """Find code review associated with a work item.

        Searches for a PR linked to the work item by:
        1. Checking cached mapping (work_item_id -> pr_id)
        2. Querying for PRs with branch matching work item ID
        3. Querying for PRs with work item reference in body

        Args:
            work_item_id: Work item to find review for

        Returns:
            CodeReview if PR exists, None otherwise

        Raises:
            ValidationError: If work_item_id is invalid
            ExternalServiceError: If GraphQL query fails
        """
        if not work_item_id:
            msg = "work_item_id is required"
            raise ValidationError(msg)

        # Check cache first
        if work_item_id in self._work_item_reviews:
            pr_id = self._work_item_reviews[work_item_id]
            try:
                return await self._fetch_pr_details(pr_id)
            except ResourceNotFoundError:
                del self._work_item_reviews[work_item_id]

        # Query for PRs matching work item ID
        owner, repo = await self._get_owner_repo()
        query = """
        query SearchPullRequests($owner: String!, $repo: String!, $searchTerm: String!) {
          search(query: $searchTerm, type: ISSUE, first: 10) {
            nodes {
              ... on PullRequest {
                id
                number
                title
                body
                state
                isDraft
                baseRefName
                headRefName
                reviews(first: 10) {
                  nodes {
                    id
                    state
                    author {
                      login
                    }
                    submittedAt
                  }
                }
                reviewRequests(first: 10) {
                  nodes {
                    requestedReviewer {
                      ... on User {
                        login
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        search_term = f'repo:{owner}/{repo} is:pr "{work_item_id}"'
        try:
            result = await self._graphql.execute(query, {"searchTerm": search_term})

            nodes = result.get("search", {}).get("nodes", [])
            if nodes and len(nodes) > 0:
                pr_node = nodes[0]
                pr_id = pr_node["id"]
                self._work_item_reviews[work_item_id] = pr_id
                return self._parse_code_review(pr_node, work_item_id)

            return None
        except Exception as e:
            msg = "github"
            raise ExternalServiceError(msg, f"Failed to search for PR: {e}")

    async def get_review_status(self, review_id: str) -> CodeReviewStatus:
        """Query current PR review status.

        Fetches the PR and computes the overall review status based on:
        - PR state (open, closed, merged)
        - Review states (approved, changes_requested)

        Args:
            review_id: PR node ID to query

        Returns:
            CodeReviewStatus (open, approved, changes_requested, merged, closed)

        Raises:
            ValidationError: If review_id is invalid
            ResourceNotFoundError: If PR doesn't exist
            ExternalServiceError: If GraphQL query fails
        """
        if not review_id:
            msg = "review_id is required"
            raise ValidationError(msg)

        query = """
        query GetPullRequest($prId: ID!) {
          node(id: $prId) {
            ... on PullRequest {
              state
              isDraft
              reviews(first: 50) {
                nodes {
                  state
                  submittedAt
                }
              }
            }
          }
        }
        """

        try:
            result = await self._graphql.execute(query, {"prId": review_id})
            pr_node = result.get("node")

            if not pr_node:
                msg = "PR"
                raise ResourceNotFoundError(msg, review_id)

            return self._compute_review_status(pr_node)
        except (ExternalServiceError, ResourceNotFoundError):
            raise
        except Exception as e:
            msg = "github"
            raise ExternalServiceError(msg, f"Failed to fetch PR status: {e}")

    async def get_review_comments(self, review_id: str) -> list[ReviewComment]:
        """Retrieve all comments on a code review.

        Fetches comments from all reviews on the PR, including review comments
        and inline code comments.

        Args:
            review_id: PR node ID to get comments from

        Returns:
            List of ReviewComment objects

        Raises:
            ValidationError: If review_id is invalid
            ResourceNotFoundError: If PR doesn't exist
            ExternalServiceError: If GraphQL query fails
        """
        if not review_id:
            msg = "review_id is required"
            raise ValidationError(msg)

        query = """
        query GetPullRequestComments($prId: ID!) {
          node(id: $prId) {
            ... on PullRequest {
              id
              reviews(first: 50) {
                nodes {
                  id
                  state
                  author {
                    login
                  }
                  body
                  submittedAt
                  comments(first: 100) {
                    nodes {
                      id
                      author {
                        login
                      }
                      body
                      createdAt
                      path
                      position
                    }
                  }
                }
              }
              comments(first: 100) {
                nodes {
                  id
                  author {
                    login
                  }
                  body
                  createdAt
                }
              }
            }
          }
        }
        """

        try:
            result = await self._graphql.execute(query, {"prId": review_id})
            pr_node = result.get("node")

            if not pr_node:
                msg = "PR"
                raise ResourceNotFoundError(msg, review_id)

            comments = []

            # Collect review body comments
            for review in pr_node.get("reviews", {}).get("nodes", []):
                if review.get("body"):
                    comments.append(ReviewComment(
                        id=review.get("id", ""),
                        author=review.get("author", {}).get("login", "unknown"),
                        body=review.get("body", ""),
                        created_at=review.get("submittedAt", ""),
                    ))

                # Collect inline code comments from review
                for comment_node in review.get("comments", {}).get("nodes", []):
                    comments.append(ReviewComment(
                        id=comment_node.get("id", ""),
                        author=comment_node.get("author", {}).get("login", "unknown"),
                        body=comment_node.get("body", ""),
                        created_at=comment_node.get("createdAt", ""),
                        file_path=comment_node.get("path"),
                        line_number=comment_node.get("position"),
                    ))

            # Collect PR discussion comments
            for comment_node in pr_node.get("comments", {}).get("nodes", []):
                comments.append(ReviewComment(
                    id=comment_node.get("id", ""),
                    author=comment_node.get("author", {}).get("login", "unknown"),
                    body=comment_node.get("body", ""),
                    created_at=comment_node.get("createdAt", ""),
                ))

            return comments
        except ResourceNotFoundError:
            raise
        except Exception as e:
            msg = "github"
            raise ExternalServiceError(msg, f"Failed to fetch PR comments: {e}")

    # Command Operations

    async def request_changes(self, review_id: str, comments: str) -> None:
        """Request changes on a code review.

        Submits a review requesting that changes be made before approval.
        Emits review.status_changed and review.comment_added events.

        Args:
            review_id: PR node ID to request changes on
            comments: Feedback about what needs to change

        Raises:
            ValidationError: If review_id or comments are invalid
            ResourceNotFoundError: If PR doesn't exist
            PermissionError: If bot cannot request changes
            ExternalServiceError: If GraphQL mutation fails

        Events:
            - review.status_changed: When PR review status changes
            - review.comment_added: When the request-changes comment is added
        """
        if not review_id:
            msg = "review_id is required"
            raise ValidationError(msg)
        if not comments or not isinstance(comments, str):
            msg = "comments must be a non-empty string"
            raise ValidationError(msg)
        if len(comments) > 65536:
            msg = "comments exceeds maximum length (65536 chars)"
            raise ValidationError(msg)

        # Get previous status
        try:
            previous_status = await self.get_review_status(review_id)
        except ResourceNotFoundError:
            msg = f"PR {review_id} not found"
            raise ResourceNotFoundError(msg)

        # Submit review with REQUEST_CHANGES event
        mutation = """
        mutation SubmitReview($prId: ID!, $event: PullRequestReviewEvent!, $body: String!) {
          submitPullRequestReview(input: {
            pullRequestId: $prId
            event: $event
            body: $body
          }) {
            pullRequestReview {
              id
              state
              author {
                login
              }
              submittedAt
            }
          }
        }
        """

        try:
            result = await self._graphql.execute(
                mutation,
                {
                    "prId": review_id,
                    "event": "REQUEST_CHANGES",
                    "body": comments,
                },
            )

            review_node = result.get("submitPullRequestReview", {}).get(
                "pullRequestReview"
            )
            if not review_node:
                msg = "github"
                raise ExternalServiceError(
                    msg, "Failed to submit review: empty response"
                )

            # Get new status
            new_status = await self.get_review_status(review_id)
            work_item_id = self._get_work_item_for_review(review_id)
            project_id = await self._get_project_id()

            # Emit status changed event
            if previous_status != new_status:
                self.emit(ReviewStatusChangedEvent(
                    type="review.status_changed",
                    timestamp=now_iso(),
                    source="github",
                    review_id=review_id,
                    work_item_id=work_item_id,
                    project_id=project_id,
                    previous_status=previous_status,
                    new_status=new_status,
                    reviewer=review_node.get("author", {}).get("login"),
                ))

            # Emit comment added event
            comment = Comment(
                id=review_node.get("id", ""),
                author=review_node.get("author", {}).get("login", "unknown"),
                body=comments,
                created_at=review_node.get("submittedAt", now_iso()),
                is_bot=True,
            )

            self.emit(ReviewCommentAddedEvent(
                type="review.comment_added",
                timestamp=now_iso(),
                source="github",
                review_id=review_id,
                work_item_id=work_item_id,
                project_id=project_id,
                comment=comment,
            ))

            logger.info(f"Requested changes on PR {review_id}")

        except ExternalServiceError:
            raise
        except Exception as e:
            msg = "github"
            raise ExternalServiceError(msg, f"Failed to request changes: {e}")

    async def approve(self, review_id: str) -> None:
        """Approve a code review.

        Approves the PR, indicating proposed changes are acceptable.
        Emits review.status_changed event.

        Args:
            review_id: PR node ID to approve

        Raises:
            ValidationError: If review_id is invalid
            ResourceNotFoundError: If PR doesn't exist
            PermissionError: If bot cannot approve
            ExternalServiceError: If GraphQL mutation fails

        Events:
            - review.status_changed: With new_status='approved'
        """
        if not review_id:
            msg = "review_id is required"
            raise ValidationError(msg)

        # Get previous status
        try:
            previous_status = await self.get_review_status(review_id)
        except ResourceNotFoundError:
            msg = f"PR {review_id} not found"
            raise ResourceNotFoundError(msg)

        # Submit APPROVE review
        mutation = """
        mutation SubmitReview($prId: ID!, $event: PullRequestReviewEvent!) {
          submitPullRequestReview(input: {
            pullRequestId: $prId
            event: $event
          }) {
            pullRequestReview {
              id
              state
              author {
                login
              }
              submittedAt
            }
          }
        }
        """

        try:
            result = await self._graphql.execute(
                mutation,
                {
                    "prId": review_id,
                    "event": "APPROVE",
                },
            )

            review_node = result.get("submitPullRequestReview", {}).get(
                "pullRequestReview"
            )
            if not review_node:
                msg = "github"
                raise ExternalServiceError(
                    msg, "Failed to approve: empty response"
                )

            # Get new status
            new_status = await self.get_review_status(review_id)
            work_item_id = self._get_work_item_for_review(review_id)
            project_id = await self._get_project_id()

            # Emit status changed event
            if previous_status != new_status:
                self.emit(ReviewStatusChangedEvent(
                    type="review.status_changed",
                    timestamp=now_iso(),
                    source="github",
                    review_id=review_id,
                    work_item_id=work_item_id,
                    project_id=project_id,
                    previous_status=previous_status,
                    new_status=new_status,
                    reviewer=review_node.get("author", {}).get("login"),
                ))

            logger.info(f"Approved PR {review_id}")

        except ExternalServiceError:
            raise
        except Exception as e:
            msg = "github"
            raise ExternalServiceError(msg, f"Failed to approve: {e}")

    # Webhook handling

    async def handle_webhook(self, payload: dict) -> None:
        """Process GitHub pull_request_review webhook event.

        Handles webhook payloads from GitHub for PR review events:
        - pull_request_review: submitted, edited, dismissed
        - pull_request: opened, closed, reopened, merged

        Args:
            payload: GitHub webhook payload

        Raises:
            ValidationError: If payload is invalid
        """
        if not payload or not isinstance(payload, dict):
            msg = "payload must be a non-empty dict"
            raise ValidationError(msg)

        event_action = payload.get("action")
        pr_data = payload.get("pull_request")

        if not pr_data:
            logger.debug("Webhook has no pull_request data, ignoring")
            return

        pr_id = str(pr_data.get("id"))
        work_item_id = self._extract_work_item_id(pr_data)
        project_id = await self._get_project_id()

        # Handle pull_request_review event
        if "review" in payload:
            await self._handle_review_event(
                payload, pr_id, work_item_id, project_id
            )
            return

        # Handle pull_request state change event
        if event_action in ["opened", "closed", "reopened", "merged"]:
            await self._handle_pr_state_change(
                payload, pr_id, work_item_id, project_id
            )

    async def _handle_review_event(
        self, payload: dict, pr_id: str, work_item_id: str | None, project_id: str
    ) -> None:
        """Handle pull_request_review webhook event.

        Args:
            payload: Webhook payload
            pr_id: PR ID for tracking
            work_item_id: Associated work item (if known)
            project_id: Project ID
        """
        action = payload.get("action")
        if action not in ["submitted", "edited"]:
            return

        review_data = payload.get("review", {})
        reviewer = review_data.get("user", {}).get("login")

        previous_status = self._last_known_status.get(pr_id, "open")
        new_status = self._map_github_review_state(review_data.get("state"))

        # Skip if state didn't change
        if previous_status == new_status:
            return

        self._last_known_status[pr_id] = new_status

        # Emit status changed event
        self.emit(ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp=now_iso(),
            source="github",
            review_id=pr_id,
            work_item_id=work_item_id,
            project_id=project_id,
            previous_status=previous_status,
            new_status=new_status,
            reviewer=reviewer,
        ))

        logger.info(f"PR {pr_id} review status changed: {previous_status} -> {new_status}")

    async def _handle_pr_state_change(
        self, payload: dict, pr_id: str, work_item_id: str | None, project_id: str
    ) -> None:
        """Handle pull_request state change webhook event.

        Args:
            payload: Webhook payload
            pr_id: PR ID for tracking
            work_item_id: Associated work item (if known)
            project_id: Project ID
        """
        action = payload.get("action")
        pr_data = payload.get("pull_request", {})

        previous_status = self._last_known_status.get(pr_id, "open")

        # Map action to status
        if action == "merged":
            new_status = "merged"
        elif action == "closed":
            new_status = "closed"
        elif action in ["opened", "reopened"]:
            new_status = "open"
        else:
            return

        # Skip if state didn't change
        if previous_status == new_status:
            return

        self._last_known_status[pr_id] = new_status

        # Emit status changed event
        self.emit(ReviewStatusChangedEvent(
            type="review.status_changed",
            timestamp=now_iso(),
            source="github",
            review_id=pr_id,
            work_item_id=work_item_id,
            project_id=project_id,
            previous_status=previous_status,
            new_status=new_status,
        ))

        logger.info(f"PR {pr_id} state changed: {previous_status} -> {new_status}")

    # Polling implementation

    async def _poll_review_changes(self, project_id: str) -> None:
        """Poll for PR status changes.

        Periodically queries open PRs in the project and compares with last known
        status to detect changes. Implements adaptive polling intervals based on
        activity levels.

        Args:
            project_id: Project to poll for changes
        """
        interval = self._polling_intervals.get(project_id, 60.0)

        while True:
            try:
                await asyncio.sleep(interval)

                # Query open PRs
                try:
                    open_prs = await self._get_open_prs(project_id)
                except asyncio.CancelledError:
                    logger.info(f"PR polling cancelled for {project_id}")
                    raise
                except (AuthenticationError, ResourceNotFoundError, ValidationError) as e:
                    logger.error(
                        f"Permanent error in PR polling for {project_id}: {e}",
                        exc_info=True,
                        extra={
                            "error_id": "ERR_REVIEW_ERROR",
                            "project_id": project_id,
                            "error_type": "permanent"
                        }
                    )
                    break
                except ExternalServiceError as e:
                    logger.warning(
                        f"Transient error in PR polling for {project_id}: {e}",
                        extra={"project_id": project_id, "error_type": "transient"}
                    )
                    continue
                except Exception as e:
                    logger.critical(
                        f"Unexpected error in PR polling for {project_id}: {e}",
                        exc_info=True,
                        extra={"project_id": project_id, "error_type": "unexpected"}
                    )
                    continue

                changes_detected = 0

                for pr_node in open_prs:
                    pr_id = pr_node.get("id")
                    current_status = self._compute_review_status(pr_node)
                    previous_status = self._last_known_status.get(pr_id)

                    # Detect status change
                    if previous_status and previous_status != current_status:
                        changes_detected += 1

                        work_item_id = self._extract_work_item_id(pr_node)

                        # Emit status changed event
                        self.emit(ReviewStatusChangedEvent(
                            type="review.status_changed",
                            timestamp=now_iso(),
                            source="github",
                            review_id=pr_id,
                            work_item_id=work_item_id,
                            project_id=project_id,
                            previous_status=previous_status,
                            new_status=current_status,
                        ))

                        logger.info(
                            f"Detected PR {pr_id} status change: "
                            f"{previous_status} -> {current_status}"
                        )

                    self._last_known_status[pr_id] = current_status

                # Adapt polling interval based on activity
                self._adapt_polling_interval(project_id, changes_detected)

            except asyncio.CancelledError:
                logger.info(f"Polling task for {project_id} cancelled")
                break
            except Exception as e:
                logger.error(
                    f"Error in polling loop for {project_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_REVIEW_ERROR", "project_id": project_id}
                )

    def _adapt_polling_interval(self, project_id: str, changes_detected: int) -> None:
        """Adapt polling interval based on activity.

        Implements exponential backoff during low activity and faster checking
        during high activity.

        Args:
            project_id: Project ID
            changes_detected: Number of changes detected in last poll
        """
        current = self._polling_intervals.get(project_id, 60.0)

        if changes_detected > 0:
            # High activity: reduce interval to 15s (min)
            new_interval = max(15.0, current * 0.5)
        else:
            # Low activity: increase interval to 300s (max)
            new_interval = min(300.0, current * 1.5)

        self._polling_intervals[project_id] = new_interval

    # Helper methods

    async def _fetch_pr_details(self, pr_id: str) -> CodeReview:
        """Fetch full PR details from GraphQL.

        Args:
            pr_id: PR node ID

        Returns:
            CodeReview object

        Raises:
            ResourceNotFoundError: If PR not found
            ExternalServiceError: If query fails
        """
        query = """
        query GetPullRequest($prId: ID!) {
          node(id: $prId) {
            ... on PullRequest {
              id
              number
              title
              body
              baseRefName
              headRefName
              state
              isDraft
              reviews(first: 50) {
                nodes {
                  id
                  state
                  author {
                    login
                  }
                  submittedAt
                }
              }
            }
          }
        }
        """

        try:
            result = await self._graphql.execute(query, {"prId": pr_id})
            pr_node = result.get("node")

            if not pr_node:
                msg = "PR"
                raise ResourceNotFoundError(msg, pr_id)

            return self._parse_code_review(pr_node)
        except ResourceNotFoundError:
            raise
        except Exception as e:
            msg = "github"
            raise ExternalServiceError(msg, f"Failed to fetch PR details: {e}")

    async def _get_open_prs(self, project_id: str) -> list[dict[str, Any]]:
        """Query all open PRs for a project.

        Args:
            project_id: Project ID

        Returns:
            List of PR nodes

        Raises:
            ExternalServiceError: If query fails
        """
        owner, repo = await self._get_owner_repo()

        query = """
        query GetOpenPRs($owner: String!, $repo: String!) {
          repository(owner: $owner, name: $repo) {
            pullRequests(first: 50, states: [OPEN]) {
              nodes {
                id
                number
                title
                body
                state
                isDraft
                baseRefName
                headRefName
                reviews(first: 50) {
                  nodes {
                    id
                    state
                    author {
                      login
                    }
                    submittedAt
                  }
                }
              }
            }
          }
        }
        """

        try:
            result = await self._graphql.execute(
                query, {"owner": owner, "repo": repo}
            )
            prs = result.get("repository", {}).get("pullRequests", {}).get("nodes", [])
            return prs
        except Exception as e:
            msg = "github"
            raise ExternalServiceError(msg, f"Failed to fetch open PRs: {e}")

    def _compute_review_status(self, pr_node: dict[str, Any]) -> CodeReviewStatus:
        """Compute overall review status from PR node.

        Maps GitHub PR state and reviews to vendor-agnostic status:
        - MERGED PR -> merged
        - CLOSED PR -> closed
        - CHANGES_REQUESTED review -> changes_requested
        - APPROVED reviews (all reviewers) -> approved
        - otherwise -> open

        Args:
            pr_node: PR node from GraphQL response

        Returns:
            CodeReviewStatus
        """
        if pr_node.get("state") == "MERGED":
            return "merged"
        if pr_node.get("state") == "CLOSED":
            return "closed"

        reviews = pr_node.get("reviews", {}).get("nodes", [])

        # Check for changes requested
        for review in reviews:
            if review.get("state") == "CHANGES_REQUESTED":
                return "changes_requested"

        # Check for approvals
        approved_count = sum(1 for r in reviews if r.get("state") == "APPROVED")
        if approved_count > 0:
            return "approved"

        return "open"

    def _map_github_review_state(
        self, github_state: str | None
    ) -> CodeReviewStatus:
        """Map GitHub review state to vendor-agnostic status.

        Args:
            github_state: GitHub review state (PENDING, APPROVED, CHANGES_REQUESTED, DISMISSED)

        Returns:
            CodeReviewStatus
        """
        mapping = {
            "PENDING": "open",
            "APPROVED": "approved",
            "CHANGES_REQUESTED": "changes_requested",
            "DISMISSED": "open",
        }
        return mapping.get(github_state, "open")  # type: ignore

    def _parse_code_review(
        self, pr_node: dict[str, Any], work_item_id: str | None = None
    ) -> CodeReview:
        """Parse PR node into CodeReview object.

        Args:
            pr_node: PR node from GraphQL
            work_item_id: Optional associated work item ID

        Returns:
            CodeReview object
        """
        reviews = pr_node.get("reviews", {}).get("nodes", [])

        # Collect reviewers and approvals
        reviewers = set()
        approvals = []

        for review in reviews:
            reviewer = review.get("author", {}).get("login")
            if reviewer:
                reviewers.add(reviewer)

            if review.get("state") == "APPROVED":
                approvals.append(Approval(
                    reviewer=reviewer or "unknown",
                    approved_at=review.get("submittedAt", ""),
                ))

        return CodeReview(
            id=pr_node.get("id", ""),
            title=pr_node.get("title", ""),
            source_branch=pr_node.get("headRefName", ""),
            target_branch=pr_node.get("baseRefName", ""),
            status=self._compute_review_status(pr_node),
            reviewers=list(reviewers),
            approvals=approvals,
            work_item_id=work_item_id,
        )

    def _extract_work_item_id(self, pr_data: dict[str, Any]) -> str | None:
        """Extract work item ID from PR.

        Looks for work item ID in PR body or branch name.

        Args:
            pr_data: PR data dict

        Returns:
            Work item ID if found, None otherwise
        """
        # Check branch name for work item reference
        branch = pr_data.get("headRefName", "")
        if "/" in branch:
            parts = branch.split("/")
            if len(parts) > 1 and parts[1].startswith("item-"):
                return parts[1]

        # Check body for work item reference
        body = pr_data.get("body", "")
        if "work item" in body.lower():
            # Simple heuristic: look for "item-123" pattern
            import re
            match = re.search(r"item-\d+", body)
            if match:
                return match.group(0)

        return None

    def _get_work_item_for_review(self, review_id: str) -> str | None:
        """Get work item ID for a review (from cache).

        Args:
            review_id: PR ID

        Returns:
            Work item ID if in cache, None otherwise
        """
        for work_item_id, pr_id in self._work_item_reviews.items():
            if pr_id == review_id:
                return work_item_id
        return None

    async def _get_owner_repo(self) -> tuple:
        """Get GitHub owner and repo from ticket adapter.

        Returns:
            Tuple of (owner, repo)

        Raises:
            ExternalServiceError: If unable to determine owner/repo
        """
        # Get from ticket adapter context (implementation-specific)
        # For now, assume adapter has these attributes
        if hasattr(self._ticket_adapter, "_owner") and hasattr(
            self._ticket_adapter, "_repo"
        ):
            return (self._ticket_adapter._owner, self._ticket_adapter._repo)

        msg = "github"
        raise ExternalServiceError(
            msg, "Unable to determine GitHub owner/repo from adapter"
        )

    async def _get_project_id(self) -> str:
        """Get current project ID.

        Returns:
            Project ID string
        """
        # For now, return generic project identifier
        # In production, this would be tracked from context
        owner, repo = await self._get_owner_repo()
        return f"{owner}/{repo}"
