---
required_sections:
  - "## Overview"
  - "## Model Definitions"
  - "## Invariants"
  - "## Relationships"
  - "## Diagram"
  - "## Events"
  - "## Examples"
applies_to: "documentation/architecture/domain/models.md"
---

# Domain Models Catalog

## Overview

The domain layer contains **90 pure business logic classes** across **19 source files**. These models form the core of Codetoreum, representing the system's fundamental concepts: work items, agents, workflows, executions, reviews, repairs, exceptions, and project configuration. All domain models are technology-agnostic—they contain no external dependencies, no I/O operations, and no framework coupling. They are organized into nine primary bounded contexts:

1. **Work Item Context** — Lifecycle and state management of work items
2. **Agent Context** — AI agents and their capabilities
3. **Execution Context** — Agent execution instances and their lifecycle
4. **Workflow Context** — Workflow definitions and stage management
5. **Review Context** — Code review cycles and feedback
6. **Repair Cycle Context** — Automated test-fix-validate cycles
7. **Project Context** — Project-level configuration and test setup
8. **Exception Context** — Domain-level error types and business rule violations
9. **Infrastructure Models** — Supporting structures (values objects, enums) for all other contexts

Domain models enforce business rules through **invariants**: conditions that must always be true. These invariants are expressed as methods on the models that validate state before allowing transitions.

## Model Definitions

### Work Item Context

**File**: `work_item.py`

Work items represent units of work (issues, tasks, features) flowing through the system.

```python
class WorkItemStatus(Enum):
    """Status enumeration for work items."""
    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    UNDER_REVIEW = "under_review"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

class WorkItemPriority(Enum):
    """Priority levels for work items."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class WorkItem:
    """Work Item aggregate root.
    
    Represents a unit of work (issue, task, feature) that flows through
    the system. Maintains its own consistency boundary and emits events
    for all state changes.
    """
    # Identity
    id: str
    project_id: str
    
    # Core attributes
    title: str
    description: str
    
    # State
    status: WorkItemStatus
    priority: WorkItemPriority
    
    # Metadata
    labels: list[str]
    external_id: str | None  # ID in external system (GitHub issue #, etc.)
    external_url: str | None
    
    # Assignment
    assigned_agent_id: str | None
    assigned_at: datetime | None
    
    # Workflow tracking
    current_workflow_id: str | None
    current_stage: str | None
    
    # Board column tracking (for SLA monitoring)
    current_column: str | None
    entered_column_at: datetime | None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # PR and discussion tracking
    pr_id: str | None = None
    discussion_id: str | None = None
    completed_at: datetime | None = None
```

**Key Responsibilities**:
- Track work item state and lifecycle
- Emit events for state changes
- Enforce workflow transition rules
- Track time spent in board columns
- Support assignment to agents

---

### Agent Context

**File**: `agent.py`

Agents represent AI systems capable of performing work on work items.

```python
class AgentType(Enum):
    """Types of agents in the system."""
    MAKER = "maker"                          # Creates/produces output
    REVIEWER = "reviewer"                    # Reviews output
    SPECIALIZED = "specialized"              # Task-specific agents
    REQUIREMENTS_ANALYST = "requirements_analyst"
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    TESTER = "tester"
    DEVOPS = "devops"

@dataclass
class AgentCapability:
    """Represents a skill/capability of an agent."""
    skill: str
    proficiency: float  # 0.0-1.0
    description: str | None

@dataclass
class Agent:
    """Agent aggregate root.
    
    Represents an AI agent with capabilities, configuration, and constraints.
    """
    # Identity
    id: str
    
    # Basic attributes
    name: str
    display_name: str
    agent_type: AgentType
    
    # Capabilities and role
    capabilities: dict[str, AgentCapability]  # skill -> capability
    role_description: str
    
    # Configuration (required fields first)
    model: str                 # LLM model (e.g., "claude-sonnet-4-5")
    timeout_seconds: int
    max_retries: int
    
    # Constraints (environment requirements)
    requires_docker: bool
    requires_dev_container: bool
    makes_code_changes: bool
    filesystem_write_allowed: bool
    
    # MCP servers
    mcp_servers: list[str]
    
    # Metadata
    metadata: dict[str, Any]
    
    # Timestamps (NO DEFAULTS - Required fields)
    created_at: datetime
    updated_at: datetime
    
    # Configuration with defaults (must come after required fields)
    temperature: float = 0.7   # LLM temperature (0.0-2.0)
    max_tokens: int = 4096     # Maximum tokens for responses
    system_prompt: str = ""    # System prompt for the agent
    commit_policy: CommitPolicy = CommitPolicy.ON_SUCCESS  # When to commit file changes
```

**Key Responsibilities**:
- Define agent capabilities and constraints
- Store configuration (model, timeout, retries)
- Track agent usage and lifecycle
- Support MCP server integration

---

### Execution Context

**File**: `agent_execution.py`, `workspace_context.py`

Execution entities represent instances of agents working on work items.

```python
class ExecutionStatus(Enum):
    """Status enumeration for agent executions."""
    PENDING = "pending"              # Waiting to be started
    INITIALIZED = "initialized"      # Created but not yet running
    RUNNING = "running"
    PAUSED = "paused"                # Execution paused by user/system
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

@dataclass
class AgentExecution:
    """Agent Execution entity.
    
    Represents a single execution instance of an agent.
    Part of the Workflow aggregate but has its own identity.
    """
    # Identity
    id: str
    agent_id: str
    work_item_id: str
    workflow_id: str
    stage_name: str
    
    # Status
    status: ExecutionStatus
    
    # Execution context
    prompt: str
    model: str
    session_id: str | None
    
    # Container tracking
    container_name: str | None
    container_id: str | None
    
    # Results
    output: str | None
    error_message: str | None
    exit_code: int | None
    
    # Metrics
    input_tokens: int
    output_tokens: int
    duration_seconds: float | None
    
    # Timestamps
    initialized_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    
    # Metadata
    metadata: dict[str, Any]
```

**Key Responsibilities**:
- Track individual agent execution lifecycle
- Store execution output and errors
- Record timing information
- Support retry logic

```python
class WorkspaceType(Enum):
    """Type of workspace for agent execution."""
    ISSUE = "issue"              # Feature branches + PRs
    HYBRID = "hybrid"            # Feature branches + PRs + discussion posting

@dataclass(frozen=True)
class WorkspaceContext:
    """Context for agent execution workspace.
    
    Immutable value object that encapsulates workspace configuration
    and routing logic. Determines how agent execution results are handled
    (branch creation, PR creation, discussion comments, etc.).
    """
    # Workspace type
    workspace_type: WorkspaceType
    
    # Identifiers
    project_id: str
    work_item_id: str
    
    # Issue workspace (feature branches + PRs)
    branch_name: str | None
    create_pr: bool
    
    # Discussion workspace (for hybrid mode)
    discussion_id: str | None
    
    # Configuration
    allow_code_changes: bool
    create_commits: bool
    post_comments: bool
```

---

### Workflow Context

**File**: `workflow.py`, `workflow_template.py`, `pipeline_stage.py`, `board_workflow_template.py`

Workflows define multi-stage pipelines that work items progress through.

```python
class WorkflowStatus(Enum):
    """Status enumeration for workflows."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Workflow:
    """Workflow aggregate root.
    
    Orchestrates execution of work items through pipeline stages.
    Maintains consistency boundary for workflow execution.
    """
    # Identity
    id: str
    work_item_id: str
    template_id: str
    project_id: str
    
    # Status
    status: WorkflowStatus
    
    # Stage tracking
    stages: list[PipelineStage]
    current_stage_index: int
    completed_stages: list[str]
    
    # Execution tracking
    started_at: datetime | None
    completed_at: datetime | None
    paused_at: datetime | None
    
    # Metadata
    metadata: dict[str, Any]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
```

```python
class StageType(Enum):
    """Type of pipeline stage."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    REVIEW = "review"

class StageStatus(Enum):
    """Status of a pipeline stage."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class PipelineStage:
    """Pipeline Stage entity.
    
    Represents a stage in a workflow pipeline with dependencies and execution tracking.
    """
    # Identity
    id: str
    name: str
    workflow_id: str
    
    # Configuration
    stage_type: StageType
    agent_config: dict[str, Any]
    description: str
    
    # Dependencies
    dependencies: list[str]
    is_parallel: bool
    
    # Review configuration (if stage_type == REVIEW)
    maker_agent_id: str | None
    reviewer_agent_id: str | None
    max_review_iterations: int
    
    # Status
    status: StageStatus
    
    # Execution tracking
    execution_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    
    # Results
    output: str | None
    error_message: str | None
    
    # Metadata
    metadata: dict[str, Any]
```

```python
class ColumnType(Enum):
    """Type of workflow column."""
    MANUAL = "manual"
    AUTOMATED = "automated"

@dataclass(frozen=True)
class ColumnTemplate:
    """Template for a board column with workflow semantics.
    
    Defines a column in a board, with optional agent assignment,
    SLA thresholds, and failure/escalation handling.
    """
    name: str
    type: ColumnType
    agent_id: str | None
    is_pipeline_trigger: bool
    is_exit_column: bool
    position: int
    auto_progress_on_completion: bool
    sla_seconds: int | None = None
    on_failure_column: str | None = None
    sla_escalation_column: str | None = None
    repair_cycle_agents: RepairCycleAgentConfig | None = None
    repair_cycle_test_types: tuple[RepairTestType, ...] | None = None
    pr_review_cycle_config: PRReviewCycleConfig | None = None
    execution_type: str = "task_queue"  # "task_queue" or "conversational"

@dataclass
class BoardWorkflowTemplate:
    """Workflow template with column-based semantics.
    
    Defines a workflow where work items progress through board columns,
    with each column optionally triggering an agent or requiring manual action.
    """
    id: str
    name: str
    board_id: str
    project_id: str
    columns: tuple[ColumnTemplate, ...]  # Immutable ordered columns
    created_at: datetime | None
    updated_at: datetime | None
```

**Key Responsibilities**:
- Define multi-stage pipelines
- Manage workflow progression
- Track stage status and execution
- Support conditional branching and failure handling
- Provide SLA monitoring on board columns

---

### Review Context

**File**: `review_cycle.py`, `pr_review_cycle_types.py`

Review cycles model code review and approval processes.

```python
class ReviewStatus(Enum):
    """Status of a review cycle."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    ESCALATED = "escalated"

class ReviewDecision(Enum):
    """Reviewer's decision."""
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    ESCALATE = "escalate"

@dataclass(frozen=True)
class ReviewFeedback:
    """Value object for review feedback.
    
    Immutable representation of reviewer's feedback on an iteration.
    """
    decision: ReviewDecision
    comment: str
    issues: tuple[str, ...]
    suggestions: tuple[str, ...]
    timestamp: datetime

@dataclass(frozen=True)
class ReviewIteration:
    """Single iteration of maker-reviewer cycle.
    
    Represents one round of work submission and review.
    Immutable value object for aggregate consistency.
    """
    iteration_number: int
    maker_output: str
    maker_execution_id: str
    reviewer_feedback: ReviewFeedback | None
    reviewer_execution_id: str | None
    started_at: datetime
    completed_at: datetime | None

@dataclass
class ReviewCycle:
    """Review Cycle aggregate root.
    
    Manages iterative maker-checker review process where a maker agent
    produces output and a reviewer agent evaluates it. The cycle continues
    until approval, escalation, or max iterations reached.
    """
    # Identity
    id: str
    
    # Workflow context
    workflow_id: str
    stage_name: str
    
    # Agents
    maker_agent_id: str
    reviewer_agent_id: str
    
    # Configuration
    max_iterations: int
    
    # Status (accessed via properties)
    _status: ReviewStatus
    _current_iteration: int
    _created_at: datetime
    _updated_at: datetime
    _iterations: list[ReviewIteration]
    _final_decision: ReviewDecision | None
    _escalation_reason: str | None
    _completed_at: datetime | None
```

```python
class PRReviewOutcome(str, Enum):
    """Outcome of a PR review cycle."""
    ISSUES_FOUND = "issues_found"
    APPROVED = "approved"
    MAX_CYCLES_REACHED = "max_cycles"

class PRReviewStatus(str, Enum):
    """Status of a PR review cycle."""
    PENDING = "pending"
    PHASE_1_CODE_REVIEW = "phase_1_code_review"
    PHASE_2_VERIFICATION = "phase_2_verification"
    PHASE_3_CI_CHECK = "phase_3_ci_check"
    PHASE_4_CONSOLIDATION = "phase_4_consolidation"
    COMPLETED = "completed"
    ESCALATED = "escalated"

@dataclass(frozen=True)
class PRReviewFinding:
    """Represents a single finding from the PR review."""
    title: str
    description: str
    severity: str  # "critical", "high", "medium", "low"
    phase: str
    context_source: str | None = None

@dataclass(frozen=True)
class PRReviewPhaseOutput:
    """Output from a single phase in the PR review cycle."""
    phase_name: str
    phase_index: int
    success: bool
    findings: tuple[PRReviewFinding, ...]
    summary: str
    duration_seconds: float
    context_source: str | None = None
    comment_id: str | None = None
    error: str | None = None

@dataclass
class PRReviewCycleConfig:
    """Configuration for a PR review cycle."""
    max_iterations: int
    require_ci_pass: bool
    code_review_timeout: int
    allow_auto_merge: bool
```

**Key Responsibilities**:
- Track review feedback from multiple reviewers
- Support iterative feedback and revisions
- Enforce approval criteria (unanimous, majority, etc.)
- Handle escalation of conflicting feedback
- Track PR review cycle phases and decisions

---

### Infrastructure Models

**File**: `value_objects.py`, `types.py`, `user.py`, `comment.py`, `conversational_session.py`

Supporting value objects and infrastructure models used across contexts.

```python
class TypeSafeId:
    """Type-safe identifier wrapper."""
    def __init__(self, value: str):
        self.value = value

@dataclass(frozen=True)
class WorkItemId(TypeSafeId):
    """Immutable work item identifier."""
    pass

@dataclass(frozen=True)
class WorkflowId(TypeSafeId):
    """Immutable workflow identifier."""
    pass

@dataclass(frozen=True)
class AgentId(TypeSafeId):
    """Immutable agent identifier."""
    pass

@dataclass(frozen=True)
class ExecutionId(TypeSafeId):
    """Immutable execution identifier."""
    pass

@dataclass(frozen=True)
class ExecutionResult:
    """Immutable result of an execution.
    
    Represents agent execution outcome with complete metrics and file tracking.
    All collections are immutable (tuples instead of lists). Metadata dict is
    wrapped in MappingProxyType to prevent in-place mutations.
    """
    # Status
    success: bool
    exit_code: int
    
    # Output
    output: str
    error_message: str | None
    
    # Metrics
    input_tokens: int
    output_tokens: int
    duration_seconds: float
    
    # Timestamp
    timestamp: datetime
    
    # Files modified (immutable tuples)
    modified_files: tuple[str, ...] = ()
    added_files: tuple[str, ...] = ()
    deleted_files: tuple[str, ...] = ()
    
    # Session continuity
    session_id: str | None = None
    
    # Metadata (wrapped in MappingProxyType for deep immutability)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Factory methods
    @classmethod
    def success_result(cls, output: str, input_tokens: int, output_tokens: int, 
                      duration_seconds: float, modified_files: list[str] | None = None,
                      added_files: list[str] | None = None, deleted_files: list[str] | None = None,
                      session_id: str | None = None, metadata: dict[str, Any] | None = None) -> "ExecutionResult"
    
    @classmethod
    def failure_result(cls, error_message: str, exit_code: int, output: str = "",
                      duration_seconds: float = 0.0, input_tokens: int = 0,
                      output_tokens: int = 0, metadata: dict[str, Any] | None = None) -> "ExecutionResult"
    
    def get_total_tokens(self) -> int
    def has_file_changes(self) -> bool
    def get_all_affected_files(self) -> list[str]
    def to_dict(self) -> dict[str, Any]

@dataclass(frozen=True)
class ProjectConfig:
    """Immutable project configuration from projects.yaml.
    
    Represents the complete configuration for a single project including
    repository details and enabled status. Frozen to ensure immutability
    in the domain layer.
    """
    repo_url: str              # Repository URL (SSH or HTTPS format)
    branch: str                # Branch name to checkout and track (e.g., "main")
    enabled: bool              # Whether project is actively processed by orchestrator
    org: str                   # Organization/namespace identifier for project

@dataclass(frozen=True)
class ContainerConfig:
    """Configuration for container creation.
    
    Immutable value object with tuples for commands/entrypoints and
    MappingProxyType for environment/volumes dicts to prevent mutations.
    """
    image: str                                                    # Image name:tag
    name: str | None = None                                       # Container name
    command: tuple[str, ...] | None = None                        # Command to run
    entrypoint: tuple[str, ...] | None = None                     # Entrypoint as tuple
    working_dir: str = "/workspace"                               # Working directory
    user: str = "1000:1000"                                       # UID:GID
    environment: Mapping[str, str] | None = None                  # Environment vars (immutable)
    volumes: Mapping[str, Mapping[str, str]] | None = None        # {host: {bind: path, mode}} (immutable)
    network: str | None = None                                    # Network name
    auto_remove: bool = False                                     # --rm flag
    detached: bool = False                                        # -d flag
    stdin_open: bool = False                                      # -i flag
    tty: bool = False                                             # -t flag
```

```python
class UserRole(str, Enum):
    """User roles for RBAC."""
    ADMIN = "admin"                          # Full system access
    DEVELOPER = "developer"                  # Can trigger workflows, view executions
    VIEWER = "viewer"                        # Read-only access
    SERVICE_ACCOUNT = "service_account"      # API access only

class Permission(str, Enum):
    """Granular permissions for authorization."""
    # Workflow permissions
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_VIEW = "workflow:view"
    WORKFLOW_CANCEL = "workflow:cancel"
    WORKFLOW_RETRY = "workflow:retry"
    
    # Execution permissions
    EXECUTION_VIEW = "execution:view"
    EXECUTION_CANCEL = "execution:cancel"
    
    # Configuration permissions
    CONFIG_VIEW = "config:view"
    CONFIG_UPDATE = "config:update"
    
    # Project permissions
    PROJECT_CREATE = "project:create"
    PROJECT_VIEW = "project:view"
    PROJECT_UPDATE = "project:update"
    PROJECT_DELETE = "project:delete"
    
    # User permissions
    USER_CREATE = "user:create"
    USER_VIEW = "user:view"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

@dataclass
class User:
    """User entity for authentication and authorization."""
    id: UUID                                                    # Unique user identifier
    username: str                                               # Unique username
    email: str                                                  # User email address
    hashed_password: str                                        # Bcrypt hashed password
    roles: set[UserRole]                                        # User roles for RBAC
    is_active: bool = True                                      # Whether user account is active
    is_verified: bool = False                                   # Whether email is verified
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))  # Creation timestamp
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))  # Last update timestamp
    last_login_at: datetime | None = None                       # Last login timestamp
    metadata: dict = field(default_factory=dict)                # Additional user metadata

@dataclass
class AuthContext:
    """Authentication context for a request.
    
    Contains information about the authenticated user or API key.
    """
    user_id: UUID                            # Authenticated user ID
    username: str                            # Authenticated username
    roles: set[UserRole]                     # User roles
    permissions: set[Permission]             # Effective permissions
    auth_method: str = "jwt"                 # jwt, api_key, or session
    api_key_id: UUID | None = None           # API key ID if authenticated via API key
    metadata: dict = field(default_factory=dict)  # Additional context metadata
```

```python
@dataclass
class Comment:
    """Represents a comment on a work item."""
    id: str
    work_item_id: str
    author_id: str
    body: str
    created_at: datetime
    updated_at: datetime
    parent_id: str | None  # For threaded discussions
```

**Key Responsibilities**:
- Provide type-safe identifiers
- Store immutable value objects (ExecutionResult, ProjectConfig)
- Track user identity and permissions
- Support conversational session state

---

### Repair Cycle Context

**File**: `repair_cycle_types.py` (17 classes)

The Repair Cycle context provides types and value objects for automated test-fix-validate cycles. It classifies failures, configures repair strategies, and tracks repair cycle results.

**Key Types**:
- **FailureClassification**: Enum categorizing root cause (CODE_DEFECT, ENVIRONMENT_ISSUE, TRANSIENT_FAILURE, DEPENDENCY_ISSUE, CONFIGURATION_ISSUE)
- **RepairTestType**: Enum for test execution order (COMPILATION, UNIT, INTEGRATION, CI, E2E)
- **RepairTestFailure**: Immutable record of a test failure with file, test name, and message
- **RepairTestWarning**: Immutable record of warnings found during testing
- **RepairTestResult**: Result from executing a test type in one iteration
- **CycleResult**: Result of a complete repair cycle iteration
- **RepairCycleResult**: Final aggregated result of entire repair cycle
- **RepairTestRunConfig**: Configuration for test runs (timeout, failure reporting, etc.)
- **RepairCycleAgentConfig**: Configuration for repair agent behavior
- **RepairCycleCheckpoint**: Checkpoint marking progress in repair cycle
- **EnvironmentRepairConfig**: Configuration for environment repair strategy
- **RepairCycleStageConfig**: Configuration for each test type stage
- **SystemicAnalysisResult**: Result of systemic analysis for environment/dependency issues
- **AnalysisContext**: Context for analysis operations
- **RebuildResult**: Result of rebuild operation
- **VerificationResult**: Result of verification operation
- **SystemicFixResult**: Result of systemic fix operation

**Invariants Enforced**:
- Test types must execute in strict order
- Failure/warning records must have all required fields
- Immutability of results (frozen dataclasses)

---

### Project Context

**File**: `project_context.py` (5 classes)

The Project Context provides project-level configuration and state management.

```python
class ProjectContextCreated(DomainEvent):
    """Emitted when project context is created."""
    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)

class ProjectTestConfigUpdated(DomainEvent):
    """Emitted when test configuration is updated."""
    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)

class ProjectDockerConfigUpdated(DomainEvent):
    """Emitted when Docker configuration is updated."""
    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)

class ProjectWorkflowMappingAdded(DomainEvent):
    """Emitted when workflow mapping is added."""
    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)

@dataclass
class ProjectContext:
    """Project aggregate root.
    
    Manages project-level configuration including test commands, Docker setup,
    and workflow mappings.
    """
    # Identity
    id: str
    
    # Project metadata
    name: str
    repository_url: str
    default_branch: str
    
    # Test configuration
    test_command: str | None
    test_framework: str | None
    
    # Docker configuration
    has_dockerfile: bool
    dockerfile_path: str | None
    requires_dev_container: bool
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
```

**Key Responsibilities**:
- Store project-level configuration
- Manage test setup and Docker configuration
- Track workflow mappings to external systems
- Emit events for configuration changes

---

### Exception Context

**File**: `exceptions.py` (9 classes)

Domain-level exception types representing business rule violations and error conditions.

```python
class DomainError(Exception):
    """Base exception for domain layer errors."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

# Entity Not Found Exceptions
class AgentNotFoundError(DomainError):
    """Raised when an agent cannot be found."""

class ExecutionNotFoundError(DomainError):
    """Raised when an execution cannot be found."""

class WorkItemNotFoundError(DomainError):
    """Raised when a work item cannot be found."""

class WorkspaceNotFoundError(DomainError):
    """Raised when a workspace cannot be found."""

# Business Logic Exceptions
class TestOutputParseError(DomainError):
    """Raised when test output structure is invalid."""

class PipelineNotFoundError(DomainError):
    """Raised when a pipeline cannot be found."""

class ConfigNotFoundError(DomainError):
    """Raised when configuration is missing."""

class InvalidStateError(DomainError):
    """Raised when model state violates invariants."""
```

**Key Responsibilities**:
- Provide typed exceptions for domain layer errors
- Enable precise error handling in application services
- Support business rule validation
- Distinguish entity not found from invalid state errors

---

## Invariants

Domain models enforce business rules through invariants:

### Work Item Invariants

1. **WorkItem-1**: Work item must have a valid status from WorkItemStatus enum
   - Enforced by: `WorkItemStatus` enum and `_validate_invariants()` check
   - Prevents: Invalid state values

2. **WorkItem-2**: Work item can only transition through valid state sequences
   - Enforced by: `assign_agent()` (NEW/ASSIGNED → ASSIGNED), `start()` (ASSIGNED → IN_PROGRESS), `mark_under_review()` (IN_PROGRESS → UNDER_REVIEW), `complete()` (IN_PROGRESS/UNDER_REVIEW → COMPLETED)
   - Prevents: Invalid stage transitions (e.g., COMPLETED → IN_PROGRESS)

3. **WorkItem-3**: If assigned to agent, must have assigned_agent_id and assigned_at timestamp
   - Enforced by: `assign_agent()` method sets both fields atomically
   - Prevents: Partial assignment state

4. **WorkItem-4**: Work item can only be completed from IN_PROGRESS or UNDER_REVIEW status
   - Enforced by: `complete()` method validates precondition
   - Prevents: Completing without proper review (if required by workflow)

5. **WorkItem-5**: Work item must belong to a project
   - Enforced by: `_validate_invariants()` checks project_id is non-empty
   - Prevents: Orphaned work items without project context

### Agent Invariants

1. **Agent-1**: Agent must have at least one capability
   - Enforced by: Constructor validation
   - Prevents: Creating agents with no skills

2. **Agent-2**: Agent timeout must be positive
   - Enforced by: Field validation in `update_timeout()`
   - Prevents: Invalid timeout values (0, negative)

3. **Agent-3**: Capability proficiency must be 0.0-1.0
   - Enforced by: `AgentCapability` validation
   - Prevents: Invalid proficiency scores

4. **Agent-4**: Agent cannot be deleted while in active execution
   - Enforced by: Application service checks active executions before deletion
   - Prevents: Orphaning active work

### Execution Invariants

1. **Execution-1**: Execution cannot advance from COMPLETED or FAILED
   - Enforced by: `advance_status()` method checks current status
   - Prevents: Re-running completed executions

2. **Execution-2**: RUNNING execution must have started_at timestamp
   - Enforced by: `start()` method sets timestamp
   - Prevents: Missing timing information

3. **Execution-3**: Execution retry count cannot exceed agent's max_retries
   - Enforced by: Application service checks before retry
   - Prevents: Infinite retry loops

### Workflow Invariants

1. **Workflow-1**: Workflow must follow defined stage order
   - Enforced by: `advance_to_next_stage()` validates order
   - Prevents: Skipping or reversing stages

2. **Workflow-2**: Workflow cannot transition to COMPLETED until all stages are done
   - Enforced by: `complete()` method verifies all stages
   - Prevents: Premature completion

3. **Workflow-3**: Current stage index must be within bounds [0, stages.length)
   - Enforced by: Bounds checking in `advance_to_next_stage()`
   - Prevents: Index out of bounds

### Review Invariants

1. **Review-1**: Review cycle cannot approve when already in terminal state
   - Enforced by: `approve()` validates cycle is in IN_PROGRESS state
   - Prevents: Approving already-completed cycles

2. **Review-2**: A reviewer can only submit feedback once per iteration
   - Enforced by: `submit_review()` checks current iteration doesn't already have feedback
   - Prevents: Duplicate feedback on same iteration

3. **Review-3**: Maker and reviewer must be different agents
   - Enforced by: `_validate_invariants()` in `create()` factory method
   - Prevents: Same agent reviewing their own work

4. **Review-4**: Max iterations must be positive and current cannot exceed max
   - Enforced by: `_validate_invariants()` validates max_iterations > 0
   - Prevents: Invalid iteration limits or exceeding bounds

5. **Review-5**: Cannot start iteration if already at max iterations
   - Enforced by: `start_iteration()` checks current_iteration < max_iterations
   - Prevents: Exceeding maximum iteration count

---

## Relationships

Domain models relate to each other as follows:

| Source | Relationship | Target | Cardinality | Notes |
|---|---|---|---|---|
| WorkItem | triggers | AgentExecution | 1:N | A work item may trigger multiple agent executions across workflow stages |
| WorkItem | flows through | Workflow | 1:N | A work item may have multiple workflows (initial + repair cycles) |
| WorkItem | belongs to | Project | N:1 | Many work items in single project |
| WorkItem | tracks | Comment | 1:N | Comments are attached to work items |
| Workflow | contains | PipelineStage | 1:N | Workflow is ordered sequence of stages |
| Workflow | has | ReviewCycle | 1:N | Review cycles for workflow stages |
| PipelineStage | executes | Agent | N:1 | Each stage uses one or more agents |
| PipelineStage | uses | ReviewCycle | 1:1 | Review stage may have a review cycle (if type=REVIEW) |
| Agent | performs | AgentExecution | 1:N | Agent has many execution instances |
| Agent | reviews | ReviewCycle | 1:N | Reviewer agent participates in review cycles |
| AgentExecution | belongs to | Workflow | N:1 | Execution is part of workflow |
| AgentExecution | updates | WorkItem | N:1 | Execution produces changes to work item |
| ReviewCycle | contains | ReviewIteration | 1:N | Multiple iterations in maker-reviewer cycle |
| ReviewIteration | has | ReviewFeedback | 0:1 | Each iteration has at most one reviewer feedback |
| BoardWorkflowTemplate | defines | ColumnTemplate | 1:N | Board template contains ordered columns |
| ColumnTemplate | triggers | Agent | N:1 | Column may trigger agent execution |
| WorkspaceContext | used by | AgentExecution | 1:N | Determines execution result handling |
| ProjectContext | configures | Agent | 1:N | Project can configure multiple agents |

---

## Diagram

### Entity Relationship Diagram

```mermaid
erDiagram
    WORK_ITEM ||--o{ WORKFLOW : "flows_through"
    WORK_ITEM ||--o{ AGENT_EXECUTION : "triggers"
    WORK_ITEM ||--o{ COMMENT : "receives"
    WORKFLOW ||--o{ PIPELINE_STAGE : "contains"
    WORKFLOW ||--o{ REVIEW_CYCLE : "has"
    WORKFLOW ||--o{ AGENT_EXECUTION : "sequences"
    PIPELINE_STAGE }o--|| AGENT : "executes"
    AGENT ||--o{ AGENT_EXECUTION : "performs"
    AGENT ||--o{ REVIEW_CYCLE : "reviews"
    AGENT_EXECUTION }o--|| EXECUTION_STATUS : "has"
    REVIEW_CYCLE ||--o{ REVIEW_ITERATION : "has"
    REVIEW_ITERATION }o--|| REVIEW_FEEDBACK : "has"
    BOARD_WORKFLOW_TEMPLATE ||--o{ COLUMN_TEMPLATE : "defines"
    COLUMN_TEMPLATE }o--|| AGENT : "triggers"
    WORKSPACE_CONTEXT ||--o{ AGENT_EXECUTION : "configures"
    
    WORK_ITEM {
        string id PK
        string project_id
        string title
        string description
        string status
        int priority
        datetime created_at
        datetime updated_at
        string assigned_agent_id FK
        string current_workflow_id FK
        string current_stage
    }
    
    AGENT {
        string id PK
        string name
        string agent_type
        dict capabilities
        int timeout_seconds
        int max_retries
    }
    
    WORKFLOW {
        string id PK
        string template_id
        string work_item_id FK
        string status
        int current_stage_index
        datetime created_at
        datetime started_at
    }
    
    PIPELINE_STAGE {
        string id PK
        string name
        string stage_type
        string agent_id FK
        int order
        int timeout_seconds
    }
    
    AGENT_EXECUTION {
        string id PK
        string agent_id FK
        string work_item_id FK
        string workflow_id FK
        string status
        string output
        datetime started_at
    }
    
    REVIEW_CYCLE {
        string id PK
        string workflow_id FK
        string stage_name
        string maker_agent_id FK
        string reviewer_agent_id FK
        int max_iterations
        string status
    }
    
    REVIEW_ITERATION {
        int iteration_number
        string maker_output
        string maker_execution_id
        string reviewer_execution_id
        datetime started_at
        datetime completed_at
    }
    
    REVIEW_FEEDBACK {
        string decision
        string comment
        tuple issues
        tuple suggestions
        datetime timestamp
    }
    
    USER {
        uuid id PK
        string username UK
        string email UK
        set roles
        bool is_active
        bool is_verified
        datetime created_at
    }
    
    COMMENT {
        string id PK
        string work_item_id FK
        string author_id FK
        string body
        datetime created_at
    }
    
    BOARD_WORKFLOW_TEMPLATE {
        string id PK
        string board_id
        string project_id
        datetime created_at
    }
    
    COLUMN_TEMPLATE {
        string name PK
        string type
        string agent_id FK
        int sla_seconds
        string on_failure_column
    }
    
    EXECUTION_STATUS {
        string id PK
        string status
        string description
    }
    
    WORKSPACE_CONTEXT {
        string workspace_type
        string project_id
        string work_item_id
        string branch_name
        bool create_pr
        string discussion_id
    }
    
    PROJECT_CONFIG {
        string repo_url
        string branch
        bool enabled
        string org
    }
```

### Class Diagram (Key Aggregates)

```mermaid
classDiagram
    class WorkItem {
        -id: string
        -project_id: string
        -title: string
        -status: WorkItemStatus
        -assigned_agent_id: string
        -current_workflow_id: string
        -current_stage: string
        +create(title, description, project_id)
        +assign_agent(agent_id, reason)
        +start()
        +mark_under_review()
        +complete()
        +fail(reason, error_details)
        +block(reason, blocking_issue_id)
        +unblock()
        +update_stage(stage)
        +can_start()
        +is_terminal()
    }
    
    class Workflow {
        -id: string
        -template_id: string
        -work_item_id: string
        -status: WorkflowStatus
        -current_stage_index: int
        -stages: list[PipelineStage]
        +advance_to_next_stage()
        +complete()
        +fail(error)
    }
    
    class PipelineStage {
        -id: string
        -name: string
        -workflow_id: string
        -stage_type: StageType
        -status: StageStatus
        -maker_agent_id: string
        -reviewer_agent_id: string
        -max_review_iterations: int
    }
    
    class Agent {
        -id: string
        -name: string
        -agent_type: AgentType
        -capabilities: dict
        -timeout_seconds: int
        -max_retries: int
        +update_capability(skill, proficiency)
        +update_timeout(seconds)
        +update_constraints(constraints)
    }
    
    class AgentExecution {
        -id: string
        -agent_id: string
        -work_item_id: string
        -status: ExecutionStatus
        -output: string
        -retry_count: int
        +start()
        +complete(output)
        +fail(error)
        +retry()
    }
    
    class ReviewCycle {
        -id: string
        -workflow_id: string
        -stage_name: string
        -maker_agent_id: string
        -reviewer_agent_id: string
        -max_iterations: int
        -_status: ReviewStatus
        +start_iteration(maker_output, maker_execution_id)
        +submit_review(decision, comment, reviewer_execution_id)
        +approve()
        +request_changes()
        +escalate(reason)
        +is_complete()
    }
    
    class ReviewFeedback {
        -decision: ReviewDecision
        -comment: string
        -issues: tuple[string]
        -suggestions: tuple[string]
        -timestamp: datetime
    }
    
    WorkItem "1" --> "0..*" Workflow: flows through
    WorkItem "1" --> "0..*" AgentExecution: triggers
    Workflow "1" --> "1..*" PipelineStage: contains
    Workflow "1" --> "0..*" ReviewCycle: has
    PipelineStage "N" --> "1" Agent: executes
    Agent "1" --> "0..*" AgentExecution: performs
    Agent "N" --> "M" ReviewCycle: reviews
    AgentExecution "N" --> "1" Workflow: belongs to
    ReviewCycle "1" --> "1..*" ReviewFeedback: collects
```

---

## Events

Every state change in domain models emits one or more domain events. These immutable events are the mechanism by which the domain layer communicates changes to the application layer and other subscribers.

### Event Emission Pattern

Domain models emit events through their methods:

1. **WorkItem.update_stage(stage)** → Emits `WorkItemStageUpdatedEvent`
2. **WorkItem.assign_agent(agent_id, reason)** → Emits `AgentAssigned`
3. **WorkItem.complete()** → Emits `WorkItemCompleted`
4. **ReviewCycle.create(...)** → Emits `ReviewCycleCreated`
5. **ReviewCycle.start_iteration(...)** → Emits `ReviewIterationStarted`
6. **ReviewCycle.submit_review(...)** → Emits `ReviewFeedbackSubmitted`
7. **ReviewCycle.approve()** → Emits `ReviewCycleApproved`
8. **ReviewCycle.escalate(reason)** → Emits `ReviewCycleEscalated`

### Event Subscribers

Events are published to the event bus and handled by multiple subscribers:

- **BoardHandler**: Updates project board when work items transition
- **MetricsHandler**: Records metrics on state changes
- **NotificationHandler**: Sends notifications to interested parties
- **AuditHandler**: Logs all state changes for audit trail
- **WorkflowHandler**: Advances workflow on stage completions

### Key Event Categories

1. **State Change Events**: WorkItemUpdatedEvent, WorkflowStageAdvancedEvent, ReviewApprovedEvent
2. **Lifecycle Events**: WorkItemCreatedEvent, ExecutionStartedEvent, ReviewCompletedEvent
3. **Transition Events**: WorkItemColumnChangedEvent, ExecutionStatusChangedEvent
4. **Validation Events**: ReviewFailedEvent, ExecutionFailedEvent

For complete event catalog, see `documentation/architecture/domain/events.md`.

---

## Examples

### Example 1: Creating a Work Item

```python
# Domain layer: Create work item
work_item = WorkItem(
    id="WI-123",
    project_id="proj-1",
    title="Implement authentication",
    description="Add OAuth2 support",
    status=WorkItemStatus.NEW,
    priority=WorkItemPriority.HIGH,
    labels=["feature", "auth"],
    external_id="github-issue-456",
    external_url="https://github.com/org/repo/issues/456",
    assigned_agent_id=None,
    assigned_at=None,
    current_workflow_id=None,
    current_stage=None,
    current_column=None,
    entered_column_at=None,
    created_at=datetime.now(UTC),
    updated_at=datetime.now(UTC)
)

# Application layer: Persist and emit event
event = WorkItemCreatedEvent(
    work_item_id=work_item.id,
    project_id=work_item.project_id,
    title=work_item.title,
    initial_column="Backlog"
)
await event_bus.publish(event)

# Subscribers react to event
# - BoardHandler: adds item to GitHub board column
# - MetricsHandler: initializes metrics tracking
# - AuditHandler: logs creation
```

### Example 2: Assigning an Agent to a Work Item

```python
# Validate agent exists and has capabilities
if agent.has_capability("implementation"):
    # Domain layer: Update work item assignment
    work_item.assigned_agent_id = agent.id
    work_item.assigned_at = datetime.now(UTC)
    work_item.status = WorkItemStatus.ASSIGNED
    
    # Emit event
    event = WorkItemAssignedEvent(
        work_item_id=work_item.id,
        agent_id=agent.id,
        agent_name=agent.name
    )
    await event_bus.publish(event)
    
    # Subscribers react:
    # - ExecutionHandler: schedules agent execution
    # - NotificationHandler: notifies agent of assignment
    # - MetricsHandler: records assignment time

else:
    # Domain layer validation: agent lacks required capability
    raise InvalidStateError(
        f"Agent {agent.id} cannot handle {work_item.title}: "
        f"missing capability 'implementation'"
    )
```

### Example 3: Handling Execution Failure and Repair Cycle

```python
# Execution fails
execution = agent_execution  # AgentExecution aggregate
execution.status = ExecutionStatus.FAILED
execution.error = "Tests failed: 3 failures, 2 warnings"

# Emit event
event = ExecutionFailedEvent(
    execution_id=execution.id,
    work_item_id=execution.work_item_id,
    error=execution.error
)
await event_bus.publish(event)

# Application layer: Repair cycle handler receives event
repair_cycle = RepairCycle(
    id=generate_id(),
    work_item_id=execution.work_item_id,
    failed_execution_id=execution.id,
    status=RepairCycleStatus.IN_PROGRESS,
    failures=[
        RepairTestFailure(
            file="tests/auth_test.py",
            test="test_login_oauth",
            message="Token validation failed"
        )
    ],
    warnings=[
        RepairTestWarning(
            file="src/auth.py",
            message="DeprecationWarning: use new auth library"
        )
    ],
    config=RepairCycleConfig(
        max_iterations=3,
        timeout_minutes=30,
        review_warnings=True
    ),
    created_at=datetime.now(UTC),
    updated_at=datetime.now(UTC)
)

# Repair cycle agents attempt fixes via RepairTestType.UNIT → INTEGRATION → E2E
```

### Example 4: Invalid State Transition (Error Case)

```python
# Domain layer invariant enforcement
workflow = Workflow(
    id="wf-1",
    stages=[
        PipelineStage(name="Development", position=0),
        PipelineStage(name="Review", position=1),
        PipelineStage(name="Deploy", position=2),
    ],
    current_stage_index=1  # Currently at Review
)

# Attempt invalid transition (skipping to Deploy before completing Review)
try:
    workflow.current_stage_index = 2  # Would skip Review
    if not workflow.can_transition_to(2):
        raise InvalidStateError(
            "Cannot skip workflow stages: must complete Review before Deploy"
        )
except InvalidStateError as e:
    # Application layer catches and logs
    logger.error(f"Workflow invariant violated: {e.message}")
    # Event NOT emitted (no state change occurred)
    # Work item remains in Review stage
```

### Example 5: Review Cycle with Maker-Reviewer Iteration

```python
# Create review cycle using factory method
review = ReviewCycle.create(
    workflow_id="wf-1",
    stage_name="code-review",
    maker_agent_id="agent-maker-1",
    reviewer_agent_id="agent-reviewer-1",
    max_iterations=3
)

# Maker produces initial output
review.start_iteration(
    maker_output="Implemented authentication module",
    maker_execution_id="exec-maker-1"
)

# Reviewer provides feedback
review.submit_review(
    decision=ReviewDecision.REQUEST_CHANGES,
    comment="Need to add input validation",
    reviewer_execution_id="exec-reviewer-1",
    issues=["Missing input validation for email field"],
    suggestions=["Add email validation before processing"]
)

# Cycle is now in CHANGES_REQUESTED state
assert review.status == ReviewStatus.CHANGES_REQUESTED
assert review.needs_maker_revision()

# Maker addresses feedback and revises
review.start_iteration(
    maker_output="Implemented authentication module with validation",
    maker_execution_id="exec-maker-2"
)

# Reviewer approves on second iteration
review.submit_review(
    decision=ReviewDecision.APPROVE,
    comment="Looks good now",
    reviewer_execution_id="exec-reviewer-2",
    issues=[],
    suggestions=[]
)

# Cycle is now APPROVED
assert review.is_complete()
assert review.final_decision == ReviewDecision.APPROVE
```

---

## Additional Domain Models

This section documents additional domain models and value objects that support specialized functionality in the system.

### Configuration Models

#### StageTemplate

**File**: `src/codetoreum/domain/workflow_template.py`

Represents the definition template for a pipeline stage in a workflow.

**Attributes**:
- `name` (str): Display name of the stage
- `agent_id` (str): Primary agent ID that executes in this stage
- `stage_type` (str): Type of stage execution ("sequential", "parallel", or "review")
- `dependencies` (list[str]): List of stage names that must complete before this stage
- `is_parallel` (bool): Whether this stage executes in parallel with other stages
- `maker_agent_id` (str | None): Agent ID for maker role (if review stage)
- `reviewer_agent_id` (str | None): Agent ID for reviewer role (if review stage)
- `max_review_iterations` (int): Maximum review iterations before escalation
- `metadata` (dict[str, Any]): Additional stage-specific configuration data

**Purpose**: Allows workflow architects to define reusable stage templates with clear roles and dependencies.

#### BoardReconciliationConfig

**File**: `src/codetoreum/domain/board_workflow_template.py`

Configuration for how boards should be reconciled with external systems (GitHub Projects, Jira boards, etc.).

**Attributes**:
- `reconciliation_type` (str): Type of reconciliation (e.g., "board_columns", "card_states")
- `sync_interval_seconds` (int): How often to sync with external system
- `conflict_resolution` (str): How to resolve conflicts ("external_wins", "local_wins", "merge")
- `external_id_mapping` (Dict[str, str]): Mapping of local IDs to external system IDs
- `ignore_patterns` (List[str]): Patterns for cards/columns to ignore during reconciliation
- `enabled` (bool): Whether reconciliation is currently enabled

**Purpose**: Controls how the system stays synchronized with external board systems.

### PR Review Cycle Models

#### PRReviewCycleState

**File**: `src/codetoreum/domain/pr_review_cycle_types.py`

Represents the current state of a PR review cycle at a point in time.

**Attributes**:
- `cycle_id` (str): Unique identifier for this review cycle
- `pr_id` (str): GitHub PR identifier
- `current_phase` (str): Current phase name (e.g., "code_review", "verification", "ci_check", "consolidation")
- `phase_index` (int): Position in phase sequence
- `cycle_number` (int): Which iteration of review (1, 2, 3, etc.)
- `findings` (List[Finding]): Issues/findings from current and prior phases
- `status` (str): Overall status ("in_progress", "approved", "changes_needed", "escalated")
- `started_at` (datetime): When cycle began
- `last_updated_at` (datetime): When state last changed

**Purpose**: Tracks the full state of a PR review cycle for resumption and debugging.

#### PRReviewCycleResult

**File**: `src/codetoreum/domain/pr_review_cycle_types.py`

Immutable record of a completed PR review cycle with all results and findings.

**Attributes**:
- `cycle_number` (int): Iteration count (1-based) for outer re-trigger tracking
- `workflow_run_id` (str): ID of the workflow run that executed this cycle
- `outcome` (PRReviewOutcome): Final outcome (ISSUES_FOUND, APPROVED, or MAX_CYCLES_REACHED)
- `phase_outputs` (tuple[PRReviewPhaseOutput, ...]): Results from each executed phase
- `all_findings` (tuple[PRReviewFinding, ...]): All findings from all phases
- `sub_issues_created` (tuple[str, ...]): IDs of created sub-issues (empty if approved/max_cycles)
- `ci_passed` (bool | None): CI check result (True/False if checked, None if skipped)
- `total_findings` (int): Total number of findings across all phases
- `critical_count`, `high_count`, `medium_count`, `low_count` (int): Counts by severity
- `total_duration_seconds` (float): Total time for entire review cycle
- `timestamp` (str): ISO 8601 timestamp when cycle started
- `next_column` (str): Name of column to move work item to (determined by outcome)

**Purpose**: Immutable record of complete PR review cycle for audit trail and decision-making.

#### PRReviewOutcome

**File**: `src/codetoreum/domain/pr_review_cycle_types.py`

An enumeration representing the final outcome of a completed PR review cycle.

**Enum Values**:
- `ISSUES_FOUND`: Review identified issues requiring fixes (creates sub-issues for each finding)
- `APPROVED`: PR approved without any issues (ready to progress to next workflow column)
- `MAX_CYCLES_REACHED`: Maximum review cycles exceeded (escalates to human reviewer)

**Purpose**: Represents the terminal outcome of a PR review cycle, determining next workflow action.

#### PRReviewPhaseOutput

**File**: `src/codetoreum/domain/pr_review_cycle_types.py`

Output produced by a single phase in the PR review cycle.

**Attributes**:
- `phase_name` (str): Name of the phase that produced this
- `phase_index` (int): Position in sequence
- `outcomes` (List[PRReviewOutcome]): Findings from this phase
- `agent_id` (str): ID of agent that executed this phase
- `duration_seconds` (float): Time spent in this phase
- `status` (str): Phase result ("success", "timeout", "error")
- `can_proceed_to_next` (bool): Whether next phase can proceed
- `execution_logs` (Optional[str]): Execution logs from phase

**Purpose**: Encapsulates output from a single review phase for composition into full cycle result.

### Session Management

#### ConversationalSessionState

**File**: `src/codetoreum/domain/conversational_session.py`

Represents the full state of a multi-turn conversational session between agent and user.

**Attributes**:
- `session_id` (str): Unique identifier for this session
- `work_item_id` (str): Work item this session is about
- `agent_id` (str): Agent engaged in conversation
- `messages` (List[Message]): All messages in conversation (user + agent)
- `current_turn` (int): Which turn of conversation (0-based)
- `context` (Dict[str, Any]): Contextual information for conversation
- `state` (str): Session state ("active", "paused", "completed", "error")
- `created_at` (datetime): When session started
- `last_message_at` (datetime): When last message occurred
- `timeout_seconds` (Optional[int]): How long before session times out
- `metadata` (Dict[str, Any]): Additional session metadata

**Purpose**: Maintains complete state for multi-turn agent conversations, enabling pause/resume and history replay.

### User and Security Models

#### APIKey

**File**: `src/codetoreum/domain/user.py`

Represents an API key for external authentication and integration.

**Attributes**:
- `id` (str): Unique identifier for this key
- `user_id` (str): Owner of the key
- `key_hash` (str): One-way hash of the actual key (actual key never stored)
- `key_prefix` (str): First few characters for identification (e.g., "ctm_abc123...")
- `name` (str): Human-readable name for this key
- `scopes` (List[str]): Permissions/scopes this key has access to
- `created_at` (datetime): When key was created
- `last_used_at` (Optional[datetime]): When key was last used
- `expires_at` (Optional[datetime]): When key expires (if applicable)
- `is_active` (bool): Whether key is currently active

**Purpose**: Enables external systems to authenticate with Codetoreum API securely.

**Invariants**:
- Actual key value never stored, only hash
- Keys must have at least one scope
- Expired keys are automatically deactivated
- Lost keys cannot be recovered; must be rotated

---

## Cross-References

Domain models are referenced by:
- **Application Services** (`src/codetoreum/application/`): Orchestrate models to implement workflows
- **Domain Events** (`src/codetoreum/domain/events/`): Emitted by models to signal state changes
- **Output Ports** (`src/codetoreum/ports/output/`): Adapters implement ports to persist/load models
- **Event Handlers** (`src/codetoreum/application/event_handlers/`): React to events and update models

Domain models are the foundation that all other layers build upon. See `documentation/architecture/domain/events.md` for domain events emitted by these models.
