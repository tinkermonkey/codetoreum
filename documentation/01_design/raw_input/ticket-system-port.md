# ITicketSystem Port

## Overview

The `ITicketSystem` port defines the interface for interacting with external issue tracking and project management systems. This is one of the most critical output ports as it manages the work items that drive the entire orchestration system.

## Interface Definition

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, AsyncIterator
from datetime import datetime
from enum import Enum

from codetroeum.domain.models import WorkItem, WorkItemStatus, Comment
from codetroeum.domain.types import WorkItemId, ProjectId, UserId

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
        """
        Create a new work item.
        
        Args:
            title: Work item title
            description: Detailed description
            project_id: Project to create item in
            labels: Optional labels/tags
            assignee: Optional initial assignee
            metadata: Additional system-specific metadata
            
        Returns:
            WorkItem: The created work item
            
        Raises:
            ValidationError: Invalid input data
            AuthorizationError: Insufficient permissions
            ExternalServiceError: Service communication failure
        """
        pass
    
    @abstractmethod
    async def update_work_item(self,
                              item_id: WorkItemId,
                              updates: Dict[str, Any]) -> WorkItem:
        """
        Update an existing work item.
        
        Args:
            item_id: Work item to update
            updates: Dictionary of fields to update
            
        Returns:
            WorkItem: Updated work item
            
        Raises:
            ResourceNotFoundError: Work item doesn't exist
            ConcurrencyConflictError: Version conflict
            ValidationError: Invalid update data
            ExternalServiceError: Service communication failure
        """
        pass
    
    @abstractmethod
    async def delete_work_item(self, item_id: WorkItemId) -> None:
        """
        Delete a work item.
        
        Args:
            item_id: Work item to delete
            
        Raises:
            ResourceNotFoundError: Work item doesn't exist
            AuthorizationError: Insufficient permissions
            ExternalServiceError: Service communication failure
        """
        pass
    
    @abstractmethod
    async def update_status(self,
                          item_id: WorkItemId,
                          status: WorkItemStatus,
                          reason: Optional[str] = None) -> WorkItem:
        """
        Update work item status.
        
        Args:
            item_id: Work item to update
            status: New status
            reason: Optional reason for status change
            
        Returns:
            WorkItem: Updated work item
            
        Raises:
            ResourceNotFoundError: Work item doesn't exist
            InvalidStateTransitionError: Invalid status transition
            ExternalServiceError: Service communication failure
        """
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
        """
        List work items with filters.
        
        Args:
            project_id: Filter by project
            status: Filter by status
            assignee: Filter by assignee
            labels: Filter by labels (ANY match)
            created_after: Filter by creation date
            updated_after: Filter by update date
            limit: Maximum items to return
            offset: Pagination offset
            
        Returns:
            List[WorkItem]: Filtered work items
            
        Raises:
            ValidationError: Invalid query parameters
            ExternalServiceError: Service communication failure
        """
        pass
    
    @abstractmethod
    async def search_work_items(self,
                               query: str,
                               project_id: Optional[ProjectId] = None,
                               limit: int = 100) -> List[WorkItem]:
        """
        Full-text search for work items.
        
        Args:
            query: Search query string
            project_id: Limit search to project
            limit: Maximum results
            
        Returns:
            List[WorkItem]: Matching work items
            
        Raises:
            ValidationError: Invalid search query
            ExternalServiceError: Service communication failure
        """
        pass
    
    @abstractmethod
    async def get_work_item_stream(self,
                                  project_id: Optional[ProjectId] = None,
                                  since: Optional[datetime] = None) -> AsyncIterator[WorkItem]:
        """
        Stream work item updates in real-time.
        
        Args:
            project_id: Filter by project
            since: Start streaming from this time
            
        Yields:
            WorkItem: Updated work items
            
        Raises:
            ExternalServiceError: Service communication failure
        """
        pass
    
    # Comment Operations
    
    @abstractmethod
    async def add_comment(self,
                         item_id: WorkItemId,
                         body: str,
                         author: Optional[UserId] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> Comment:
        """
        Add a comment to a work item.
        
        Args:
            item_id: Work item to comment on
            body: Comment text (markdown supported)
            author: Comment author (defaults to system user)
            metadata: Additional metadata
            
        Returns:
            Comment: Created comment
            
        Raises:
            ResourceNotFoundError: Work item doesn't exist
            ValidationError: Invalid comment data
            ExternalServiceError: Service communication failure
        """
        pass
    
    @abstractmethod
    async def get_comments(self,
                          item_id: WorkItemId,
                          since: Optional[datetime] = None,
                          limit: int = 100) -> List[Comment]:
        """
        Get comments for a work item.
        
        Args:
            item_id: Work item to get comments for
            since: Get comments after this time
            limit: Maximum comments to return
            
        Returns:
            List[Comment]: Work item comments
            
        Raises:
            ResourceNotFoundError: Work item doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass
    
    # Relationship Operations
    
    @abstractmethod
    async def link_work_items(self,
                             source_id: WorkItemId,
                             target_id: WorkItemId,
                             relationship: str) -> None:
        """
        Create relationship between work items.
        
        Args:
            source_id: Source work item
            target_id: Target work item
            relationship: Relationship type (blocks, relates-to, parent-of)
            
        Raises:
            ResourceNotFoundError: Work item doesn't exist
            ValidationError: Invalid relationship
            ExternalServiceError: Service communication failure
        """
        pass
    
    @abstractmethod
    async def get_related_items(self,
                               item_id: WorkItemId,
                               relationship: Optional[str] = None) -> List[WorkItem]:
        """
        Get related work items.
        
        Args:
            item_id: Work item to get relations for
            relationship: Filter by relationship type
            
        Returns:
            List[WorkItem]: Related work items
            
        Raises:
            ResourceNotFoundError: Work item doesn't exist
            ExternalServiceError: Service communication failure
        """
        pass
    
    # Webhook Operations
    
    @abstractmethod
    async def register_webhook(self,
                              url: str,
                              events: List[str],
                              project_id: Optional[ProjectId] = None) -> str:
        """
        Register a webhook for events.
        
        Args:
            url: Webhook endpoint URL
            events: List of events to subscribe to
            project_id: Limit to specific project
            
        Returns:
            str: Webhook ID
            
        Raises:
            ValidationError: Invalid webhook configuration
            AuthorizationError: Insufficient permissions
            ExternalServiceError: Service communication failure
        """
        pass
    
    @abstractmethod
    async def unregister_webhook(self, webhook_id: str) -> None:
        """
        Unregister a webhook.
        
        Args:
            webhook_id: Webhook to unregister
            
        Raises:
            ResourceNotFoundError: Webhook doesn't exist
            AuthorizationError: Insufficient permissions
            ExternalServiceError: Service communication failure
        """
        pass
```

## Domain Models

### WorkItem Model

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
    
    # Computed properties
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

### Comment Model

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

## Implementation Examples

### GitHub Adapter

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
    
    async def create_work_item(self,
                              title: str,
                              description: str,
                              project_id: ProjectId,
                              labels: Optional[List[str]] = None,
                              assignee: Optional[UserId] = None,
                              metadata: Optional[Dict[str, Any]] = None) -> WorkItem:
        try:
            issue = await self.client.issues.create(
                self.org,
                self.repo,
                title=title,
                body=description,
                labels=labels or [],
                assignee=assignee
            )
            return self._map_issue_to_work_item(issue)
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
    
    def _map_issue_state(self, 
                        state: str,
                        labels: List[GitHubLabel]) -> WorkItemStatus:
        """Map GitHub state and labels to WorkItemStatus."""
        label_names = {label.name.lower() for label in labels}
        
        if state == "closed":
            if "cancelled" in label_names:
                return WorkItemStatus.CANCELLED
            return WorkItemStatus.COMPLETED
        
        if "in-progress" in label_names:
            return WorkItemStatus.IN_PROGRESS
        if "review" in label_names:
            return WorkItemStatus.REVIEW
        
        return WorkItemStatus.NEW
```

### Jira Adapter

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
    
    def _map_issue_to_work_item(self, issue: Issue) -> WorkItem:
        """Map Jira issue to domain model."""
        return WorkItem(
            id=issue.key,
            title=issue.fields.summary,
            description=issue.fields.description or "",
            project_id=issue.fields.project.key,
            status=self._map_jira_status(issue.fields.status.name),
            priority=self._map_jira_priority(issue.fields.priority.name),
            labels=issue.fields.labels,
            assignee=issue.fields.assignee.name if issue.fields.assignee else None,
            created_at=parser.parse(issue.fields.created),
            updated_at=parser.parse(issue.fields.updated),
            created_by=issue.fields.reporter.name,
            metadata={
                "issue_type": issue.fields.issuetype.name,
                "key": issue.key
            }
        )
```

### Mock Adapter for Testing

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
    
    async def list_work_items(self,
                             project_id: Optional[ProjectId] = None,
                             status: Optional[WorkItemStatus] = None,
                             **kwargs) -> List[WorkItem]:
        results = list(self.work_items.values())
        
        if project_id:
            results = [w for w in results if w.project_id == project_id]
        if status:
            results = [w for w in results if w.status == status]
        
        return results[:kwargs.get('limit', 100)]
```

## Testing

### Contract Tests

```python
class TicketSystemContract:
    """Contract tests for ITicketSystem implementations."""
    
    @abstractmethod
    def create_adapter(self) -> ITicketSystem:
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
        assert retrieved.description == "Test Description"
    
    async def test_update_status(self):
        """Test status updates."""
        adapter = self.create_adapter()
        
        # Create
        work_item = await adapter.create_work_item(
            title="Test",
            description="Test",
            project_id="test"
        )
        
        # Update status
        updated = await adapter.update_status(
            work_item.id,
            WorkItemStatus.IN_PROGRESS
        )
        
        assert updated.status == WorkItemStatus.IN_PROGRESS
    
    async def test_comments(self):
        """Test comment operations."""
        adapter = self.create_adapter()
        
        # Create work item
        work_item = await adapter.create_work_item(
            title="Test",
            description="Test",
            project_id="test"
        )
        
        # Add comment
        comment = await adapter.add_comment(
            work_item.id,
            "Test comment"
        )
        
        assert comment.body == "Test comment"
        
        # Get comments
        comments = await adapter.get_comments(work_item.id)
        assert len(comments) == 1
        assert comments[0].body == "Test comment"

# Test implementations
class TestGitHubAdapter(TicketSystemContract):
    def create_adapter(self) -> ITicketSystem:
        return GitHubTicketAdapter(
            token="test-token",
            organization="test-org",
            repository="test-repo"
        )

class TestInMemoryAdapter(TicketSystemContract):
    def create_adapter(self) -> ITicketSystem:
        return InMemoryTicketAdapter()
```

## Configuration

### Adapter Configuration

```python
@dataclass
class TicketSystemConfig:
    """Configuration for ticket system adapters."""
    
    adapter_type: str  # github, jira, linear, mock
    connection_params: Dict[str, Any]
    retry_config: RetryConfig
    cache_config: Optional[CacheConfig] = None
    
    @classmethod
    def from_env(cls) -> 'TicketSystemConfig':
        """Load from environment variables."""
        adapter_type = os.getenv("TICKET_SYSTEM_TYPE", "mock")
        
        if adapter_type == "github":
            return cls(
                adapter_type="github",
                connection_params={
                    "token": os.getenv("GITHUB_TOKEN"),
                    "organization": os.getenv("GITHUB_ORG"),
                    "repository": os.getenv("GITHUB_REPO")
                },
                retry_config=RetryConfig(max_retries=3, backoff=2.0)
            )
        # ... other adapters
```

## Best Practices

1. **Always handle rate limits** - Implement exponential backoff
2. **Cache when appropriate** - Reduce API calls
3. **Map to domain models** - Don't leak external types
4. **Validate inputs** - Check before calling external API
5. **Log external calls** - For debugging and monitoring
6. **Handle webhooks idempotently** - Prevent duplicate processing
7. **Use batch operations** - When available in the API

## Next Steps

- Review [ILLMProvider Port](llm-provider-port.md)
- Explore [IEventStore Port](event-store-port.md)
- See [Secondary Adapters](../adapters/secondary/00-overview.md)
