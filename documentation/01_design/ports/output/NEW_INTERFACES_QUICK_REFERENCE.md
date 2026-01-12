# New Port Interfaces - Quick Reference

**Phase 2 Implementation**: 8 new port interfaces enabling vendor-agnostic integration

## Interface Summary

### 1. IMonitoredService (Protocol)
**Location**: `monitoring.py`
**Pattern**: Mixin interface for monitoring lifecycle

```python
# Methods
await start_monitoring(project_id: str, config: MonitoringConfig) -> None
await stop_monitoring(project_id: str) -> None
await get_monitoring_status(project_id: str) -> MonitoringStatus

# Data Classes
class MonitoringConfig:
    project_id: str
    poll_interval_seconds: Optional[int]
    webhook_enabled: bool

class MonitoringStatus:
    state: MonitoringState  # STOPPED, STARTING, ACTIVE, STOPPING, ERROR
    project_id: str
    started_at: Optional[str]
    error_message: Optional[str]
```

### 2. IWorkItemService
**Location**: `work_item_service.py`
**Extends**: `IEventEmitter`, `IMonitoredService`
**Events**: `workitem.created`, `workitem.updated`

```python
# Query Methods
await get_work_item(id: WorkItemId) -> WorkItem
await get_work_items_by_status(project_id: ProjectId, status: str) -> List[WorkItem]
await get_work_items_by_column(project_id: ProjectId, column_name: str) -> List[WorkItem]

# Command Methods
await create_work_item(project_id: ProjectId, title: str, description: str, **kwargs) -> WorkItem
await update_work_item(item_id: WorkItemId, updates: Dict[str, Any]) -> WorkItem

# Inherited from IMonitoredService
await start_monitoring(project_id: str, config: MonitoringConfig) -> None
await stop_monitoring(project_id: str) -> None
```

### 3. IBoardService
**Location**: `board_service.py`
**Extends**: `IEventEmitter`, `IMonitoredService`
**Events**: `workitem.column_changed`, `board.reconciled`

```python
# Query Methods
await get_board(project_id: str, board_id: str) -> ProjectBoard
await get_columns(board_id: str) -> List[Column]
await get_items_in_column(board_id: str, column_name: str) -> List[str]
await get_item_position(work_item_id: str) -> Tuple[str, int]  # (column_name, position)

# Command Methods
await move_item_to_column(work_item_id: str, target_column: str) -> None
await reconcile_board(config: BoardConfig) -> ReconciliationResult

# Data Classes
class Column:
    id: str
    name: str
    position: int
    work_item_ids: List[str]

class ProjectBoard:
    id: str
    name: str
    project_id: str
    columns: List[Column]

class BoardConfig:
    board_id: str
    expected_columns: List[str]
    auto_create_missing: bool = True

class ReconciliationResult:
    columns_added: List[str]
    columns_removed: List[str]
    items_moved: int
```

### 4. IDiscussionAdapter
**Location**: `discussion_adapter.py`
**Extends**: `IEventEmitter`
**Events**: `comment.needs_response`, `comment.posted`
**Note**: Monitoring is work-item-specific, not project-wide

```python
# Query Methods
await get_thread(work_item_id: str) -> DiscussionThread

# Command Methods
await add_comment(work_item_id: str, content: str, parent_id: Optional[str] = None) -> Comment

# Monitoring Methods (work-item-specific)
def start_monitoring(work_item_id: str, config: DiscussionMonitoringConfig) -> None
def stop_monitoring(work_item_id: str) -> None

# Data Classes
class DiscussionMonitoringConfig:
    project_id: str
    column_name: str
    agent_assignment: str
    last_processed_comment_id: Optional[str] = None

class DiscussionThread:
    id: str
    work_item_id: str
    comments: List[Comment]
    thread_type: Literal['flat', 'nested']
```

### 5. ICodeReviewService
**Location**: `code_review_service.py`
**Extends**: `IEventEmitter`, `IMonitoredService`
**Events**: `review.status_changed`, `review.comment_added`

```python
# Query Methods
await get_review_for_work_item(work_item_id: str) -> Optional[CodeReview]
await get_review_status(review_id: str) -> CodeReviewStatus
await get_review_comments(review_id: str) -> List[ReviewComment]

# Command Methods
await request_changes(review_id: str, comments: str) -> None
await approve(review_id: str) -> None

# Data Classes
CodeReviewStatus = Literal['open', 'approved', 'changes_requested', 'merged', 'closed']

class CodeReview:
    id: str
    title: str
    source_branch: str
    target_branch: str
    status: CodeReviewStatus
    reviewers: List[str]
    approvals: List[Approval]
    work_item_id: Optional[str] = None

class Approval:
    reviewer: str
    approved_at: str

class ReviewComment:
    id: str
    author: str
    body: str
    created_at: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
```

### 6. IPipelineLockService
**Location**: `pipeline_lock_service.py`
**Extends**: `IEventEmitter`
**Events**: `lock.acquired`, `lock.released`, `lock.stale_detected`

```python
# Query Methods
await get_lock(project_id: str, board_id: str) -> Optional[PipelineLock]
await get_all_locks() -> List[PipelineLock]

# Command Methods
await try_acquire_lock(project_id: str, board_id: str, work_item_id: str) -> Tuple[bool, str]
await release_lock(project_id: str, board_id: str, work_item_id: str) -> bool

# Data Class
class PipelineLock:
    project_id: str
    board_id: str
    work_item_id: str
    locked_by_work_item: str
    lock_acquired_at: str
    lock_status: Literal['locked', 'unlocked']
```

### 7. IVersionControlService
**Location**: `version_control_service.py`
**Note**: Synchronous, no event emission, no monitoring

```python
# Command Methods
await clone_repository(url: str, target_path: str, branch: Optional[str] = None) -> None
await pull_latest(repo_path: str) -> None
await checkout(repo_path: str, branch: str) -> None
await commit(repo_path: str, message: str) -> str  # Returns commit SHA
await push(repo_path: str, branch: str) -> None

# Query Methods
await get_repository(identifier: str) -> Repository

# Data Class
class Repository:
    id: str
    name: str
    url: str
    default_branch: str
```

### 8. IIdentityService
**Location**: `identity_service.py`
**Note**: Query-only, no event emission, no monitoring

```python
# Query Methods
def is_bot_user(username: str) -> bool
def get_bot_username() -> str
def get_human_users(usernames: List[str]) -> List[str]

# Configuration
def configure(config: BotIdentityConfig) -> None

# Data Class
class BotIdentityConfig:
    bot_usernames: List[str]
    bot_patterns: List[Pattern]
```

## Service Classification

### Event-Emitting (Detect External Changes)
- ✅ `IWorkItemService`
- ✅ `IBoardService`
- ✅ `IDiscussionAdapter`
- ✅ `ICodeReviewService`
- ✅ `IPipelineLockService`

### Synchronous Commands Only (No Events)
- ❌ `IVersionControlService`
- ❌ `IIdentityService`

## Contract Tests Available

Each interface has corresponding contract tests:

| Interface | Test Class | Test Methods | Location |
|-----------|-----------|--------------|----------|
| `IEventEmitter` | `TestEventEmitterContract` | 7 | `test_event_emitter_contract.py` |
| `IMonitoredService` | `TestMonitoredServiceContract` | 8 | `test_monitored_service_contract.py` |
| `IBoardService` | `TestBoardServiceContract` | 8 | `test_board_service_contract.py` |
| `IPipelineLockService` | `TestPipelineLockServiceContract` | 10 | `test_pipeline_lock_service_contract.py` |
| `IDiscussionAdapter` | `TestDiscussionAdapterContract` | 8 | `test_discussion_adapter_contract.py` |

## Typical Usage Pattern

### 1. Event-Emitting Service
```python
from codetoreum.ports.output import IBoardService, MonitoringConfig

# Create/obtain service (e.g., GitHub adapter)
service = GitHubBoardService(...)

# Subscribe to events
service.on("workitem.column_changed", handle_column_change)

# Start monitoring
await service.start_monitoring(
    "proj-123",
    MonitoringConfig(project_id="proj-123")
)

# Query board
board = await service.get_board("proj-123", "board-456")

# Stop when done
await service.stop_monitoring("proj-123")
```

### 2. Lock Service
```python
from codetoreum.ports.output import IPipelineLockService

service = PipelineLockService(...)

# Try to acquire lock
success, reason = await service.try_acquire_lock("proj-123", "board-456", "item-789")

if success:
    try:
        # Do work on item
        await process_item("item-789")
    finally:
        # Always release
        await service.release_lock("proj-123", "board-456", "item-789")
else:
    print(f"Could not lock: {reason}")
```

### 3. Identity Service
```python
from codetoreum.ports.output import IIdentityService, BotIdentityConfig

service = IdentityService()

# Configure
config = BotIdentityConfig(
    bot_usernames=["dependabot"],
    bot_patterns=[re.compile("^bot-.*")]
)
service.configure(config)

# Query
if not service.is_bot_user("alice"):
    # Alice is human, process feedback
    ...
```

## Key Design Principles

1. **Vendor-Agnostic**: No vendor-specific terminology in interfaces
2. **Event-Based**: External change detection via event emission
3. **Monitoring Lifecycle**: Consistent `start_monitoring`/`stop_monitoring` pattern
4. **Error Clarity**: Clear exception types or return values (e.g., `try_acquire_lock`)
5. **Composition**: Mixins allow combining capabilities (e.g., `IEventEmitter` + `IMonitoredService`)

## Next Steps

- Implement concrete adapters (GitHub, JIRA, etc.)
- Run contract tests against implementations
- Integrate with orchestrator event bus
- Add resilience patterns (circuit breakers, rate limiting)
