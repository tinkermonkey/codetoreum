# Comprehensive Output Ports Reference

This document catalogs all output port interfaces in the Codetoreum platform. Output ports define contracts for external system interactions, following the hexagonal architecture pattern.

## Port Categories

Output ports are organized by responsibility domain:
- **Core System**: Fundamental operations (tickets, VCS, containers, LLM)
- **Board Management**: Project board operations and reconciliation
- **Code Review**: Pull request and review lifecycle
- **Work Item Management**: Work item CRUD and status tracking
- **Infrastructure**: Event handling, storage, monitoring
- **Domain Services**: Specialized business logic services

## Core System Ports

### ITicketSystem
**Location**: `ports/output/ticket_system.py`

Vendor-agnostic interface for ticket/issue management. Abstract interface over GitHub Issues, Jira, Linear, etc.

**Key Methods**:
- `get_issue()` - Retrieve issue details
- `update_issue()` - Update issue status, labels, assignments
- `create_issue()` - Create new issues
- `list_issues()` - Query issues with filters

**Events**: N/A (events emitted by specialized services)

**Example Implementations**: GitHubTicketAdapter, JiraTicketAdapter

### IVersionControlService
**Location**: `ports/output/version_control_service.py`

Abstract version control operations (Git, Mercurial, etc.). Handles clone, checkout, commit, push operations.

**Key Methods**:
- `clone_repository()` - Clone a repository
- `create_branch()` - Create feature branch
- `commit()` - Create commit with message
- `push()` - Push commits to remote
- `get_branches()` - List existing branches

**Events**: N/A (low-level operations)

**Example Implementations**: GitVersionControlAdapter

### IContainer
**Location**: `ports/output/container.py`

Container runtime abstraction (Docker, Kubernetes, etc.). Manages agent execution environments.

**Key Methods**:
- `run_command()` - Execute command in container
- `mount_directory()` - Mount host directory
- `cleanup()` - Clean up container resources
- `get_logs()` - Retrieve container output

**Events**: N/A (infrastructure level)

**Example Implementations**: DockerContainerAdapter, KubernetesContainerAdapter

### ILLMProvider
**Location**: `ports/output/llm_provider.py`

Language model provider abstraction (Claude, GPT-4, etc.). Orchestrates agent interactions with LLM APIs.

**Key Methods**:
- `execute_agent()` - Run agent with context
- `converse()` - Multi-turn conversation
- `validate_context_window()` - Check token budget

**Events**: N/A (direct integration)

**Example Implementations**: ClaudeCodeAdapter, OpenAIAdapter

## Board Management Ports

### IBoardService
**Location**: `ports/output/board_service.py`

Project board management (GitHub Projects v2, Trello, etc.). Vendor-agnostic board structure and work item positioning.

**Key Methods**:
- `get_board_structure()` - Query columns, lanes, and work items
- `move_work_item()` - Transition work item between columns
- `reconcile_board()` - Sync orchestrator state with external board

**Events**:
- `work.item.moved` → WorkItemMovedEvent
- `board.reconciled` → BoardReconciledEvent

**Example Implementations**: GitHubBoardAdapter, TrelloBoardAdapter

### IPipelineLockService
**Location**: `ports/output/pipeline_lock_service.py`

Distributed locking for workflow coordination. Prevents concurrent pipeline execution.

**Key Methods**:
- `acquire_lock()` - Acquire execution lock
- `release_lock()` - Release execution lock
- `is_locked()` - Check lock status

**Events**:
- `pipeline.lock.acquired` → LockAcquiredEvent
- `pipeline.lock.released` → LockReleasedEvent

**Example Implementations**: RedisLockService, DynamoDBLockService

## Code Review Ports

### ICodeReviewService
**Location**: `ports/output/code_review_service.py`

Code review lifecycle (GitHub PRs, GitLab MRs, etc.). Manages review status, approvals, and comments.

**Key Methods**:
- `get_review()` - Get review status and approvals
- `request_review()` - Request review from users
- `approve()` - Approve code review
- `request_changes()` - Request changes with feedback
- `get_comments()` - Retrieve review comments

**Events**:
- `review.status.changed` → ReviewStatusChangedEvent
- `review.approved` → ReviewApprovedEvent
- `review.changes.requested` → ReviewChangesRequestedEvent

**Example Implementations**: GitHubCodeReviewAdapter, GitLabCodeReviewAdapter

### IDiscussionAdapter
**Location**: `ports/output/discussion_adapter.py`

Discussion thread management (GitHub discussions, issue comments, etc.).

**Key Methods**:
- `get_discussion()` - Retrieve discussion thread
- `post_comment()` - Add comment to discussion
- `update_comment()` - Edit existing comment
- `get_comments()` - List thread comments

**Events**:
- `comment.needs.response` → CommentNeedsResponseEvent

**Example Implementations**: GitHubDiscussionAdapter

## Work Item Management Ports

### IWorkItemService
**Location**: `ports/output/work_item_service.py`

Extended work item operations with event emission. Combines ticket operations with event notification.

**Key Methods**:
- `get_work_item()` - Retrieve work item
- `update_work_item()` - Update work item properties
- `list_work_items()` - Query work items

**Events**:
- `work.item.updated` → WorkItemUpdatedEvent
- `work.item.created` → WorkItemCreatedEvent

**Example Implementations**: IWorkItemService implementations

### IBranchResolutionService
**Location**: `ports/output/branch_resolution_service.py`

Branch resolution decision service. Determines whether to create new or reuse existing branches based on issue metadata.

**Key Methods**:
- `resolve_branch()` - Resolve branch for work item
  - **Parameters**: `project_id`, `issue_id`, `issue_metadata` (Mapping[str, Any])
  - **Returns**: `BranchResolution` (action, branch_name, confidence, reasoning)

**Events**:
- `branch.resolved` → BranchResolvedEvent

**Design Pattern**: Composes `ITicketSystem` and `IVersionControlService` at adapter level. Port remains pure interface.

**Example Implementations**: IntelligentBranchResolutionAdapter, SimpleStrategyBranchResolutionAdapter

**Responsibilities**:
- Analyze issue metadata (title, description, labels, relationships)
- Query existing branches for potential matches
- Apply resolution strategies (exact match, parent issue, sibling, fuzzy match, create new)
- Return resolution decision with confidence and reasoning
- Emit resolution events for audit trail

## Infrastructure Ports

### IEventEmitter
**Location**: `ports/output/event_emitter.py`

Event publication interface. All services that emit events extend this port.

**Key Methods**:
- `emit()` - Publish domain event

**Used By**: IBranchResolutionService, IBoardService, ICodeReviewService, IDiscussionAdapter, and others

### IEventStore
**Location**: `ports/output/event_store.py`

Event sourcing storage. Persists complete audit trail of domain events.

**Key Methods**:
- `append()` - Store new event
- `load_events()` - Retrieve events by aggregate
- `replay()` - Replay events for state reconstruction

**Example Implementations**: RedisEventStore, PostgreSQLEventStore

### IStorage
**Location**: `ports/output/storage.py`

Artifact storage (S3, local filesystem, etc.). Stores agent outputs, code snippets, logs.

**Key Methods**:
- `put()` - Store artifact
- `get()` - Retrieve artifact
- `delete()` - Remove artifact

**Example Implementations**: S3StorageAdapter, LocalStorageAdapter

### IMetrics
**Location**: `ports/output/metrics.py`

Metrics/observability interface. Records system metrics and performance data.

**Key Methods**:
- `record_counter()` - Increment metric counter
- `record_gauge()` - Record gauge value
- `record_histogram()` - Record distribution

**Example Implementations**: PrometheusMetricsAdapter, CloudWatchMetricsAdapter

### IMonitoring
**Location**: `ports/output/monitoring.py`

Lifecycle monitoring for services. Controls when services actively monitor state changes.

**Key Methods**:
- `start_monitoring()` - Begin active monitoring
- `stop_monitoring()` - Cease monitoring
- `is_monitoring()` - Check monitoring status

## Domain Services Ports

### IReviewCycleService
**Location**: `ports/output/review_cycle_service.py`

Maker-checker review cycle orchestration. Manages code review feedback loops.

**Key Methods**:
- `start_review_cycle()` - Initiate review
- `submit_feedback()` - Submit review feedback
- `get_cycle_status()` - Query review status

**Events**:
- `review.cycle.started` → ReviewCycleStartedEvent
- `review.cycle.completed` → ReviewCycleCompletedEvent

### IRepairCycleService
**Location**: `ports/output/repair_cycle_service.py`

Repair cycle orchestration for build/test failures. Manages test-fix-validate loops.

**Key Methods**:
- `start_repair_cycle()` - Initiate repair
- `submit_fix()` - Submit potential fix
- `validate_fix()` - Validate fix with tests

**Events**:
- `repair.cycle.started` → RepairCycleStartedEvent
- `repair.cycle.completed` → RepairCycleCompletedEvent

### IContainerRecoveryService
**Location**: `ports/output/container_recovery.py`

Container failure recovery. Handles agent execution failures and recovery strategies.

**Key Methods**:
- `can_recover()` - Check if failure is recoverable
- `recover()` - Execute recovery strategy
- `get_retry_count()` - Query retry attempts

**Events**:
- `container.recovered` → ContainerRecoveredEvent
- `container.recovery.failed` → ContainerRecoveryFailedEvent

### ICIPipelineService
**Location**: `ports/output/ci_pipeline_service.py`

CI pipeline management with event emission and monitoring. Provides vendor-agnostic abstraction for CI systems (GitHub Actions, GitLab CI, Jenkins, CircleCI, etc.). Enables querying CI status for pull requests and executing local CI checks within containers.

**Key Methods**:
- `get_pr_ci_status()` - Query CI status for a pull request from external CI system
  - **Parameters**: `pr_id` (str), `project_id` (str), `timeout_seconds` (int, default 300)
  - **Returns**: `CIPipelineStatus` with check results and pipeline URL
- `run_ci_checks()` - Execute CI checks locally in a working directory
  - **Parameters**: `project_id` (str), `working_directory` (str), `timeout_seconds` (int, default 600)
  - **Returns**: `CIRunResult` with boolean success flag, check results, and detailed output

**Value Objects**:
- `CICheckStatus` (Enum) - Status of individual CI check (PENDING, RUNNING, PASSED, FAILED, SKIPPED)
- `CICheckResult` - Result of single CI check execution (name, status, conclusion, url)
- `CIPipelineStatus` - Status of CI pipeline for pull request (pr_id, status, check_results tuple, pipeline_url, total_checks, passed, failed, pending)
- `CIRunResult` - Result of running CI checks locally (passed bool, check_results tuple, warnings tuple, output)

**Events**:
- `ci.pipeline_status_checked` → CIPipelineStatusCheckedEvent (PR CI status queried)
- `ci.run_started` → CIRunStartedEvent (Local CI execution starts)
- `ci.run_completed` → CIRunCompletedEvent (Local CI execution completes)

**Example Implementations**: MockCIPipelineAdapter, GitHubCIPipelineAdapter

## Port Design Principles

1. **Vendor Agnostic**: Ports hide external system details
2. **Single Responsibility**: Each port has focused concern
3. **Event-Driven**: Domain services emit events for state changes
4. **Pure Contracts**: No implementation logic in port definitions
5. **Immutable Parameters**: Complex parameters use `Mapping` for immutability
6. **Clear Error Boundaries**: Custom exceptions for port contract violations

## Event Emission Pattern

Services extending `IEventEmitter` publish domain events following this pattern:

```python
class MyService(IEventEmitter, ABC):
    """Service with event emission."""

    async def my_operation(self) -> Result:
        """Perform operation and emit event."""
        # ... business logic ...

        # Emit event for state change
        event = MyStateChangedEvent(...)
        await self.emit("my.state.changed", event)

        return result
```

Events are immutable dataclasses with complete audit information.

## Port Composition

Complex services compose multiple ports at the adapter level:

- **IBranchResolutionService**: Composes `ITicketSystem` + `IVersionControlService`
- **ICodeReviewService**: Wraps VCS pull request operations
- **IBoardService**: Manages board and work item state

Composition happens in adapters, not in port definitions, keeping ports pure.
