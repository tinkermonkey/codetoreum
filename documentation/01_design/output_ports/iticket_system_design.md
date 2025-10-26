# ITicketSystem Output Port Design

## Overview

The `ITicketSystem` port provides an abstraction for interacting with issue tracking and project management systems. This is a critical output port as work items (tickets/issues) are the primary drivers of the orchestration system.

## Port Interface

### Core Interface Definition

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncIterator
from datetime import datetime
from enum import Enum

from codetoreum.domain.models import WorkItem, WorkItemStatus, Comment
from codetoreum.domain.types import WorkItemId, ProjectId, UserId

class ITicketSystem(ABC):
    """
    Interface for ticket/issue management systems.

    This port abstracts operations for work item management,
    supporting various backends like GitHub Issues, Jira, Linear, etc.
    """

    # Work Item Operations

    @abstractmethod
    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        """
        Retrieve a work item by ID.

        Args:
            item_id: Unique identifier for the work item

        Returns:
            WorkItem: The requested work item

        Raises:
            ResourceNotFoundError: Work item doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass

    @abstractmethod
    async def create_work_item(self,
                              title: str,
                              description: str,
                              project_id: ProjectId,
                              labels: Optional[List[str]] = None,
                              assignee: Optional[UserId] = None,
                              metadata: Optional[Dict[str, Any]] = None) -> WorkItem:
        """Create a new work item."""
        pass

    @abstractmethod
    async def update_work_item(self,
                              item_id: WorkItemId,
                              updates: Dict[str, Any]) -> WorkItem:
        """Update an existing work item."""
        pass

    @abstractmethod
    async def delete_work_item(self, item_id: WorkItemId) -> None:
        """Delete a work item."""
        pass

    @abstractmethod
    async def update_status(self,
                          item_id: WorkItemId,
                          status: WorkItemStatus,
                          reason: Optional[str] = None) -> WorkItem:
        """Update work item status."""
        pass

    # Query Operations

    @abstractmethod
    async def list_work_items(self,
                             project_id: Optional[ProjectId] = None,
                             status: Optional[WorkItemStatus] = None,
                             assignee: Optional[UserId] = None,
                             labels: Optional[List[str]] = None,
                             created_after: Optional[datetime] = None,
                             updated_after: Optional[datetime] = None,
                             limit: int = 100,
                             offset: int = 0) -> List[WorkItem]:
        """List work items with filters."""
        pass

    @abstractmethod
    async def search_work_items(self,
                               query: str,
                               project_id: Optional[ProjectId] = None,
                               limit: int = 100) -> List[WorkItem]:
        """Full-text search for work items."""
        pass

    @abstractmethod
    async def get_work_item_stream(self,
                                  project_id: Optional[ProjectId] = None,
                                  since: Optional[datetime] = None) -> AsyncIterator[WorkItem]:
        """Stream work item updates in real-time."""
        pass

    # Comment Operations

    @abstractmethod
    async def add_comment(self,
                         item_id: WorkItemId,
                         body: str,
                         author: Optional[UserId] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> Comment:
        """Add a comment to a work item."""
        pass

    @abstractmethod
    async def get_comments(self,
                          item_id: WorkItemId,
                          since: Optional[datetime] = None,
                          limit: int = 100) -> List[Comment]:
        """Get comments for a work item."""
        pass

    # Relationship Operations

    @abstractmethod
    async def link_work_items(self,
                             source_id: WorkItemId,
                             target_id: WorkItemId,
                             relationship: str) -> None:
        """Create relationship between work items (blocks, relates-to, parent-of)."""
        pass

    @abstractmethod
    async def get_related_items(self,
                               item_id: WorkItemId,
                               relationship: Optional[str] = None) -> List[WorkItem]:
        """Get related work items."""
        pass

    # Webhook Operations

    @abstractmethod
    async def register_webhook(self,
                              url: str,
                              events: List[str],
                              project_id: Optional[ProjectId] = None) -> str:
        """Register a webhook for events."""
        pass

    @abstractmethod
    async def unregister_webhook(self, webhook_id: str) -> None:
        """Unregister a webhook."""
        pass
```

## Domain Models

### WorkItem

```python
@dataclass
class WorkItem:
    """Domain model for work items."""

    id: WorkItemId
    title: str
    description: str
    project_id: ProjectId
    status: WorkItemStatus
    priority: WorkItemPriority
    labels: List[str]
    assignee: Optional[UserId]
    created_at: datetime
    updated_at: datetime
    created_by: UserId
    metadata: Dict[str, Any]

    @property
    def is_active(self) -> bool:
        return self.status not in [
            WorkItemStatus.COMPLETED,
            WorkItemStatus.CANCELLED
        ]

    @property
    def age_days(self) -> int:
        return (datetime.utcnow() - self.created_at).days
```

### Comment

```python
@dataclass
class Comment:
    """Domain model for comments."""

    id: str
    work_item_id: WorkItemId
    body: str
    author: UserId
    created_at: datetime
    updated_at: Optional[datetime]
    metadata: Dict[str, Any]

    @property
    def is_edited(self) -> bool:
        return self.updated_at is not None
```

### Enums

```python
class WorkItemStatus(Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class WorkItemPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4
```

## Adapter Implementations

### GitHub Adapter

**File**: `src/adapters/secondary/ticket_systems/github_adapter.py`

```python
class GitHubTicketAdapter(ITicketSystem):
    """GitHub Issues implementation of ITicketSystem."""

    def __init__(self,
                 token: str,
                 organization: str,
                 repository: str):
        self.client = GitHub(token)
        self.org = organization
        self.repo = repository

    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        try:
            issue = await self.client.issues.get(
                self.org,
                self.repo,
                int(item_id)
            )
            return self._map_issue_to_work_item(issue)
        except GitHubNotFound:
            raise ResourceNotFoundError("WorkItem", item_id)
        except GitHubException as e:
            raise ExternalServiceError("GitHub", str(e))

    def _map_issue_to_work_item(self, issue: GitHubIssue) -> WorkItem:
        """Map GitHub issue to domain model."""
        return WorkItem(
            id=str(issue.number),
            title=issue.title,
            description=issue.body or "",
            project_id=f"{self.org}/{self.repo}",
            status=self._map_issue_state(issue.state, issue.labels),
            priority=self._extract_priority(issue.labels),
            labels=[label.name for label in issue.labels],
            assignee=issue.assignee.login if issue.assignee else None,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
            created_by=issue.user.login,
            metadata={
                "html_url": issue.html_url,
                "state": issue.state,
                "number": issue.number
            }
        )
```

**Key Features**:
- Maps GitHub Issues to domain WorkItem model
- Handles GitHub-specific state and label mapping
- Supports both Issues and Projects v2 workflows
- Rate limit handling with exponential backoff
- Webhook integration for real-time updates

### Jira Adapter

**File**: `src/adapters/secondary/ticket_systems/jira_adapter.py`

```python
class JiraTicketAdapter(ITicketSystem):
    """Jira implementation of ITicketSystem."""

    def __init__(self,
                 url: str,
                 username: str,
                 api_token: str,
                 project_key: str):
        self.client = JIRA(
            server=url,
            basic_auth=(username, api_token)
        )
        self.project_key = project_key

    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        try:
            issue = await self.client.issue(item_id)
            return self._map_issue_to_work_item(issue)
        except JIRAError as e:
            if e.status_code == 404:
                raise ResourceNotFoundError("WorkItem", item_id)
            raise ExternalServiceError("Jira", str(e))
```

**Key Features**:
- Maps Jira issues to domain model
- Supports custom fields and issue types
- JQL query support for advanced filtering
- Transition workflow mapping

### In-Memory Mock Adapter

**File**: `src/adapters/secondary/ticket_systems/memory_adapter.py`

```python
class InMemoryTicketAdapter(ITicketSystem):
    """In-memory implementation for testing."""

    def __init__(self):
        self.work_items: Dict[WorkItemId, WorkItem] = {}
        self.comments: Dict[WorkItemId, List[Comment]] = {}
        self.relationships: Dict[WorkItemId, List[Tuple[WorkItemId, str]]] = {}
        self.next_id = 1

    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        if item_id not in self.work_items:
            raise ResourceNotFoundError("WorkItem", item_id)
        return self.work_items[item_id]

    async def create_work_item(self,
                              title: str,
                              description: str,
                              project_id: ProjectId,
                              labels: Optional[List[str]] = None,
                              assignee: Optional[UserId] = None,
                              metadata: Optional[Dict[str, Any]] = None) -> WorkItem:
        item_id = str(self.next_id)
        self.next_id += 1

        work_item = WorkItem(
            id=item_id,
            title=title,
            description=description,
            project_id=project_id,
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority.NORMAL,
            labels=labels or [],
            assignee=assignee,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by="system",
            metadata=metadata or {}
        )

        self.work_items[item_id] = work_item
        self.comments[item_id] = []

        return work_item
```

**Key Features**:
- Fast in-memory operations for testing
- Deterministic behavior
- No external dependencies
- Full interface implementation

## Error Handling

### Exception Hierarchy

```python
class PortError(Exception):
    """Base exception for port operations."""
    pass

class ResourceNotFoundError(PortError):
    """Resource doesn't exist."""
    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(f"{resource_type} not found: {resource_id}")
        self.resource_type = resource_type
        self.resource_id = resource_id

class ConcurrencyConflictError(PortError):
    """Concurrent modification detected."""
    pass

class ExternalServiceError(PortError):
    """External service failure."""
    def __init__(self, service: str, message: str):
        super().__init__(f"{service} error: {message}")
        self.service = service

class RateLimitError(PortError):
    """Rate limit exceeded."""
    def __init__(self, retry_after: Optional[int] = None):
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")
        self.retry_after = retry_after
```

## Testing

### Contract Tests

```python
class ITicketSystemContract(ABC):
    """Contract tests for all ITicketSystem implementations."""

    @abstractmethod
    def create_adapter(self) -> ITicketSystem:
        """Create the adapter instance to test."""
        pass

    async def test_create_and_retrieve(self):
        """Test basic CRUD operations."""
        adapter = self.create_adapter()

        # Create
        work_item = await adapter.create_work_item(
            title="Test Item",
            description="Test Description",
            project_id="test-project"
        )

        assert work_item.id is not None
        assert work_item.title == "Test Item"

        # Retrieve
        retrieved = await adapter.get_work_item(work_item.id)
        assert retrieved.title == "Test Item"
```

## Configuration

```python
@dataclass
class TicketSystemConfig:
    """Configuration for ticket system adapters."""

    adapter_type: str  # github, jira, linear, mock
    connection_params: Dict[str, Any]
    retry_config: RetryConfig
    cache_config: Optional[CacheConfig] = None
```

## Integration Points

### Used By
- Workflow Orchestrator (application service)
- Work Item Repository (domain service)
- Event Processors (for webhook handling)

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Always map to domain models** - Never expose external API types
2. **Handle rate limits gracefully** - Implement exponential backoff
3. **Cache when appropriate** - Reduce external API calls
4. **Validate inputs** - Check before calling external APIs
5. **Log all external calls** - For debugging and monitoring
6. **Support idempotent operations** - For webhook event processing
