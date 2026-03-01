"""GitHub Issues adapter for ITicketSystem interface."""

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from dateutil import parser as dateparser

from codetoreum.domain.comment import Comment
from codetoreum.domain.types import CommentId, ProjectId, UserId, WorkItemId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
    WorkItemNotFoundError,
)
from codetoreum.ports.output.ticket_system import ITicketSystem


@dataclass
class GitHubConfig:
    """Configuration for GitHub Issues adapter."""

    # Authentication
    token: str  # Personal Access Token or GitHub App token

    # Repository
    organization: str
    repository: str

    # API configuration
    api_base_url: str = "https://api.github.com"
    api_version: str = "2022-11-28"
    timeout_seconds: int = 30

    # Caching
    cache_ttl_seconds: int = 300  # 5 minutes
    cache_max_entries: int = 1000  # Maximum cache entries before eviction


class GitHubTicketAdapter(ITicketSystem):
    """
    GitHub Issues adapter for ticket system operations.

    This adapter implements the ITicketSystem interface using GitHub's REST API.
    It handles authentication, rate limiting, pagination, and error mapping.
    """

    def __init__(self, config: GitHubConfig):
        """
        Initialize GitHub adapter.

        Args:
            config: GitHub configuration
        """
        self.config = config
        self._http_client: httpx.AsyncClient | None = None

        # In-memory cache with eviction support
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._cache_access_times: dict[str, datetime] = {}  # Track LRU

        # Rate limit tracking
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: datetime | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            headers = {
                "Authorization": f"Bearer {self.config.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": self.config.api_version,
            }

            self._http_client = httpx.AsyncClient(
                base_url=self.config.api_base_url,
                headers=headers,
                timeout=self.config.timeout_seconds,
            )

        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def _evict_cache_if_needed(self) -> None:
        """Evict oldest cache entries if cache is full."""
        if len(self._cache) >= self.config.cache_max_entries:
            # Evict 10% of oldest entries (LRU)
            evict_count = max(1, self.config.cache_max_entries // 10)

            # Sort by access time and remove oldest
            sorted_keys = sorted(self._cache_access_times.keys(), key=lambda k: self._cache_access_times[k])

            for key in sorted_keys[:evict_count]:
                self._cache.pop(key, None)
                self._cache_access_times.pop(key, None)

    def _check_cache(self, key: str) -> Any | None:
        """Check cache for value."""
        if key not in self._cache:
            return None

        cached_at, value = self._cache[key]
        age_seconds = (datetime.now(UTC) - cached_at).total_seconds()

        if age_seconds > self.config.cache_ttl_seconds:
            del self._cache[key]
            self._cache_access_times.pop(key, None)
            return None

        # Update access time for LRU
        self._cache_access_times[key] = datetime.now(UTC)
        return value

    def _set_cache(self, key: str, value: Any) -> None:
        """Set cache value with eviction if needed."""
        self._evict_cache_if_needed()
        self._cache[key] = (datetime.now(UTC), value)
        self._cache_access_times[key] = datetime.now(UTC)

    def _invalidate_cache(self, key: str) -> None:
        """Invalidate cache entry."""
        self._cache.pop(key, None)
        self._cache_access_times.pop(key, None)

    def _sanitize_error_message(self, error: str) -> str:
        """
        Sanitize error messages to remove sensitive information.

        Args:
            error: Raw error message

        Returns:
            Sanitized error message
        """
        # Remove tokens
        sanitized = re.sub(r"ghp_[a-zA-Z0-9]{36}", "[REDACTED_TOKEN]", error)
        sanitized = re.sub(r"ghs_[a-zA-Z0-9]{36}", "[REDACTED_TOKEN]", sanitized)

        # Truncate to reasonable length
        if len(sanitized) > 500:
            sanitized = sanitized[:500] + "... [truncated]"

        return sanitized

    def _update_rate_limits(self, response: httpx.Response) -> None:
        """
        Update rate limit tracking from response headers.

        Args:
            response: HTTP response with rate limit headers
        """
        # Parse GitHub rate limit headers
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")

        if remaining:
            self._rate_limit_remaining = int(remaining)

        if reset:
            self._rate_limit_reset = datetime.fromtimestamp(int(reset), tz=UTC)

    async def _make_request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        """
        Make HTTP request.

        Args:
            method: HTTP method
            path: API path
            **kwargs: Additional request parameters

        Returns:
            HTTP response

        Raises:
            AuthenticationError: Invalid credentials
            ExternalServiceError: GitHub API error

        Note:
            Retry logic, rate limiting, and timeout handling are managed by
            the infrastructure layer via resilience decorators (ResilientTicketSystemDecorator).
            This method remains pure and does not embed resilience patterns.
        """
        client = await self._get_client()

        try:
            response = await client.request(method, path, **kwargs)

            # Update rate limit tracking from headers
            self._update_rate_limits(response)

            # Handle authentication errors
            if response.status_code == 401:
                msg = "Invalid GitHub token"
                raise AuthenticationError(msg)

            # Handle rate limiting (don't retry, let infrastructure handle it)
            if response.status_code == 403:
                if "rate limit" in response.text.lower():
                    msg = "GitHub"
                    raise ExternalServiceError(msg, "Rate limit exceeded")

            return response

        except httpx.TimeoutException as e:
            msg = "GitHub"
            raise ExternalServiceError(msg, "Request timeout") from e
        except httpx.RequestError as e:
            sanitized_error = self._sanitize_error_message(str(e))
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Request failed: {sanitized_error}") from e

    def _map_github_issue_to_work_item(self, issue: dict[str, Any], project_id: str) -> WorkItem:
        """
        Map GitHub issue to WorkItem domain model.

        Args:
            issue: GitHub issue data
            project_id: Project identifier

        Returns:
            WorkItem domain object
        """
        # Map GitHub state to WorkItemStatus
        state = issue.get("state", "open")
        if state == "closed":
            status = WorkItemStatus.COMPLETED
        else:
            # Check labels for more specific status
            labels = [label["name"] for label in issue.get("labels", [])]
            if "blocked" in labels:
                status = WorkItemStatus.BLOCKED
            elif "in-progress" in labels:
                status = WorkItemStatus.IN_PROGRESS
            elif "review" in labels:
                status = WorkItemStatus.UNDER_REVIEW
            else:
                status = WorkItemStatus.NEW

        # Map priority from labels
        priority = WorkItemPriority.MEDIUM  # default
        labels = [label["name"].lower() for label in issue.get("labels", [])]
        if "critical" in labels or "p0" in labels:
            priority = WorkItemPriority.CRITICAL
        elif "high" in labels or "p1" in labels:
            priority = WorkItemPriority.HIGH
        elif "low" in labels or "p3" in labels:
            priority = WorkItemPriority.LOW

        # Extract assigned agent from labels
        assigned_agent_id = None
        for label in [label["name"] for label in issue.get("labels", [])]:
            if label.startswith("agent:"):
                assigned_agent_id = label.split(":", 1)[1]
                break

        # Parse dates using proper date parser
        created_at = dateparser.isoparse(issue["created_at"])
        updated_at = dateparser.isoparse(issue["updated_at"])
        completed_at = dateparser.isoparse(issue["closed_at"]) if issue.get("closed_at") else None

        return WorkItem(
            id=WorkItemId(str(issue["number"])),
            project_id=project_id,
            title=issue["title"],
            description=issue.get("body") or "",
            status=status,
            priority=priority,
            labels=[label["name"] for label in issue.get("labels", [])],
            external_id=str(issue["number"]),
            external_url=issue["html_url"],
            assigned_agent_id=assigned_agent_id,
            assigned_at=None,  # GitHub doesn't track this separately
            current_workflow_id=None,
            current_stage=None,
            created_at=created_at,
            updated_at=updated_at,
            completed_at=completed_at,
        )

    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        """Get work item by ID."""
        cache_key = f"issue:{item_id}"
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        path = f"/repos/{self.config.organization}/{self.config.repository}/issues/{item_id}"
        response = await self._make_request("GET", path)

        if response.status_code == 404:
            msg = f"Work item {item_id} not found"
            raise WorkItemNotFoundError(msg)
        if response.status_code != 200:
            sanitized_error = self._sanitize_error_message(response.text)
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Unexpected status {response.status_code}: {sanitized_error}")

        issue = response.json()
        # Extract project_id from repository
        project_id = ProjectId(f"{self.config.organization}/{self.config.repository}")
        work_item = self._map_github_issue_to_work_item(issue, project_id)

        self._set_cache(cache_key, work_item)
        return work_item

    async def create_work_item(
        self,
        title: str,
        description: str,
        project_id: ProjectId,
        labels: list[str] | None = None,
        assignee: UserId | None = None,
        priority: WorkItemPriority | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkItem:
        """Create a new work item."""
        if not title:
            msg = "Title is required"
            raise ValidationError(msg)

        # Build request payload
        payload: dict[str, Any] = {
            "title": title,
            "body": description,
        }

        if labels:
            # Add priority label if specified
            issue_labels = list(labels)
            if priority:
                if priority == WorkItemPriority.CRITICAL:
                    issue_labels.append("critical")
                elif priority == WorkItemPriority.HIGH:
                    issue_labels.append("high")
                elif priority == WorkItemPriority.LOW:
                    issue_labels.append("low")
            payload["labels"] = issue_labels

        if assignee:
            payload["assignees"] = [assignee]

        path = f"/repos/{self.config.organization}/{self.config.repository}/issues"
        response = await self._make_request("POST", path, json=payload)

        if response.status_code != 201:
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Failed to create issue: {response.text}")

        issue = response.json()
        return self._map_github_issue_to_work_item(issue, project_id)

    async def update_work_item(self, item_id: WorkItemId, updates: dict[str, Any]) -> WorkItem:
        """Update an existing work item."""
        payload: dict[str, Any] = {}

        # Map domain updates to GitHub API format
        if "title" in updates:
            payload["title"] = updates["title"]

        if "description" in updates:
            payload["body"] = updates["description"]

        if "status" in updates:
            status = updates["status"]
            if isinstance(status, WorkItemStatus):
                if status == WorkItemStatus.COMPLETED:
                    payload["state"] = "closed"
                else:
                    payload["state"] = "open"

        if "labels" in updates:
            payload["labels"] = updates["labels"]

        path = f"/repos/{self.config.organization}/{self.config.repository}/issues/{item_id}"
        response = await self._make_request("PATCH", path, json=payload)

        if response.status_code == 404:
            msg = f"Work item {item_id} not found"
            raise WorkItemNotFoundError(msg)
        if response.status_code != 200:
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Failed to update issue: {response.text}")

        # Invalidate cache
        self._invalidate_cache(f"issue:{item_id}")

        issue = response.json()
        project_id = ProjectId(f"{self.config.organization}/{self.config.repository}")
        return self._map_github_issue_to_work_item(issue, project_id)

    async def delete_work_item(self, item_id: WorkItemId) -> None:
        """
        Delete a work item.

        **Implementation Limitation**:
        GitHub's REST API does not support deleting issues. This is a platform limitation,
        not an adapter limitation. As a workaround, this method closes the issue by setting
        its status to COMPLETED.

        If true deletion is required, you must use the GitHub web interface with appropriate
        repository permissions.

        Args:
            item_id: ID of the work item to delete (close)

        Raises:
            WorkItemNotFoundError: Work item not found
        """
        await self.update_work_item(item_id, {"status": WorkItemStatus.COMPLETED})
        self._invalidate_cache(f"issue:{item_id}")

    async def update_status(
        self,
        item_id: WorkItemId,
        status: WorkItemStatus,
        reason: str | None = None,
    ) -> WorkItem:
        """Update work item status."""
        updates = {"status": status}
        work_item = await self.update_work_item(item_id, updates)

        # Add comment with reason if provided
        if reason:
            await self.add_comment(
                item_id,
                f"Status updated to {status.value}: {reason}",
            )

        return work_item

    async def list_work_items(
        self,
        project_id: ProjectId | None = None,
        status: WorkItemStatus | None = None,
        assignee: UserId | None = None,
        labels: list[str] | None = None,
        created_after: datetime | None = None,
        updated_after: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkItem]:
        """List work items with filters."""
        # Build query parameters
        params: dict[str, Any] = {
            "per_page": min(limit, 100),
            "page": (offset // 100) + 1,
        }

        if status:
            if status == WorkItemStatus.COMPLETED:
                params["state"] = "closed"
            else:
                params["state"] = "open"
        else:
            params["state"] = "all"

        if assignee:
            params["assignee"] = assignee

        if labels:
            params["labels"] = ",".join(labels)

        if created_after:
            params["since"] = created_after.isoformat()

        path = f"/repos/{self.config.organization}/{self.config.repository}/issues"
        response = await self._make_request("GET", path, params=params)

        if response.status_code != 200:
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Failed to list issues: {response.text}")

        issues = response.json()
        proj_id = ProjectId(f"{self.config.organization}/{self.config.repository}")

        work_items = []
        for issue in issues:
            # Skip pull requests (they appear in issues endpoint)
            if "pull_request" in issue:
                continue

            work_item = self._map_github_issue_to_work_item(issue, proj_id)

            # Apply updated_after filter (not supported by GitHub API)
            if updated_after and work_item.updated_at < updated_after:
                continue

            work_items.append(work_item)

        return work_items[:limit]

    async def search_work_items(
        self,
        query: str,
        project_id: ProjectId | None = None,
        limit: int = 100,
    ) -> list[WorkItem]:
        """Full-text search for work items."""
        # Build search query
        search_query = f"{query} repo:{self.config.organization}/{self.config.repository} is:issue"

        params = {
            "q": search_query,
            "per_page": min(limit, 100),
        }

        response = await self._make_request("GET", "/search/issues", params=params)

        if response.status_code != 200:
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Search failed: {response.text}")

        result = response.json()
        issues = result.get("items", [])

        proj_id = ProjectId(f"{self.config.organization}/{self.config.repository}")
        return [self._map_github_issue_to_work_item(issue, proj_id) for issue in issues]

    async def get_work_item_stream(
        self,
        project_id: ProjectId | None = None,
        since: datetime | None = None,
    ) -> AsyncIterator[WorkItem]:
        """
        Stream work item updates.

        Note: GitHub doesn't support real-time streaming.
        This implementation polls for updates.
        """
        last_check = since or datetime.now(UTC)

        while True:
            items = await self.list_work_items(
                project_id=project_id,
                updated_after=last_check,
                limit=100,
            )

            for item in items:
                yield item

            if items:
                last_check = max(item.updated_at for item in items)

            # Poll every 30 seconds
            await asyncio.sleep(30)

    async def add_comment(
        self,
        item_id: WorkItemId,
        body: str,
        author: UserId | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Comment:
        """Add a comment to a work item."""
        if not body:
            msg = "Comment body is required"
            raise ValidationError(msg)

        payload = {"body": body}

        path = f"/repos/{self.config.organization}/{self.config.repository}/issues/{item_id}/comments"
        response = await self._make_request("POST", path, json=payload)

        if response.status_code == 404:
            msg = f"Work item {item_id} not found"
            raise WorkItemNotFoundError(msg)
        if response.status_code != 201:
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Failed to create comment: {response.text}")

        comment_data = response.json()

        # Parse dates using proper date parser
        created_at = dateparser.isoparse(comment_data["created_at"])
        updated_at = dateparser.isoparse(comment_data["updated_at"]) if comment_data.get("updated_at") else None

        return Comment(
            id=CommentId(str(comment_data["id"])),
            work_item_id=item_id,
            author_id=UserId(comment_data["user"]["login"]),
            body=comment_data["body"],
            created_at=created_at,
            updated_at=updated_at,
        )

    async def get_comments(
        self,
        item_id: WorkItemId,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Comment]:
        """Get comments for a work item."""
        params: dict[str, Any] = {
            "per_page": min(limit, 100),
        }

        if since:
            params["since"] = since.isoformat()

        path = f"/repos/{self.config.organization}/{self.config.repository}/issues/{item_id}/comments"
        response = await self._make_request("GET", path, params=params)

        if response.status_code == 404:
            msg = f"Work item {item_id} not found"
            raise WorkItemNotFoundError(msg)
        if response.status_code != 200:
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Failed to get comments: {response.text}")

        comments_data = response.json()

        comments = []
        for comment in comments_data:
            # Parse dates using proper date parser
            created_at = dateparser.isoparse(comment["created_at"])
            updated_at = dateparser.isoparse(comment["updated_at"]) if comment.get("updated_at") else None

            comments.append(
                Comment(
                    id=CommentId(str(comment["id"])),
                    work_item_id=item_id,
                    author_id=UserId(comment["user"]["login"]),
                    body=comment["body"],
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )

        return comments

    async def link_work_items(
        self,
        source_id: WorkItemId,
        target_id: WorkItemId,
        relationship: str,
    ) -> None:
        """
        Create relationship between work items.

        GitHub doesn't have native relationships, so we add a comment.
        """
        body = f"This issue {relationship} #{target_id}"
        await self.add_comment(source_id, body)

    async def get_related_items(
        self,
        item_id: WorkItemId,
        relationship: str | None = None,
    ) -> list[WorkItem]:
        """
        Get related work items.

        This searches for issue references in comments and description.
        """
        # Get the work item
        work_item = await self.get_work_item(item_id)

        # Extract issue numbers from description and comments
        issue_pattern = r"#(\d+)"

        referenced_ids = set()

        # Search in description
        for match in re.finditer(issue_pattern, work_item.description):
            referenced_ids.add(WorkItemId(match.group(1)))

        # Search in comments
        comments = await self.get_comments(item_id)
        for comment in comments:
            for match in re.finditer(issue_pattern, comment.body):
                referenced_ids.add(WorkItemId(match.group(1)))

        # Fetch referenced work items
        related_items = []
        for ref_id in referenced_ids:
            try:
                item = await self.get_work_item(ref_id)
                related_items.append(item)
            except WorkItemNotFoundError:
                # Skip invalid references
                continue

        return related_items

    async def register_webhook(
        self,
        url: str,
        events: list[str],
        project_id: ProjectId | None = None,
    ) -> str:
        """Register a webhook for events."""
        if not url:
            msg = "Webhook URL is required"
            raise ValidationError(msg)

        payload = {
            "config": {
                "url": url,
                "content_type": "json",
            },
            "events": events,
            "active": True,
        }

        path = f"/repos/{self.config.organization}/{self.config.repository}/hooks"
        response = await self._make_request("POST", path, json=payload)

        if response.status_code != 201:
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Failed to create webhook: {response.text}")

        webhook_data = response.json()
        return str(webhook_data["id"])

    async def unregister_webhook(self, webhook_id: str) -> None:
        """Unregister a webhook."""
        path = f"/repos/{self.config.organization}/{self.config.repository}/hooks/{webhook_id}"
        response = await self._make_request("DELETE", path)

        if response.status_code == 404:
            msg = "Webhook"
            raise ResourceNotFoundError(msg, webhook_id)
        if response.status_code != 204:
            msg = "GitHub"
            raise ExternalServiceError(msg, f"Failed to delete webhook: {response.text}")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit with proper cleanup.

        Ensures cleanup happens even if exceptions occur.
        """
        try:
            await self.close()
        except Exception:
            # Suppress cleanup errors to avoid masking original exception
            pass
        return False  # Don't suppress exceptions
