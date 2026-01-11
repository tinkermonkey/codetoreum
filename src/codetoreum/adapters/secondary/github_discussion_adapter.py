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
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass

import httpx

from codetoreum.domain.events.discussion_events import (
    Comment,
    CommentContext,
    CommentNeedsResponseEvent,
    CommentPostedEvent,
)
from codetoreum.ports.exceptions import (
    AuthenticationError,
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
from codetoreum.infrastructure.http.github_graphql_client import GitHubGraphQLClient


@dataclass
class GitHubDiscussionConfig:
    """Configuration for GitHub Discussion adapter.

    Attributes:
        token: GitHub personal access token or GitHub App token
        organization: GitHub organization name
        repository: GitHub repository name
        api_base_url: Base URL for GitHub REST API
        graphql_client: Optional pre-configured GraphQL client
        webhook_enabled: Whether to use webhook-based detection
        polling_interval_seconds: Interval for polling fallback (default 30)
        api_version: GitHub API version header
        timeout_seconds: HTTP request timeout
    """

    token: str
    organization: str
    repository: str
    api_base_url: str = "https://api.github.com"
    graphql_client: Optional[GitHubGraphQLClient] = None
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
            project_id="proj-1",
            column_name="Review",
            agent_assignment="agent-1"
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
    ):
        """Initialize GitHub discussion adapter.

        Args:
            config: GitHub configuration
            identity_service: Service for bot identification

        Raises:
            ValidationError: If configuration is invalid
        """
        self._config = config
        self._identity_service = identity_service
        self._http_client: Optional[httpx.AsyncClient] = None
        self._graphql_client = config.graphql_client
        self._webhook_enabled = config.webhook_enabled

        # Event emitter state
        self._event_handlers: Dict[str, List[Callable]] = {}

        # Monitoring state: work_item_id -> config
        self._monitoring: Dict[str, DiscussionMonitoringConfig] = {}

        # Polling state: work_item_id -> last_comment_id
        self._last_processed: Dict[str, Optional[str]] = {}

        # Polling tasks: work_item_id -> asyncio.Task
        self._polling_tasks: Dict[str, asyncio.Task] = {}

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

    # Query Operations

    async def get_thread(self, work_item_id: str) -> DiscussionThread:
        """Retrieve full discussion thread for a work item.

        Fetches all comments on the GitHub issue using REST API pagination.

        Args:
            work_item_id: GitHub issue number (as string)

        Returns:
            DiscussionThread: Complete thread with all comments

        Raises:
            ResourceNotFoundError: Issue doesn't exist
            ExternalServiceError: API communication failure
            ValidationError: Invalid work_item_id
        """
        if not work_item_id or not work_item_id.isdigit():
            raise ValidationError(f"Invalid work_item_id: {work_item_id}")

        client = await self._get_client()
        comments = []
        page = 1
        per_page = 100

        try:
            while True:
                # Fetch page of comments
                url = (
                    f"/repos/{self._config.organization}/{self._config.repository}"
                    f"/issues/{work_item_id}/comments"
                )

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
                    raise AuthenticationError("GitHub authentication failed")
                if response.status_code == 404:
                    raise ResourceNotFoundError(f"Issue not found: {work_item_id}")
                if response.status_code == 403:
                    raise ExternalServiceError("GitHub rate limit exceeded")
                if response.status_code >= 400:
                    raise ExternalServiceError(
                        f"GitHub API error: {response.status_code}"
                    )

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
            raise ExternalServiceError(f"GitHub API request failed: {str(e)}")

    # Command Operations

    async def add_comment(
        self,
        work_item_id: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> Comment:
        """Post a comment to a work item (GitHub issue).

        Adds a comment to the issue's discussion thread via REST API.
        Parent_id is ignored for GitHub issues (flat thread model).

        Args:
            work_item_id: GitHub issue number
            content: Comment text
            parent_id: Ignored for GitHub issues (unsupported)

        Returns:
            Comment: Newly posted comment with server-assigned ID

        Raises:
            ResourceNotFoundError: Issue doesn't exist
            ValidationError: Invalid content or work_item_id
            ExternalServiceError: API communication failure
        """
        if not work_item_id or not work_item_id.isdigit():
            raise ValidationError(f"Invalid work_item_id: {work_item_id}")

        if not content or not content.strip():
            raise ValidationError("Comment content cannot be empty")

        if len(content) > 65536:  # GitHub limit
            raise ValidationError("Comment content exceeds maximum length (65536 chars)")

        client = await self._get_client()

        try:
            url = (
                f"/repos/{self._config.organization}/{self._config.repository}"
                f"/issues/{work_item_id}/comments"
            )

            response = await client.post(
                url,
                json={"body": content},
            )

            if response.status_code == 401:
                raise AuthenticationError("GitHub authentication failed")
            if response.status_code == 404:
                raise ResourceNotFoundError(f"Issue not found: {work_item_id}")
            if response.status_code == 403:
                raise ExternalServiceError("GitHub rate limit exceeded")
            if response.status_code >= 400:
                raise ExternalServiceError(
                    f"GitHub API error: {response.status_code}"
                )

            data = response.json()
            comment = Comment(
                id=str(data["id"]),
                author=data["user"]["login"],
                body=data["body"],
                created_at=data["created_at"],
                parent_id=None,
                is_bot=self._identity_service.is_bot_user(data["user"]["login"]),
            )

            # Emit comment.posted event if monitoring
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

            return comment

        except (httpx.RequestError, httpx.HTTPError) as e:
            raise ExternalServiceError(f"GitHub API request failed: {str(e)}")

    # Work-Item-Specific Monitoring

    def start_monitoring(
        self, work_item_id: str, config: DiscussionMonitoringConfig
    ) -> None:
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
            raise ValidationError("work_item_id cannot be empty")
        if not config.project_id:
            raise ValidationError("config.project_id cannot be empty")

        self._monitoring[work_item_id] = config

        # Initialize last_processed (will be set on first poll/webhook)
        if config.last_processed_comment_id:
            self._last_processed[work_item_id] = config.last_processed_comment_id
        else:
            self._last_processed[work_item_id] = None

        # Start polling if webhook not enabled
        if not self._webhook_enabled:
            self._polling_tasks[work_item_id] = asyncio.create_task(
                self._poll_comments(work_item_id)
            )

    def stop_monitoring(self, work_item_id: str) -> None:
        """Stop monitoring a specific work item for new comments.

        Cancels polling task if running. After this call, no events are emitted.

        Args:
            work_item_id: Work item to stop monitoring

        Raises:
            ValidationError: Invalid work_item_id
            ResourceNotFoundError: Not currently monitoring
        """
        if not work_item_id:
            raise ValidationError("work_item_id cannot be empty")

        if work_item_id not in self._monitoring:
            raise ResourceNotFoundError(f"Not monitoring work item: {work_item_id}")

        # Cancel polling task if running
        if work_item_id in self._polling_tasks:
            task = self._polling_tasks[work_item_id]
            task.cancel()
            del self._polling_tasks[work_item_id]

        # Clean up monitoring state
        del self._monitoring[work_item_id]
        self._last_processed.pop(work_item_id, None)

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
            raise ValidationError("Invalid webhook payload: missing issue or comment")

        work_item_id = str(issue["number"])

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
                except Exception:
                    # Log error but continue polling
                    continue

                # Find new comments since last poll
                new_comments = self._filter_new_comments(
                    thread.comments, self._last_processed.get(work_item_id)
                )

                # Process each new comment
                config = self._monitoring.get(work_item_id)
                if config:
                    for comment in new_comments:
                        # Only emit for human comments
                        if not comment.is_bot:
                            self._emit_comment_needs_response(
                                work_item_id, config, comment
                            )

                        # Update last processed
                        self._last_processed[work_item_id] = comment.id

            except asyncio.CancelledError:
                break
            except Exception:
                # Log error but continue polling
                continue

    def _filter_new_comments(
        self, comments: List[Comment], last_id: Optional[str]
    ) -> List[Comment]:
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
        context = CommentContext(
            thread_id=f"thread-{work_item_id}",
            parent_comment=None,  # GitHub issues are flat
            is_initial_request=self._is_initial_comment(work_item_id, comment),
            column_name=config.column_name,
            agent_assignment=config.agent_assignment,
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

    def on(
        self, event_type: str, handler: Callable[[object], None]
    ) -> None:
        """Subscribe to events of a specific type.

        Args:
            event_type: Event type to subscribe to
            handler: Callback function for events

        Raises:
            ValueError: Invalid parameters
        """
        if not event_type:
            raise ValueError("event_type cannot be empty")
        if not callable(handler):
            raise ValueError("handler must be callable")

        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []

        self._event_handlers[event_type].append(handler)

    def off(
        self, event_type: str, handler: Callable[[object], None]
    ) -> None:
        """Unsubscribe from events.

        Args:
            event_type: Event type to unsubscribe from
            handler: Handler to remove

        Raises:
            ValueError: Handler not registered
        """
        if event_type not in self._event_handlers or handler not in self._event_handlers[event_type]:
            raise ValueError(f"Handler not subscribed to event type: {event_type}")

        self._event_handlers[event_type].remove(handler)

    def emit(self, event: object) -> None:
        """Emit an event to all subscribers.

        Args:
            event: Event to emit

        Raises:
            ValueError: Invalid event type
        """
        if not hasattr(event, "type"):
            raise ValueError("event must have a 'type' attribute")

        event_type = event.type  # type: ignore
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                handler(event)

    # Utility Methods

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current time as ISO 8601 timestamp."""
        return datetime.now(timezone.utc).isoformat()
