"""GitHub Issues adapter for ITicketSystem interface."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from codetoreum.domain.comment import Comment
from codetoreum.domain.types import ProjectId, UserId, WorkItemId, CommentId
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
from codetoreum.ports.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    ProjectNotFoundError,
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

    # Rate limiting and retry
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    timeout_seconds: int = 30

    # Caching
    cache_ttl_seconds: int = 300  # 5 minutes


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
        self._http_client: Optional[httpx.AsyncClient] = None

        # Simple in-memory cache
        self._cache: Dict[str, tuple[datetime, Any]] = {}

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

    def _check_cache(self, key: str) -> Optional[Any]:
        """Check cache for value."""
        if key not in self._cache:
            return None

        cached_at, value = self._cache[key]
        age_seconds = (datetime.now(timezone.utc) - cached_at).total_seconds()

        if age_seconds > self.config.cache_ttl_seconds:
            del self._cache[key]
            return None

        return value

    def _set_cache(self, key: str, value: Any) -> None:
        """Set cache value."""
        self._cache[key] = (datetime.now(timezone.utc), value)

    def _invalidate_cache(self, key: str) -> None:
        """Invalidate cache entry."""
        self._cache.pop(key, None)

    async def _make_request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method
            path: API path
            **kwargs: Additional request parameters

        Returns:
            HTTP response

        Raises:
            AuthenticationError: Invalid credentials
            ExternalServiceError: GitHub API error
        """
        client = await self._get_client()

        for attempt in range(self.config.max_retries):
            try:
                response = await client.request(method, path, **kwargs)

                # Handle authentication errors
                if response.status_code == 401:
                    raise AuthenticationError("Invalid GitHub token")

                # Handle rate limiting
                if response.status_code == 403:
                    if "rate limit" in response.text.lower():
                        # Wait and retry
                        if attempt < self.config.max_retries - 1:
                            await asyncio.sleep(self.config.retry_delay_seconds * (2 ** attempt))
                            continue
                        raise ExternalServiceError("GitHub", "Rate limit exceeded")

                return response

            except httpx.TimeoutException:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay_seconds * (2 ** attempt))
                    continue
                raise ExternalServiceError("GitHub", "Request timeout")
            except httpx.RequestError as e:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay_seconds * (2 ** attempt))
                    continue
                raise ExternalServiceError("GitHub", f"Request failed: {str(e)}")

        raise ExternalServiceError("GitHub", "Max retries exceeded")

    def _map_github_issue_to_work_item(self, issue: Dict[str, Any], project_id: str) -> WorkItem:
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
            created_at=datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(issue["updated_at"].replace("Z", "+00:00")),
            completed_at=datetime.fromisoformat(issue["closed_at"].replace("Z", "+00:00")) if issue.get("closed_at") else None,
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
            raise WorkItemNotFoundError(f"Work item {item_id} not found")
        elif response.status_code != 200:
            raise ExternalServiceError("GitHub", f"Unexpected status {response.status_code}: {response.text}")

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
        labels: Optional[List[str]] = None,
        assignee: Optional[UserId] = None,
        priority: Optional[WorkItemPriority] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkItem:
        """Create a new work item."""
        if not title:
            raise ValidationError("Title is required")

        # Build request payload
        payload: Dict[str, Any] = {
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
            raise ExternalServiceError("GitHub", f"Failed to create issue: {response.text}")

        issue = response.json()
        return self._map_github_issue_to_work_item(issue, project_id)

    async def update_work_item(
        self, item_id: WorkItemId, updates: Dict[str, Any]
    ) -> WorkItem:
        """Update an existing work item."""
        payload: Dict[str, Any] = {}

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
            raise WorkItemNotFoundError(f"Work item {item_id} not found")
        elif response.status_code != 200:
            raise ExternalServiceError("GitHub", f"Failed to update issue: {response.text}")

        # Invalidate cache
        self._invalidate_cache(f"issue:{item_id}")

        issue = response.json()
        project_id = ProjectId(f"{self.config.organization}/{self.config.repository}")
        return self._map_github_issue_to_work_item(issue, project_id)

    async def delete_work_item(self, item_id: WorkItemId) -> None:
        """
        Delete a work item.

        Note: GitHub doesn't support deleting issues via API.
        This method closes the issue instead.
        """
        await self.update_work_item(item_id, {"status": WorkItemStatus.COMPLETED})
        self._invalidate_cache(f"issue:{item_id}")

    async def update_status(
        self,
        item_id: WorkItemId,
        status: WorkItemStatus,
        reason: Optional[str] = None,
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
        project_id: Optional[ProjectId] = None,
        status: Optional[WorkItemStatus] = None,
        assignee: Optional[UserId] = None,
        labels: Optional[List[str]] = None,
        created_after: Optional[datetime] = None,
        updated_after: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[WorkItem]:
        """List work items with filters."""
        # Build query parameters
        params: Dict[str, Any] = {
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
            raise ExternalServiceError("GitHub", f"Failed to list issues: {response.text}")

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
        project_id: Optional[ProjectId] = None,
        limit: int = 100,
    ) -> List[WorkItem]:
        """Full-text search for work items."""
        # Build search query
        search_query = f"{query} repo:{self.config.organization}/{self.config.repository} is:issue"

        params = {
            "q": search_query,
            "per_page": min(limit, 100),
        }

        response = await self._make_request("GET", "/search/issues", params=params)

        if response.status_code != 200:
            raise ExternalServiceError("GitHub", f"Search failed: {response.text}")

        result = response.json()
        issues = result.get("items", [])

        proj_id = ProjectId(f"{self.config.organization}/{self.config.repository}")
        return [self._map_github_issue_to_work_item(issue, proj_id) for issue in issues]

    async def get_work_item_stream(
        self,
        project_id: Optional[ProjectId] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[WorkItem]:
        """
        Stream work item updates.

        Note: GitHub doesn't support real-time streaming.
        This implementation polls for updates.
        """
        last_check = since or datetime.now(timezone.utc)

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
        author: Optional[UserId] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Comment:
        """Add a comment to a work item."""
        if not body:
            raise ValidationError("Comment body is required")

        payload = {"body": body}

        path = f"/repos/{self.config.organization}/{self.config.repository}/issues/{item_id}/comments"
        response = await self._make_request("POST", path, json=payload)

        if response.status_code == 404:
            raise WorkItemNotFoundError(f"Work item {item_id} not found")
        elif response.status_code != 201:
            raise ExternalServiceError("GitHub", f"Failed to create comment: {response.text}")

        comment_data = response.json()

        return Comment(
            id=CommentId(str(comment_data["id"])),
            work_item_id=item_id,
            author_id=UserId(comment_data["user"]["login"]),
            body=comment_data["body"],
            created_at=datetime.fromisoformat(comment_data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(comment_data["updated_at"].replace("Z", "+00:00")) if comment_data.get("updated_at") else None,
        )

    async def get_comments(
        self,
        item_id: WorkItemId,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Comment]:
        """Get comments for a work item."""
        params: Dict[str, Any] = {
            "per_page": min(limit, 100),
        }

        if since:
            params["since"] = since.isoformat()

        path = f"/repos/{self.config.organization}/{self.config.repository}/issues/{item_id}/comments"
        response = await self._make_request("GET", path, params=params)

        if response.status_code == 404:
            raise WorkItemNotFoundError(f"Work item {item_id} not found")
        elif response.status_code != 200:
            raise ExternalServiceError("GitHub", f"Failed to get comments: {response.text}")

        comments_data = response.json()

        return [
            Comment(
                id=CommentId(str(comment["id"])),
                work_item_id=item_id,
                author_id=UserId(comment["user"]["login"]),
                body=comment["body"],
                created_at=datetime.fromisoformat(comment["created_at"].replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(comment["updated_at"].replace("Z", "+00:00")) if comment.get("updated_at") else None,
            )
            for comment in comments_data
        ]

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
        relationship: Optional[str] = None,
    ) -> List[WorkItem]:
        """
        Get related work items.

        This searches for issue references in comments and description.
        """
        # Get the work item
        work_item = await self.get_work_item(item_id)

        # Extract issue numbers from description and comments
        import re
        issue_pattern = r'#(\d+)'

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
        events: List[str],
        project_id: Optional[ProjectId] = None,
    ) -> str:
        """Register a webhook for events."""
        if not url:
            raise ValidationError("Webhook URL is required")

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
            raise ExternalServiceError("GitHub", f"Failed to create webhook: {response.text}")

        webhook_data = response.json()
        return str(webhook_data["id"])

    async def unregister_webhook(self, webhook_id: str) -> None:
        """Unregister a webhook."""
        path = f"/repos/{self.config.organization}/{self.config.repository}/hooks/{webhook_id}"
        response = await self._make_request("DELETE", path)

        if response.status_code == 404:
            from codetoreum.ports.exceptions import ResourceNotFoundError
            raise ResourceNotFoundError("Webhook", webhook_id)
        elif response.status_code != 204:
            raise ExternalServiceError("GitHub", f"Failed to delete webhook: {response.text}")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
