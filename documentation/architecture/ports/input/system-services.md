# System Services Input Ports

This documentation covers the input ports for authentication, audit logging, workspace management, and conversational loop orchestration.

## Purpose

The system services input ports provide:

- **IAuthenticationPort**: User authentication, authorization, and token management
- **IAuditQueryPort**: Access to audit trail and event history
- **IWorkspaceQueryPort**: Query workspace status, usage, and logs
- **IConversationalLoopService**: Multi-turn agent dialogue management

These ports abstract critical cross-cutting system services.

## Interface Definition

### IAuthenticationPort

```python
class IAuthenticationPort(ABC):
    """Input port for authentication and authorization."""

    @abstractmethod
    async def create_user(self, command: CreateUserCommand) -> User:
        """Create a new user."""
        pass

    @abstractmethod
    async def update_user(self, command: UpdateUserCommand) -> User:
        """Update user information."""
        pass

    @abstractmethod
    async def get_user(self, user_id: UUID) -> User:
        """Get user by ID."""
        pass

    @abstractmethod
    async def get_user_by_username(self, username: str) -> User:
        """Get user by username."""
        pass

    @abstractmethod
    async def delete_user(self, user_id: UUID) -> None:
        """Delete user (soft delete)."""
        pass

    @abstractmethod
    async def login(self, command: LoginCommand) -> LoginResult:
        """Authenticate user with credentials."""
        pass

    @abstractmethod
    async def validate_token(self, token: str) -> AuthContext:
        """Validate authentication token."""
        pass

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> LoginResult:
        """Refresh authentication token."""
        pass

    @abstractmethod
    async def create_api_key(self, command: CreateAPIKeyCommand) -> tuple[APIKey, str]:
        """Create API key for programmatic access."""
        pass

    @abstractmethod
    async def validate_api_key(self, key: str) -> AuthContext:
        """Validate API key."""
        pass

    @abstractmethod
    async def revoke_api_key(self, key_id: UUID, requesting_user_id: UUID, is_admin: bool) -> None:
        """Revoke API key."""
        pass

    @abstractmethod
    async def list_api_keys(self, user_id: UUID) -> list[APIKey]:
        """List API keys for user."""
        pass

    @abstractmethod
    async def check_permission(self, auth_context: AuthContext, permission: str) -> bool:
        """Check if user has permission."""
        pass
```

### IAuditQueryPort

```python
class IAuditQueryPort(ABC):
    """Input port for audit log queries."""

    @abstractmethod
    async def query_audit_events(
        self,
        filters: AuditEventFilters | None = None,
        pagination: PaginationParams | None = None
    ) -> AuditEventListResult:
        """Query audit events with filtering."""
        pass

    @abstractmethod
    async def get_audit_trail(self, entity_id: str, entity_type: str) -> AuditTrailResult:
        """Get complete audit trail for entity."""
        pass

    @abstractmethod
    async def get_audit_event(self, event_id: str) -> AuditEvent:
        """Get specific audit event."""
        pass

    @abstractmethod
    async def count_audit_events(self, filters: AuditEventFilters | None = None) -> int:
        """Count audit events matching filters."""
        pass
```

### IWorkspaceQueryPort

```python
class IWorkspaceQueryPort(ABC):
    """Input port for workspace queries."""

    @abstractmethod
    async def get_workspace(self, workspace_id: str) -> WorkspaceInfo:
        """Get workspace by ID."""
        pass

    @abstractmethod
    async def get_workspace_by_execution(self, execution_id: str) -> WorkspaceInfo:
        """Get workspace for execution."""
        pass

    @abstractmethod
    async def list_workspaces(
        self,
        filters: WorkspaceFilters | None = None,
        pagination: PaginationParams | None = None
    ) -> WorkspaceListResult:
        """List workspaces with filtering."""
        pass

    @abstractmethod
    async def list_active_workspaces(self, pagination: PaginationParams | None = None) -> WorkspaceListResult:
        """List currently active workspaces."""
        pass

    @abstractmethod
    async def get_resource_usage_summary(self, project_id: str | None = None) -> dict[str, Any]:
        """Get resource usage summary."""
        pass

    @abstractmethod
    async def count_workspaces(self, filters: WorkspaceFilters | None = None) -> int:
        """Count workspaces matching filters."""
        pass

    @abstractmethod
    async def get_workspace_logs(
        self,
        workspace_id: str,
        limit: int = 1000,
        level: str | None = None
    ) -> WorkspaceLogsResult:
        """Get workspace logs."""
        pass
```

### IConversationalLoopService

```python
class IConversationalLoopService(ABC):
    """Input port for multi-turn agent dialogue management."""

    @abstractmethod
    async def initialize_loop(
        self,
        work_item_id: str,
        agent_id: str,
        initial_context: dict[str, Any]
    ) -> ConversationalSessionState:
        """Initialize new conversational loop."""
        pass

    @abstractmethod
    async def handle_comment_event(self, event: CommentNeedsResponseEvent) -> None:
        """Handle comment event in loop."""
        pass

    @abstractmethod
    async def handle_column_change_event(self, event: WorkItemColumnChangedEvent) -> None:
        """Handle workflow column change in loop."""
        pass

    @abstractmethod
    async def cleanup_loop(self, work_item_id: str, reason: str) -> None:
        """Clean up conversational loop."""
        pass

    @abstractmethod
    async def load_session_state(self, work_item_id: str) -> ConversationalSessionState | None:
        """Load conversational session state."""
        pass

    @abstractmethod
    async def save_session_state(self, state: ConversationalSessionState) -> None:
        """Save conversational session state."""
        pass
```

## Methods

### IAuthenticationPort Methods

| Method | Parameters | Return Type | Description |
|---|---|---|---|
| `create_user()` | `command: CreateUserCommand` | `User` | Create new system user |
| `update_user()` | `command: UpdateUserCommand` | `User` | Update user profile |
| `get_user()` | `user_id: UUID` | `User` | Get user by ID |
| `get_user_by_username()` | `username: str` | `User` | Get user by username |
| `delete_user()` | `user_id: UUID` | `None` | Delete user (soft delete) |
| `login()` | `command: LoginCommand` | `LoginResult` | Authenticate with credentials |
| `validate_token()` | `token: str` | `AuthContext` | Validate JWT token |
| `refresh_token()` | `refresh_token: str` | `LoginResult` | Get new token pair |
| `create_api_key()` | `command: CreateAPIKeyCommand` | `tuple[APIKey, str]` | Create API key |
| `validate_api_key()` | `key: str` | `AuthContext` | Validate API key |
| `revoke_api_key()` | `key_id, requesting_user_id, is_admin` | `None` | Revoke API key |
| `list_api_keys()` | `user_id: UUID` | `list[APIKey]` | List user API keys |
| `check_permission()` | `auth_context, permission` | `bool` | Check user permission |

### IAuditQueryPort Methods

| Method | Parameters | Return Type | Description |
|---|---|---|---|
| `query_audit_events()` | `filters, pagination` | `AuditEventListResult` | Query audit events |
| `get_audit_trail()` | `entity_id, entity_type` | `AuditTrailResult` | Get entity audit trail |
| `get_audit_event()` | `event_id: str` | `AuditEvent` | Get specific event |
| `count_audit_events()` | `filters` | `int` | Count matching events |

### IWorkspaceQueryPort Methods

| Method | Parameters | Return Type | Description |
|---|---|---|---|
| `get_workspace()` | `workspace_id: str` | `WorkspaceInfo` | Get workspace by ID |
| `get_workspace_by_execution()` | `execution_id: str` | `WorkspaceInfo` | Get workspace for execution |
| `list_workspaces()` | `filters, pagination` | `WorkspaceListResult` | List workspaces |
| `list_active_workspaces()` | `pagination` | `WorkspaceListResult` | List active workspaces |
| `get_resource_usage_summary()` | `project_id` | `dict[str, Any]` | Get resource usage metrics |
| `count_workspaces()` | `filters` | `int` | Count workspaces |
| `get_workspace_logs()` | `workspace_id, limit, level` | `WorkspaceLogsResult` | Get workspace logs |

### IConversationalLoopService Methods

| Method | Parameters | Return Type | Description |
|---|---|---|---|
| `initialize_loop()` | `work_item_id, agent_id, initial_context` | `ConversationalSessionState` | Start conversational loop |
| `handle_comment_event()` | `event: CommentNeedsResponseEvent` | `None` | Process comment event |
| `handle_column_change_event()` | `event: WorkItemColumnChangedEvent` | `None` | Process column change event |
| `cleanup_loop()` | `work_item_id, reason` | `None` | End conversational loop |
| `load_session_state()` | `work_item_id: str` | `ConversationalSessionState \| None` | Load session state |
| `save_session_state()` | `state: ConversationalSessionState` | `None` | Persist session state |

## Events Emitted

This port does not directly emit domain events. Events are emitted by application services.

## Error Contracts

- **UserNotFoundError** — When user doesn't exist
- **AuthenticationError** — When credentials invalid
- **InvalidTokenError** — When token invalid or expired
- **PermissionDeniedError** — When user lacks required permission
- **WorkspaceNotFoundError** — When workspace doesn't exist
- **ValidationError** — When input parameters invalid

## Adapter Implementations

| Adapter Class | Type | File Path | Notes |
|---|---|---|---|
| `MockAuthenticationAdapter` | Testing | `adapters/primary/input_port_adapters/mock/` | In-memory authentication implementation |
| `MockAuditQueryAdapter` | Testing | `adapters/primary/input_port_adapters/mock/` | In-memory audit log implementation |
| `MockWorkspaceQueryAdapter` | Testing | `adapters/primary/input_port_adapters/mock/` | In-memory workspace query implementation |
| `MockConversationalLoopAdapter` | Testing | `adapters/primary/input_port_adapters/mock/` | In-memory conversational loop implementation |

## Diagram

```mermaid
classDiagram
    class IAuthenticationPort {
        <<interface>>
        +create_user(CreateUserCommand) User
        +get_user(user_id) User
        +login(LoginCommand) LoginResult
        +validate_token(token) AuthContext
        +refresh_token(refresh_token) LoginResult
        +create_api_key(CreateAPIKeyCommand) tuple
        +check_permission(auth_context, permission) bool
    }

    class IAuditQueryPort {
        <<interface>>
        +query_audit_events(filters, pagination) AuditEventListResult
        +get_audit_trail(entity_id, entity_type) AuditTrailResult
        +get_audit_event(event_id) AuditEvent
        +count_audit_events(filters) int
    }

    class IWorkspaceQueryPort {
        <<interface>>
        +get_workspace(workspace_id) WorkspaceInfo
        +get_workspace_by_execution(execution_id) WorkspaceInfo
        +list_workspaces(filters, pagination) WorkspaceListResult
        +list_active_workspaces(pagination) WorkspaceListResult
        +get_resource_usage_summary(project_id) dict
    }

    class IConversationalLoopService {
        <<interface>>
        +initialize_loop(work_item_id, agent_id, initial_context) ConversationalSessionState
        +handle_comment_event(CommentNeedsResponseEvent) None
        +handle_column_change_event(WorkItemColumnChangedEvent) None
        +cleanup_loop(work_item_id, reason) None
        +load_session_state(work_item_id) ConversationalSessionState
    }
```
