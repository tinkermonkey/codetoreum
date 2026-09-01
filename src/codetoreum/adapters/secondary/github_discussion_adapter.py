"""GitHub issue comment adapter with event emission.

Implements IDiscussionAdapter for GitHub issues using REST API for comments
and GraphQL for Projects v2 integration. Supports both webhook-based and
polling-based detection of new comments.

Features:
- Posts comments to GitHub issues via REST API
- Retrieves discussion threads via REST API
- Webhook handler for real-time comment detection
- Polling fallback with configurable intervals
- Bot comment filtering using IIdentityService
- Event emission for comment.needs_response and comment.posted
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from codetoreum.adapters.secondary.github_ticket_adapter import GitHubTicketAdapter
from codetoreum.domain.events.discussion_events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    CommentPostedEvent,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.http.github_graphql_client import GitHubGraphQLClient
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from codetoreum.ports.output.discussion_adapter import (
    DiscussionMonitoringConfig,
    DiscussionThread,
    IDiscussionAdapter,
)
from codetoreum.ports.output.identity_service import IIdentityService

logger = logging.getLogger(__name__)


@dataclass
class GitHubDiscussionConfig:
    """Configuration for GitHub Discussion adapter.

    Attributes:
        token: GitHub personal access token or GitHub App token
        organization: GitHub organization name
        repository: GitHub repository name (optional, can be resolved per-project via ticket_adapter)
        api_base_url: Base URL for GitHub REST API
        graphql_client: Optional pre-configured GraphQL client
        webhook_enabled: Whether to use webhook-based detection
        polling_interval_seconds: Interval for polling fallback (default 30)
        api_version: GitHub API version header
        timeout_seconds: HTTP request timeout
    """

    token: str
    organization: str
    repository: str = ""
    api_base_url: str = "https://api.github.com"
    graphql_client: GitHubGraphQLClient | None = None
    webhook_enabled: bool = True
    polling_interval_seconds: int = 30
    api_version: str = "2022-11-28"
    timeout_seconds: int = 30


class GitHubDiscussionAdapter(IDiscussionAdapter):
    """GitHub issue comment adapter with event emission.

    Manages comments on GitHub issues with support for both webhook-based
    and polling-based detection. Filters bot comments and emits standardized
    events for orchestrator consumption.

    Example:
        config = GitHubDiscussionConfig(
            token="ghp_...",
            organization="myorg",
            repository="myrepo"
        )
        adapter = GitHubDiscussionAdapter(config, identity_service)

        # Start monitoring an issue
        mon_config = DiscussionMonitoringConfig(
            project_id="proj-1"
        )
        adapter.start_monitoring("issue-123", mon_config)

        # Handle comments
        adapter.on("comment.needs_response", lambda e: print(f"Got comment: {e.comment.body}"))

        # Post a response
        comment = await adapter.add_comment("issue-123", "This looks good!")

        adapter.stop_monitoring("issue-123")
    """

    def __init__(
        self,
        config: GitHubDiscussionConfig,
        identity_service: IIdentityService,
        ticket_adapter: GitHubTicketAdapter | None = None,
    ):
        """Initialize GitHub discussion adapter.

        Args:
            config: GitHub configuration
            identity_service: Service for bot identification
            ticket_adapter: Optional GitHub ticket adapter for per-project repository resolution.
                When supplied, the adapter resolves owner/repo per work item's project_id
                via ticket_adapter._get_repo(project_id). Falls back to config.repository
                when not supplied or project isn't registered.

        Raises:
            ValidationError: If configuration is invalid
        """
        self._config = config
        self._identity_service = identity_service
        self._ticket_adapter = ticket_adapter
        self._http_client: httpx.AsyncClient | None = None
        self._graphql_client = config.graphql_client
        self._webhook_enabled = config.webhook_enabled

        # Event emitter state
        self._event_handlers: dict[str, list[Callable]] = {}

        # Monitoring state: work_item_id -> config
        self._monitoring: dict[str, DiscussionMonitoringConfig] = {}

        # Polling state: work_item_id -> last_comment_id
        self._last_processed: dict[str, str | None] = {}

        # Polling tasks: work_item_id -> asyncio.Task
        self._polling_tasks: dict[str, asyncio.Task] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for GitHub REST API."""
        if self._http_client is None:
            headers = {
                "Authorization": f"Bearer {self._config.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": self._config.api_version,
            }

            self._http_client = httpx.AsyncClient(
                base_url=self._config.api_base_url,
                headers=headers,
                timeout=self._config.timeout_seconds,
            )

        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False

    def _resolve_repository(self, work_item_id: str) -> str:
        """Resolve the GitHub repository for a work item.

        When ticket_adapter is supplied, resolves owner/repo per-project via
        ticket_adapter._get_repo(project_id), sourcing project_id from the
        internally tracked self._monitoring[work_item_id].project_id.
        Falls back to self._config.repository when ticket_adapter is not supplied
        or the project isn't registered.

        Args:
            work_item_id: ID of the work item

        Returns:
            str: Repository name

        Raises:
            ConfigurationError: If unable to determine repository
        """
        if self._ticket_adapter and work_item_id in self._monitoring:
            try:
                project_id = self._monitoring[work_item_id].project_id
                repo = self._ticket_adapter._get_repo(project_id)
                return repo
            except (ConfigurationError, KeyError):
                # Fall back to config.repository if ticket_adapter resolution fails
                pass

        if self._config.repository:
            return self._config.repository

        raise ConfigurationError(
            f"Unable to determine GitHub repository for work_item_id '{work_item_id}'. "
            "Either provide ticket_adapter for multi-project resolution or set "
            "config.repository for single-repo fallback."
        )

    # Query Operations

    async def get_thread(self, work_item_id: str) -> DiscussionThread:
        """Retrieve full discussion thread for a work item.

        Routes to the GitHub Discussions API (GraphQL) when work_item_id starts
        with "D_" (a Discussion node ID), or the Issues comments REST API for
        numeric issue numbers.

        Args:
            work_item_id: GitHub issue number (digits) or Discussion node ID (D_...)

        Returns:
            DiscussionThread: Complete thread with all comments

        Raises:
            ResourceNotFoundError: Issue/discussion doesn't exist
            ExternalServiceError: API communication failure
            ValidationError: Invalid work_item_id
        """
        if not work_item_id:
            msg = f"Invalid work_item_id: {work_item_id}"
            raise ValidationError(msg)

        if work_item_id.startswith("D_"):
            return await self._get_discussion_thread(work_item_id)

        if not work_item_id.isdigit():
            msg = (
                f"Invalid work_item_id '{work_item_id}': must be a numeric issue number or a Discussion node ID (D_...)"
            )
            raise ValidationError(msg)

        client = await self._get_client()
        comments = []
        page = 1
        per_page = 100
        repository = self._resolve_repository(work_item_id)

        try:
            while True:
                # Fetch page of comments
                url = f"/repos/{self._config.organization}/{repository}/issues/{work_item_id}/comments"

                response = await client.get(
                    url,
                    params={
                        "page": page,
                        "per_page": per_page,
                        "sort": "created",
                        "direction": "asc",
                    },
                )

                if response.status_code == 401:
                    msg = "GitHub authentication failed"
                    raise AuthenticationError(msg)
                if response.status_code == 404:
                    msg = "Issue"
                    raise ResourceNotFoundError(msg, work_item_id)
                if response.status_code == 403:
                    msg = "GitHub"
                    raise ExternalServiceError(service=msg, message="Rate limit exceeded")
                if response.status_code >= 400:
                    msg = "GitHub"
                    raise ExternalServiceError(service=msg, message=f"API error: {response.status_code}")

                page_data = response.json()
                if not page_data:
                    break

                # Parse comments from response
                for item in page_data:
                    comment = Comment(
                        id=str(item["id"]),
                        author=item["user"]["login"],
                        body=item["body"],
                        created_at=item["created_at"],
                        parent_id=None,  # GitHub issue comments are flat
                        is_bot=self._identity_service.is_bot_user(item["user"]["login"]),
                    )
                    comments.append(comment)

                # Check if there are more pages
                if len(page_data) < per_page:
                    break

                page += 1

            return DiscussionThread(
                id=f"thread-{work_item_id}",
                work_item_id=work_item_id,
                comments=comments,
                thread_type="flat",
            )

        except (httpx.RequestError, httpx.HTTPError) as e:
            raise ExternalServiceError(service="GitHub", message=f"API request failed: {e!s}")

    async def _get_discussion_thread(self, discussion_id: str) -> DiscussionThread:
        """Retrieve all comments on a GitHub Discussion via GraphQL API."""
        if self._graphql_client is None:
            raise ExternalServiceError(
                service="GitHub", message="GraphQL client required to fetch GitHub Discussion threads"
            )

        query = """
        query GetDiscussionComments($id: ID!, $after: String) {
          node(id: $id) {
            ... on Discussion {
              comments(first: 100, after: $after) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  id
                  body
                  author { login }
                  createdAt
                }
              }
            }
          }
        }
        """

        comments: list[Comment] = []
        cursor: str | None = None

        while True:
            variables: dict = {"id": discussion_id}
            if cursor:
                variables["after"] = cursor

            result = await self._graphql_client.execute(query, variables)
            node = result.get("node")
            if not node:
                raise ResourceNotFoundError("Discussion", discussion_id)

            page = node["comments"]
            for item in page["nodes"]:
                comments.append(
                    Comment(
                        id=item["id"],
                        author=item["author"]["login"],
                        body=item["body"],
                        created_at=item["createdAt"],
                        parent_id=None,
                        is_bot=self._identity_service.is_bot_user(item["author"]["login"]),
                    )
                )

            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]

        return DiscussionThread(
            id=f"thread-{discussion_id}",
            work_item_id=discussion_id,
            comments=comments,
            thread_type="flat",
        )

    # Command Operations

    async def add_comment(
        self,
        work_item_id: str,
        content: str,
        parent_id: str | None = None,
    ) -> Comment:
        """Post a comment to a work item.

        Routes to the GitHub Discussions API (GraphQL) when work_item_id starts
        with "D_" (a Discussion node ID), or the Issues comments REST API for
        numeric issue numbers. This routing is an internal implementation detail
        — callers use only the work_item_id and are unaware of the distinction.

        Args:
            work_item_id: GitHub issue number (digits) or Discussion node ID (D_...)
            content: Comment text
            parent_id: Ignored (GitHub flat thread model for issues; top-level for discussions)

        Returns:
            Comment: Newly posted comment with server-assigned ID

        Raises:
            ResourceNotFoundError: Issue/discussion doesn't exist
            ValidationError: Invalid content or work_item_id
            ExternalServiceError: API communication failure
        """
        if not work_item_id:
            msg = f"Invalid work_item_id: {work_item_id}"
            raise ValidationError(msg)

        if not content or not content.strip():
            msg = "Comment content cannot be empty"
            raise ValidationError(msg)

        if len(content) > 65536:  # GitHub limit
            msg = "Comment content exceeds maximum length (65536 chars)"
            raise ValidationError(msg)

        if work_item_id.startswith("D_"):
            return await self._add_discussion_comment(work_item_id, content)

        if not work_item_id.isdigit():
            msg = (
                f"Invalid work_item_id '{work_item_id}': must be a numeric issue number or a Discussion node ID (D_...)"
            )
            raise ValidationError(msg)

        return await self._add_issue_comment(work_item_id, content)

    async def _add_issue_comment(self, work_item_id: str, content: str) -> Comment:
        """Post a comment to a GitHub issue via REST API."""
        client = await self._get_client()
        repository = self._resolve_repository(work_item_id)

        try:
            url = f"/repos/{self._config.organization}/{repository}/issues/{work_item_id}/comments"

            response = await client.post(
                url,
                json={"body": content},
            )

            if response.status_code == 401:
                msg = "GitHub authentication failed"
                raise AuthenticationError(msg)
            if response.status_code == 404:
                msg = "Issue"
                raise ResourceNotFoundError(msg, work_item_id)
            if response.status_code == 403:
                msg = "GitHub"
                raise ExternalServiceError(service=msg, message="Rate limit exceeded")
            if response.status_code >= 400:
                msg = "GitHub"
                raise ExternalServiceError(service=msg, message=f"API error: {response.status_code}")

            data = response.json()
            comment = Comment(
                id=str(data["id"]),
                author=data["user"]["login"],
                body=data["body"],
                created_at=data["created_at"],
                parent_id=None,
                is_bot=self._identity_service.is_bot_user(data["user"]["login"]),
            )

        except (httpx.RequestError, httpx.HTTPError) as e:
            raise ExternalServiceError(service="GitHub", message=f"API request failed: {e!s}")

        self._emit_comment_posted(work_item_id, comment)
        return comment

    async def _add_discussion_comment(self, discussion_id: str, content: str) -> Comment:
        """Post a comment to a GitHub Discussion via GraphQL API."""
        if self._graphql_client is None:
            raise ExternalServiceError(
                service="GitHub", message="GraphQL client required to post comments on GitHub Discussions"
            )

        mutation = """
        mutation AddDiscussionComment($discussionId: ID!, $body: String!) {
          addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
            comment {
              id
              body
              author { login }
              createdAt
            }
          }
        }
        """

        try:
            result = await self._graphql_client.execute(mutation, {"discussionId": discussion_id, "body": content})
        except ExternalServiceError as exc:
            # GitHub GraphQL returns "Could not resolve to a node" for unknown IDs.
            # Translate to the documented ResourceNotFoundError contract.
            if "could not resolve" in str(exc).lower() or "not_found" in str(exc).lower():
                raise ResourceNotFoundError("Discussion", discussion_id) from exc
            raise

        data = result["addDiscussionComment"]["comment"]
        comment = Comment(
            id=data["id"],
            author=data["author"]["login"],
            body=data["body"],
            created_at=data["createdAt"],
            parent_id=None,
            is_bot=self._identity_service.is_bot_user(data["author"]["login"]),
        )

        self._emit_comment_posted(discussion_id, comment)
        return comment

    def _emit_comment_posted(self, work_item_id: str, comment: Comment) -> None:
        """Emit a CommentPostedEvent if this work item is being monitored."""
        if work_item_id in self._monitoring:
            config = self._monitoring[work_item_id]
            self.emit(
                CommentPostedEvent(
                    type="comment.posted",
                    work_item_id=work_item_id,
                    project_id=config.project_id,
                    comment=comment,
                    timestamp=self._get_iso_timestamp(),
                    source="github",
                )
            )

    # Work-Item-Specific Monitoring

    def start_monitoring(self, work_item_id: str, config: DiscussionMonitoringConfig) -> None:
        """Start monitoring a specific work item for new comments.

        Enables change detection via webhook (if enabled) and/or polling.
        Only new comments (after this call) trigger events.

        Args:
            work_item_id: Work item to monitor
            config: Monitoring configuration

        Raises:
            ValidationError: Invalid parameters
            ResourceNotFoundError: Work item doesn't exist
        """
        if not work_item_id:
            msg = "work_item_id cannot be empty"
            raise ValidationError(msg)
        if not config.project_id:
            msg = "config.project_id cannot be empty"
            raise ValidationError(msg)

        self._monitoring[work_item_id] = config

        # Initialize last_processed (will be set on first poll/webhook)
        if config.last_processed_comment_id:
            self._last_processed[work_item_id] = config.last_processed_comment_id
        else:
            self._last_processed[work_item_id] = None

        # Start polling if webhook not enabled
        if not self._webhook_enabled:
            self._polling_tasks[work_item_id] = asyncio.create_task(self._poll_comments(work_item_id))

    def stop_monitoring(self, work_item_id: str) -> None:
        """Stop monitoring a specific work item for new comments.

        Cancels polling task if running. After this call, no events are emitted.
        Closes HTTP client if no other work items are being monitored.

        Args:
            work_item_id: Work item to stop monitoring

        Raises:
            ValidationError: Invalid work_item_id
            ResourceNotFoundError: Not currently monitoring
        """
        if not work_item_id:
            msg = "work_item_id cannot be empty"
            raise ValidationError(msg)

        if work_item_id not in self._monitoring:
            msg = "WorkItem"
            raise ResourceNotFoundError(msg, work_item_id)

        # Cancel polling task if running
        if work_item_id in self._polling_tasks:
            task = self._polling_tasks[work_item_id]
            task.cancel()
            del self._polling_tasks[work_item_id]

        # Clean up monitoring state
        del self._monitoring[work_item_id]
        self._last_processed.pop(work_item_id, None)

        # Close HTTP client if no more work items being monitored
        if not self._monitoring and self._http_client is not None:
            # Schedule close to be called from async context
            try:
                task = asyncio.create_task(self.close())

                # Attach error handler to catch any failures
                def _handle_close_error(task: asyncio.Task) -> None:
                    if task.cancelled():
                        return
                    exc = task.exception()
                    if exc is not None:
                        logger.error(
                            f"Failed to close HTTP client: {exc}",
                            exc_info=exc,
                            extra={
                                "error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR,
                                "operation": "http_client_close",
                            },
                        )

                task.add_done_callback(_handle_close_error)
            except RuntimeError as e:
                # No event loop running - HTTP client cleanup is deferred
                logger.warning(
                    f"Cannot close HTTP client without event loop, cleanup deferred: {e}",
                    exc_info=True,
                    extra={
                        "error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR,
                        "operation": "async_close_deferred",
                        "note": "AsyncClient requires async context for graceful shutdown",
                    },
                )

    # Webhook Handling

    async def handle_webhook(self, payload: dict) -> None:
        """Process GitHub issue_comment webhook event.

        Handles webhook payloads from GitHub for issue comment events.
        Filters bot comments and emits comment.needs_response events.

        Args:
            payload: GitHub webhook payload

        Raises:
            ValidationError: Invalid payload structure
        """
        # Only process created/edited actions
        action = payload.get("action")
        if action not in ["created", "edited"]:
            return

        # Extract issue and comment data
        issue = payload.get("issue")
        comment_data = payload.get("comment")

        if not issue or not comment_data:
            msg = "Invalid webhook payload: missing issue or comment"
            raise ValidationError(msg)

        work_item_id = str(issue.get("number", issue.get("id")))

        # Ignore if not monitoring this work item
        if work_item_id not in self._monitoring:
            return

        config = self._monitoring[work_item_id]
        author = comment_data["user"]["login"]

        # Skip bot comments
        if self._identity_service.is_bot_user(author):
            return

        # Build comment object
        comment = Comment(
            id=str(comment_data["id"]),
            author=author,
            body=comment_data["body"],
            created_at=comment_data["created_at"],
            parent_id=None,
            is_bot=False,
        )

        # Track last processed comment
        self._last_processed[work_item_id] = comment.id

        # Emit comment.needs_response event
        self._emit_comment_needs_response(work_item_id, config, comment)

    # Polling Implementation

    async def _poll_comments(self, work_item_id: str) -> None:
        """Poll for new comments on a work item.

        Periodically fetches the comment thread and emits events for new comments.
        Runs until the task is cancelled via stop_monitoring().

        Args:
            work_item_id: Work item to poll
        """
        interval = self._config.polling_interval_seconds

        while True:
            try:
                await asyncio.sleep(interval)

                # Get current thread
                try:
                    thread = await self.get_thread(work_item_id)
                except Exception as e:
                    logger.warning(
                        f"Polling error for {work_item_id}: {e}",
                        exc_info=True,
                    )
                    continue

                # Find new comments since last poll
                new_comments = self._filter_new_comments(thread.comments, self._last_processed.get(work_item_id))

                # Process each new comment
                config = self._monitoring.get(work_item_id)
                if config:
                    for comment in new_comments:
                        # Only emit for human comments
                        if not comment.is_bot:
                            self._emit_comment_needs_response(work_item_id, config, comment)

                        # Update last processed
                        self._last_processed[work_item_id] = comment.id

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"Unexpected error in polling loop for {work_item_id}: {e}",
                    exc_info=True,
                    extra={"error_id": "ERR_DISCUSSION_ERROR", "work_item_id": work_item_id},
                )
                continue

    def _filter_new_comments(self, comments: list[Comment], last_id: str | None) -> list[Comment]:
        """Filter comments to only new ones.

        Returns all comments after the last_id, or all comments if last_id is None.

        Args:
            comments: All comments in thread
            last_id: Last comment ID already processed

        Returns:
            List[Comment]: New comments only
        """
        if not last_id:
            return comments

        new_comments = []
        found_last = False

        for comment in comments:
            if found_last:
                new_comments.append(comment)
            elif comment.id == last_id:
                found_last = True

        return new_comments

    def _emit_comment_needs_response(
        self,
        work_item_id: str,
        config: DiscussionMonitoringConfig,
        comment: Comment,
    ) -> None:
        """Emit comment.needs_response event for a human comment.

        Args:
            work_item_id: ID of the work item
            config: Monitoring configuration for context
            comment: The comment requiring response
        """
        # GitHub issues use flat comment structure (no threading)
        # Determine if this is the initial comment
        is_initial = self._is_initial_comment(work_item_id, comment)

        if is_initial:
            context = CommentContext.for_initial_request()
        else:
            context = CommentContext(
                thread_id=f"thread-{work_item_id}",
                parent_comment=None,
                is_initial_request=False,
            )

        self.emit(
            CommentNeedsResponseEvent(
                type="comment.needs_response",
                work_item_id=work_item_id,
                project_id=config.project_id,
                comment=comment,
                context=context,
                timestamp=self._get_iso_timestamp(),
                source="github",
            )
        )

    def _is_initial_comment(self, work_item_id: str, comment: Comment) -> bool:
        """Determine if comment is the initial request on the work item.

        A comment is initial if it's the first human comment we've seen
        for this work item (indicating the original issue description).

        Args:
            work_item_id: ID of the work item
            comment: The comment to check

        Returns:
            bool: True if this appears to be the initial request
        """
        # If we have no last_processed, this is likely the initial comment
        return self._last_processed.get(work_item_id) is None

    # IEventEmitter Implementation

    def on(self, event_type: str, handler: Callable[[object], None]) -> None:
        """Subscribe to events of a specific type.

        Args:
            event_type: Event type to subscribe to
            handler: Callback function for events

        Raises:
            ValueError: Invalid parameters
        """
        if not event_type:
            msg = "event_type cannot be empty"
            raise ValueError(msg)
        if not callable(handler):
            msg = "handler must be callable"
            raise ValueError(msg)

        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []

        self._event_handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Callable[[object], None]) -> None:
        """Unsubscribe from events.

        Args:
            event_type: Event type to unsubscribe from
            handler: Handler to remove

        Raises:
            ValueError: Handler not registered
        """
        if event_type not in self._event_handlers or handler not in self._event_handlers[event_type]:
            msg = f"Handler not subscribed to event type: {event_type}"
            raise ValueError(msg)

        self._event_handlers[event_type].remove(handler)

    def emit(self, event: object) -> None:
        """Emit an event to all subscribers.

        Handler failures are logged at ERROR level with full stack traces but do not
        prevent other handlers from executing. This allows event processing to continue
        while ensuring failures are visible in logs for monitoring and debugging.

        Args:
            event: Event to emit

        Raises:
            ValueError: Invalid event type
            asyncio.CancelledError: If cancellation is requested (never suppressed)
        """
        event_type = getattr(event, "type", None)
        if event_type is None:
            msg = "event must have a 'type' attribute"
            raise ValueError(msg)
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
                        "error_id": ErrorRegistry.ERR_VALIDATION_FAILED,
                    },
                )
                failures.append((handler_name, str(e)))
            except Exception as e:
                # Unexpected runtime errors from handlers
                logger.error(
                    f"Handler {handler_name} execution error for {event_type}: {e}",
                    exc_info=True,
                    extra={
                        "error_id": ErrorRegistry.ERR_HANDLER_EXECUTION,
                        "event_type": event_type,
                        "event_id": getattr(event, "event_id", None),
                        "handler": handler_name,
                    },
                )
                failures.append((handler_name, str(e)))

        # Log summary if any handlers failed
        if failures:
            logger.error(
                f"Event emission for {event_type} completed with {len(failures)} handler failure(s)",
                extra={
                    "error_id": ErrorRegistry.ERR_HANDLER_EXECUTION,
                    "event_type": event_type,
                    "event_id": getattr(event, "event_id", None),
                    "failure_count": len(failures),
                },
            )

    # Utility Methods

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current time as ISO 8601 timestamp."""
        return datetime.now(UTC).isoformat()
