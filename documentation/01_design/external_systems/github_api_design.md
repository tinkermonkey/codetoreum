# GitHub API External System - Detailed Design

## Overview

The GitHub API serves as the primary interface for version control, issue tracking, project management, and team collaboration within the Codetoreum platform. This document provides comprehensive design details for the GitHub API integration, including the abstraction layer, authentication mechanisms, and mock implementations.

## System Purpose

**Primary Functions**:
1. Repository management (clone, pull, push, branch operations)
2. Issue and pull request tracking
3. Project board automation (GitHub Projects v2)
4. Discussion management
5. Webhook event handling
6. Code review integration
7. Label and milestone management

## Port Interface Design

### ITicketSystem Interface

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class WorkItem:
    """
    Domain model for a work item (issue, ticket, card).
    Independent of any specific ticket system.
    """
    id: str                          # Unique identifier
    number: int                      # Human-readable number
    title: str                       # Work item title
    description: str                 # Full description/body
    status: str                      # Current status/column
    labels: List[str]                # Tags/labels
    created_at: datetime             # Creation timestamp
    updated_at: datetime             # Last update timestamp
    assignees: List[str]             # Assigned users
    author: str                      # Creator
    url: str                         # Web URL

    # Optional fields
    parent_id: Optional[str] = None  # Parent work item
    milestone: Optional[str] = None  # Milestone/sprint
    due_date: Optional[datetime] = None
    custom_fields: Dict[str, Any] = None

@dataclass
class Comment:
    """Domain model for a comment on a work item."""
    id: str
    work_item_id: str
    author: str
    body: str
    created_at: datetime
    updated_at: datetime
    is_reply_to: Optional[str] = None  # Thread parent

@dataclass
class ProjectBoard:
    """Domain model for a project board."""
    id: str
    name: str
    columns: List['BoardColumn']
    url: str

@dataclass
class BoardColumn:
    """Domain model for a board column."""
    id: str
    name: str
    position: int
    work_item_count: int

class ITicketSystem(ABC):
    """
    Port interface for ticket/issue tracking systems.

    Abstracts GitHub Issues, Jira, Markdown files, etc.
    """

    # Work Item Operations
    @abstractmethod
    async def get_work_item(self, item_id: str) -> WorkItem:
        """Retrieve a work item by ID."""
        pass

    @abstractmethod
    async def create_work_item(
        self,
        title: str,
        description: str,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        parent_id: Optional[str] = None
    ) -> WorkItem:
        """Create a new work item."""
        pass

    @abstractmethod
    async def update_work_item(
        self,
        item_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        labels: Optional[List[str]] = None
    ) -> WorkItem:
        """Update an existing work item."""
        pass

    @abstractmethod
    async def list_work_items(
        self,
        status: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignee: Optional[str] = None
    ) -> List[WorkItem]:
        """List work items with optional filtering."""
        pass

    # Comment Operations
    @abstractmethod
    async def create_comment(
        self,
        work_item_id: str,
        body: str,
        reply_to: Optional[str] = None
    ) -> Comment:
        """Add a comment to a work item."""
        pass

    @abstractmethod
    async def list_comments(self, work_item_id: str) -> List[Comment]:
        """Retrieve all comments for a work item."""
        pass

    # Label Operations
    @abstractmethod
    async def create_label(
        self,
        name: str,
        color: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new label."""
        pass

    @abstractmethod
    async def add_labels(
        self,
        work_item_id: str,
        labels: List[str]
    ) -> WorkItem:
        """Add labels to a work item."""
        pass

    @abstractmethod
    async def remove_labels(
        self,
        work_item_id: str,
        labels: List[str]
    ) -> WorkItem:
        """Remove labels from a work item."""
        pass

    # Project Board Operations
    @abstractmethod
    async def get_project_board(self, board_id: str) -> ProjectBoard:
        """Retrieve project board details."""
        pass

    @abstractmethod
    async def move_work_item(
        self,
        work_item_id: str,
        column_id: str
    ) -> None:
        """Move a work item to a different column."""
        pass

    @abstractmethod
    async def get_work_items_in_column(
        self,
        board_id: str,
        column_id: str
    ) -> List[WorkItem]:
        """List all work items in a specific column."""
        pass
```

### IRepository Interface

```python
from pathlib import Path

class IRepository(ABC):
    """
    Port interface for repository operations.

    Abstracts Git operations on remote repositories.
    """

    @abstractmethod
    async def clone(
        self,
        repo_url: str,
        destination: Path,
        branch: Optional[str] = None
    ) -> None:
        """Clone a repository."""
        pass

    @abstractmethod
    async def pull(
        self,
        repo_path: Path,
        branch: str,
        rebase: bool = False
    ) -> None:
        """Pull changes from remote."""
        pass

    @abstractmethod
    async def push(
        self,
        repo_path: Path,
        branch: str,
        force: bool = False
    ) -> None:
        """Push changes to remote."""
        pass

    @abstractmethod
    async def create_branch(
        self,
        repo_path: Path,
        branch_name: str,
        from_branch: Optional[str] = None
    ) -> None:
        """Create a new branch."""
        pass

    @abstractmethod
    async def checkout(
        self,
        repo_path: Path,
        branch: str
    ) -> None:
        """Switch to a branch."""
        pass

    @abstractmethod
    async def commit(
        self,
        repo_path: Path,
        message: str,
        files: Optional[List[str]] = None
    ) -> str:
        """Create a commit. Returns commit SHA."""
        pass

    @abstractmethod
    async def get_branches(
        self,
        repo_path: Path,
        remote: bool = False
    ) -> List[str]:
        """List branches."""
        pass

    @abstractmethod
    async def create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str
    ) -> Dict[str, Any]:
        """Create a pull request."""
        pass
```

## Production Adapter: GitHubAdapter

### Implementation Structure

```python
from github import Github
from github.GithubException import GithubException
import httpx
from typing import Optional

class GitHubTicketAdapter(ITicketSystem):
    """
    Production adapter for GitHub Issues and Project Boards.

    Uses GitHub REST API v3 and GraphQL API v4.
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        token: Optional[str] = None,
        app_auth: Optional['GitHubAppAuth'] = None
    ):
        """
        Initialize GitHub adapter.

        Args:
            owner: Repository owner (org or user)
            repo: Repository name
            token: Personal access token (optional)
            app_auth: GitHub App authentication (optional)
        """
        self.owner = owner
        self.repo = repo

        # Authentication
        if app_auth:
            self.client = Github(app_auth.get_installation_token())
            self.auth_type = 'app'
        elif token:
            self.client = Github(token)
            self.auth_type = 'token'
        else:
            raise ValueError("Either token or app_auth must be provided")

        self.repository = self.client.get_repo(f"{owner}/{repo}")

        # GraphQL client for Projects v2
        self.graphql_url = "https://api.github.com/graphql"
        self.graphql_headers = {
            "Authorization": f"Bearer {token or app_auth.get_installation_token()}",
            "Content-Type": "application/json"
        }

    async def get_work_item(self, item_id: str) -> WorkItem:
        """
        Retrieve a GitHub issue.

        Args:
            item_id: Issue number (as string)

        Returns:
            WorkItem domain model
        """
        try:
            issue_number = int(item_id)
            issue = self.repository.get_issue(issue_number)

            return self._convert_to_work_item(issue)
        except GithubException as e:
            raise TicketSystemError(f"Failed to get issue {item_id}: {e}")

    async def create_work_item(
        self,
        title: str,
        description: str,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        parent_id: Optional[str] = None
    ) -> WorkItem:
        """
        Create a GitHub issue.

        If parent_id provided, adds "Parent Issue: #{parent_id}" to description.
        """
        # Build description with parent reference
        full_description = description
        if parent_id:
            full_description = f"Parent Issue: #{parent_id}\n\n{description}"

        try:
            issue = self.repository.create_issue(
                title=title,
                body=full_description,
                labels=labels or [],
                assignees=assignees or []
            )

            return self._convert_to_work_item(issue)
        except GithubException as e:
            raise TicketSystemError(f"Failed to create issue: {e}")

    async def create_comment(
        self,
        work_item_id: str,
        body: str,
        reply_to: Optional[str] = None
    ) -> Comment:
        """
        Create a comment on a GitHub issue.

        Note: GitHub API doesn't natively support threaded comments,
        so reply_to is stored as metadata but not enforced.
        """
        issue_number = int(work_item_id)
        issue = self.repository.get_issue(issue_number)

        # Add reply reference in comment body if needed
        if reply_to:
            body = f"*In reply to comment {reply_to}*\n\n{body}"

        try:
            comment = issue.create_comment(body)
            return self._convert_to_comment(comment)
        except GithubException as e:
            raise TicketSystemError(f"Failed to create comment: {e}")

    async def get_project_board(self, board_id: str) -> ProjectBoard:
        """
        Retrieve GitHub Project (v2) board.

        Uses GraphQL API for Projects v2.
        """
        query = """
        query GetProject($projectId: ID!) {
          node(id: $projectId) {
            ... on ProjectV2 {
              id
              title
              url
              fields(first: 20) {
                nodes {
                  ... on ProjectV2SingleSelectField {
                    id
                    name
                    options {
                      id
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """

        variables = {"projectId": board_id}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.graphql_url,
                json={"query": query, "variables": variables},
                headers=self.graphql_headers
            )
            data = response.json()

        if "errors" in data:
            raise TicketSystemError(f"GraphQL error: {data['errors']}")

        project = data["data"]["node"]
        return self._convert_to_project_board(project)

    async def move_work_item(
        self,
        work_item_id: str,
        column_id: str
    ) -> None:
        """
        Move an issue to a different column in Projects v2.

        Requires GraphQL mutation.
        """
        # First, get the project item ID for this issue
        issue_number = int(work_item_id)
        project_item_id = await self._get_project_item_id(issue_number)

        # Then move it
        mutation = """
        mutation MoveProjectItem($projectId: ID!, $itemId: ID!, $fieldId: ID!, $columnId: String!) {
          updateProjectV2ItemFieldValue(
            input: {
              projectId: $projectId
              itemId: $itemId
              fieldId: $fieldId
              value: { singleSelectOptionId: $columnId }
            }
          ) {
            projectV2Item {
              id
            }
          }
        }
        """

        # Execute mutation...
        # (Implementation details omitted for brevity)

    def _convert_to_work_item(self, issue) -> WorkItem:
        """Convert GitHub Issue to WorkItem domain model."""
        # Extract parent from body
        parent_id = None
        if issue.body and "Parent Issue: #" in issue.body:
            import re
            match = re.search(r'Parent Issue: #(\d+)', issue.body)
            if match:
                parent_id = match.group(1)

        return WorkItem(
            id=str(issue.number),
            number=issue.number,
            title=issue.title,
            description=issue.body or "",
            status=issue.state,
            labels=[label.name for label in issue.labels],
            created_at=issue.created_at,
            updated_at=issue.updated_at,
            assignees=[assignee.login for assignee in issue.assignees],
            author=issue.user.login,
            url=issue.html_url,
            parent_id=parent_id,
            milestone=issue.milestone.title if issue.milestone else None
        )

    def _convert_to_comment(self, comment) -> Comment:
        """Convert GitHub IssueComment to Comment domain model."""
        return Comment(
            id=str(comment.id),
            work_item_id=str(comment.issue_url.split('/')[-1]),
            author=comment.user.login,
            body=comment.body,
            created_at=comment.created_at,
            updated_at=comment.updated_at
        )


class GitHubRepositoryAdapter(IRepository):
    """
    Production adapter for Git repository operations.

    Uses GitPython and GitHub CLI.
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        token: Optional[str] = None
    ):
        self.owner = owner
        self.repo = repo
        self.token = token
        self.repo_url = f"git@github.com:{owner}/{repo}.git"

    async def clone(
        self,
        repo_url: str,
        destination: Path,
        branch: Optional[str] = None
    ) -> None:
        """Clone repository using git command."""
        cmd = ['git', 'clone', repo_url, str(destination)]
        if branch:
            cmd.extend(['--branch', branch])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RepositoryError(f"Clone failed: {stderr.decode()}")

    async def create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str
    ) -> Dict[str, Any]:
        """
        Create pull request using GitHub CLI.

        Requires 'gh' CLI to be installed and authenticated.
        """
        cmd = [
            'gh', 'pr', 'create',
            '--title', title,
            '--body', body,
            '--head', head_branch,
            '--base', base_branch,
            '--repo', f"{self.owner}/{self.repo}"
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RepositoryError(f"PR creation failed: {stderr.decode()}")

        pr_url = stdout.decode().strip()

        return {
            'url': pr_url,
            'success': True
        }
```

## Mock Adapter: InMemoryTicketAdapter

```python
from collections import defaultdict

class InMemoryTicketAdapter(ITicketSystem):
    """
    Mock adapter for testing and simulation.

    Stores all data in memory with no external dependencies.
    """

    def __init__(self):
        self.work_items: Dict[str, WorkItem] = {}
        self.comments: Dict[str, List[Comment]] = defaultdict(list)
        self.labels: Dict[str, Dict] = {}
        self.boards: Dict[str, ProjectBoard] = {}
        self.next_id = 1

    async def get_work_item(self, item_id: str) -> WorkItem:
        """Retrieve work item from memory."""
        if item_id not in self.work_items:
            raise TicketSystemError(f"Work item {item_id} not found")
        return self.work_items[item_id]

    async def create_work_item(
        self,
        title: str,
        description: str,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        parent_id: Optional[str] = None
    ) -> WorkItem:
        """Create work item in memory."""
        item_id = str(self.next_id)
        self.next_id += 1

        work_item = WorkItem(
            id=item_id,
            number=int(item_id),
            title=title,
            description=description,
            status="open",
            labels=labels or [],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            assignees=assignees or [],
            author="test-user",
            url=f"memory://work-item/{item_id}",
            parent_id=parent_id
        )

        self.work_items[item_id] = work_item
        return work_item

    async def create_comment(
        self,
        work_item_id: str,
        body: str,
        reply_to: Optional[str] = None
    ) -> Comment:
        """Create comment in memory."""
        comment_id = f"comment-{len(self.comments[work_item_id]) + 1}"

        comment = Comment(
            id=comment_id,
            work_item_id=work_item_id,
            author="test-user",
            body=body,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            is_reply_to=reply_to
        )

        self.comments[work_item_id].append(comment)
        return comment

    async def move_work_item(
        self,
        work_item_id: str,
        column_id: str
    ) -> None:
        """Move work item to column (updates status)."""
        if work_item_id in self.work_items:
            self.work_items[work_item_id].status = column_id

    def add_test_work_item(self, work_item: WorkItem):
        """Helper for test setup - directly add work item."""
        self.work_items[work_item.id] = work_item

    def get_all_work_items(self) -> List[WorkItem]:
        """Helper for test assertions - get all items."""
        return list(self.work_items.values())
```

## Authentication Design

### GitHub App Authentication

```python
import jwt
import time
from typing import Optional

class GitHubAppAuth:
    """
    GitHub App authentication manager.

    Generates installation tokens for API access.
    """

    def __init__(
        self,
        app_id: str,
        private_key_path: str,
        installation_id: str
    ):
        self.app_id = app_id
        self.installation_id = installation_id

        with open(private_key_path, 'r') as f:
            self.private_key = f.read()

        self._installation_token: Optional[str] = None
        self._token_expires_at: Optional[int] = None

    def get_jwt(self) -> str:
        """
        Generate JWT for GitHub App authentication.

        Valid for 10 minutes.
        """
        now = int(time.time())

        payload = {
            'iat': now,
            'exp': now + (10 * 60),  # 10 minutes
            'iss': self.app_id
        }

        return jwt.encode(payload, self.private_key, algorithm='RS256')

    def get_installation_token(self) -> str:
        """
        Get installation access token.

        Caches token until expiration.
        """
        now = int(time.time())

        # Return cached token if still valid
        if self._installation_token and self._token_expires_at:
            if now < (self._token_expires_at - 60):  # 1 min buffer
                return self._installation_token

        # Generate new token
        jwt_token = self.get_jwt()

        url = f"https://api.github.com/app/installations/{self.installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        response = httpx.post(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        self._installation_token = data['token']

        # Parse expiration
        expires_at_str = data['expires_at']
        # Convert to timestamp...

        return self._installation_token
```

### Personal Access Token

```python
class PersonalAccessTokenAuth:
    """Simple PAT authentication."""

    def __init__(self, token: str):
        self.token = token

    def get_token(self) -> str:
        return self.token
```

## Error Handling

```python
class TicketSystemError(Exception):
    """Base exception for ticket system operations."""
    pass

class WorkItemNotFoundError(TicketSystemError):
    """Raised when work item doesn't exist."""
    pass

class AuthenticationError(TicketSystemError):
    """Raised when authentication fails."""
    pass

class RateLimitError(TicketSystemError):
    """Raised when API rate limit exceeded."""

    def __init__(self, reset_at: datetime, *args):
        super().__init__(*args)
        self.reset_at = reset_at

class RepositoryError(Exception):
    """Base exception for repository operations."""
    pass
```

## Configuration

```python
@dataclass
class GitHubConfig:
    """GitHub adapter configuration."""
    owner: str
    repo: str

    # Authentication (one required)
    token: Optional[str] = None
    app_id: Optional[str] = None
    app_private_key_path: Optional[str] = None
    app_installation_id: Optional[str] = None

    # API settings
    api_base_url: str = "https://api.github.com"
    graphql_url: str = "https://api.github.com/graphql"
    timeout: int = 30
    max_retries: int = 3

    def validate(self):
        """Validate configuration."""
        has_pat = self.token is not None
        has_app = all([
            self.app_id,
            self.app_private_key_path,
            self.app_installation_id
        ])

        if not (has_pat or has_app):
            raise ValueError("Either token or app credentials required")
```

## Testing Strategy

### Unit Tests

```python
import pytest

@pytest.fixture
def mock_adapter():
    return InMemoryTicketAdapter()

async def test_create_work_item(mock_adapter):
    """Test work item creation."""
    item = await mock_adapter.create_work_item(
        title="Test Issue",
        description="Test description",
        labels=["bug"]
    )

    assert item.title == "Test Issue"
    assert item.labels == ["bug"]
    assert item.status == "open"

async def test_parent_child_relationship(mock_adapter):
    """Test parent-child work items."""
    parent = await mock_adapter.create_work_item(
        title="Epic",
        description="Epic description"
    )

    child = await mock_adapter.create_work_item(
        title="Sub-task",
        description="Sub-task description",
        parent_id=parent.id
    )

    assert child.parent_id == parent.id
```

### Integration Tests

```python
@pytest.mark.integration
async def test_github_adapter_real_api():
    """Test real GitHub API (requires token)."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        pytest.skip("No GitHub token provided")

    adapter = GitHubTicketAdapter(
        owner="test-org",
        repo="test-repo",
        token=token
    )

    # Test read-only operation
    item = await adapter.get_work_item("1")
    assert item.number == 1
```

## Deployment Considerations

### Rate Limiting

GitHub API has rate limits:
- **Personal Access Token**: 5,000 requests/hour
- **GitHub App**: 15,000 requests/hour per installation

**Mitigation**:
- Request queue with rate limiting
- Exponential backoff on 429 errors
- Cache frequently accessed data
- Batch operations where possible

### Webhook Integration

```python
class GitHubWebhookHandler:
    """
    Handle GitHub webhook events.

    Processes push, pull_request, issues, project_card events.
    """

    def __init__(self, secret: str):
        self.secret = secret

    def verify_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """Verify webhook signature."""
        import hmac
        import hashlib

        mac = hmac.new(
            self.secret.encode(),
            payload,
            hashlib.sha256
        )

        expected = f"sha256={mac.hexdigest()}"
        return hmac.compare_digest(expected, signature)

    async def handle_event(
        self,
        event_type: str,
        payload: Dict[str, Any]
    ):
        """Route webhook event to appropriate handler."""
        if event_type == "issues":
            await self.handle_issues_event(payload)
        elif event_type == "project_card":
            await self.handle_project_card_event(payload)
        # ... more handlers
```

## Summary

The GitHub API integration provides:
1. **Clean abstraction** through ITicketSystem and IRepository ports
2. **Production adapter** for real GitHub API access
3. **Mock adapter** for testing and simulation
4. **Flexible authentication** (PAT and GitHub App)
5. **Error handling** with specific exception types
6. **Rate limiting** protection
7. **Webhook support** for event-driven automation
8. **Full testing** support with mock implementations

This design enables the platform to work with GitHub while maintaining the flexibility to swap in alternative ticket systems (Jira, Markdown files, etc.) without changing core business logic.
