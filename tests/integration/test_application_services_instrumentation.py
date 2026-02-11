"""Integration tests for application service instrumentation.

Verifies that WorkflowOrchestrator, AgentScheduler, and ExecutionService
methods emit OpenTelemetry spans with proper business context.
"""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from codetoreum.application.workflow_orchestrator import (
    WorkflowOrchestrator,
    CardMovedEvent,
    IssueData,
    StageCompletedEvent,
    ReviewCycleCompletedEvent,
    FeedbackEvent,
)
from codetoreum.application.agent_scheduler import (
    AgentScheduler,
    InMemoryTaskQueue,
    MockResourceMonitor,
    MockRateLimiter,
    MockProjectConfiguration,
    MockSchedulingEvents,
)
from codetoreum.application.execution_service import ExecutionService
from codetoreum.domain.agent import Agent
from codetoreum.domain.work_item import WorkItem, WorkItemPriority
from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.value_objects import ExecutionContext, ContainerConfig
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def tracer_provider():
    """Provide a test tracer with in-memory span exporter."""
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    yield provider
    provider.force_flush()


# ============================================================================
# WorkflowOrchestrator Tests
# ============================================================================


@pytest.mark.asyncio
async def test_workflow_orchestrator_handle_card_movement(tracer_provider):
    """Verify WorkflowOrchestrator.handle_card_movement emits instrumented span."""
    # Setup mocks
    task_queue = AsyncMock()
    task_queue.enqueue = AsyncMock(return_value="task-123")
    config = AsyncMock()
    config.get_workflow_config = AsyncMock(return_value=MagicMock(
        columns=[MagicMock(name="backlog", position=0, agent="planning_agent")]
    ))
    config.get_agent_config = AsyncMock(return_value=MagicMock(
        requires_dev_container=False
    ))
    workflow_state = AsyncMock()
    workflow_state.get_workflow_state = AsyncMock(return_value=MagicMock(
        is_in_progress=MagicMock(return_value=False),
        mark_in_progress=MagicMock()
    ))
    decision_events = AsyncMock()
    decision_events.emit_routing_decision = AsyncMock()
    event_store = AsyncMock()

    orchestrator = WorkflowOrchestrator(
        task_queue=task_queue,
        config=config,
        workflow_state=workflow_state,
        decision_events=decision_events,
        event_store=event_store,
    )

    # Create event
    event = CardMovedEvent(
        project="test-project",
        board="main-board",
        issue_number=123,
        from_column="backlog",
        to_column="backlog",
        issue_data=IssueData(
            number=123,
            title="Test Issue",
            body="Test body",
            labels=["bug"],
            state="open",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        timestamp=datetime.now(timezone.utc),
    )

    # Execute
    result = await orchestrator.handle_card_movement(event)

    # Assert span was created
    spans = tracer_provider.get_finished_spans()
    movement_span = next(
        (s for s in spans if s.name == "workflow.handle_card_movement"),
        None,
    )

    assert movement_span is not None
    assert movement_span.attributes["service"] == "workflow_orchestrator"
    assert movement_span.attributes["operation"] == "card_movement"


@pytest.mark.asyncio
async def test_workflow_orchestrator_handle_stage_completion(tracer_provider):
    """Verify WorkflowOrchestrator.handle_stage_completion emits span."""
    # Setup mocks
    config = AsyncMock()
    config.get_workflow_config = AsyncMock(return_value=MagicMock(
        columns=[MagicMock(name="dev", position=0, agent="dev_agent")]
    ))
    task_queue = AsyncMock()
    workflow_state = AsyncMock()
    decision_events = AsyncMock()
    event_store = AsyncMock()

    orchestrator = WorkflowOrchestrator(
        task_queue=task_queue,
        config=config,
        workflow_state=workflow_state,
        decision_events=decision_events,
        event_store=event_store,
    )

    # Create event
    event = StageCompletedEvent(
        project="test-project",
        issue_number=456,
        stage_name="development",
        agent_name="dev_agent",
        success=True,
        output="Task completed",
        context={"board": "main-board"},
        timestamp=datetime.now(timezone.utc),
    )

    # Execute
    result = await orchestrator.handle_stage_completion(event)

    # Assert span
    spans = tracer_provider.get_finished_spans()
    completion_span = next(
        (s for s in spans if s.name == "workflow.handle_stage_completion"),
        None,
    )

    assert completion_span is not None
    assert completion_span.attributes["service"] == "workflow_orchestrator"
    assert completion_span.attributes["operation"] == "stage_completion"


@pytest.mark.asyncio
async def test_workflow_orchestrator_handle_review_cycle(tracer_provider):
    """Verify WorkflowOrchestrator.handle_review_cycle_completion emits span."""
    # Setup mocks
    config = AsyncMock()
    config.get_workflow_config = AsyncMock(return_value=MagicMock(
        columns=[MagicMock(
            name="review",
            position=1,
            agent="review_agent",
            auto_advance_on_approval=False
        )]
    ))
    task_queue = AsyncMock()
    workflow_state = AsyncMock()
    decision_events = AsyncMock()
    event_store = AsyncMock()

    orchestrator = WorkflowOrchestrator(
        task_queue=task_queue,
        config=config,
        workflow_state=workflow_state,
        decision_events=decision_events,
        event_store=event_store,
    )

    # Create event
    event = ReviewCycleCompletedEvent(
        project="test-project",
        issue_number=789,
        approved=True,
        iteration=1,
        maker_agent="dev_agent",
        reviewer_agent="review_agent",
        feedback=None,
        timestamp=datetime.now(timezone.utc),
        context={"board": "main-board"},
    )

    # Execute
    result = await orchestrator.handle_review_cycle_completion(event)

    # Assert span
    spans = tracer_provider.get_finished_spans()
    review_span = next(
        (s for s in spans if s.name == "workflow.handle_review_cycle_completion"),
        None,
    )

    assert review_span is not None
    assert review_span.attributes["service"] == "workflow_orchestrator"
    assert review_span.attributes["operation"] == "review_completion"


@pytest.mark.asyncio
async def test_workflow_orchestrator_handle_feedback(tracer_provider):
    """Verify WorkflowOrchestrator.handle_feedback emits span."""
    # Setup mocks
    task_queue = AsyncMock()
    task_queue.enqueue = AsyncMock(return_value="feedback-task-001")
    config = AsyncMock()
    workflow_state = AsyncMock()
    decision_events = AsyncMock()
    event_store = AsyncMock()

    orchestrator = WorkflowOrchestrator(
        task_queue=task_queue,
        config=config,
        workflow_state=workflow_state,
        decision_events=decision_events,
        event_store=event_store,
    )

    # Create event
    event = FeedbackEvent(
        project="test-project",
        issue_number=111,
        feedback_type="revision_request",
        author="reviewer",
        content="Please fix the code",
        reply_to_comment_id="comment-123",
        timestamp=datetime.now(timezone.utc),
    )

    # Execute
    result = await orchestrator.handle_feedback(event)

    # Assert span
    spans = tracer_provider.get_finished_spans()
    feedback_span = next(
        (s for s in spans if s.name == "workflow.handle_feedback"),
        None,
    )

    assert feedback_span is not None
    assert feedback_span.attributes["service"] == "workflow_orchestrator"
    assert feedback_span.attributes["operation"] == "feedback"


# ============================================================================
# AgentScheduler Tests
# ============================================================================


@pytest.mark.asyncio
async def test_agent_scheduler_schedule_execution(tracer_provider):
    """Verify AgentScheduler.schedule emits instrumented span."""
    # Setup mocks
    task_queue = InMemoryTaskQueue()
    resource_monitor = MockResourceMonitor()
    rate_limiter = MockRateLimiter()
    config = MockProjectConfiguration()
    scheduling_events = MockSchedulingEvents()
    event_store = AsyncMock()

    scheduler = AgentScheduler(
        task_queue=task_queue,
        resource_monitor=resource_monitor,
        rate_limiter=rate_limiter,
        config=config,
        scheduling_events=scheduling_events,
        event_store=event_store,
    )

    # Create work item and agent
    work_item = WorkItem(
        id="work-item-001",
        title="Test Work Item",
        description="Test description",
        project_id="test-project",
        current_stage="backlog",
    )
    agent = Agent(
        id="test-agent",
        name="Test Agent",
        model="test-model",
    )

    # Execute
    result = await scheduler.schedule(work_item, agent, WorkItemPriority.MEDIUM)

    # Assert span
    spans = tracer_provider.get_finished_spans()
    schedule_span = next(
        (s for s in spans if s.name == "agent.schedule_execution"),
        None,
    )

    assert schedule_span is not None
    assert schedule_span.attributes["service"] == "agent_scheduler"
    assert schedule_span.attributes["operation"] == "schedule"


@pytest.mark.asyncio
async def test_agent_scheduler_can_schedule(tracer_provider):
    """Verify AgentScheduler.can_schedule emits span."""
    # Setup mocks
    task_queue = InMemoryTaskQueue()
    resource_monitor = MockResourceMonitor()
    rate_limiter = MockRateLimiter()
    config = MockProjectConfiguration()
    scheduling_events = MockSchedulingEvents()
    event_store = AsyncMock()

    scheduler = AgentScheduler(
        task_queue=task_queue,
        resource_monitor=resource_monitor,
        rate_limiter=rate_limiter,
        config=config,
        scheduling_events=scheduling_events,
        event_store=event_store,
    )

    # Load agent config
    agent_config = await config.get_agent_config("test-agent")

    # Execute
    can_schedule = await scheduler.can_schedule(agent_config, "test-project")

    # Assert span
    spans = tracer_provider.get_finished_spans()
    capability_span = next(
        (s for s in spans if s.name == "agent.check_scheduling_capability"),
        None,
    )

    assert capability_span is not None
    assert capability_span.attributes["service"] == "agent_scheduler"
    assert capability_span.attributes["operation"] == "check_capability"


# ============================================================================
# ExecutionService Tests
# ============================================================================


@pytest.mark.asyncio
async def test_execution_service_create_execution(tracer_provider):
    """Verify ExecutionService.create_execution emits span."""
    # Setup mocks
    llm_provider = AsyncMock()
    container = AsyncMock()
    event_store = AsyncMock()
    event_store.append = AsyncMock()
    storage = AsyncMock()

    service = ExecutionService(
        llm_provider=llm_provider,
        container=container,
        event_store=event_store,
        storage=storage,
    )

    # Create agent and work item
    agent = Agent(
        id="exec-agent",
        name="Execution Agent",
        model="test-model",
    )
    work_item = WorkItem(
        id="work-item-002",
        title="Test",
        description="Test",
        project_id="test-project",
        current_stage="backlog",
    )

    # Execute
    execution = await service.create_execution(
        agent=agent,
        work_item=work_item,
        workflow_id="workflow-001",
        stage_name="development",
        prompt="Test prompt",
    )

    # Assert span
    spans = tracer_provider.get_finished_spans()
    create_span = next(
        (s for s in spans if s.name == "execution.create_execution"),
        None,
    )

    assert create_span is not None
    assert create_span.attributes["service"] == "execution_service"
    assert create_span.attributes["operation"] == "create"


@pytest.mark.asyncio
async def test_execution_service_start_execution(tracer_provider):
    """Verify ExecutionService.start_execution emits span."""
    # Setup mocks
    llm_provider = AsyncMock()
    container = AsyncMock()
    event_store = AsyncMock()
    event_store.append = AsyncMock()
    storage = AsyncMock()

    service = ExecutionService(
        llm_provider=llm_provider,
        container=container,
        event_store=event_store,
        storage=storage,
    )

    # Create execution
    execution = AgentExecution.create(
        agent_id="exec-agent",
        work_item_id="work-item-003",
        workflow_id="workflow-002",
        stage_name="development",
        prompt="Test prompt",
        model="test-model",
    )

    # Clear pending events for this test
    execution.clear_events()

    # Create execution context
    context = ExecutionContext(
        project_id="test-project",
        model="test-model",
        timeout_seconds=300,
        metadata={},
    )

    # Execute
    result = await service.start_execution(
        execution=execution,
        context=context,
    )

    # Assert span
    spans = tracer_provider.get_finished_spans()
    start_span = next(
        (s for s in spans if s.name == "execution.start_execution"),
        None,
    )

    assert start_span is not None
    assert start_span.attributes["service"] == "execution_service"
    assert start_span.attributes["operation"] == "start"


@pytest.mark.asyncio
async def test_execution_service_cancel_execution(tracer_provider):
    """Verify ExecutionService.cancel_execution emits span."""
    # Setup mocks
    llm_provider = AsyncMock()
    container = AsyncMock()
    event_store = AsyncMock()
    event_store.append = AsyncMock()
    storage = AsyncMock()

    service = ExecutionService(
        llm_provider=llm_provider,
        container=container,
        event_store=event_store,
        storage=storage,
    )

    # Create execution
    execution = AgentExecution.create(
        agent_id="exec-agent",
        work_item_id="work-item-004",
        workflow_id="workflow-003",
        stage_name="development",
        prompt="Test prompt",
        model="test-model",
    )

    # Clear pending events
    execution.clear_events()

    # Start execution first
    execution.start()
    execution.clear_events()

    # Execute cancel
    result = await service.cancel_execution(execution=execution)

    # Assert span
    spans = tracer_provider.get_finished_spans()
    cancel_span = next(
        (s for s in spans if s.name == "execution.cancel_execution"),
        None,
    )

    assert cancel_span is not None
    assert cancel_span.attributes["service"] == "execution_service"
    assert cancel_span.attributes["operation"] == "cancel"


# ============================================================================
# Error Recording Tests
# ============================================================================


@pytest.mark.asyncio
async def test_agent_scheduler_error_recording(tracer_provider):
    """Verify spans record exceptions with full context."""
    # Setup mocks that will fail
    task_queue = AsyncMock()
    task_queue.enqueue = AsyncMock(
        side_effect=Exception("Queue unavailable")
    )
    resource_monitor = MockResourceMonitor()
    rate_limiter = MockRateLimiter()
    config = MockProjectConfiguration()
    scheduling_events = MockSchedulingEvents()
    event_store = AsyncMock()

    scheduler = AgentScheduler(
        task_queue=task_queue,
        resource_monitor=resource_monitor,
        rate_limiter=rate_limiter,
        config=config,
        scheduling_events=scheduling_events,
        event_store=event_store,
    )

    # Create work item and agent
    work_item = WorkItem(
        id="work-item-error",
        title="Error Test",
        description="Test",
        project_id="test-project",
        current_stage="backlog",
    )
    agent = Agent(
        id="error-agent",
        name="Error Agent",
        model="test-model",
    )

    # Execute - expect failure
    with pytest.raises(Exception):
        result = await scheduler.schedule(work_item, agent, WorkItemPriority.MEDIUM)

    # Assert error was recorded in span
    spans = tracer_provider.get_finished_spans()
    error_span = next(
        (s for s in spans if s.status.is_error),
        None,
    )

    assert error_span is not None
    assert len(error_span.events) > 0
    exception_event = next(
        (e for e in error_span.events if e.name == "exception"),
        None,
    )
    assert exception_event is not None
