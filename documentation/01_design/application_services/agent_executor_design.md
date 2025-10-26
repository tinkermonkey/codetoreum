# Agent Executor Service - Detailed Design

## Overview

The Agent Executor is the centralized service responsible for ALL agent executions in the system. It guarantees consistent observability event emission, workspace management, Claude Code integration, and output handling for every agent invocation.

## Responsibilities

### Primary Responsibilities
1. **Unified Execution Entry Point**: Single entry point for all agent executions
2. **Guaranteed Observability**: Emit lifecycle events (initialized, started, completed, failed) for every execution
3. **Workspace Coordination**: Prepare and finalize workspace context (git branches, discussions)
4. **Claude Code Integration**: Execute agents via Claude Code with streaming support
5. **Output Handling**: Extract, format, and post agent output to GitHub
6. **State Tracking**: Track execution state and prevent duplicates

### Secondary Responsibilities
1. **Error Recovery**: Handle failures with retries and circuit breakers
2. **Session Continuity**: Manage Claude Code session IDs for multi-turn conversations
3. **Dev Container Validation**: Ensure required Docker images are available
4. **Metric Collection**: Track execution metrics (duration, success rate, token usage)

## Port Interfaces (Hexagonal Architecture)

### Input Ports (Commands)
```python
class IAgentExecutor(ABC):
    """Primary interface for agent execution"""

    @abstractmethod
    async def execute_agent(
        self,
        agent_name: str,
        project_name: str,
        task_context: Dict[str, Any],
        task_id_prefix: str = "task"
    ) -> AgentExecutionResult:
        """
        Execute an agent with the given context

        Args:
            agent_name: Name of the agent to execute
            project_name: Project name
            task_context: Context dictionary with issue, board, column, etc.
            task_id_prefix: Prefix for task ID generation

        Returns:
            AgentExecutionResult with output, metadata, and status
        """
        pass

    @abstractmethod
    async def execute_agent_with_context(
        self,
        agent_instance: Agent,
        execution_context: ExecutionContext
    ) -> AgentExecutionResult:
        """
        Execute a specific agent instance with full execution context

        Args:
            agent_instance: Instantiated agent
            execution_context: Complete execution context

        Returns:
            AgentExecutionResult
        """
        pass
```

### Output Ports (Infrastructure Dependencies)
```python
class IAgentRegistry(ABC):
    """Interface to agent registry for agent instantiation"""
    @abstractmethod
    def get_agent(self, agent_name: str, project: str) -> Agent:
        """Get agent instance by name"""
        pass

class IWorkspaceContextFactory(ABC):
    """Interface to workspace context creation"""
    @abstractmethod
    async def create_workspace_context(
        self,
        workspace_type: WorkspaceType,
        project: str,
        issue_number: int,
        task_context: Dict[str, Any]
    ) -> IWorkspaceContext:
        """Create appropriate workspace context"""
        pass

class IClaudeIntegration(ABC):
    """Interface to Claude Code execution"""
    @abstractmethod
    async def execute(
        self,
        prompt: str,
        context: ExecutionContext,
        stream_callback: Callable
    ) -> ClaudeResult:
        """Execute Claude Code with prompt"""
        pass

class IGitHubOutputHandler(ABC):
    """Interface to GitHub output posting"""
    @abstractmethod
    async def post_output(
        self,
        project: str,
        issue_number: int,
        agent_name: str,
        output: str,
        workspace_type: WorkspaceType,
        reply_to_id: Optional[str] = None
    ) -> PostResult:
        """Post agent output to GitHub"""
        pass

class IObservability(ABC):
    """Interface to observability event emission"""
    @abstractmethod
    async def emit_agent_initialized(
        self, event: AgentInitializedEvent
    ) -> str:
        """Emit agent initialized event, returns execution_id"""
        pass

    @abstractmethod
    async def emit_agent_completed(
        self, event: AgentCompletedEvent
    ) -> None:
        """Emit agent completed event"""
        pass

    @abstractmethod
    async def emit_agent_failed(
        self, event: AgentFailedEvent
    ) -> None:
        """Emit agent failed event"""
        pass

class IWorkExecutionState(ABC):
    """Interface to execution state tracking"""
    @abstractmethod
    async def mark_in_progress(
        self, project: str, issue_number: int, column: str, agent: str
    ) -> bool:
        """Mark work as in progress, returns False if already in progress"""
        pass

    @abstractmethod
    async def mark_completed(
        self, project: str, issue_number: int, column: str, agent: str
    ) -> None:
        """Mark work as completed"""
        pass
```

## Domain Models

### Input Models
```python
@dataclass
class ExecutionContext:
    """Complete context for agent execution"""
    # Identification
    pipeline_id: str
    task_id: str
    agent: str
    project: str

    # Work directory
    work_dir: Path

    # Nested task context
    context: Dict[str, Any]  # Contains issue, board, column, etc.

    # Execution tracking
    completed_work: List[str]
    decisions: List[Dict]
    metrics: Dict[str, Any]
    validation: Dict[str, Any]

    # Infrastructure callbacks
    stream_callback: Optional[Callable]

    # Configuration
    claude_model: str
    use_docker: bool
    agent_config: Dict[str, Any]
```

### Output Models
```python
@dataclass
class AgentExecutionResult:
    """Result of agent execution"""
    success: bool
    output: str  # Primary output (markdown)
    execution_id: str  # Unique execution identifier
    agent_name: str
    project: str
    task_id: str

    # Execution metadata
    duration_ms: float
    started_at: datetime
    completed_at: datetime

    # Claude metadata
    session_id: Optional[str]  # For session continuity
    token_usage: Optional[TokenUsage]

    # Workspace metadata
    branch_name: Optional[str]
    commit_sha: Optional[str]
    discussion_id: Optional[str]

    # GitHub metadata
    comment_id: Optional[str]
    comment_url: Optional[str]

    # Error information
    error: Optional[str]
    error_type: Optional[ErrorType]

@dataclass
class TokenUsage:
    """Claude API token usage"""
    input_tokens: int
    output_tokens: int
    total_tokens: int

class ErrorType(Enum):
    """Types of execution errors"""
    WORKSPACE_ERROR = "workspace_error"
    CLAUDE_ERROR = "claude_error"
    OUTPUT_ERROR = "output_error"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT_ERROR = "timeout_error"
    UNKNOWN_ERROR = "unknown_error"
```

## Core Execution Logic

### 1. Main Execution Flow
```python
class AgentExecutor:
    def __init__(
        self,
        agent_registry: IAgentRegistry,
        workspace_factory: IWorkspaceContextFactory,
        claude: IClaudeIntegration,
        github_output: IGitHubOutputHandler,
        observability: IObservability,
        work_state: IWorkExecutionState,
        config: IProjectConfiguration
    ):
        self.agent_registry = agent_registry
        self.workspace_factory = workspace_factory
        self.claude = claude
        self.github_output = github_output
        self.observability = observability
        self.work_state = work_state
        self.config = config

    async def execute_agent(
        self,
        agent_name: str,
        project_name: str,
        task_context: Dict[str, Any],
        task_id_prefix: str = "task"
    ) -> AgentExecutionResult:
        """
        Execute agent with guaranteed observability and workspace management

        Execution Flow:
        1. Generate unique task_id and execution_id
        2. Emit task_received event
        3. Mark work as in-progress
        4. Create stream callback for live logs
        5. Build execution context
        6. Prepare workspace (branch/discussion)
        7. Emit agent_initialized event
        8. Get agent instance from registry
        9. Execute agent via agent.execute(context)
        10. Extract and format output
        11. Post output to GitHub
        12. Finalize workspace (commit/push)
        13. Record execution outcome
        14. Emit agent_completed/failed event
        15. Return result
        """
        start_time = datetime.utcnow()
        task_id = f"{task_id_prefix}_{agent_name}_{int(time.time())}"
        execution_id = str(uuid.uuid4())

        # Emit task received
        await self.observability.emit_task_received(
            TaskReceivedEvent(
                agent=agent_name,
                task_id=task_id,
                project=project_name,
                context=task_context,
                timestamp=start_time
            )
        )

        try:
            # Check if work already in progress
            issue_number = task_context.get('issue_number')
            column = task_context.get('column')
            if issue_number and column:
                in_progress = await self.work_state.mark_in_progress(
                    project_name, issue_number, column, agent_name
                )
                if not in_progress:
                    return AgentExecutionResult(
                        success=False,
                        output="",
                        execution_id=execution_id,
                        agent_name=agent_name,
                        project=project_name,
                        task_id=task_id,
                        duration_ms=0,
                        started_at=start_time,
                        completed_at=datetime.utcnow(),
                        error="Work already in progress",
                        error_type=ErrorType.VALIDATION_ERROR,
                        session_id=None,
                        token_usage=None,
                        branch_name=None,
                        commit_sha=None,
                        discussion_id=None,
                        comment_id=None,
                        comment_url=None
                    )

            # Create stream callback
            stream_callback = self._create_stream_callback(
                agent_name, task_id, project_name
            )

            # Build execution context
            exec_context = await self._build_execution_context(
                agent_name, project_name, task_id, task_context, stream_callback
            )

            # Prepare workspace
            workspace_context = None
            if issue_number and not task_context.get('skip_workspace_prep'):
                workspace_type = task_context.get('workspace_type', 'issues')
                workspace_context = await self.workspace_factory.create_workspace_context(
                    WorkspaceType(workspace_type),
                    project_name,
                    issue_number,
                    task_context
                )

                prep_result = await workspace_context.prepare_execution()
                # Merge preparation results into task_context
                task_context.update(prep_result)

            # Emit agent initialized
            agent_config = await self.config.get_agent_config(agent_name)
            await self.observability.emit_agent_initialized(
                AgentInitializedEvent(
                    agent=agent_name,
                    task_id=task_id,
                    execution_id=execution_id,
                    project=project_name,
                    agent_config=agent_config,
                    branch_name=task_context.get('branch_name'),
                    container_name=self._get_container_name(project_name, task_id),
                    timestamp=datetime.utcnow()
                )
            )

            # Get agent instance
            agent = self.agent_registry.get_agent(agent_name, project_name)

            # Execute agent
            result = await agent.execute(exec_context)

            # Extract output
            output = result.get('markdown_analysis') or result.get('raw_analysis_result', '')
            session_id = result.get('claude_session_id')
            token_usage = result.get('token_usage')

            # Post output to GitHub
            post_result = await self.github_output.post_output(
                project_name,
                issue_number,
                agent_name,
                output,
                WorkspaceType(task_context.get('workspace_type', 'issues')),
                task_context.get('reply_to_comment_id')
            )

            # Finalize workspace
            if workspace_context:
                commit_message = f"{agent_name} analysis for issue #{issue_number}"
                finalize_result = await workspace_context.finalize_execution(
                    result, commit_message
                )
                task_context.update(finalize_result)

            # Mark completed
            if issue_number and column:
                await self.work_state.mark_completed(
                    project_name, issue_number, column, agent_name
                )

            end_time = datetime.utcnow()
            duration_ms = (end_time - start_time).total_seconds() * 1000

            # Emit completed
            await self.observability.emit_agent_completed(
                AgentCompletedEvent(
                    agent=agent_name,
                    task_id=task_id,
                    execution_id=execution_id,
                    project=project_name,
                    duration_ms=duration_ms,
                    success=True,
                    output=output,
                    timestamp=end_time
                )
            )

            return AgentExecutionResult(
                success=True,
                output=output,
                execution_id=execution_id,
                agent_name=agent_name,
                project=project_name,
                task_id=task_id,
                duration_ms=duration_ms,
                started_at=start_time,
                completed_at=end_time,
                session_id=session_id,
                token_usage=token_usage,
                branch_name=task_context.get('branch_name'),
                commit_sha=task_context.get('commit_sha'),
                discussion_id=task_context.get('discussion_id'),
                comment_id=post_result.comment_id if post_result else None,
                comment_url=post_result.comment_url if post_result else None,
                error=None,
                error_type=None
            )

        except Exception as e:
            # Mark failed
            if issue_number and column:
                await self.work_state.mark_completed(
                    project_name, issue_number, column, agent_name
                )

            end_time = datetime.utcnow()
            duration_ms = (end_time - start_time).total_seconds() * 1000

            # Emit failed
            await self.observability.emit_agent_failed(
                AgentFailedEvent(
                    agent=agent_name,
                    task_id=task_id,
                    execution_id=execution_id,
                    project=project_name,
                    duration_ms=duration_ms,
                    error=str(e),
                    error_type=self._classify_error(e),
                    timestamp=end_time
                )
            )

            return AgentExecutionResult(
                success=False,
                output="",
                execution_id=execution_id,
                agent_name=agent_name,
                project=project_name,
                task_id=task_id,
                duration_ms=duration_ms,
                started_at=start_time,
                completed_at=end_time,
                error=str(e),
                error_type=self._classify_error(e),
                session_id=None,
                token_usage=None,
                branch_name=None,
                commit_sha=None,
                discussion_id=None,
                comment_id=None,
                comment_url=None
            )
```

### 2. Stream Callback Creation
```python
def _create_stream_callback(
    self, agent_name: str, task_id: str, project_name: str
) -> Callable:
    """
    Create callback for Claude Code stream events

    The callback:
    1. Receives stream events from Claude Code
    2. Publishes to Redis pub/sub for real-time delivery to web UI
    3. Adds to Redis Stream for historical access
    4. Tracks session_id and token usage
    """
    async def callback(event: Dict[str, Any]) -> None:
        event_data = {
            'agent': agent_name,
            'task_id': task_id,
            'project': project_name,
            'timestamp': event.get('timestamp', time.time()),
            'event': event
        }

        # Publish to Redis pub/sub (real-time)
        await self.observability.publish_stream_event(
            'orchestrator:claude_stream',
            event_data
        )

        # Add to Redis Stream (history)
        await self.observability.add_to_stream(
            'orchestrator:claude_logs_stream',
            event_data
        )

    return callback
```

### 3. Execution Context Builder
```python
async def _build_execution_context(
    self,
    agent_name: str,
    project_name: str,
    task_id: str,
    task_context: Dict[str, Any],
    stream_callback: Callable
) -> ExecutionContext:
    """Build complete execution context for agent"""
    # Get project directory
    work_dir = await self._get_project_dir(project_name)

    # Get agent configuration
    agent_config = await self.config.get_agent_config(agent_name)

    # Generate pipeline ID
    pipeline_id = f"pipeline_{task_id}_{int(time.time())}"

    return ExecutionContext(
        pipeline_id=pipeline_id,
        task_id=task_id,
        agent=agent_name,
        project=project_name,
        work_dir=work_dir,
        context=task_context,
        completed_work=[],
        decisions=[],
        metrics={},
        validation={},
        stream_callback=stream_callback,
        claude_model=agent_config.model,
        use_docker=task_context.get('use_docker', True),
        agent_config=agent_config.__dict__
    )
```

## Testing Strategy

### Unit Tests
```python
async def test_execute_agent_success():
    """Test successful agent execution with all events emitted"""
    # Arrange
    mock_registry = MockAgentRegistry()
    mock_workspace = MockWorkspaceFactory()
    mock_claude = MockClaudeIntegration()
    mock_github = MockGitHubOutputHandler()
    mock_obs = MockObservability()
    mock_state = MockWorkExecutionState()
    mock_config = MockProjectConfiguration()

    executor = AgentExecutor(
        mock_registry, mock_workspace, mock_claude,
        mock_github, mock_obs, mock_state, mock_config
    )

    # Act
    result = await executor.execute_agent(
        "business_analyst",
        "test-project",
        {"issue_number": 123, "column": "Requirements"}
    )

    # Assert
    assert result.success
    assert result.output != ""
    assert result.execution_id is not None

    # Verify events emitted
    assert len(mock_obs.events) == 3  # task_received, initialized, completed
    assert mock_obs.events[0].type == "task_received"
    assert mock_obs.events[1].type == "agent_initialized"
    assert mock_obs.events[2].type == "agent_completed"

    # Verify workspace prepared and finalized
    assert mock_workspace.prepare_called
    assert mock_workspace.finalize_called

    # Verify output posted
    assert mock_github.post_called

async def test_execute_agent_failure():
    """Test agent execution failure with proper error handling"""
    # Similar to success but inject failure
    pass

async def test_execute_agent_duplicate_prevention():
    """Test that duplicate executions are prevented"""
    pass
```

## Simulation Mode Support

The Agent Executor fully supports simulation mode:

1. **Mock Claude Integration**: Returns predetermined responses
2. **Mock Workspace**: In-memory git operations
3. **Mock GitHub Output**: Captures output without API calls
4. **Mock Observability**: Captures events in memory
5. **Deterministic IDs**: Use seeded random for reproducible execution_ids

## Performance Considerations

1. **Parallel Workspace Prep**: Prepare workspace and build context concurrently
2. **Streaming**: Use streaming for Claude Code to minimize latency
3. **Async Throughout**: All I/O operations are async
4. **Connection Pooling**: Reuse HTTP connections for GitHub API

## Error Handling

1. **Workspace Errors**: Retry with exponential backoff, max 3 attempts
2. **Claude Errors**: Capture and classify, emit detailed error events
3. **GitHub Errors**: Retry with backoff, fallback to local file if persistent
4. **State Errors**: Log and continue, don't block execution

## Migration from Legacy

### Legacy Location
- `services/agent_executor.py`

### Migration Strategy
1. Already well-structured, mainly need to add port interfaces
2. Extract direct Redis/Elasticsearch dependencies
3. Replace with port interfaces
4. Implement adapters
5. Add comprehensive tests
