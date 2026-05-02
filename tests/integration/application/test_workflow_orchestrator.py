"""Integration tests for WorkflowOrchestrator."""

from datetime import UTC, datetime

import pytest

from codetoreum.adapters.testing import InMemoryEventStore, InMemoryTicketAdapter
from codetoreum.application.workflow_orchestrator import (
    AgentConfig,
    CardMovedEvent,
    ColumnConfig,
    FeedbackEvent,
    IDecisionEvents,
    IProjectConfiguration,
    IProjectsAPI,
    IssueData,
    ITaskQueue,
    IWorkflowStateManager,
    ProgressionDecision,
    ReviewCycleCompletedEvent,
    RoutingDecision,
    StageCompletedEvent,
    Task,
    WorkflowAction,
    WorkflowConfig,
    WorkflowOrchestrator,
    WorkflowState,
)
from codetoreum.domain.value_objects import ProjectConfig
from codetoreum.domain.work_item import WorkItemPriority

# Mock implementations for testing


class MockTaskQueue(ITaskQueue):
    """Mock task queue for testing."""

    def __init__(self):
        self.tasks = []

    async def enqueue(self, task: Task) -> str:
        self.tasks.append(task)
        return str(task.id)

    def size(self) -> int:
        return len(self.tasks)

    def get_last_task(self) -> Task | None:
        return self.tasks[-1] if self.tasks else None


class MockProjectConfiguration(IProjectConfiguration):
    """Mock project configuration."""

    def __init__(self):
        self.workflows = {
            ("test-project", "Development"): WorkflowConfig(
                name="Development Workflow",
                columns=[
                    ColumnConfig(
                        name="Requirements",
                        position=1,
                        agent="business_analyst",
                        auto_advance_on_approval=True,
                        discussion_category=None,
                        stage_type="agent",
                        review_required=False,
                        reviewer_agent=None,
                    ),
                    ColumnConfig(
                        name="Implementation",
                        position=2,
                        agent="developer",
                        auto_advance_on_approval=False,
                        discussion_category=None,
                        stage_type="agent",
                        review_required=True,
                        reviewer_agent="code_reviewer",
                    ),
                    ColumnConfig(
                        name="Testing",
                        position=3,
                        agent="tester",
                        auto_advance_on_approval=True,
                        discussion_category=None,
                        stage_type="agent",
                        review_required=False,
                        reviewer_agent=None,
                    ),
                ],
                workspace_type="issues",
            )
        }
        self.agents = {
            "business_analyst": AgentConfig(
                id="business_analyst",
                name="Business Analyst",
                prompt_template="Analyze requirements",
                capabilities=["analysis"],
                requires_dev_container=False,
            ),
            "developer": AgentConfig(
                id="developer",
                name="Developer",
                prompt_template="Implement code",
                capabilities=["coding"],
                requires_dev_container=True,
            ),
            "code_reviewer": AgentConfig(
                id="code_reviewer",
                name="Code Reviewer",
                prompt_template="Review code",
                capabilities=["review"],
                requires_dev_container=True,
            ),
            "feedback_handler": AgentConfig(
                id="feedback_handler",
                name="Feedback Handler",
                prompt_template="Handle user feedback",
                capabilities=["communication"],
                requires_dev_container=False,
            ),
        }

    async def get_workflow_config(self, project: str, board: str) -> WorkflowConfig:
        config = self.workflows.get((project, board))
        if config is None:
            msg = f"Workflow config not found for {project}/{board}"
            raise ValueError(msg)
        return config

    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        config = self.agents.get(agent_name)
        if config is None:
            msg = f"Agent config not found for {agent_name}"
            raise ValueError(msg)
        return config


class MockWorkflowStateManager(IWorkflowStateManager):
    """Mock workflow state manager."""

    def __init__(self):
        self.states: dict[str, WorkflowState] = {}
        self.item_positions: dict[str, dict] = {}

    async def get_workflow_state(self, issue_id: str) -> WorkflowState:
        if issue_id not in self.states:
            self.states[issue_id] = WorkflowState(in_progress_tasks={}, current_column=None, current_agent=None)
        return self.states[issue_id]

    async def update_workflow_state(self, issue_id: str, state: WorkflowState) -> None:
        self.states[issue_id] = state

    async def get_item_position(self, work_item_id: str) -> dict | None:
        """Get current position information for a work item."""
        return self.item_positions.get(work_item_id)


class MockDecisionEvents(IDecisionEvents):
    """Mock decision events."""

    def __init__(self):
        self.routing_decisions = []
        self.progression_decisions = []

    async def emit_routing_decision(self, decision: RoutingDecision) -> None:
        self.routing_decisions.append(decision)

    async def emit_progression_decision(self, decision: ProgressionDecision) -> None:
        self.progression_decisions.append(decision)


class MockProjectsAPI(IProjectsAPI):
    """Mock GitHub Projects API."""

    def __init__(self):
        self.card_movements = []
        self.labels_added = []

    async def move_card_to_column(self, project: str, issue_number: int, column_name: str) -> None:
        self.card_movements.append((project, issue_number, column_name))

    async def add_label(self, project: str, issue_number: int, label: str) -> None:
        self.labels_added.append((project, issue_number, label))


# Test fixtures


@pytest.fixture
def mock_task_queue():
    queue = MockTaskQueue()
    yield queue
    queue.tasks.clear()


@pytest.fixture
def mock_config():
    config = MockProjectConfiguration()
    return config


@pytest.fixture
def mock_workflow_state():
    state = MockWorkflowStateManager()
    yield state
    state.states.clear()


@pytest.fixture
def mock_decision_events():
    events = MockDecisionEvents()
    yield events
    events.routing_decisions.clear()
    events.progression_decisions.clear()


@pytest.fixture
def project_config():
    """Create a valid ProjectConfig for testing orchestrate_project."""
    return ProjectConfig(
        repo_url="https://github.com/test/repo.git",
        branch="main",
        enabled=True,
        org="test-org"
    )


@pytest.fixture
def mock_event_store():
    store = InMemoryEventStore()
    yield store
    store.clear()


@pytest.fixture
def mock_ticket_system():
    adapter = InMemoryTicketAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def mock_projects_api():
    api = MockProjectsAPI()
    yield api
    api.card_movements.clear()
    api.labels_added.clear()


@pytest.fixture
def orchestrator(
    mock_task_queue,
    mock_config,
    mock_workflow_state,
    mock_decision_events,
    mock_event_store,
    mock_ticket_system,
    mock_projects_api,
):
    return WorkflowOrchestrator(
        task_queue=mock_task_queue,
        config=mock_config,
        workflow_state=mock_workflow_state,
        decision_events=mock_decision_events,
        event_store=mock_event_store,
        ticket_system=mock_ticket_system,
        projects_api=mock_projects_api,
    )


# Tests


@pytest.mark.asyncio
async def test_handle_card_movement_success(orchestrator, mock_task_queue, mock_decision_events):
    """Test successful card movement handling."""
    event = CardMovedEvent(
        project="test-project",
        board="Development",
        issue_number=123,
        from_column="Backlog",
        to_column="Requirements",
        issue_data=IssueData(
            number=123,
            title="Test Issue",
            body="Test description",
            labels=["enhancement"],
            state="open",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        timestamp=datetime.now(UTC),
    )

    result = await orchestrator.handle_card_movement(event)

    assert result.success is True
    assert result.action == WorkflowAction.TASK_QUEUED
    assert result.task_id is not None
    assert result.agent_name == "business_analyst"
    assert mock_task_queue.size() == 1
    assert len(mock_decision_events.routing_decisions) == 1

    # Verify task context
    task = mock_task_queue.get_last_task()
    assert task.agent == "business_analyst"
    assert task.project == "test-project"
    assert task.context["issue_number"] == 123
    assert task.context["column"] == "Requirements"


@pytest.mark.asyncio
async def test_handle_card_movement_duplicate_work(orchestrator, mock_workflow_state, mock_task_queue):
    """Test that duplicate work is prevented."""
    # First card movement
    event1 = CardMovedEvent(
        project="test-project",
        board="Development",
        issue_number=123,
        from_column="Backlog",
        to_column="Requirements",
        issue_data=IssueData(
            number=123,
            title="Test Issue",
            body="Test description",
            labels=[],
            state="open",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        timestamp=datetime.now(UTC),
    )

    result1 = await orchestrator.handle_card_movement(event1)
    assert result1.success is True
    assert mock_task_queue.size() == 1

    # Second card movement (duplicate)
    result2 = await orchestrator.handle_card_movement(event1)
    assert result2.success is False
    assert result2.action == WorkflowAction.NO_ACTION
    assert "already in progress" in result2.reason
    assert mock_task_queue.size() == 1  # No new task queued


@pytest.mark.asyncio
async def test_handle_card_movement_invalid_column(orchestrator, mock_task_queue):
    """Test card movement to invalid column."""
    event = CardMovedEvent(
        project="test-project",
        board="Development",
        issue_number=123,
        from_column="Backlog",
        to_column="InvalidColumn",
        issue_data=IssueData(
            number=123,
            title="Test Issue",
            body="Test description",
            labels=[],
            state="open",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        timestamp=datetime.now(UTC),
    )

    result = await orchestrator.handle_card_movement(event)

    assert result.success is False
    assert result.action == WorkflowAction.NO_ACTION
    assert "not found in workflow config" in result.reason
    assert mock_task_queue.size() == 0


@pytest.mark.asyncio
async def test_handle_stage_completion_with_review(orchestrator, mock_task_queue, mock_decision_events):
    """Test stage completion that requires review."""
    event = StageCompletedEvent(
        project="test-project",
        issue_number=123,
        stage_name="Implementation",
        agent_name="developer",
        success=True,
        output="Implementation complete",
        context={"board": "Development"},
        timestamp=datetime.now(UTC),
    )

    result = await orchestrator.handle_stage_completion(event)

    assert result.success is True
    assert result.action == WorkflowAction.TASK_QUEUED
    assert result.agent_name == "code_reviewer"
    assert mock_task_queue.size() == 1

    # Verify review task was queued
    task = mock_task_queue.get_last_task()
    assert task.agent == "code_reviewer"
    assert task.context["maker_agent"] == "developer"
    assert task.context["maker_output"] == "Implementation complete"


@pytest.mark.asyncio
async def test_handle_stage_completion_with_auto_advance(
    orchestrator, mock_task_queue, mock_projects_api, mock_decision_events
):
    """Test stage completion with auto-advance."""
    event = StageCompletedEvent(
        project="test-project",
        issue_number=123,
        stage_name="Requirements",
        agent_name="business_analyst",
        success=True,
        output="Requirements analyzed",
        context={"board": "Development"},
        timestamp=datetime.now(UTC),
    )

    result = await orchestrator.handle_stage_completion(event)

    assert result.success is True
    assert result.action == WorkflowAction.AUTO_ADVANCE
    assert result.next_column == "Implementation"

    # Verify card was moved
    assert len(mock_projects_api.card_movements) == 1
    assert mock_projects_api.card_movements[0] == (
        "test-project",
        123,
        "Implementation",
    )

    # Verify progression decision was emitted
    assert len(mock_decision_events.progression_decisions) == 1
    decision = mock_decision_events.progression_decisions[0]
    assert decision.action == WorkflowAction.AUTO_ADVANCE
    assert decision.from_stage == "Requirements"
    assert decision.to_stage == "Implementation"


@pytest.mark.asyncio
async def test_handle_stage_completion_failure(orchestrator, mock_decision_events):
    """Test handling of stage failure."""
    event = StageCompletedEvent(
        project="test-project",
        issue_number=123,
        stage_name="Implementation",
        agent_name="developer",
        success=False,
        output="Implementation failed",
        context={"board": "Development"},
        timestamp=datetime.now(UTC),
    )

    result = await orchestrator.handle_stage_completion(event)

    assert result.success is False
    assert result.action == WorkflowAction.ESCALATE
    assert len(mock_decision_events.progression_decisions) == 1
    decision = mock_decision_events.progression_decisions[0]
    assert decision.action == WorkflowAction.ESCALATE


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_approved(orchestrator, mock_projects_api):
    """Test review cycle completion with approval."""
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=123,
        approved=True,
        iteration=1,
        maker_agent="developer",
        reviewer_agent="code_reviewer",
        feedback=None,
        timestamp=datetime.now(UTC),
        context={"board": "Development"},
    )

    result = await orchestrator.handle_review_cycle_completion(event)

    assert result.success is True
    assert result.action == WorkflowAction.COMPLETE
    # Note: Implementation column has auto_advance_on_approval=False


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_rejected(orchestrator, mock_task_queue):
    """Test review cycle completion with rejection."""
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=123,
        approved=False,
        iteration=1,
        maker_agent="developer",
        reviewer_agent="code_reviewer",
        feedback="Please fix issues",
        timestamp=datetime.now(UTC),
        context={"board": "Development", "max_iterations": 3},
    )

    result = await orchestrator.handle_review_cycle_completion(event)

    assert result.success is True
    assert result.action == WorkflowAction.TASK_QUEUED
    assert result.agent_name == "developer"
    assert mock_task_queue.size() == 1

    # Verify revision task
    task = mock_task_queue.get_last_task()
    assert task.agent == "developer"
    assert task.context["iteration"] == 2
    assert task.context["feedback"] == "Please fix issues"


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_max_iterations(orchestrator, mock_projects_api):
    """Test review cycle escalation after max iterations."""
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=123,
        approved=False,
        iteration=3,
        maker_agent="developer",
        reviewer_agent="code_reviewer",
        feedback="Still has issues",
        timestamp=datetime.now(UTC),
        context={"board": "Development", "max_iterations": 3},
    )

    result = await orchestrator.handle_review_cycle_completion(event)

    assert result.success is True
    assert result.action == WorkflowAction.ESCALATE
    assert "Max review iterations" in result.reason

    # Verify escalation label was added
    assert len(mock_projects_api.labels_added) == 1
    assert mock_projects_api.labels_added[0] == (
        "test-project",
        123,
        "needs-human-review",
    )


@pytest.mark.asyncio
async def test_handle_feedback(orchestrator, mock_task_queue):
    """Test handling user feedback."""
    event = FeedbackEvent(
        project="test-project",
        issue_number=123,
        feedback_type="comment",
        author="user123",
        content="Can you explain this?",
        reply_to_comment_id="comment-456",
        timestamp=datetime.now(UTC),
    )

    result = await orchestrator.handle_feedback(event)

    assert result.success is True
    assert result.action == WorkflowAction.TASK_QUEUED
    assert result.agent_name == "feedback_handler"
    assert mock_task_queue.size() == 1

    # Verify feedback task
    task = mock_task_queue.get_last_task()
    assert task.agent == "feedback_handler"
    assert task.context["feedback_content"] == "Can you explain this?"
    assert task.context["author"] == "user123"
    assert task.priority == WorkItemPriority.HIGH


@pytest.mark.asyncio
async def test_workflow_state_persistence(orchestrator, mock_workflow_state):
    """Test workflow state is persisted correctly."""
    event = CardMovedEvent(
        project="test-project",
        board="Development",
        issue_number=123,
        from_column="Backlog",
        to_column="Requirements",
        issue_data=IssueData(
            number=123,
            title="Test Issue",
            body="Test description",
            labels=[],
            state="open",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        timestamp=datetime.now(UTC),
    )

    await orchestrator.handle_card_movement(event)

    # Verify state was saved
    state = await mock_workflow_state.get_workflow_state("test-project:123")
    assert state.current_column == "Requirements"
    assert state.current_agent == "business_analyst"
    assert state.is_in_progress("Requirements", "business_analyst")


@pytest.mark.asyncio
async def test_handle_stage_completion_with_extra_context_keys(orchestrator, mock_task_queue, mock_decision_events):
    """Test stage completion ignores extra keys in context dict."""
    event = StageCompletedEvent(
        project="test-project",
        issue_number=123,
        stage_name="Implementation",
        agent_name="developer",
        success=True,
        output="Implementation complete",
        context={"board": "Development", "extra_key": "extra_value", "another": 123},
        timestamp=datetime.now(UTC),
    )

    # Should ignore extra keys and use board="Development"
    result = await orchestrator.handle_stage_completion(event)

    assert result.success is True
    assert result.action == WorkflowAction.TASK_QUEUED
    assert result.agent_name == "code_reviewer"


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_with_extra_context_keys(orchestrator, mock_projects_api):
    """Test review cycle completion ignores extra keys in context dict."""
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=123,
        approved=True,
        iteration=1,
        maker_agent="developer",
        reviewer_agent="code_reviewer",
        feedback=None,
        context={"board": "Development", "extra": "value", "other": 456},
        timestamp=datetime.now(UTC),
    )

    # Should ignore extra keys and use board="Development"
    result = await orchestrator.handle_review_cycle_completion(event)

    assert result.success is True
    assert result.action == WorkflowAction.COMPLETE


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_missing_max_iterations(orchestrator, mock_task_queue):
    """Test review cycle completion without max_iterations uses default of 3."""
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=123,
        approved=False,
        iteration=2,
        maker_agent="developer",
        reviewer_agent="code_reviewer",
        feedback="Please fix",
        context={"board": "Development"},  # No max_iterations key
        timestamp=datetime.now(UTC),
    )

    result = await orchestrator.handle_review_cycle_completion(event)

    # Iteration 2 < max_iterations default 3, so should retry
    assert result.success is True
    assert result.action == WorkflowAction.TASK_QUEUED
    assert result.agent_name == "developer"

    # Verify retry task was queued
    task = mock_task_queue.get_last_task()
    assert task.agent == "developer"


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_max_iterations_exceeded(orchestrator, mock_decision_events):
    """Test review cycle completion escalates when max_iterations reached."""
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=123,
        approved=False,
        iteration=3,
        maker_agent="developer",
        reviewer_agent="code_reviewer",
        feedback="Still not good",
        context={"board": "Development"},  # max_iterations defaults to 3
        timestamp=datetime.now(UTC),
    )

    result = await orchestrator.handle_review_cycle_completion(event)

    # Iteration 3 >= max_iterations default 3, so escalate
    assert result.action == WorkflowAction.ESCALATE
    assert "Max review iterations (3) reached" in result.reason


# Tests for orchestrate_project method


class MockBoardService:
    """Mock board service for orchestrate_project testing."""

    def __init__(self):
        self.boards = []
        self.board_items = {}

    async def get_all_boards(self):
        """Get all boards."""
        return self.boards

    async def get_board_items(self, project_id: str, board_id: str):
        """Get items on a board."""
        return self.board_items.get(board_id, [])


class MockBoardItem:
    """Mock board item."""

    def __init__(self, work_item_id: int, column_name: str):
        self.work_item_id = work_item_id
        self.column_name = column_name


class MockBoard:
    """Mock board."""

    def __init__(self, name: str, board_id: str, project_id: str):
        self.name = name
        self.id = board_id
        self.project_id = project_id


@pytest.mark.asyncio
async def test_orchestrate_project_happy_path(
    mock_task_queue,
    mock_config,
    mock_workflow_state,
    mock_decision_events,
    mock_event_store,
    mock_ticket_system,
    mock_projects_api,
    project_config,
):
    """Test orchestrate_project successfully enqueues tasks for board items."""
    # Setup board service
    board_service = MockBoardService()
    board = MockBoard("Development", "board-1", "test-project")
    board_service.boards = [board]
    board_service.board_items["board-1"] = [
        MockBoardItem(123, "Requirements"),
        MockBoardItem(124, "Implementation"),
    ]

    orchestrator = WorkflowOrchestrator(
        task_queue=mock_task_queue,
        config=mock_config,
        workflow_state=mock_workflow_state,
        decision_events=mock_decision_events,
        event_store=mock_event_store,
        ticket_system=mock_ticket_system,
        projects_api=mock_projects_api,
        board_service=board_service,
    )

    actions_taken = await orchestrator.orchestrate_project("test-project", "/workspace", project_config)

    # Verify tasks were enqueued
    assert mock_task_queue.size() == 2
    assert actions_taken == 2

    # Verify routing decisions were emitted
    assert len(mock_decision_events.routing_decisions) == 2
    assert mock_decision_events.routing_decisions[0].project == "test-project"
    assert mock_decision_events.routing_decisions[0].selected_agent == "business_analyst"
    assert mock_decision_events.routing_decisions[1].selected_agent == "developer"


@pytest.mark.asyncio
async def test_orchestrate_project_no_boards(
    mock_task_queue,
    mock_config,
    mock_workflow_state,
    mock_decision_events,
    mock_event_store,
    mock_ticket_system,
    mock_projects_api,
    project_config,
):
    """Test orchestrate_project returns 0 when no boards found."""
    board_service = MockBoardService()
    board_service.boards = []

    orchestrator = WorkflowOrchestrator(
        task_queue=mock_task_queue,
        config=mock_config,
        workflow_state=mock_workflow_state,
        decision_events=mock_decision_events,
        event_store=mock_event_store,
        ticket_system=mock_ticket_system,
        projects_api=mock_projects_api,
        board_service=board_service,
    )

    actions_taken = await orchestrator.orchestrate_project("test-project", "/workspace", project_config)

    assert actions_taken == 0
    assert mock_task_queue.size() == 0


@pytest.mark.asyncio
async def test_orchestrate_project_no_matching_boards_for_project(
    mock_task_queue,
    mock_config,
    mock_workflow_state,
    mock_decision_events,
    mock_event_store,
    mock_ticket_system,
    mock_projects_api,
    project_config,
):
    """Test orchestrate_project continues when workflow config not found for board."""
    board_service = MockBoardService()
    # Create a board that won't match any workflow config
    board = MockBoard("NonExistent", "board-1", "test-project")
    board_service.boards = [board]
    board_service.board_items["board-1"] = [
        MockBoardItem(123, "SomeColumn"),
    ]

    orchestrator = WorkflowOrchestrator(
        task_queue=mock_task_queue,
        config=mock_config,
        workflow_state=mock_workflow_state,
        decision_events=mock_decision_events,
        event_store=mock_event_store,
        ticket_system=mock_ticket_system,
        projects_api=mock_projects_api,
        board_service=board_service,
    )

    actions_taken = await orchestrator.orchestrate_project("test-project", "/workspace", project_config)

    # No tasks should be enqueued due to missing workflow config
    assert actions_taken == 0
    assert mock_task_queue.size() == 0


@pytest.mark.asyncio
async def test_orchestrate_project_workflow_config_load_failure_continues(
    mock_task_queue,
    mock_config,
    mock_workflow_state,
    mock_decision_events,
    mock_event_store,
    mock_ticket_system,
    mock_projects_api,
    project_config,
):
    """Test orchestrate_project continues processing when workflow config load fails."""
    board_service = MockBoardService()
    board = MockBoard("Development", "board-1", "test-project")
    board_service.boards = [board]
    board_service.board_items["board-1"] = [
        MockBoardItem(123, "Requirements"),
    ]

    # Use modified config that will raise exception
    class FailingConfig(MockProjectConfiguration):
        async def get_workflow_config(self, project: str, board: str) -> WorkflowConfig:
            raise ValueError("Config load failure")

    failing_config = FailingConfig()

    orchestrator = WorkflowOrchestrator(
        task_queue=mock_task_queue,
        config=failing_config,
        workflow_state=mock_workflow_state,
        decision_events=mock_decision_events,
        event_store=mock_event_store,
        ticket_system=mock_ticket_system,
        projects_api=mock_projects_api,
        board_service=board_service,
    )

    # Should not raise exception, just return 0 actions
    actions_taken = await orchestrator.orchestrate_project("test-project", "/workspace", project_config)

    assert actions_taken == 0
    assert mock_task_queue.size() == 0


@pytest.mark.asyncio
async def test_orchestrate_project_individual_item_failure_continues(
    mock_task_queue,
    mock_config,
    mock_workflow_state,
    mock_decision_events,
    mock_event_store,
    mock_ticket_system,
    mock_projects_api,
    project_config,
):
    """Test orchestrate_project continues after individual item processing failure."""
    board_service = MockBoardService()
    board = MockBoard("Development", "board-1", "test-project")
    board_service.boards = [board]
    board_service.board_items["board-1"] = [
        MockBoardItem(123, "Requirements"),
        MockBoardItem(124, "Implementation"),
    ]

    # Use modified config that will fail for a specific agent
    class PartialFailConfig(MockProjectConfiguration):
        async def get_agent_config(self, agent_name: str) -> AgentConfig:
            if agent_name == "business_analyst":
                raise ValueError("Agent config load failure")
            return await super().get_agent_config(agent_name)

    partial_config = PartialFailConfig()

    orchestrator = WorkflowOrchestrator(
        task_queue=mock_task_queue,
        config=partial_config,
        workflow_state=mock_workflow_state,
        decision_events=mock_decision_events,
        event_store=mock_event_store,
        ticket_system=mock_ticket_system,
        projects_api=mock_projects_api,
        board_service=board_service,
    )

    # Should successfully process item 124 (developer) despite item 123 (business_analyst) failing
    actions_taken = await orchestrator.orchestrate_project("test-project", "/workspace", project_config)

    # Should have 1 task (only for developer/Implementation)
    assert mock_task_queue.size() == 1
    assert actions_taken == 1

    task = mock_task_queue.get_last_task()
    assert task.agent == "developer"
    assert task.context["work_item_id"] == 124


@pytest.mark.asyncio
async def test_orchestrate_project_non_numeric_work_item_id_skipped(
    mock_task_queue,
    mock_config,
    mock_workflow_state,
    mock_decision_events,
    mock_event_store,
    mock_ticket_system,
    mock_projects_api,
    project_config,
):
    """Test orchestrate_project skips non-numeric work_item_ids without enqueueing."""
    board_service = MockBoardService()
    board = MockBoard("Development", "board-1", "test-project")
    board_service.boards = [board]

    # Create a custom board item class that allows string work_item_id
    class StringBoardItem:
        def __init__(self, work_item_id, column_name):
            self.work_item_id = work_item_id
            self.column_name = column_name

    # Mix numeric and non-numeric work item IDs
    board_service.board_items["board-1"] = [
        StringBoardItem("ABC-123", "Requirements"),  # Non-numeric
        StringBoardItem(456, "Implementation"),  # Numeric
    ]

    orchestrator = WorkflowOrchestrator(
        task_queue=mock_task_queue,
        config=mock_config,
        workflow_state=mock_workflow_state,
        decision_events=mock_decision_events,
        event_store=mock_event_store,
        ticket_system=mock_ticket_system,
        projects_api=mock_projects_api,
        board_service=board_service,
    )

    # Should process only the numeric work item (456), skipping "ABC-123"
    actions_taken = await orchestrator.orchestrate_project("test-project", "/workspace", project_config)

    # Should have only 1 task (for developer/Implementation with ID 456)
    assert mock_task_queue.size() == 1
    assert actions_taken == 1

    task = mock_task_queue.get_last_task()
    assert task.agent == "developer"
    assert task.context["work_item_id"] == 456


@pytest.mark.asyncio
async def test_orchestrate_project_disabled_project_skipped(
    mock_task_queue,
    mock_config,
    mock_workflow_state,
    mock_decision_events,
    mock_event_store,
    mock_ticket_system,
    mock_projects_api,
):
    """Test orchestrate_project returns 0 when project is disabled."""
    # Create a disabled project config
    disabled_config = ProjectConfig(
        repo_url="https://github.com/test/repo.git",
        branch="main",
        enabled=False,
        org="test-org"
    )

    board_service = MockBoardService()
    board = MockBoard("Development", "board-1", "test-project")
    board_service.boards = [board]
    board_service.board_items["board-1"] = [
        MockBoardItem(123, "Requirements"),
    ]

    orchestrator = WorkflowOrchestrator(
        task_queue=mock_task_queue,
        config=mock_config,
        workflow_state=mock_workflow_state,
        decision_events=mock_decision_events,
        event_store=mock_event_store,
        ticket_system=mock_ticket_system,
        projects_api=mock_projects_api,
        board_service=board_service,
    )

    # Should skip orchestration for disabled project
    actions_taken = await orchestrator.orchestrate_project("test-project", "/workspace", disabled_config)

    # Should not enqueue any tasks
    assert mock_task_queue.size() == 0
    assert actions_taken == 0
