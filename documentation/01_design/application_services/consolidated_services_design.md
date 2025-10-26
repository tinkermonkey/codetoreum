# Consolidated Application Services Design

This document provides detailed designs for the remaining application services, organized by functional category.

## Table of Contents
1. [Core Orchestration Services](#core-orchestration-services)
2. [Workspace Services](#workspace-services)
3. [Review and Feedback Services](#review-and-feedback-services)
4. [GitHub Integration Services](#github-integration-services)
5. [Task Management Services](#task-management-services)
6. [Observability Services](#observability-services)
7. [Pipeline Support Services](#pipeline-support-services)
8. [Configuration Services](#configuration-services)
9. [Infrastructure Services](#infrastructure-services)
10. [Pattern Detection Services](#pattern-detection-services)
11. [Support Services](#support-services)
12. [Execution Services](#execution-services)

---

## Core Orchestration Services

### Agent Scheduler

**Purpose**: Schedules and manages agent execution timing, priorities, and resource allocation.

**Port Interfaces**:
```python
class IAgentScheduler(ABC):
    @abstractmethod
    async def schedule(
        self, work_item: WorkItem, agent: Agent, priority: TaskPriority
    ) -> ScheduleResult:
        """Schedule agent execution for work item"""
        pass

    @abstractmethod
    async def can_schedule(self, agent: Agent) -> bool:
        """Check if agent can be scheduled (resource availability)"""
        pass

    @abstractmethod
    async def get_queue_depth(self, agent: str) -> int:
        """Get number of queued tasks for agent"""
        pass
```

**Key Responsibilities**:
- Priority-based task queuing
- Resource availability checking (dev containers, rate limits)
- Agent-specific queue management
- Rate limiting and throttling
- Fair scheduling across projects

**Implementation Notes**:
- Uses task queue with priority scoring
- Checks dev container state before scheduling
- Enforces per-agent concurrency limits
- Tracks Claude API rate limits
- Emits scheduling decision events

### Pipeline Manager

**Purpose**: Manages pipeline execution, stage coordination, and state checkpointing.

**Port Interfaces**:
```python
class IPipelineManager(ABC):
    @abstractmethod
    async def execute_pipeline(
        self, pipeline_config: PipelineConfig, context: Dict[str, Any]
    ) -> PipelineResult:
        """Execute complete pipeline"""
        pass

    @abstractmethod
    async def execute_stage(
        self, stage: Stage, context: Dict[str, Any]
    ) -> StageResult:
        """Execute single pipeline stage"""
        pass

    @abstractmethod
    async def checkpoint(self, pipeline_id: str, state: PipelineState) -> None:
        """Save pipeline checkpoint"""
        pass

    @abstractmethod
    async def recover(self, pipeline_id: str) -> Optional[PipelineState]:
        """Recover pipeline from checkpoint"""
        pass
```

**Key Responsibilities**:
- Sequential stage execution
- Stage dependency resolution
- State checkpointing and recovery
- Error handling and retry logic
- Stage result propagation

**Implementation Notes**:
- Checkpoints after each stage completion
- Recovers from last checkpoint on failure
- Propagates context through stages
- Implements circuit breaker pattern
- Emits pipeline lifecycle events

---

## Workspace Services

### Workspace Router

**Purpose**: Routes work items to appropriate workspace types based on configuration and agent capabilities.

**Port Interfaces**:
```python
class IWorkspaceRouter(ABC):
    @abstractmethod
    async def route(
        self, work_item: WorkItem, agent: Agent, pipeline: str
    ) -> WorkspaceRoutingDecision:
        """Determine workspace type for work item"""
        pass

    @abstractmethod
    async def select_discussion_category(
        self, work_item: WorkItem, agent: Agent
    ) -> Optional[str]:
        """Select discussion category for discussions workspace"""
        pass
```

**Routing Decision Logic**:
```python
@dataclass
class WorkspaceRoutingDecision:
    workspace_type: WorkspaceType  # ISSUES, DISCUSSIONS, HYBRID
    reason: str
    category_id: Optional[str]  # For discussions
    use_git: bool  # For hybrid

def route(work_item, agent, pipeline):
    # Check pipeline configuration
    pipeline_workspace = config.get_pipeline_workspace(pipeline)
    if pipeline_workspace != HYBRID:
        return WorkspaceRoutingDecision(
            workspace_type=pipeline_workspace,
            reason="Pipeline configured for {pipeline_workspace}",
            category_id=None,
            use_git=(pipeline_workspace == ISSUES)
        )

    # Hybrid mode: decide based on agent
    if agent.makes_code_changes:
        return WorkspaceRoutingDecision(
            workspace_type=ISSUES,
            reason="Agent makes code changes, requires git",
            category_id=None,
            use_git=True
        )
    else:
        return WorkspaceRoutingDecision(
            workspace_type=DISCUSSIONS,
            reason="Agent does analysis only, discussions sufficient",
            category_id=determine_category(work_item, agent),
            use_git=False
        )
```

### Issues Workspace Manager

**Purpose**: Manages Git-based workspace operations for issue workflows.

**Port Interfaces**:
```python
class IIssuesWorkspaceManager(ABC):
    @abstractmethod
    async def prepare(self, context: WorkspaceContext) -> PreparationResult:
        """Prepare workspace: branch, checkout, sync"""
        pass

    @abstractmethod
    async def finalize(
        self, context: WorkspaceContext, changes: Changes
    ) -> FinalizationResult:
        """Finalize workspace: commit, push"""
        pass

    @abstractmethod
    async def detect_conflicts(self, branch: str) -> ConflictDetectionResult:
        """Detect merge conflicts with main"""
        pass
```

**Preparation Flow**:
1. Determine or create feature branch
2. Checkout branch
3. Sync with main (pull --rebase)
4. Detect conflicts
5. Return branch metadata

**Finalization Flow**:
1. Stage changes
2. Create commit with standardized message
3. Push to remote
4. Return commit metadata

### Discussions Workspace Manager

**Purpose**: Manages discussion-based workspace operations.

**Port Interfaces**:
```python
class IDiscussionsWorkspaceManager(ABC):
    @abstractmethod
    async def prepare(self, context: WorkspaceContext) -> PreparationResult:
        """Prepare discussion workspace"""
        pass

    @abstractmethod
    async def finalize(
        self, context: WorkspaceContext, output: str
    ) -> FinalizationResult:
        """Finalize discussion workspace (no-op, output already posted)"""
        pass

    @abstractmethod
    async def ensure_discussion_exists(
        self, issue_number: int, category_id: str
    ) -> str:
        """Ensure discussion exists, return discussion_id"""
        pass
```

### Feature Branch Manager

**Purpose**: Manages feature branch lifecycle and naming conventions.

**Port Interfaces**:
```python
class IFeatureBranchManager(ABC):
    @abstractmethod
    async def get_or_create_branch(
        self, issue_number: int, parent_issue: Optional[int] = None
    ) -> BranchResult:
        """Get existing branch or create new one"""
        pass

    @abstractmethod
    async def detect_existing_branch(
        self, issue_number: int
    ) -> Optional[ExistingBranch]:
        """Detect existing branch for issue"""
        pass

    @abstractmethod
    def generate_branch_name(
        self, issue_number: int, parent_issue: Optional[int] = None
    ) -> str:
        """Generate branch name following conventions"""
        pass
```

**Branch Detection Logic**:
```python
def detect_existing_branch(issue_number):
    branches = git.list_remote_branches()

    # Search for exact match
    exact_pattern = f"feature/issue-{issue_number}"
    for branch in branches:
        if branch == exact_pattern:
            return ExistingBranch(
                name=branch,
                confidence=1.0,
                reason="Exact issue number match"
            )

    # Search for sub-issue match
    sub_pattern = f"feature/issue-*/sub-{issue_number}"
    for branch in branches:
        if matches_pattern(branch, sub_pattern):
            return ExistingBranch(
                name=branch,
                confidence=0.9,
                reason="Sub-issue match"
            )

    # Search for partial matches
    for branch in branches:
        if str(issue_number) in branch:
            return ExistingBranch(
                name=branch,
                confidence=0.5,
                reason="Partial match"
            )

    return None
```

### Git Workflow Manager

**Purpose**: Executes Git operations.

**Port Interfaces**:
```python
class IGitWorkflowManager(ABC):
    @abstractmethod
    async def create_branch(self, branch_name: str, base: str = "main") -> None:
        """Create new branch"""
        pass

    @abstractmethod
    async def checkout_branch(self, branch_name: str) -> None:
        """Checkout branch"""
        pass

    @abstractmethod
    async def commit(self, message: str, files: Optional[List[str]] = None) -> str:
        """Create commit, return commit SHA"""
        pass

    @abstractmethod
    async def push(self, branch: str, force: bool = False) -> None:
        """Push branch to remote"""
        pass

    @abstractmethod
    async def pull_rebase(self, branch: str = "main") -> RebaseResult:
        """Pull with rebase from branch"""
        pass

    @abstractmethod
    async def create_pull_request(
        self, branch: str, title: str, body: str
    ) -> PullRequestResult:
        """Create pull request via gh CLI"""
        pass
```

---

## Review and Feedback Services

### Review Service

**Purpose**: Orchestrates maker-checker review cycles.

**Port Interfaces**:
```python
class IReviewService(ABC):
    @abstractmethod
    async def start_review_cycle(
        self, maker_output: str, stage_config: StageConfig, context: Dict[str, Any]
    ) -> ReviewCycleResult:
        """Start new review cycle"""
        pass

    @abstractmethod
    async def execute_iteration(
        self, cycle: ReviewCycle
    ) -> ReviewIterationResult:
        """Execute one maker-checker iteration"""
        pass

    @abstractmethod
    async def should_escalate(self, cycle: ReviewCycle) -> bool:
        """Check if cycle should escalate to human"""
        pass

    @abstractmethod
    async def complete_cycle(
        self, cycle: ReviewCycle, approved: bool
    ) -> ReviewCompletionResult:
        """Complete review cycle"""
        pass
```

**Review Cycle Flow**:
```python
async def execute_review_cycle(maker_output, stage_config, context):
    cycle = ReviewCycle(
        maker_agent=stage_config.agent,
        reviewer_agent=stage_config.reviewer_agent,
        max_iterations=stage_config.max_iterations,
        iteration=0
    )

    while cycle.iteration < cycle.max_iterations:
        # Queue reviewer
        reviewer_result = await execute_reviewer(
            cycle.reviewer_agent,
            maker_output,
            context
        )

        # Parse review
        review = await review_parser.parse(reviewer_result.output)

        if review.approved:
            return await complete_cycle(cycle, approved=True)

        # Queue maker revision
        cycle.iteration += 1
        maker_output = await execute_maker_revision(
            cycle.maker_agent,
            maker_output,
            review.feedback,
            context
        )

    # Max iterations reached
    return await escalate_to_human(cycle)
```

### Review Parser

**Purpose**: Parses reviewer output into structured data.

**Port Interfaces**:
```python
class IReviewParser(ABC):
    @abstractmethod
    def parse(self, review_output: str) -> ReviewResult:
        """Parse reviewer output"""
        pass

    @abstractmethod
    def extract_issues(self, review_output: str) -> List[ReviewIssue]:
        """Extract issue list"""
        pass

    @abstractmethod
    def is_approved(self, review_output: str) -> bool:
        """Check if approved"""
        pass
```

**Parsing Logic**:
```python
def parse(review_output):
    # Look for approval marker
    approved = "[APPROVED]" in review_output

    # Extract issues section
    issues = []
    if "## Issues" in review_output:
        issues_section = extract_section(review_output, "## Issues")
        issues = parse_issue_list(issues_section)

    return ReviewResult(
        approved=approved,
        issues=issues,
        summary=extract_section(review_output, "## Summary"),
        raw_output=review_output
    )

def parse_issue_list(section):
    # Parse numbered or bulleted lists
    # Example: "1. [Issue Title]: Description"
    pattern = r"^\d+\.\s*\[([^\]]+)\]:\s*(.+)$"
    issues = []
    for line in section.split('\n'):
        match = re.match(pattern, line.strip())
        if match:
            issues.append(ReviewIssue(
                title=match.group(1),
                description=match.group(2),
                severity=infer_severity(match.group(2))
            ))
    return issues
```

### Feedback Manager

**Purpose**: Tracks and routes user feedback.

**Port Interfaces**:
```python
class IFeedbackManager(ABC):
    @abstractmethod
    async def detect_feedback(
        self, issue_number: int, agent: str
    ) -> Optional[Feedback]:
        """Detect new feedback on agent output"""
        pass

    @abstractmethod
    async def route_feedback(
        self, feedback: Feedback, context: Dict[str, Any]
    ) -> FeedbackRoutingResult:
        """Route feedback to appropriate agent"""
        pass

    @abstractmethod
    async def mark_processed(self, feedback_id: str) -> None:
        """Mark feedback as processed"""
        pass
```

**Feedback Detection Logic**:
```python
async def detect_feedback(issue_number, agent):
    # Get last agent comment timestamp
    last_comment_time = await get_last_agent_comment_time(
        issue_number, agent
    )

    # Get comments after last agent comment
    new_comments = await github.get_comments_since(
        issue_number, last_comment_time
    )

    # Filter for human comments
    human_comments = [
        c for c in new_comments
        if not c.author.endswith('[bot]')
    ]

    if not human_comments:
        return None

    # Classify feedback type
    comment = human_comments[0]
    feedback_type = classify_feedback(comment.body)

    return Feedback(
        type=feedback_type,
        author=comment.author,
        content=comment.body,
        comment_id=comment.id,
        is_question=(feedback_type == FeedbackType.QUESTION),
        timestamp=comment.created_at
    )
```

### Human Feedback Loop Service

**Purpose**: Manages human-in-the-loop interactions.

**Port Interfaces**:
```python
class IHumanFeedbackLoopService(ABC):
    @abstractmethod
    async def start_conversation(
        self, issue_number: int, agent: str, initial_comment_id: str
    ) -> ConversationSession:
        """Start conversational session"""
        pass

    @abstractmethod
    async def route_question(
        self, question: str, session: ConversationSession
    ) -> QuestionRoutingResult:
        """Route question to agent"""
        pass

    @abstractmethod
    async def check_exit_condition(
        self, session: ConversationSession
    ) -> bool:
        """Check if conversation should end (column change)"""
        pass

    @abstractmethod
    async def end_conversation(
        self, session: ConversationSession, reason: str
    ) -> None:
        """End conversational session"""
        pass
```

### Review Filter Manager

**Purpose**: Manages review issue filters.

**Port Interfaces**:
```python
class IReviewFilterManager(ABC):
    @abstractmethod
    async def add_filter(self, filter: ReviewFilter) -> str:
        """Add new filter, return filter_id"""
        pass

    @abstractmethod
    async def apply_filters(
        self, issues: List[ReviewIssue], agent: str
    ) -> List[ReviewIssue]:
        """Apply filters to issue list"""
        pass

    @abstractmethod
    async def learn_from_feedback(
        self, issue: ReviewIssue, human_decision: HumanDecision
    ) -> Optional[ReviewFilter]:
        """Learn filter from human feedback"""
        pass
```

---

## GitHub Integration Services

### GitHub Project Manager

**Purpose**: Manages GitHub Projects v2 boards.

**Port Interfaces**:
```python
class IGitHubProjectManager(ABC):
    @abstractmethod
    async def reconcile_project(
        self, project_config: ProjectConfig
    ) -> ReconciliationResult:
        """Reconcile project board with configuration"""
        pass

    @abstractmethod
    async def create_board(
        self, project: str, board_name: str
    ) -> BoardCreationResult:
        """Create new project board"""
        pass

    @abstractmethod
    async def update_columns(
        self, board_id: str, columns: List[ColumnConfig]
    ) -> ColumnUpdateResult:
        """Update board columns"""
        pass

    @abstractmethod
    async def move_card(
        self, board_id: str, card_id: str, column_id: str
    ) -> CardMoveResult:
        """Move card to column"""
        pass
```

**Reconciliation Flow**:
1. Load project configuration
2. Load saved GitHub state
3. Check if config changed (hash comparison)
4. For each pipeline:
   - Find or create board
   - Get Status field
   - For each column in workflow:
     - Find or create column option
     - Save column_id to state
5. Create or update labels
6. Save updated state

### Project Monitor

**Purpose**: Monitors GitHub boards for changes.

**Port Interfaces**:
```python
class IProjectMonitor(ABC):
    @abstractmethod
    async def start_monitoring(self, projects: List[str]) -> None:
        """Start monitoring projects"""
        pass

    @abstractmethod
    async def stop_monitoring(self) -> None:
        """Stop monitoring"""
        pass

    @abstractmethod
    async def poll_board(self, project: str, board: str) -> List[CardChange]:
        """Poll board for changes"""
        pass
```

**Polling Logic**:
```python
async def poll_board(project, board):
    # Get board state from GitHub
    items = await github_api.get_board_items(board_id)

    changes = []
    for item in items:
        issue_number = item.content.number
        current_column = item.field_value

        # Get last known column
        last_column = await redis.get(
            f"last_column:{project}:{issue_number}"
        )

        if current_column != last_column:
            changes.append(CardChange(
                issue_number=issue_number,
                from_column=last_column,
                to_column=current_column,
                timestamp=datetime.utcnow()
            ))

            # Update last known column
            await redis.set(
                f"last_column:{project}:{issue_number}",
                current_column
            )

    return changes
```

### GitHub Integration Service

**Purpose**: Handles GitHub API operations.

**Port Interfaces**:
```python
class IGitHubIntegrationService(ABC):
    @abstractmethod
    async def post_comment(
        self, issue_number: int, body: str, reply_to: Optional[str] = None
    ) -> CommentResult:
        """Post comment to issue"""
        pass

    @abstractmethod
    async def post_discussion_comment(
        self, discussion_id: str, body: str, reply_to: Optional[str] = None
    ) -> CommentResult:
        """Post comment to discussion"""
        pass

    @abstractmethod
    async def get_issue(self, issue_number: int) -> Issue:
        """Get issue data"""
        pass

    @abstractmethod
    async def update_labels(
        self, issue_number: int, labels: List[str]
    ) -> None:
        """Update issue labels"""
        pass

    @abstractmethod
    async def post_agent_output(
        self, context: Dict[str, Any], output: str, reply_to: Optional[str] = None
    ) -> PostResult:
        """Post agent output (workspace-aware routing)"""
        pass
```

**Workspace-Aware Posting**:
```python
async def post_agent_output(context, output, reply_to):
    workspace_type = context.get('workspace_type', 'issues')

    if workspace_type == 'discussions':
        discussion_id = context.get('discussion_id')
        return await post_discussion_comment(
            discussion_id, output, reply_to
        )
    else:
        issue_number = context.get('issue_number')
        return await post_comment(
            issue_number, output, reply_to
        )
```

### GitHub Discussions Service

**Purpose**: Specialized service for GitHub Discussions.

**Port Interfaces**:
```python
class IGitHubDiscussionsService(ABC):
    @abstractmethod
    async def create_discussion(
        self, category_id: str, title: str, body: str
    ) -> DiscussionResult:
        """Create new discussion"""
        pass

    @abstractmethod
    async def get_discussion(self, discussion_id: str) -> Discussion:
        """Get discussion data"""
        pass

    @abstractmethod
    async def add_comment(
        self, discussion_id: str, body: str, reply_to: Optional[str] = None
    ) -> CommentResult:
        """Add comment to discussion"""
        pass

    @abstractmethod
    async def get_categories(self) -> List[Category]:
        """Get discussion categories"""
        pass
```

---

## Task Management Services

### Task Queue Manager

**Purpose**: Manages priority-based task queue.

**Port Interfaces**:
```python
class ITaskQueueManager(ABC):
    @abstractmethod
    async def enqueue(self, task: Task) -> str:
        """Enqueue task, return task_id"""
        pass

    @abstractmethod
    async def dequeue(self) -> Optional[Task]:
        """Dequeue highest priority task"""
        pass

    @abstractmethod
    async def peek(self) -> Optional[Task]:
        """View next task without removing"""
        pass

    @abstractmethod
    async def size(self) -> int:
        """Get queue size"""
        pass

    @abstractmethod
    async def get_tasks_for_agent(self, agent: str) -> List[Task]:
        """Get all tasks for agent"""
        pass
```

**Priority Scoring**:
```python
def calculate_score(task):
    # Lower score = higher priority (sorted set ascending)
    # Score formula: -(priority * 1000 + timestamp)
    # This ensures:
    # - Higher priority tasks come first
    # - Among same priority, older tasks come first
    return -(task.priority.value * 1000 + task.created_at.timestamp())
```

### Work Execution State Tracker

**Purpose**: Tracks in-progress executions.

**Port Interfaces**:
```python
class IWorkExecutionStateTracker(ABC):
    @abstractmethod
    async def mark_in_progress(
        self, project: str, issue_number: int, column: str, agent: str
    ) -> bool:
        """Mark work in progress, returns False if already in progress"""
        pass

    @abstractmethod
    async def mark_completed(
        self, project: str, issue_number: int, column: str, agent: str
    ) -> None:
        """Mark work completed"""
        pass

    @abstractmethod
    async def is_in_progress(
        self, project: str, issue_number: int, column: str, agent: str
    ) -> bool:
        """Check if work in progress"""
        pass

    @abstractmethod
    async def cleanup_stuck_states(self, max_age_hours: int = 2) -> int:
        """Cleanup stuck states, return count cleaned"""
        pass
```

**Redis Key Pattern**:
```
execution_state:{project}:{issue_number}:{column}:{agent}
Value: {'status': 'in_progress', 'started_at': '...', ...}
TTL: 2 hours
```

### Conversational Session State Manager

**Purpose**: Manages conversational threads.

**Port Interfaces**:
```python
class IConversationalSessionStateManager(ABC):
    @abstractmethod
    async def start_session(
        self, project: str, issue_number: int, agent: str,
        board: str, column: str
    ) -> str:
        """Start session, return session_id"""
        pass

    @abstractmethod
    async def update_session(
        self, session_id: str, message: ConversationMessage
    ) -> None:
        """Add message to session"""
        pass

    @abstractmethod
    async def get_session(
        self, project: str, issue_number: int
    ) -> Optional[ConversationSession]:
        """Get active session"""
        pass

    @abstractmethod
    async def end_session(
        self, session_id: str, reason: str
    ) -> None:
        """End session"""
        pass

    @abstractmethod
    async def check_column_exit(
        self, session: ConversationSession, current_column: str
    ) -> bool:
        """Check if column changed (exit condition)"""
        pass
```

---

## Observability Services

### Event Processor

**Purpose**: Processes and routes observability events.

**Port Interfaces**:
```python
class IEventProcessor(ABC):
    @abstractmethod
    async def emit(self, event: ObservabilityEvent) -> None:
        """Emit event to all destinations"""
        pass

    @abstractmethod
    async def publish_stream(self, channel: str, event: Dict[str, Any]) -> None:
        """Publish to Redis pub/sub"""
        pass

    @abstractmethod
    async def add_to_stream(self, stream: str, event: Dict[str, Any]) -> None:
        """Add to Redis Stream"""
        pass

    @abstractmethod
    async def index_to_elasticsearch(self, event: ObservabilityEvent) -> None:
        """Index event to Elasticsearch"""
        pass
```

**Event Flow**:
```
Component → EventProcessor.emit()
  ├─> Redis Pub/Sub (real-time delivery)
  ├─> Redis Stream (history, 1000 events, 2hr TTL)
  └─> Elasticsearch (long-term storage, daily indices)
```

### Decision Event Emitter

**Purpose**: Convenience wrapper for decision events.

**Port Interfaces**:
```python
class IDecisionEventEmitter(ABC):
    @abstractmethod
    async def emit_routing_decision(
        self, issue_number: int, project: str, board: str,
        column: str, agent: str, reason: str, **kwargs
    ) -> None:
        """Emit agent routing decision"""
        pass

    @abstractmethod
    async def emit_progression_decision(
        self, issue_number: int, project: str, from_stage: str,
        to_stage: str, action: str, reason: str, **kwargs
    ) -> None:
        """Emit workflow progression decision"""
        pass

    @abstractmethod
    async def emit_feedback_detected(
        self, issue_number: int, project: str, board: str,
        feedback_type: str, content: str, **kwargs
    ) -> None:
        """Emit feedback detection"""
        pass
```

### Metrics Collector

**Purpose**: Collects execution and quality metrics.

**Port Interfaces**:
```python
class IMetricsCollector(ABC):
    @abstractmethod
    async def record_task_metric(
        self, agent: str, duration_ms: float, success: bool, **kwargs
    ) -> None:
        """Record task execution metric"""
        pass

    @abstractmethod
    async def record_quality_metric(
        self, agent: str, metric_name: str, score: float, **kwargs
    ) -> None:
        """Record quality metric"""
        pass

    @abstractmethod
    async def get_agent_metrics(
        self, agent: str, start_time: datetime, end_time: datetime
    ) -> AgentMetrics:
        """Get aggregated metrics for agent"""
        pass
```

### Health Monitor

**Purpose**: Monitors system health.

**Port Interfaces**:
```python
class IHealthMonitor(ABC):
    @abstractmethod
    async def check_health(self) -> HealthStatus:
        """Check overall system health"""
        pass

    @abstractmethod
    async def check_redis(self) -> ComponentHealth:
        """Check Redis connectivity"""
        pass

    @abstractmethod
    async def check_github(self) -> ComponentHealth:
        """Check GitHub API access"""
        pass

    @abstractmethod
    async def check_docker(self) -> ComponentHealth:
        """Check Docker availability"""
        pass

    @abstractmethod
    async def check_elasticsearch(self) -> ComponentHealth:
        """Check Elasticsearch connectivity"""
        pass
```

---

## Pipeline Support Services

### Pipeline Progression Service

**Purpose**: Manages issue movement between columns.

**Port Interfaces**:
```python
class IPipelineProgressionService(ABC):
    @abstractmethod
    async def move_to_column(
        self, project: str, issue_number: int, column_name: str
    ) -> ProgressionResult:
        """Move issue to column"""
        pass

    @abstractmethod
    async def get_next_column(
        self, workflow: WorkflowConfig, current_column: str
    ) -> Optional[str]:
        """Determine next column"""
        pass

    @abstractmethod
    async def can_auto_advance(
        self, workflow: WorkflowConfig, current_column: str
    ) -> bool:
        """Check if can auto-advance"""
        pass
```

### Pipeline Run Manager

**Purpose**: Tracks pipeline runs.

**Port Interfaces**:
```python
class IPipelineRunManager(ABC):
    @abstractmethod
    async def start_run(
        self, project: str, issue_number: int, pipeline: str
    ) -> str:
        """Start pipeline run, return run_id"""
        pass

    @abstractmethod
    async def complete_run(
        self, run_id: str, success: bool
    ) -> None:
        """Complete pipeline run"""
        pass

    @abstractmethod
    async def get_active_runs(self) -> List[PipelineRun]:
        """Get all active runs"""
        pass

    @abstractmethod
    async def cleanup_stale_runs(self, max_age_hours: int = 2) -> int:
        """Cleanup stale runs"""
        pass
```

### Repair Cycle Service & Runner

**Purpose**: Test-driven repair cycles.

**Port Interfaces**:
```python
class IRepairCycleService(ABC):
    @abstractmethod
    async def execute_repair_cycle(
        self, test_configs: List[TestConfig], agent: str,
        context: Dict[str, Any]
    ) -> RepairCycleResult:
        """Execute complete repair cycle"""
        pass

    @abstractmethod
    async def run_tests(
        self, test_config: TestConfig, container_id: str
    ) -> TestResult:
        """Run tests in container"""
        pass

    @abstractmethod
    async def fix_failures(
        self, failures: List[TestFailure], agent: str, container_id: str
    ) -> FixResult:
        """Fix test failures"""
        pass
```

**Repair Cycle Flow**:
1. Create or recover container
2. For each test type:
   - Run tests
   - If failures: Group by file
   - For each failing file:
     - Prompt agent to fix
     - Re-run tests
     - Repeat up to max iterations
   - If warnings and review enabled:
     - Prompt agent to review warnings
3. Cleanup container
4. Return results

---

## Configuration Services

### Configuration Manager

**Purpose**: Central configuration access.

**Port Interfaces**:
```python
class IConfigurationManager(ABC):
    @abstractmethod
    async def get_project_config(self, project: str) -> ProjectConfig:
        """Get project configuration"""
        pass

    @abstractmethod
    async def get_agent_config(self, agent: str) -> AgentConfig:
        """Get agent configuration"""
        pass

    @abstractmethod
    async def get_pipeline_template(self, template: str) -> PipelineTemplate:
        """Get pipeline template"""
        pass

    @abstractmethod
    async def get_workflow_template(self, workflow: str) -> WorkflowTemplate:
        """Get workflow template"""
        pass

    @abstractmethod
    async def get_mcp_servers(self, agent: str) -> List[MCPServer]:
        """Get MCP servers for agent"""
        pass
```

### State Manager

**Purpose**: GitHub state persistence.

**Port Interfaces**:
```python
class IStateManager(ABC):
    @abstractmethod
    async def save_github_state(
        self, project: str, state: GitHubState
    ) -> None:
        """Save GitHub state"""
        pass

    @abstractmethod
    async def load_github_state(self, project: str) -> GitHubState:
        """Load GitHub state"""
        pass

    @abstractmethod
    async def needs_reconciliation(self, project: str) -> bool:
        """Check if reconciliation needed"""
        pass
```

### Dev Container State Manager

**Purpose**: Tracks Docker image status.

**Port Interfaces**:
```python
class IDevContainerStateManager(ABC):
    @abstractmethod
    async def get_status(self, project: str) -> DevContainerStatus:
        """Get dev container status"""
        pass

    @abstractmethod
    async def update_status(
        self, project: str, status: DevContainerStatus
    ) -> None:
        """Update dev container status"""
        pass

    @abstractmethod
    async def verify_image_exists(self, project: str) -> bool:
        """Check if Docker image exists"""
        pass
```

---

## Infrastructure Services

### Project Workspace Manager

**Purpose**: Manages project directories.

**Port Interfaces**:
```python
class IProjectWorkspaceManager(ABC):
    @abstractmethod
    async def initialize_project(self, project: str) -> InitializationResult:
        """Initialize project workspace"""
        pass

    @abstractmethod
    async def get_project_dir(self, project: str) -> Path:
        """Get project directory path"""
        pass

    @abstractmethod
    async def clone_or_update(self, project: str) -> CloneResult:
        """Clone or update project repository"""
        pass
```

### Auto Commit Service

**Purpose**: Automated git commits.

**Port Interfaces**:
```python
class IAutoCommitService(ABC):
    @abstractmethod
    async def commit_changes(
        self, branch: str, message: str
    ) -> CommitResult:
        """Auto-commit changes"""
        pass

    @abstractmethod
    async def detect_changes(self) -> List[str]:
        """Detect changed files"""
        pass

    @abstractmethod
    def generate_commit_message(
        self, agent: str, issue_number: int
    ) -> str:
        """Generate standardized commit message"""
        pass
```

### Agent Container Recovery Service

**Purpose**: Recovers containers on restart.

**Port Interfaces**:
```python
class IAgentContainerRecoveryService(ABC):
    @abstractmethod
    async def recover_or_cleanup(self) -> RecoveryResult:
        """Recover or cleanup containers on startup"""
        pass

    @abstractmethod
    async def assess_container(
        self, container_name: str
    ) -> ContainerAssessment:
        """Assess container state"""
        pass
```

### Scheduled Tasks Service

**Purpose**: Periodic maintenance.

**Port Interfaces**:
```python
class IScheduledTasksService(ABC):
    @abstractmethod
    async def start(self) -> None:
        """Start scheduled tasks"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop scheduled tasks"""
        pass

    @abstractmethod
    async def add_task(
        self, name: str, schedule: str, handler: Callable
    ) -> None:
        """Add scheduled task"""
        pass
```

---

## Pattern Detection Services

All pattern detection services follow similar interfaces:

### Pattern Detection Service

```python
class IPatternDetectionService(ABC):
    @abstractmethod
    async def detect_patterns(
        self, logs: List[LogEntry], time_window: timedelta
    ) -> List[Pattern]:
        """Detect patterns in logs"""
        pass
```

### Pattern Ingestion Service

```python
class IPatternIngestionService(ABC):
    @abstractmethod
    async def ingest(self, data: Union[LogEntry, Event]) -> None:
        """Ingest data for pattern analysis"""
        pass
```

### Pattern Analysis Service

```python
class IPatternAnalysisService(ABC):
    @abstractmethod
    async def analyze(self, pattern: Pattern) -> AnalysisResult:
        """Analyze detected pattern"""
        pass
```

### Pattern GitHub Integration

```python
class IPatternGitHubIntegration(ABC):
    @abstractmethod
    async def create_issue_for_pattern(
        self, pattern: Pattern, analysis: AnalysisResult
    ) -> str:
        """Create GitHub issue for pattern, return issue_number"""
        pass
```

### Pattern Alerting Service

```python
class IPatternAlertingService(ABC):
    @abstractmethod
    async def alert(self, pattern: Pattern, severity: AlertSeverity) -> None:
        """Send alert for pattern"""
        pass
```

---

## Support Services

### Circuit Breaker Service

**Purpose**: Fault tolerance.

**Port Interfaces**:
```python
class ICircuitBreakerService(ABC):
    @abstractmethod
    async def call(
        self, name: str, func: Callable, *args, **kwargs
    ) -> Any:
        """Call function with circuit breaker"""
        pass

    @abstractmethod
    async def get_state(self, name: str) -> CircuitBreakerState:
        """Get circuit breaker state"""
        pass

    @abstractmethod
    async def reset(self, name: str) -> None:
        """Reset circuit breaker"""
        pass
```

**States**: CLOSED (normal), OPEN (failing), HALF_OPEN (testing recovery)

### Claude Token Scheduler

**Purpose**: Rate limiting.

**Port Interfaces**:
```python
class IClaudeTokenScheduler(ABC):
    @abstractmethod
    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens, blocks if not available"""
        pass

    @abstractmethod
    async def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens, returns False if not available"""
        pass

    @abstractmethod
    async def get_available_tokens(self) -> int:
        """Get available tokens"""
        pass
```

**Algorithm**: Token bucket with configurable rate and burst size

### Claude Code Failure Handler

**Purpose**: Handles Claude Code failures.

**Port Interfaces**:
```python
class IClaudeCodeFailureHandler(ABC):
    @abstractmethod
    async def handle_failure(
        self, error: Exception, context: Dict[str, Any]
    ) -> FailureHandlingResult:
        """Handle Claude Code failure"""
        pass

    @abstractmethod
    def classify_error(self, error: Exception) -> ErrorType:
        """Classify error type"""
        pass

    @abstractmethod
    async def should_retry(
        self, error: Exception, attempt: int
    ) -> bool:
        """Determine if should retry"""
        pass
```

---

## Execution Services

### Claude Integration Service

**Purpose**: Claude Code CLI execution.

**Port Interfaces**:
```python
class IClaudeIntegrationService(ABC):
    @abstractmethod
    async def execute(
        self, prompt: str, context: ExecutionContext,
        stream_callback: Callable
    ) -> ClaudeResult:
        """Execute Claude Code with prompt"""
        pass

    @abstractmethod
    async def execute_local(
        self, prompt: str, work_dir: Path, stream_callback: Callable
    ) -> ClaudeResult:
        """Execute Claude Code locally"""
        pass

    @abstractmethod
    async def execute_docker(
        self, prompt: str, container_config: ContainerConfig,
        stream_callback: Callable
    ) -> ClaudeResult:
        """Execute Claude Code in Docker"""
        pass
```

**Execution Paths**:
- **Local**: Direct `claude` CLI for dev_environment_setup (needs Docker socket)
- **Docker**: Containerized execution for all other agents

### Docker Agent Runner

**Purpose**: Docker container management.

**Port Interfaces**:
```python
class IDockerAgentRunner(ABC):
    @abstractmethod
    async def run_in_container(
        self, config: ContainerConfig, command: List[str],
        stream_callback: Callable
    ) -> ContainerResult:
        """Run command in agent container"""
        pass

    @abstractmethod
    async def create_container(
        self, config: ContainerConfig
    ) -> str:
        """Create container, return container_id"""
        pass

    @abstractmethod
    async def cleanup_container(self, container_id: str) -> None:
        """Cleanup container"""
        pass

    @abstractmethod
    async def stream_logs(
        self, container_id: str, callback: Callable
    ) -> None:
        """Stream container logs"""
        pass
```

**Container Configuration**:
```python
@dataclass
class ContainerConfig:
    image: str
    name: str
    working_dir: str
    volumes: Dict[str, str]  # host_path: container_path
    environment: Dict[str, str]
    network: str
    user: str
```

---

## Summary

This document provides comprehensive designs for all 46 application services in the redesigned Codetoreum system. Each service:

1. **Has Clear Responsibilities**: Single responsibility principle
2. **Defines Port Interfaces**: Hexagonal architecture with clear contracts
3. **Uses Domain Models**: Rich domain objects instead of dictionaries
4. **Supports Testing**: Mock implementations for all ports
5. **Enables Simulation**: In-memory adapters for full system testing
6. **Is Observable**: Emits events and metrics
7. **Handles Errors**: Comprehensive error handling and recovery

All services follow the same architectural patterns and can be tested, simulated, and extended independently.
