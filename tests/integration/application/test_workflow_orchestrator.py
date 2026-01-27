"""Integration tests for WorkflowOrchestrator."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

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
    WorkflowResult,
    WorkflowState,
)
from codetoreum.adapters.testing import InMemoryEventStore, InMemoryTicketAdapter
from codetoreum.domain.work_item import WorkItemPriority


# Mock implementations for testing


class MockTaskQueue(ITaskQueue):
    """Mock task queue for testing."""

    def __init__(self):
        self.tasks = []

    async def enqueue(self, task: Task) -> str:
        self.tasks.append(task)
        return task.id

    def size(self) -> int:
        return len(self.tasks)

    def get_last_task(self) -> Task:
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
        }

    async def get_workflow_config(self, project: str, board: str) -> WorkflowConfig:
        return self.workflows.get((project, board))

    async def get_agent_config(self, agent_name: str) -> AgentConfig:
        return self.agents.get(agent_name)


class MockWorkflowStateManager(IWorkflowStateManager):
    """Mock workflow state manager."""

    def __init__(self):
        self.states = {}

    async def get_workflow_state(self, issue_id: str) -> WorkflowState:
        if issue_id not in self.states:
            self.states[issue_id] = WorkflowState(
                in_progress_tasks={}, current_column=None, current_agent=None
            )
        return self.states[issue_id]

    async def update_workflow_state(
        self, issue_id: str, state: WorkflowState
    ) -> None:
        self.states[issue_id] = state


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

    async def move_card_to_column(
        self, project: str, issue_number: int, column_name: str
    ) -> None:
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
    yield config


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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        timestamp=datetime.now(timezone.utc),
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
async def test_handle_card_movement_duplicate_work(
    orchestrator, mock_workflow_state, mock_task_queue
):
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        timestamp=datetime.now(timezone.utc),
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        timestamp=datetime.now(timezone.utc),
    )

    result = await orchestrator.handle_card_movement(event)

    assert result.success is False
    assert result.action == WorkflowAction.NO_ACTION
    assert "not found in workflow config" in result.reason
    assert mock_task_queue.size() == 0


@pytest.mark.asyncio
async def test_handle_stage_completion_with_review(
    orchestrator, mock_task_queue, mock_decision_events
):
    """Test stage completion that requires review."""
    event = StageCompletedEvent(
        project="test-project",
        issue_number=123,
        stage_name="Implementation",
        agent_name="developer",
        success=True,
        output="Implementation complete",
        context={"board": "Development"},
        timestamp=datetime.now(timezone.utc),
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
        timestamp=datetime.now(timezone.utc),
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
async def test_handle_stage_completion_failure(
    orchestrator, mock_decision_events
):
    """Test handling of stage failure."""
    event = StageCompletedEvent(
        project="test-project",
        issue_number=123,
        stage_name="Implementation",
        agent_name="developer",
        success=False,
        output="Implementation failed",
        context={"board": "Development"},
        timestamp=datetime.now(timezone.utc),
    )

    result = await orchestrator.handle_stage_completion(event)

    assert result.success is False
    assert result.action == WorkflowAction.ESCALATE
    assert len(mock_decision_events.progression_decisions) == 1
    decision = mock_decision_events.progression_decisions[0]
    assert decision.action == WorkflowAction.ESCALATE


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_approved(
    orchestrator, mock_projects_api
):
    """Test review cycle completion with approval."""
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=123,
        approved=True,
        iteration=1,
        maker_agent="developer",
        reviewer_agent="code_reviewer",
        feedback=None,
        timestamp=datetime.now(timezone.utc),
        context={"board": "Development"},
    )

    result = await orchestrator.handle_review_cycle_completion(event)

    assert result.success is True
    assert result.action == WorkflowAction.COMPLETE
    # Note: Implementation column has auto_advance_on_approval=False


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_rejected(
    orchestrator, mock_task_queue
):
    """Test review cycle completion with rejection."""
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=123,
        approved=False,
        iteration=1,
        maker_agent="developer",
        reviewer_agent="code_reviewer",
        feedback="Please fix issues",
        timestamp=datetime.now(timezone.utc),
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
async def test_handle_review_cycle_completion_max_iterations(
    orchestrator, mock_projects_api
):
    """Test review cycle escalation after max iterations."""
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=123,
        approved=False,
        iteration=3,
        maker_agent="developer",
        reviewer_agent="code_reviewer",
        feedback="Still has issues",
        timestamp=datetime.now(timezone.utc),
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
        timestamp=datetime.now(timezone.utc),
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        timestamp=datetime.now(timezone.utc),
    )

    await orchestrator.handle_card_movement(event)

    # Verify state was saved
    state = await mock_workflow_state.get_workflow_state("test-project:123")
    assert state.current_column == "Requirements"
    assert state.current_agent == "business_analyst"
    assert state.is_in_progress("Requirements", "business_analyst")


@pytest.mark.asyncio
async def test_handle_stage_completion_context_none(orchestrator):
    """Test stage completion with context=None raises AttributeError (type violation)."""
    event = StageCompletedEvent(
        project="test-project",
        issue_number=123,
        stage_name="Implementation",
        agent_name="developer",
        success=True,
        output="Implementation complete",
        context=None,  # Type violation: context should be Dict[str, Any]
        timestamp=datetime.now(timezone.utc),
    )

    # Should raise AttributeError since None doesn't have .get() method
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute"):
        await orchestrator.handle_stage_completion(event)


@pytest.mark.asyncio
async def test_handle_stage_completion_with_extra_context_keys(
    orchestrator, mock_task_queue, mock_decision_events
):
    """Test stage completion ignores extra keys in context dict."""
    event = StageCompletedEvent(
        project="test-project",
        issue_number=123,
        stage_name="Implementation",
        agent_name="developer",
        success=True,
        output="Implementation complete",
        context={"board": "Development", "extra_key": "extra_value", "another": 123},
        timestamp=datetime.now(timezone.utc),
    )

    # Should ignore extra keys and use board="Development"
    result = await orchestrator.handle_stage_completion(event)

    assert result.success is True
    assert result.action == WorkflowAction.TASK_QUEUED
    assert result.agent_name == "code_reviewer"


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_context_none(orchestrator):
    """Test review cycle completion with context=None raises AttributeError (type violation)."""
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=123,
        approved=True,
        iteration=1,
        maker_agent="developer",
        reviewer_agent="code_reviewer",
        feedback=None,
        context=None,  # Type violation: context should be Dict[str, Any]
        timestamp=datetime.now(timezone.utc),
    )

    # Should raise AttributeError since None doesn't have .get() method
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute"):
        await orchestrator.handle_review_cycle_completion(event)


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_with_extra_context_keys(
    orchestrator, mock_projects_api
):
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
        timestamp=datetime.now(timezone.utc),
    )

    # Should ignore extra keys and use board="Development"
    result = await orchestrator.handle_review_cycle_completion(event)

    assert result.success is True
    assert result.action == WorkflowAction.COMPLETE


@pytest.mark.asyncio
async def test_handle_review_cycle_completion_missing_max_iterations(
    orchestrator, mock_task_queue
):
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
        timestamp=datetime.now(timezone.utc),
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
async def test_handle_review_cycle_completion_max_iterations_exceeded(
    orchestrator, mock_decision_events
):
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
        timestamp=datetime.now(timezone.utc),
    )

    result = await orchestrator.handle_review_cycle_completion(event)

    # Iteration 3 >= max_iterations default 3, so escalate
    assert result.action == WorkflowAction.ESCALATE
    assert "Max review iterations (3) reached" in result.reason
