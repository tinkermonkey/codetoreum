# Core System Output Ports

This documentation covers the fundamental output ports that abstract basic system operations: ticket management, version control, containers, and LLM providers.

## Purpose

The core system output ports define contracts for the foundational external systems that Codetoreum depends on:

- **ITicketSystem**: Vendor-agnostic interface for issue/ticket management (GitHub Issues, Jira, Linear, etc.)
- **IVersionControlService**: Abstract version control operations (Git, Mercurial, etc.)
- **IContainer**: Container runtime abstraction (Docker, Kubernetes, etc.) for agent execution
- **ILLMProvider**: Language model provider abstraction (Claude, GPT-4, etc.) for agent interactions

These ports enable vendor-agnostic implementations and seamless system switching.

## Interface Definition

### ITicketSystem

```python
class ITicketSystem(ABC):
    """
    Interface for ticket/issue management systems.
    
    Vendor-agnostic abstraction over GitHub Issues, Jira, Linear, etc.
    Supports work item CRUD, comments, relationships, webhooks, and streaming.
    """
    
    # Work Item Operations
    @abstractmethod
    async def get_work_item(self, item_id: WorkItemId) -> WorkItem:
        """Retrieve a work item by ID."""
        
    @abstractmethod
    async def create_work_item(self, title: str, description: str, project_id: ProjectId,
                              labels: list[str] | None = None, assignee: UserId | None = None,
                              priority: WorkItemPriority | None = None, metadata: dict[str, Any] | None = None,
                              parent_issue_id: str | None = None, pr_id: str | None = None,
                              discussion_id: str | None = None) -> WorkItem:
        """Create a new work item."""
        
    @abstractmethod
    async def get_child_issues(self, parent_id: WorkItemId) -> list[WorkItem]:
        """Retrieve all child work items for a given parent."""
        
    @abstractmethod
    async def update_work_item(self, item_id: WorkItemId, updates: dict[str, Any]) -> WorkItem:
        """Update an existing work item."""
        
    @abstractmethod
    async def delete_work_item(self, item_id: WorkItemId) -> None:
        """Delete a work item."""
        
    @abstractmethod
    async def update_status(self, item_id: WorkItemId, status: WorkItemStatus, reason: str | None = None) -> WorkItem:
        """Update work item status."""
    
    # Query Operations
    @abstractmethod
    async def list_work_items(self, project_id: ProjectId | None = None, status: WorkItemStatus | None = None,
                             assignee: UserId | None = None, labels: list[str] | None = None,
                             created_after: datetime | None = None, updated_after: datetime | None = None,
                             limit: int = 100, offset: int = 0) -> list[WorkItem]:
        """List work items with filters."""
        
    @abstractmethod
    async def search_work_items(self, query: str, project_id: ProjectId | None = None, limit: int = 100) -> list[WorkItem]:
        """Full-text search for work items."""
        
    @abstractmethod
    async def get_work_item_stream(self, project_id: ProjectId | None = None, since: datetime | None = None) -> AsyncIterator[WorkItem]:
        """Stream work item updates in real-time."""
    
    # Comment Operations
    @abstractmethod
    async def add_comment(self, item_id: WorkItemId, body: str, author: UserId | None = None,
                         metadata: dict[str, Any] | None = None) -> Comment:
        """Add a comment to a work item."""
        
    @abstractmethod
    async def get_comments(self, item_id: WorkItemId, since: datetime | None = None, limit: int = 100) -> list[Comment]:
        """Get comments for a work item."""
    
    # Relationship Operations
    @abstractmethod
    async def link_work_items(self, source_id: WorkItemId, target_id: WorkItemId, relationship: str) -> None:
        """Create relationship between work items."""
        
    @abstractmethod
    async def get_related_items(self, item_id: WorkItemId, relationship: str | None = None) -> list[WorkItem]:
        """Get related work items."""
    
    # Webhook Operations
    @abstractmethod
    async def register_webhook(self, url: str, events: list[str], project_id: ProjectId | None = None) -> str:
        """Register a webhook for events."""
        
    @abstractmethod
    async def unregister_webhook(self, webhook_id: str) -> None:
        """Unregister a webhook."""
```

### IVersionControlService

```python
class IVersionControlService(ABC):
    """
    Abstract version control operations (Git, Mercurial, etc.).
    
    Handles clone, checkout, commit, push operations on repositories.
    """
    
    @abstractmethod
    async def clone_repository(self, repo_url: str, target_path: str) -> Repository:
        """Clone a repository."""
        pass
    
    @abstractmethod
    async def create_branch(self, repo_path: str, branch_name: str, from_branch: str = "main") -> Branch:
        """Create feature branch."""
        pass
    
    @abstractmethod
    async def checkout_branch(self, repo_path: str, branch_name: str) -> None:
        """Checkout a branch."""
        pass
    
    @abstractmethod
    async def commit(self, repo_path: str, message: str, files: list[str] | None = None) -> Commit:
        """Create commit with message."""
        pass
    
    @abstractmethod
    async def push(self, repo_path: str, branch_name: str, force: bool = False) -> PushResult:
        """Push commits to remote."""
        pass
    
    @abstractmethod
    async def get_branches(self, repo_path: str) -> list[Branch]:
        """List existing branches."""
        pass
    
    @abstractmethod
    async def get_commit(self, repo_path: str, commit_hash: str) -> Commit:
        """Get commit details."""
        pass
```

### IContainer

```python
class IContainer(ABC):
    """
    Container runtime abstraction (Docker, Kubernetes, etc.).
    
    Manages agent execution environments and containerized workloads.
    """
    
    @abstractmethod
    async def run_command(self, command: str, container_id: str, timeout: int | None = None) -> CommandResult:
        """Execute command in container."""
        pass
    
    @abstractmethod
    async def mount_directory(self, container_id: str, host_path: str, container_path: str, read_only: bool = False) -> None:
        """Mount host directory into container."""
        pass
    
    @abstractmethod
    async def cleanup(self, container_id: str) -> None:
        """Clean up container resources."""
        pass
    
    @abstractmethod
    async def get_logs(self, container_id: str, tail: int | None = None) -> str:
        """Retrieve container output."""
        pass
    
    @abstractmethod
    async def get_status(self, container_id: str) -> ContainerStatus:
        """Get container status."""
        pass
    
    @abstractmethod
    async def create_container(self, image: str, name: str, env_vars: dict[str, str] | None = None) -> Container:
        """Create and start a new container."""
        pass
```

### ILLMProvider

```python
class ILLMProvider(ABC):
    """
    Language model provider abstraction (Claude, GPT-4, etc.).
    
    Orchestrates agent interactions with LLM APIs.
    """
    
    @abstractmethod
    async def execute_agent(self, context: AgentContext) -> AgentExecutionResult:
        """Run agent with context."""
        pass
    
    @abstractmethod
    async def converse(self, session_id: str, messages: list[Message]) -> ConversationResult:
        """Multi-turn conversation."""
        pass
    
    @abstractmethod
    async def validate_context_window(self, tokens: int) -> bool:
        """Check token budget."""
        pass
    
    @abstractmethod
    async def get_model_info(self) -> ModelInfo:
        """Get model capabilities and limits."""
        pass
    
    @abstractmethod
    async def stream_response(self, prompt: str) -> AsyncIterator[str]:
        """Stream response tokens."""
        pass
```

### IRepository

```python
class IRepository(ABC):
    """
    Generic repository operations for version-controlled source code.
    
    Abstracts git operations (clone, branch, commit, push, merge, etc.)
    """
    
    @abstractmethod
    async def clone(self, repo_url: str, repo_path: Path, branch: str | None = None) -> None:
        """Clone a repository."""
        
    @abstractmethod
    async def checkout(self, repo_path: Path, branch: str) -> None:
        """Checkout a branch."""
        
    @abstractmethod
    async def create_branch(self, repo_path: Path, branch_name: str, from_branch: str | None = None) -> None:
        """Create a new branch."""
        
    @abstractmethod
    async def stage_files(self, repo_path: Path, files: list[str]) -> None:
        """Stage files for commit."""
        
    @abstractmethod
    async def commit(self, repo_path: Path, message: str, author: CommitAuthor | None = None) -> CommitHash:
        """Create a commit."""
        
    @abstractmethod
    async def push(self, repo_path: Path, branch: str | None = None, force: bool = False) -> None:
        """Push commits to remote."""
        
    @abstractmethod
    async def pull(self, repo_path: Path, branch: str | None = None) -> None:
        """Pull changes from remote."""
        
    @abstractmethod
    async def fetch(self, repo_path: Path) -> None:
        """Fetch from remote without merging."""
        
    @abstractmethod
    async def diff(self, repo_path: Path, base_branch: str, head_branch: str) -> str:
        """Get diff between branches."""
        
    @abstractmethod
    async def status(self, repo_path: Path) -> RepositoryStatus:
        """Get repository status."""
        
    @abstractmethod
    async def list_branches(self, repo_path: Path, remote: bool = False) -> list[BranchName]:
        """List branches."""
        
    @abstractmethod
    async def merge(self, repo_path: Path, source_branch: str, target_branch: str) -> MergeResult:
        """Merge branch."""
        
    @abstractmethod
    async def get_file_content(self, repo_path: Path, file_path: str, ref: str | None = None) -> bytes:
        """Get file content at ref."""
        
    @abstractmethod
    async def get_commit_info(self, repo_path: Path, commit_hash: CommitHash) -> CommitInfo:
        """Get commit information."""
        
    @abstractmethod
    async def get_commit_history(self, repo_path: Path, max_count: int = 50) -> list[CommitInfo]:
        """Get commit history."""
        
    @abstractmethod
    async def add_remote(self, repo_path: Path, name: str, url: str) -> None:
        """Add remote repository."""
        
    @abstractmethod
    async def remove_remote(self, repo_path: Path, name: str) -> None:
        """Remove remote repository."""
```

## Methods

### ITicketSystem Methods (15 methods)

| Method | Parameters | Return Type | Description |
|---|---|---|---|
| `get_work_item()` | `item_id: WorkItemId` | `WorkItem` | Retrieve work item by ID |
| `create_work_item()` | `title, description, project_id, labels, assignee, priority, metadata, parent_issue_id, pr_id, discussion_id` | `WorkItem` | Create new work item with optional parent/PR/discussion links |
| `get_child_issues()` | `parent_id: WorkItemId` | `list[WorkItem]` | Get child issues for parent |
| `update_work_item()` | `item_id, updates: dict` | `WorkItem` | Update work item properties |
| `delete_work_item()` | `item_id: WorkItemId` | `None` | Delete a work item |
| `update_status()` | `item_id, status, reason` | `WorkItem` | Update work item status with optional reason |
| `list_work_items()` | `project_id, status, assignee, labels, created_after, updated_after, limit, offset` | `list[WorkItem]` | List work items with comprehensive filtering |
| `search_work_items()` | `query, project_id, limit` | `list[WorkItem]` | Full-text search for work items |
| `get_work_item_stream()` | `project_id, since` | `AsyncIterator[WorkItem]` | Stream work item updates in real-time |
| `add_comment()` | `item_id, body, author, metadata` | `Comment` | Add comment to work item |
| `get_comments()` | `item_id, since, limit` | `list[Comment]` | Get comments with pagination and time filter |
| `link_work_items()` | `source_id, target_id, relationship` | `None` | Create relationship between work items |
| `get_related_items()` | `item_id, relationship` | `list[WorkItem]` | Get related work items optionally filtered by relationship |
| `register_webhook()` | `url, events, project_id` | `str` | Register webhook, returns webhook ID |
| `unregister_webhook()` | `webhook_id` | `None` | Unregister webhook by ID |

### IVersionControlService Methods

| Method | Parameters | Return Type | Description |
|---|---|---|---|
| `clone_repository()` | `repo_url, target_path` | `Repository` | Clone a repository |
| `create_branch()` | `repo_path, branch_name, from_branch` | `Branch` | Create feature branch |
| `checkout_branch()` | `repo_path, branch_name` | `None` | Switch to branch |
| `commit()` | `repo_path, message, files` | `Commit` | Create commit |
| `push()` | `repo_path, branch_name, force` | `PushResult` | Push commits to remote |
| `get_branches()` | `repo_path` | `list[Branch]` | List branches |
| `get_commit()` | `repo_path, commit_hash` | `Commit` | Get commit details |

### IContainer Methods

| Method | Parameters | Return Type | Description |
|---|---|---|---|
| `run_command()` | `command, container_id, timeout` | `CommandResult` | Execute command in container |
| `mount_directory()` | `container_id, host_path, container_path, read_only` | `None` | Mount host directory |
| `cleanup()` | `container_id` | `None` | Clean up resources |
| `get_logs()` | `container_id, tail` | `str` | Get container logs |
| `get_status()` | `container_id` | `ContainerStatus` | Get container status |
| `create_container()` | `image, name, env_vars` | `Container` | Create and start container |

### ILLMProvider Methods

| Method | Parameters | Return Type | Description |
|---|---|---|---|
| `execute_agent()` | `context: AgentContext` | `AgentExecutionResult` | Run agent with context |
| `converse()` | `session_id, messages` | `ConversationResult` | Multi-turn conversation |
| `validate_context_window()` | `tokens: int` | `bool` | Validate token budget |
| `get_model_info()` | — | `ModelInfo` | Get model capabilities |
| `stream_response()` | `prompt: str` | `AsyncIterator[str]` | Stream response tokens |

### IRepository Methods (17 methods)

| Method | Parameters | Return Type | Description |
|---|---|---|---|
| `clone()` | `repo_url, repo_path, branch` | `None` | Clone a repository |
| `checkout()` | `repo_path, branch` | `None` | Checkout a branch |
| `create_branch()` | `repo_path, branch_name, from_branch` | `None` | Create a new branch |
| `stage_files()` | `repo_path, files: list[str]` | `None` | Stage files for commit |
| `commit()` | `repo_path, message, author` | `CommitHash` | Create a commit |
| `push()` | `repo_path, branch, force` | `None` | Push commits to remote |
| `pull()` | `repo_path, branch` | `None` | Pull changes from remote |
| `fetch()` | `repo_path` | `None` | Fetch from remote without merging |
| `diff()` | `repo_path, base_branch, head_branch` | `str` | Get diff between branches |
| `status()` | `repo_path` | `RepositoryStatus` | Get repository status |
| `list_branches()` | `repo_path, remote` | `list[BranchName]` | List branches |
| `merge()` | `repo_path, source_branch, target_branch` | `MergeResult` | Merge branch |
| `get_file_content()` | `repo_path, file_path, ref` | `bytes` | Get file content at ref |
| `get_commit_info()` | `repo_path, commit_hash` | `CommitInfo` | Get commit information |
| `get_commit_history()` | `repo_path, max_count` | `list[CommitInfo]` | Get commit history |
| `add_remote()` | `repo_path, name, url` | `None` | Add remote repository |
| `remove_remote()` | `repo_path, name` | `None` | Remove remote repository |

## Events Emitted

These ports do not emit domain events directly. Events are emitted by adapters when state changes occur in external systems.

## Error Contracts

- **ExternalServiceError** — When service communication fails
- **RepositoryNotFoundError** — When repository doesn't exist
- **WorkItemNotFoundError** — When work item doesn't exist
- **ContainerError** — When container operation fails
- **TokenLimitExceededError** — When LLM token budget exceeded
- **TimeoutError** — When external system doesn't respond in time
- **ValidationError** — When input parameters invalid

## Adapter Implementations

| Adapter Class | Type | File Path | Notes |
|---|---|---|---|
| `GitHubTicketAdapter` | Production | `src/codetoreum/adapters/secondary/github_ticket_adapter.py` | GitHub Issues implementation |
| `GitRepositoryAdapter` | Production | `src/codetoreum/adapters/secondary/git_repository_adapter.py` | Git version control operations |
| `DockerContainerAdapter` | Production | `src/codetoreum/adapters/secondary/docker_container_adapter.py` | Docker container runtime |
| `ClaudeCodeAdapter` | Production | `src/codetoreum/adapters/secondary/claude_code_adapter.py` | Claude API provider |
| `DockerContainerRecoveryAdapter` | Production | `src/codetoreum/adapters/secondary/docker_container_recovery_adapter.py` | Docker recovery operations |

## Diagram

```mermaid
classDiagram
    class ITicketSystem {
        <<interface>>
        +get_work_item(item_id) WorkItem
        +create_work_item(...) WorkItem
        +get_child_issues(parent_id) list
        +update_work_item(item_id, updates) WorkItem
        +list_work_items(project_id, filters) list
        +add_comment(item_id, comment) Comment
        +get_comments(item_id) list
    }
    
    class IVersionControlService {
        <<interface>>
        +clone_repository(repo_url, target_path) Repository
        +create_branch(repo_path, branch_name, from_branch) Branch
        +checkout_branch(repo_path, branch_name) None
        +commit(repo_path, message, files) Commit
        +push(repo_path, branch_name, force) PushResult
        +get_branches(repo_path) list
        +get_commit(repo_path, commit_hash) Commit
    }
    
    class IContainer {
        <<interface>>
        +run_command(command, container_id, timeout) CommandResult
        +mount_directory(container_id, host_path, container_path, read_only) None
        +cleanup(container_id) None
        +get_logs(container_id, tail) str
        +get_status(container_id) ContainerStatus
        +create_container(image, name, env_vars) Container
    }
    
    class ILLMProvider {
        <<interface>>
        +execute_agent(context) AgentExecutionResult
        +converse(session_id, messages) ConversationResult
        +validate_context_window(tokens) bool
        +get_model_info() ModelInfo
        +stream_response(prompt) AsyncIterator
    }
    
    class GitHubTicketAdapter {
        +graphql_client: GraphQLClient
    }
    
    class DockerContainerAdapter {
        +docker_client: DockerClient
    }
    
    class ClaudeCodeAdapter {
        +api_client: AnthropicAPI
    }
    
    ITicketSystem <|-- GitHubTicketAdapter: implements
    IContainer <|-- DockerContainerAdapter: implements
    ILLMProvider <|-- ClaudeCodeAdapter: implements
```
