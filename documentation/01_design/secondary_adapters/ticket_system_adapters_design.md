# Ticket System Adapters - Detailed Design

## Overview

Ticket system adapters connect the core orchestration domain to external issue tracking systems. They implement the `ITicketSystem` output port interface, enabling work item retrieval, status updates, commenting, and project board management.

## Port Interface Definition

### ITicketSystem Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime

class WorkItem:
    """Domain model for a work item."""
    def __init__(
        self,
        id: str,
        title: str,
        description: str,
        status: str,
        labels: List[str],
        assignees: List[str],
        created_at: datetime,
        updated_at: datetime,
        metadata: Dict[str, Any]
    ):
        self.id = id
        self.title = title
        self.description = description
        self.status = status
        self.labels = labels
        self.assignees = assignees
        self.created_at = created_at
        self.updated_at = updated_at
        self.metadata = metadata

class ITicketSystem(ABC):
    """
    Output port interface for ticket/work item systems.

    Implementations connect to external issue tracking systems
    (GitHub Issues, Jira, local files, etc.) and translate between
    the external representation and the domain's WorkItem model.
    """

    @abstractmethod
    async def get_work_item(self, item_id: str) -> WorkItem:
        """
        Retrieve a work item by ID.

        Args:
            item_id: Unique identifier for the work item

        Returns:
            WorkItem domain object

        Raises:
            WorkItemNotFoundError: If item doesn't exist
            TicketSystemError: For communication/API errors
        """
        pass

    @abstractmethod
    async def update_work_item(
        self,
        item_id: str,
        updates: Dict[str, Any]
    ) -> WorkItem:
        """
        Update a work item's fields.

        Args:
            item_id: Work item identifier
            updates: Dictionary of field updates
                Common fields: status, labels, assignees, title, description

        Returns:
            Updated WorkItem

        Raises:
            WorkItemNotFoundError: If item doesn't exist
            ValidationError: If updates are invalid
            TicketSystemError: For communication errors
        """
        pass

    @abstractmethod
    async def create_comment(
        self,
        item_id: str,
        comment: str,
        reply_to_id: Optional[str] = None
    ) -> str:
        """
        Create a comment on a work item.

        Args:
            item_id: Work item identifier
            comment: Comment text (markdown supported)
            reply_to_id: Optional ID to reply to (for threading)

        Returns:
            Comment ID

        Raises:
            WorkItemNotFoundError: If item doesn't exist
            TicketSystemError: For communication errors
        """
        pass

    @abstractmethod
    async def get_comments(
        self,
        item_id: str,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve comments for a work item.

        Args:
            item_id: Work item identifier
            since: Optional datetime to filter comments after

        Returns:
            List of comment dictionaries with keys:
                - id: Comment ID
                - author: Comment author
                - body: Comment text
                - created_at: Creation timestamp

        Raises:
            WorkItemNotFoundError: If item doesn't exist
            TicketSystemError: For communication errors
        """
        pass

    @abstractmethod
    async def get_project_board_items(
        self,
        project_id: str,
        column_id: Optional[str] = None
    ) -> List[WorkItem]:
        """
        Get work items from a project board.

        Args:
            project_id: Project board identifier
            column_id: Optional column filter

        Returns:
            List of WorkItem objects

        Raises:
            ProjectNotFoundError: If project doesn't exist
            TicketSystemError: For communication errors
        """
        pass

    @abstractmethod
    async def move_to_column(
        self,
        item_id: str,
        column_id: str,
        project_id: str
    ) -> None:
        """
        Move a work item to a different column on a project board.

        Args:
            item_id: Work item identifier
            column_id: Target column identifier
            project_id: Project board identifier

        Raises:
            WorkItemNotFoundError: If item doesn't exist
            ColumnNotFoundError: If column doesn't exist
            TicketSystemError: For communication errors
        """
        pass

    @abstractmethod
    async def find_parent_item(self, item_id: str) -> Optional[str]:
        """
        Find the parent work item ID if this is a sub-item.

        Args:
            item_id: Work item identifier

        Returns:
            Parent item ID or None if no parent

        Raises:
            WorkItemNotFoundError: If item doesn't exist
            TicketSystemError: For communication errors
        """
        pass

    @abstractmethod
    async def create_work_item(
        self,
        title: str,
        description: str,
        labels: Optional[List[str]] = None,
        parent_id: Optional[str] = None
    ) -> WorkItem:
        """
        Create a new work item.

        Args:
            title: Work item title
            description: Work item description (markdown)
            labels: Optional list of labels
            parent_id: Optional parent item for sub-items

        Returns:
            Created WorkItem

        Raises:
            ValidationError: If input is invalid
            TicketSystemError: For communication errors
        """
        pass
```

---

## Adapter Implementations

### 1. GitHub Issues Adapter (Production)

#### Purpose
Connect to GitHub Issues and Projects v2 for work item management.

#### Dependencies
- GitHub REST API v3
- GitHub GraphQL API v4
- GitHub App authentication or Personal Access Token

#### Configuration

```python
@dataclass
class GitHubIssuesConfig:
    """Configuration for GitHub Issues adapter."""

    # Authentication
    auth_type: str  # 'app' or 'token'
    github_token: Optional[str] = None
    github_app_id: Optional[str] = None
    github_app_installation_id: Optional[str] = None
    github_app_private_key_path: Optional[str] = None

    # Repository
    organization: str
    repository: str

    # API endpoints
    api_base_url: str = "https://api.github.com"
    graphql_url: str = "https://api.github.com/graphql"

    # Rate limiting
    max_retries: int = 3
    retry_delay: float = 1.0

    # Caching
    cache_ttl: int = 300  # 5 minutes
```

#### Implementation

```python
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
from gql import gql, Client
from gql.transport.httpx import HTTPXTransport

class GitHubIssuesAdapter(ITicketSystem):
    """Production adapter for GitHub Issues."""

    def __init__(
        self,
        config: GitHubIssuesConfig,
        http_client: Optional[httpx.AsyncClient] = None
    ):
        self.config = config
        self.http_client = http_client or httpx.AsyncClient(
            base_url=config.api_base_url,
            headers=self._build_headers(),
            timeout=30.0
        )

        # GraphQL client for Projects v2
        self.graphql_client = Client(
            transport=HTTPXTransport(
                url=config.graphql_url,
                headers=self._build_headers()
            )
        )

        # Simple in-memory cache
        self._cache: Dict[str, tuple[datetime, Any]] = {}

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers with authentication."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

        if self.config.auth_type == 'token':
            headers["Authorization"] = f"Bearer {self.config.github_token}"
        elif self.config.auth_type == 'app':
            # Generate JWT and get installation token
            token = self._get_installation_token()
            headers["Authorization"] = f"Bearer {token}"

        return headers

    async def get_work_item(self, item_id: str) -> WorkItem:
        """Retrieve GitHub issue by number."""
        # Check cache
        cache_key = f"issue:{item_id}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        # Fetch from API
        response = await self.http_client.get(
            f"/repos/{self.config.organization}/{self.config.repository}/issues/{item_id}"
        )

        if response.status_code == 404:
            raise WorkItemNotFoundError(f"Issue {item_id} not found")
        elif response.status_code != 200:
            raise TicketSystemError(
                f"GitHub API error: {response.status_code} {response.text}"
            )

        issue_data = response.json()
        work_item = self._map_issue_to_work_item(issue_data)

        # Cache result
        self._add_to_cache(cache_key, work_item)

        return work_item

    async def update_work_item(
        self,
        item_id: str,
        updates: Dict[str, Any]
    ) -> WorkItem:
        """Update GitHub issue."""
        # Map domain updates to GitHub API format
        github_updates = {}

        if 'status' in updates:
            github_updates['state'] = 'open' if updates['status'] != 'closed' else 'closed'

        if 'labels' in updates:
            github_updates['labels'] = updates['labels']

        if 'assignees' in updates:
            github_updates['assignees'] = updates['assignees']

        if 'title' in updates:
            github_updates['title'] = updates['title']

        if 'description' in updates:
            github_updates['body'] = updates['description']

        # Send update
        response = await self.http_client.patch(
            f"/repos/{self.config.organization}/{self.config.repository}/issues/{item_id}",
            json=github_updates
        )

        if response.status_code == 404:
            raise WorkItemNotFoundError(f"Issue {item_id} not found")
        elif response.status_code != 200:
            raise TicketSystemError(
                f"GitHub API error: {response.status_code} {response.text}"
            )

        issue_data = response.json()
        work_item = self._map_issue_to_work_item(issue_data)

        # Invalidate cache
        self._remove_from_cache(f"issue:{item_id}")

        return work_item

    async def create_comment(
        self,
        item_id: str,
        comment: str,
        reply_to_id: Optional[str] = None
    ) -> str:
        """Create comment on GitHub issue."""
        # GitHub doesn't support native comment threading,
        # so we format threaded comments with markdown
        body = comment
        if reply_to_id:
            body = f"> Reply to comment {reply_to_id}\n\n{comment}"

        response = await self.http_client.post(
            f"/repos/{self.config.organization}/{self.config.repository}/issues/{item_id}/comments",
            json={"body": body}
        )

        if response.status_code == 404:
            raise WorkItemNotFoundError(f"Issue {item_id} not found")
        elif response.status_code != 201:
            raise TicketSystemError(
                f"GitHub API error: {response.status_code} {response.text}"
            )

        comment_data = response.json()
        return str(comment_data['id'])

    async def get_comments(
        self,
        item_id: str,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve comments for GitHub issue."""
        params = {}
        if since:
            params['since'] = since.isoformat()

        response = await self.http_client.get(
            f"/repos/{self.config.organization}/{self.config.repository}/issues/{item_id}/comments",
            params=params
        )

        if response.status_code == 404:
            raise WorkItemNotFoundError(f"Issue {item_id} not found")
        elif response.status_code != 200:
            raise TicketSystemError(
                f"GitHub API error: {response.status_code} {response.text}"
            )

        comments_data = response.json()
        return [
            {
                'id': str(comment['id']),
                'author': comment['user']['login'],
                'body': comment['body'],
                'created_at': datetime.fromisoformat(
                    comment['created_at'].replace('Z', '+00:00')
                )
            }
            for comment in comments_data
        ]

    async def get_project_board_items(
        self,
        project_id: str,
        column_id: Optional[str] = None
    ) -> List[WorkItem]:
        """Get items from GitHub Projects v2 board."""
        # Use GraphQL for Projects v2
        query = gql("""
            query GetProjectItems($projectId: ID!, $columnId: ID) {
              node(id: $projectId) {
                ... on ProjectV2 {
                  items(first: 100) {
                    nodes {
                      id
                      content {
                        ... on Issue {
                          number
                          title
                          body
                          state
                          labels(first: 10) {
                            nodes {
                              name
                            }
                          }
                          assignees(first: 5) {
                            nodes {
                              login
                            }
                          }
                          createdAt
                          updatedAt
                        }
                      }
                      fieldValueByName(name: "Status") {
                        ... on ProjectV2ItemFieldSingleSelectValue {
                          optionId
                          name
                        }
                      }
                    }
                  }
                }
              }
            }
        """)

        result = self.graphql_client.execute(
            query,
            variable_values={
                "projectId": project_id,
                "columnId": column_id
            }
        )

        items = result['node']['items']['nodes']
        work_items = []

        for item in items:
            if not item['content']:
                continue

            issue = item['content']
            status = item.get('fieldValueByName', {}).get('name', 'Unknown')

            # Filter by column if specified
            if column_id and item.get('fieldValueByName', {}).get('optionId') != column_id:
                continue

            work_item = WorkItem(
                id=str(issue['number']),
                title=issue['title'],
                description=issue['body'] or '',
                status=status,
                labels=[label['name'] for label in issue['labels']['nodes']],
                assignees=[assignee['login'] for assignee in issue['assignees']['nodes']],
                created_at=datetime.fromisoformat(issue['createdAt'].replace('Z', '+00:00')),
                updated_at=datetime.fromisoformat(issue['updatedAt'].replace('Z', '+00:00')),
                metadata={'project_item_id': item['id']}
            )
            work_items.append(work_item)

        return work_items

    async def move_to_column(
        self,
        item_id: str,
        column_id: str,
        project_id: str
    ) -> None:
        """Move issue to different column on Projects v2 board."""
        # GraphQL mutation to update project item field
        mutation = gql("""
            mutation UpdateProjectItemField(
                $projectId: ID!,
                $itemId: ID!,
                $fieldId: ID!,
                $valueId: String!
            ) {
              updateProjectV2ItemFieldValue(input: {
                projectId: $projectId
                itemId: $itemId
                fieldId: $fieldId
                value: {
                  singleSelectOptionId: $valueId
                }
              }) {
                projectV2Item {
                  id
                }
              }
            }
        """)

        # Get field ID for Status field (cached or queried)
        status_field_id = await self._get_status_field_id(project_id)

        # Get project item ID for this issue
        project_item_id = await self._get_project_item_id(project_id, item_id)

        self.graphql_client.execute(
            mutation,
            variable_values={
                "projectId": project_id,
                "itemId": project_item_id,
                "fieldId": status_field_id,
                "valueId": column_id
            }
        )

    async def find_parent_item(self, item_id: str) -> Optional[str]:
        """Find parent issue by parsing issue body for parent references."""
        issue = await self.get_work_item(item_id)

        # Look for parent reference patterns in description
        # Pattern: "Parent: #123" or "Part of #456"
        import re
        patterns = [
            r'Parent:\s*#(\d+)',
            r'Part of\s*#(\d+)',
            r'Sub-issue of\s*#(\d+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, issue.description, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    async def create_work_item(
        self,
        title: str,
        description: str,
        labels: Optional[List[str]] = None,
        parent_id: Optional[str] = None
    ) -> WorkItem:
        """Create new GitHub issue."""
        body = description
        if parent_id:
            body = f"Parent: #{parent_id}\n\n{description}"

        issue_data = {
            "title": title,
            "body": body
        }

        if labels:
            issue_data["labels"] = labels

        response = await self.http_client.post(
            f"/repos/{self.config.organization}/{self.config.repository}/issues",
            json=issue_data
        )

        if response.status_code != 201:
            raise TicketSystemError(
                f"GitHub API error: {response.status_code} {response.text}"
            )

        issue = response.json()
        return self._map_issue_to_work_item(issue)

    def _map_issue_to_work_item(self, issue_data: Dict[str, Any]) -> WorkItem:
        """Map GitHub issue JSON to WorkItem domain model."""
        return WorkItem(
            id=str(issue_data['number']),
            title=issue_data['title'],
            description=issue_data['body'] or '',
            status=issue_data['state'],
            labels=[label['name'] for label in issue_data.get('labels', [])],
            assignees=[assignee['login'] for assignee in issue_data.get('assignees', [])],
            created_at=datetime.fromisoformat(
                issue_data['created_at'].replace('Z', '+00:00')
            ),
            updated_at=datetime.fromisoformat(
                issue_data['updated_at'].replace('Z', '+00:00')
            ),
            metadata={
                'url': issue_data['html_url'],
                'comments_count': issue_data.get('comments', 0)
            }
        )

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key not in self._cache:
            return None

        timestamp, value = self._cache[key]
        if (datetime.utcnow() - timestamp).total_seconds() > self.config.cache_ttl:
            del self._cache[key]
            return None

        return value

    def _add_to_cache(self, key: str, value: Any) -> None:
        """Add value to cache with current timestamp."""
        self._cache[key] = (datetime.utcnow(), value)

    def _remove_from_cache(self, key: str) -> None:
        """Remove value from cache."""
        self._cache.pop(key, None)

    async def _get_status_field_id(self, project_id: str) -> str:
        """Get the field ID for the Status field on a project."""
        # Implementation would query Projects v2 fields
        # Cached to avoid repeated queries
        pass

    async def _get_project_item_id(
        self,
        project_id: str,
        issue_number: str
    ) -> str:
        """Get the project item ID for an issue on a specific project board."""
        # Implementation would query Projects v2 items
        pass
```

---

### 2. In-Memory Ticket Adapter (Testing/Mock)

#### Purpose
Provide a fully functional in-memory ticket system for testing and simulation without external dependencies.

#### Implementation

```python
from typing import Dict, List, Optional
from datetime import datetime
import uuid

class InMemoryTicketAdapter(ITicketSystem):
    """Mock adapter for testing without GitHub."""

    def __init__(self):
        # Storage
        self._work_items: Dict[str, WorkItem] = {}
        self._comments: Dict[str, List[Dict[str, Any]]] = {}
        self._projects: Dict[str, Dict[str, List[str]]] = {}  # {project_id: {column_id: [item_ids]}}
        self._parent_relationships: Dict[str, str] = {}  # {child_id: parent_id}

        # Auto-increment for IDs
        self._next_id = 1

    async def get_work_item(self, item_id: str) -> WorkItem:
        """Retrieve work item from memory."""
        if item_id not in self._work_items:
            raise WorkItemNotFoundError(f"Work item {item_id} not found")

        return self._work_items[item_id]

    async def update_work_item(
        self,
        item_id: str,
        updates: Dict[str, Any]
    ) -> WorkItem:
        """Update work item in memory."""
        if item_id not in self._work_items:
            raise WorkItemNotFoundError(f"Work item {item_id} not found")

        item = self._work_items[item_id]

        # Apply updates
        if 'status' in updates:
            item.status = updates['status']
        if 'labels' in updates:
            item.labels = updates['labels']
        if 'assignees' in updates:
            item.assignees = updates['assignees']
        if 'title' in updates:
            item.title = updates['title']
        if 'description' in updates:
            item.description = updates['description']

        item.updated_at = datetime.utcnow()

        return item

    async def create_comment(
        self,
        item_id: str,
        comment: str,
        reply_to_id: Optional[str] = None
    ) -> str:
        """Create comment in memory."""
        if item_id not in self._work_items:
            raise WorkItemNotFoundError(f"Work item {item_id} not found")

        comment_id = str(uuid.uuid4())
        comment_data = {
            'id': comment_id,
            'author': 'test-user',
            'body': comment,
            'created_at': datetime.utcnow(),
            'reply_to_id': reply_to_id
        }

        if item_id not in self._comments:
            self._comments[item_id] = []

        self._comments[item_id].append(comment_data)

        return comment_id

    async def get_comments(
        self,
        item_id: str,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve comments from memory."""
        if item_id not in self._work_items:
            raise WorkItemNotFoundError(f"Work item {item_id} not found")

        comments = self._comments.get(item_id, [])

        if since:
            comments = [
                c for c in comments
                if c['created_at'] > since
            ]

        return comments

    async def get_project_board_items(
        self,
        project_id: str,
        column_id: Optional[str] = None
    ) -> List[WorkItem]:
        """Get items from memory project board."""
        if project_id not in self._projects:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        project = self._projects[project_id]

        if column_id:
            if column_id not in project:
                raise ColumnNotFoundError(f"Column {column_id} not found")
            item_ids = project[column_id]
        else:
            # All items across all columns
            item_ids = []
            for column_items in project.values():
                item_ids.extend(column_items)

        return [self._work_items[item_id] for item_id in item_ids]

    async def move_to_column(
        self,
        item_id: str,
        column_id: str,
        project_id: str
    ) -> None:
        """Move item to different column in memory."""
        if item_id not in self._work_items:
            raise WorkItemNotFoundError(f"Work item {item_id} not found")

        if project_id not in self._projects:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        project = self._projects[project_id]

        if column_id not in project:
            raise ColumnNotFoundError(f"Column {column_id} not found")

        # Remove from all columns
        for col_items in project.values():
            if item_id in col_items:
                col_items.remove(item_id)

        # Add to target column
        project[column_id].append(item_id)

    async def find_parent_item(self, item_id: str) -> Optional[str]:
        """Find parent item from memory relationships."""
        return self._parent_relationships.get(item_id)

    async def create_work_item(
        self,
        title: str,
        description: str,
        labels: Optional[List[str]] = None,
        parent_id: Optional[str] = None
    ) -> WorkItem:
        """Create work item in memory."""
        item_id = str(self._next_id)
        self._next_id += 1

        work_item = WorkItem(
            id=item_id,
            title=title,
            description=description,
            status='open',
            labels=labels or [],
            assignees=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            metadata={}
        )

        self._work_items[item_id] = work_item

        if parent_id:
            self._parent_relationships[item_id] = parent_id

        return work_item

    # Test helper methods

    def add_test_item(self, work_item: WorkItem) -> None:
        """Add a pre-constructed work item for testing."""
        self._work_items[work_item.id] = work_item

    def create_test_project(
        self,
        project_id: str,
        columns: List[str]
    ) -> None:
        """Create a test project board."""
        self._projects[project_id] = {
            column_id: [] for column_id in columns
        }

    def add_item_to_project(
        self,
        project_id: str,
        column_id: str,
        item_id: str
    ) -> None:
        """Add item to project column for testing."""
        if project_id not in self._projects:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        if column_id not in self._projects[project_id]:
            raise ColumnNotFoundError(f"Column {column_id} not found")

        self._projects[project_id][column_id].append(item_id)

    def reset(self) -> None:
        """Reset all state for testing."""
        self._work_items.clear()
        self._comments.clear()
        self._projects.clear()
        self._parent_relationships.clear()
        self._next_id = 1
```

---

## Exception Definitions

```python
class TicketSystemError(Exception):
    """Base exception for ticket system errors."""
    pass

class WorkItemNotFoundError(TicketSystemError):
    """Work item does not exist."""
    pass

class ProjectNotFoundError(TicketSystemError):
    """Project board does not exist."""
    pass

class ColumnNotFoundError(TicketSystemError):
    """Project board column does not exist."""
    pass

class ValidationError(TicketSystemError):
    """Input validation failed."""
    pass
```

---

## Adapter Registry

```python
from typing import Dict, Type

class TicketSystemRegistry:
    """Registry for ticket system adapter implementations."""

    def __init__(self):
        self._adapters: Dict[str, Type[ITicketSystem]] = {}

    def register(self, name: str, adapter_class: Type[ITicketSystem]) -> None:
        """Register an adapter implementation."""
        self._adapters[name] = adapter_class

    def create(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None
    ) -> ITicketSystem:
        """Create an adapter instance by name."""
        if name not in self._adapters:
            raise ValueError(f"Unknown ticket system adapter: {name}")

        adapter_class = self._adapters[name]

        if config:
            return adapter_class(**config)
        else:
            return adapter_class()

    def list_adapters(self) -> List[str]:
        """List registered adapter names."""
        return list(self._adapters.keys())

# Global registry instance
ticket_system_registry = TicketSystemRegistry()

# Register built-in adapters
ticket_system_registry.register('github', GitHubIssuesAdapter)
ticket_system_registry.register('in-memory', InMemoryTicketAdapter)
```

---

## Usage Examples

### Production Usage

```python
from config import GitHubIssuesConfig

# Create GitHub adapter
config = GitHubIssuesConfig(
    auth_type='token',
    github_token=os.getenv('GITHUB_TOKEN'),
    organization='myorg',
    repository='myrepo'
)

ticket_system = GitHubIssuesAdapter(config)

# Retrieve work item
work_item = await ticket_system.get_work_item('123')
print(f"Title: {work_item.title}")

# Create comment
comment_id = await ticket_system.create_comment(
    '123',
    "Analysis complete. See attached design document."
)

# Update status
await ticket_system.update_work_item('123', {'status': 'in_progress'})
```

### Testing Usage

```python
# Create in-memory adapter
ticket_system = InMemoryTicketAdapter()

# Set up test data
test_item = WorkItem(
    id='1',
    title='Test Feature',
    description='Implement test feature',
    status='open',
    labels=['enhancement'],
    assignees=[],
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow(),
    metadata={}
)
ticket_system.add_test_item(test_item)

# Create test project board
ticket_system.create_test_project('project-1', ['todo', 'in_progress', 'done'])
ticket_system.add_item_to_project('project-1', 'todo', '1')

# Test workflow
items = await ticket_system.get_project_board_items('project-1', 'todo')
assert len(items) == 1

await ticket_system.move_to_column('1', 'in_progress', 'project-1')

items = await ticket_system.get_project_board_items('project-1', 'in_progress')
assert len(items) == 1
```

### Registry Usage

```python
# Using registry for dynamic selection
adapter_name = config.get('ticket_system', 'github')

ticket_system = ticket_system_registry.create(
    adapter_name,
    config.get('ticket_system_config')
)

# Works with any registered adapter
work_item = await ticket_system.get_work_item('123')
```

---

## Testing Strategy

### Unit Tests

```python
import pytest

class TestGitHubIssuesAdapter:
    """Unit tests for GitHub adapter."""

    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        # Use respx or similar to mock httpx
        pass

    @pytest.mark.asyncio
    async def test_get_work_item_success(self, mock_http_client):
        """Test successful work item retrieval."""
        # Mock API response
        # Create adapter
        # Call get_work_item
        # Assert correct WorkItem returned
        pass

    @pytest.mark.asyncio
    async def test_get_work_item_not_found(self, mock_http_client):
        """Test work item not found error."""
        # Mock 404 response
        # Create adapter
        # Assert WorkItemNotFoundError raised
        pass

class TestInMemoryTicketAdapter:
    """Unit tests for in-memory adapter."""

    @pytest.fixture
    def adapter(self):
        """Create fresh adapter for each test."""
        return InMemoryTicketAdapter()

    @pytest.mark.asyncio
    async def test_create_and_retrieve_work_item(self, adapter):
        """Test creating and retrieving work items."""
        # Create work item
        # Retrieve it
        # Assert fields match
        pass

    @pytest.mark.asyncio
    async def test_project_board_operations(self, adapter):
        """Test project board item management."""
        # Create project
        # Add items to columns
        # Move items between columns
        # Assert correct state
        pass
```

### Integration Tests

```python
class TestTicketSystemIntegration:
    """Integration tests with real GitHub API (optional)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_workflow_with_github(self):
        """Test complete workflow with real GitHub."""
        # Requires GITHUB_TOKEN and test repository
        # Create issue
        # Add comments
        # Update status
        # Clean up
        pass
```

---

## Migration Path

### From Legacy to New Design

1. **Extract interface** from existing `GitHubIntegration` class
2. **Implement `ITicketSystem`** with GitHub adapter
3. **Create in-memory adapter** for testing
4. **Update application services** to depend on `ITicketSystem` interface
5. **Inject adapters** via dependency injection
6. **Add adapter registry** for configuration-based selection
7. **Migrate tests** to use in-memory adapter

---

## Future Extensibility

### Additional Adapters

**Jira Adapter**:
- Implement `ITicketSystem` interface
- Use Jira REST API
- Map Jira issue types to WorkItem
- Handle Jira-specific workflow states

**Markdown File Adapter**:
- Read/write markdown files in a directory
- Parse YAML front matter for metadata
- Use file naming conventions for IDs
- Track state in a separate index file

---

## Performance Considerations

### Caching
- Cache frequently accessed work items (5-minute TTL)
- Invalidate cache on updates
- Consider Redis for distributed caching

### Rate Limiting
- Respect GitHub API rate limits (5000 req/hour for authenticated)
- Implement exponential backoff on rate limit errors
- Use conditional requests (ETags) to save quota

### Batching
- Batch multiple work item retrievals into single GraphQL query
- Use Projects v2 GraphQL API for efficient board queries

---

## Security Considerations

### Authentication
- Never log tokens or credentials
- Use environment variables for secrets
- Support both GitHub App and Personal Access Token
- Rotate tokens regularly

### Authorization
- Validate permissions before operations
- Handle 403 Forbidden errors gracefully
- Audit sensitive operations (issue updates, deletions)

### Data Sanitization
- Sanitize markdown input to prevent injection
- Validate issue numbers and IDs
- Escape user input in GraphQL queries

---

## Observability

### Metrics
- Track API call latency (p50, p95, p99)
- Count API errors by type (404, 403, 500, etc.)
- Monitor rate limit consumption
- Cache hit/miss ratios

### Logging
- Log all API calls with request ID
- Log errors with full context
- Structured logging with correlation IDs

### Events
- Emit events for work item state changes
- Track adapter operations in event store
- Enable audit trail for compliance
