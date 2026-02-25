"""Integration tests for AgentScheduler."""

from datetime import UTC, datetime

import pytest

from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.application.agent_scheduler import (
    AgentConfig,
    AgentScheduler,
    InMemoryTaskQueue,
    MockProjectConfiguration,
    MockRateLimiter,
    MockResourceMonitor,
    MockSchedulingEvents,
    ScheduleAction,
)
from codetoreum.domain.agent import Agent, AgentCapability, AgentType
from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus

# Test fixtures

# Helper function to create test agents
def create_test_agent(agent_id: str, agent_name: str, requires_dev_container: bool = False):
    """Helper to create test agents."""
    return Agent(
        id=agent_id,
        name=agent_name,
        display_name=agent_name.replace("-", " ").title(),
        agent_type=AgentType.DEVELOPER,
        capabilities={
            "code_generation": AgentCapability(skill="code_generation", proficiency=0.9)
        },
        role_description="Test agent for scheduling",
        model="claude-sonnet-4-5",
        timeout_seconds=300,
        max_retries=3,
        requires_docker=False,
        requires_dev_container=requires_dev_container,
        makes_code_changes=True,
        filesystem_write_allowed=True,
        mcp_servers=[],
        metadata={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )



@pytest.fixture
def mock_task_queue():
    return InMemoryTaskQueue()


@pytest.fixture
def mock_resource_monitor():
    return MockResourceMonitor(
        dev_containers_available={"test-project": True, "blocked-project": False},
        running_agents={"busy-agent": 3, "available-agent": 0},
    )


@pytest.fixture
def mock_rate_limiter():
    return MockRateLimiter(
        rate_limited_agents={"limited-agent": True, "available-agent": False}
    )


@pytest.fixture
def mock_config():
    return MockProjectConfiguration(
        agents={
            "available-agent": AgentConfig(
                id="available-agent",
                name="Available Agent",
                max_concurrent=3,
                requires_dev_container=False,
                rate_limit_rpm=60,
            ),
            "busy-agent": AgentConfig(
                id="busy-agent",
                name="Busy Agent",
                max_concurrent=3,
                requires_dev_container=False,
                rate_limit_rpm=60,
            ),
            "limited-agent": AgentConfig(
                id="limited-agent",
                name="Limited Agent",
                max_concurrent=3,
                requires_dev_container=False,
                rate_limit_rpm=10,
            ),
            "dev-container-agent": AgentConfig(
                id="dev-container-agent",
                name="Dev Container Agent",
                max_concurrent=3,
                requires_dev_container=True,
                rate_limit_rpm=None,
            ),
        }
    )


@pytest.fixture
def mock_scheduling_events():
    return MockSchedulingEvents()


@pytest.fixture
def mock_event_store():
    store = InMemoryEventStore()
    yield store
    store.clear()


@pytest.fixture
def scheduler(
    mock_task_queue,
    mock_resource_monitor,
    mock_rate_limiter,
    mock_config,
    mock_scheduling_events,
    mock_event_store,
):
    return AgentScheduler(
        task_queue=mock_task_queue,
        resource_monitor=mock_resource_monitor,
        rate_limiter=mock_rate_limiter,
        config=mock_config,
        scheduling_events=mock_scheduling_events,
        event_store=mock_event_store,
    )


@pytest.fixture
def sample_work_item():
    return WorkItem(
        id="work-item-1",
        project_id="test-project",
        title="Test Work Item",
        description="Test description",
        status=WorkItemStatus.NEW,
        priority=WorkItemPriority.MEDIUM,
        labels=["test"],
        external_id="123",
        external_url="https://github.com/test/repo/issues/123",
        assigned_agent_id=None,
        assigned_at=None,
        current_workflow_id=None,
        current_stage=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        completed_at=None,
    )


@pytest.fixture
def sample_agent():
    return create_test_agent("available-agent", "available_agent")


# Tests


@pytest.mark.asyncio
async def test_schedule_success(
    scheduler, mock_task_queue, mock_scheduling_events, sample_work_item, sample_agent
):
    """Test successful task scheduling."""
    result = await scheduler.schedule(
        sample_work_item, sample_agent, WorkItemPriority.MEDIUM
    )

    assert result.success is True
    assert result.action == ScheduleAction.QUEUED
    assert result.task_id is not None
    assert result.reason == "Task successfully queued"

    # Verify task was enqueued
    assert await mock_task_queue.get_queue_depth("available-agent") == 1

    # Verify scheduling event was emitted
    assert len(mock_scheduling_events.queued_events) == 1
    event = mock_scheduling_events.queued_events[0]
    assert event["agent"] == "available-agent"
    assert event["project"] == "test-project"


@pytest.mark.asyncio
async def test_schedule_rate_limited(
    scheduler, mock_task_queue, mock_scheduling_events, sample_work_item
):
    """Test scheduling when rate limited."""
    limited_agent = create_test_agent("limited-agent", "limited_agent")

    result = await scheduler.schedule(
        sample_work_item, limited_agent, WorkItemPriority.MEDIUM
    )

    assert result.success is False
    assert result.action == ScheduleAction.THROTTLED
    assert result.task_id is None
    assert "Rate limit exceeded" in result.reason
    assert result.retry_after == 60

    # Verify task was NOT enqueued
    assert await mock_task_queue.get_queue_depth("limited-agent") == 0

    # Verify throttled event was emitted
    assert len(mock_scheduling_events.throttled_events) == 1
    event = mock_scheduling_events.throttled_events[0]
    assert event["agent"] == "limited-agent"
    assert event["retry_after"] == 60


@pytest.mark.asyncio
async def test_schedule_resource_unavailable_dev_container(
    scheduler, mock_task_queue, mock_scheduling_events
):
    """Test scheduling when dev container unavailable."""
    work_item = WorkItem(
        id="work-item-2",
        project_id="blocked-project",
        title="Blocked Work Item",
        description="Test description",
        status=WorkItemStatus.NEW,
        priority=WorkItemPriority.MEDIUM,
        labels=[],
        external_id="124",
        external_url="https://github.com/test/repo/issues/124",
        assigned_agent_id=None,
        assigned_at=None,
        current_workflow_id=None,
        current_stage=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        completed_at=None,
    )

    agent = create_test_agent("dev-container-agent", "dev_container_agent", requires_dev_container=True)

    result = await scheduler.schedule(work_item, agent, WorkItemPriority.MEDIUM)

    assert result.success is False
    assert result.action == ScheduleAction.RESOURCE_UNAVAILABLE
    assert result.task_id is None
    assert "Dev container not available" in result.reason

    # Verify task was NOT enqueued
    assert await mock_task_queue.get_queue_depth("dev-container-agent") == 0

    # Verify rejected event was emitted
    assert len(mock_scheduling_events.rejected_events) == 1
    event = mock_scheduling_events.rejected_events[0]
    assert event["agent"] == "dev-container-agent"
    assert event["project"] == "blocked-project"


@pytest.mark.asyncio
async def test_schedule_resource_unavailable_max_concurrency(
    scheduler, mock_task_queue, mock_scheduling_events, sample_work_item
):
    """Test scheduling when max concurrency reached."""
    busy_agent = create_test_agent("busy-agent", "busy_agent")

    result = await scheduler.schedule(
        sample_work_item, busy_agent, WorkItemPriority.MEDIUM
    )

    assert result.success is False
    assert result.action == ScheduleAction.RESOURCE_UNAVAILABLE
    assert result.task_id is None
    assert "max concurrency" in result.reason

    # Verify task was NOT enqueued
    assert await mock_task_queue.get_queue_depth("busy-agent") == 0

    # Verify rejected event was emitted
    assert len(mock_scheduling_events.rejected_events) == 1


@pytest.mark.asyncio
async def test_can_schedule_available(scheduler):
    """Test can_schedule when resources available."""
    agent_config = AgentConfig(
        id="test-agent",
        name="Test Agent",
        max_concurrent=3,
        requires_dev_container=False,
        rate_limit_rpm=None,
    )

    can_schedule = await scheduler.can_schedule(agent_config, "test-project")
    assert can_schedule is True


@pytest.mark.asyncio
async def test_can_schedule_dev_container_unavailable(scheduler):
    """Test can_schedule when dev container unavailable."""
    agent_config = AgentConfig(
        id="test-agent",
        name="Test Agent",
        max_concurrent=3,
        requires_dev_container=True,
        rate_limit_rpm=None,
    )

    can_schedule = await scheduler.can_schedule(agent_config, "blocked-project")
    assert can_schedule is False


@pytest.mark.asyncio
async def test_can_schedule_max_concurrency(scheduler):
    """Test can_schedule when at max concurrency."""
    agent_config = AgentConfig(
        id="busy-agent",
        name="Busy Agent",
        max_concurrent=3,
        requires_dev_container=False,
        rate_limit_rpm=None,
    )

    can_schedule = await scheduler.can_schedule(agent_config, "test-project")
    assert can_schedule is False


@pytest.mark.asyncio
async def test_get_queue_depth(scheduler, mock_task_queue, sample_work_item, sample_agent):
    """Test getting queue depth."""
    # Initially empty
    depth = await scheduler.get_queue_depth("available-agent")
    assert depth == 0

    # Schedule a task
    await scheduler.schedule(sample_work_item, sample_agent, WorkItemPriority.MEDIUM)

    # Check depth again
    depth = await scheduler.get_queue_depth("available-agent")
    assert depth == 1


@pytest.mark.asyncio
async def test_schedule_with_priority(
    scheduler, mock_task_queue, sample_work_item, sample_agent
):
    """Test scheduling with different priorities."""
    # Schedule high priority task
    result_high = await scheduler.schedule(
        sample_work_item, sample_agent, WorkItemPriority.HIGH
    )

    assert result_high.success is True

    # Verify task has correct priority
    tasks = list(mock_task_queue.tasks.values())
    assert len(tasks) == 1
    assert tasks[0].priority == WorkItemPriority.HIGH


@pytest.mark.asyncio
async def test_schedule_task_context(
    scheduler, mock_task_queue, sample_work_item, sample_agent
):
    """Test task context is built correctly."""
    await scheduler.schedule(sample_work_item, sample_agent, WorkItemPriority.MEDIUM)

    tasks = list(mock_task_queue.tasks.values())
    assert len(tasks) == 1

    task = tasks[0]
    assert task.context["work_item_id"] == "work-item-1"
    assert task.context["work_item_title"] == "Test Work Item"
    assert task.context["work_item_description"] == "Test description"
    assert task.context["work_item_labels"] == ["test"]


@pytest.mark.asyncio
async def test_schedule_multiple_tasks(
    scheduler, mock_task_queue, sample_agent
):
    """Test scheduling multiple tasks for same agent."""
    # Create multiple work items
    work_items = [
        WorkItem(
            id=f"work-item-{i}",
            project_id="test-project",
            title=f"Work Item {i}",
            description=f"Description {i}",
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority.MEDIUM,
            labels=[],
            external_id=str(i),
            external_url=f"https://github.com/test/repo/issues/{i}",
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            completed_at=None,
        )
        for i in range(3)
    ]

    # Schedule all work items
    for work_item in work_items:
        result = await scheduler.schedule(
            work_item, sample_agent, WorkItemPriority.MEDIUM
        )
        assert result.success is True

    # Verify all tasks queued
    depth = await scheduler.get_queue_depth("available-agent")
    assert depth == 3


@pytest.mark.asyncio
async def test_schedule_config_error(
    scheduler, mock_task_queue, mock_scheduling_events, sample_work_item
):
    """Test scheduling with unknown agent."""
    unknown_agent = create_test_agent("unknown-agent", "unknown_agent")

    result = await scheduler.schedule(
        sample_work_item, unknown_agent, WorkItemPriority.MEDIUM
    )

    # Should succeed with default config
    assert result.success is True
    assert result.action == ScheduleAction.QUEUED
