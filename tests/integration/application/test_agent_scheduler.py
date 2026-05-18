"""Integration tests for AgentScheduler."""

import asyncio
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
    Task,
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
        capabilities={"code_generation": AgentCapability(skill="code_generation", proficiency=0.9)},
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
    return MockRateLimiter(rate_limited_agents={"limited-agent": True, "available-agent": False})


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
        current_column=None,
        entered_column_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        completed_at=None,
    )


@pytest.fixture
def sample_agent():
    return create_test_agent("available-agent", "available_agent")


# Tests


@pytest.mark.asyncio
async def test_schedule_success(scheduler, mock_task_queue, mock_scheduling_events, sample_work_item, sample_agent):
    """Test successful task scheduling."""
    result = await scheduler.schedule(sample_work_item, sample_agent, WorkItemPriority.MEDIUM)

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
async def test_schedule_rate_limited(scheduler, mock_task_queue, mock_scheduling_events, sample_work_item):
    """Test scheduling when rate limited."""
    limited_agent = create_test_agent("limited-agent", "limited_agent")

    result = await scheduler.schedule(sample_work_item, limited_agent, WorkItemPriority.MEDIUM)

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
async def test_schedule_resource_unavailable_dev_container(scheduler, mock_task_queue, mock_scheduling_events):
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
        current_column=None,
        entered_column_at=None,
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

    result = await scheduler.schedule(sample_work_item, busy_agent, WorkItemPriority.MEDIUM)

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
async def test_schedule_with_priority(scheduler, mock_task_queue, sample_work_item, sample_agent):
    """Test scheduling with different priorities."""
    # Schedule high priority task
    result_high = await scheduler.schedule(sample_work_item, sample_agent, WorkItemPriority.HIGH)

    assert result_high.success is True

    # Verify task has correct priority
    tasks = list(mock_task_queue.tasks.values())
    assert len(tasks) == 1
    assert tasks[0].priority == WorkItemPriority.HIGH


@pytest.mark.asyncio
async def test_schedule_task_context(scheduler, mock_task_queue, sample_work_item, sample_agent):
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
async def test_schedule_multiple_tasks(scheduler, mock_task_queue, sample_agent):
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
            current_column=None,
            entered_column_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            completed_at=None,
        )
        for i in range(3)
    ]

    # Schedule all work items
    for work_item in work_items:
        result = await scheduler.schedule(work_item, sample_agent, WorkItemPriority.MEDIUM)
        assert result.success is True

    # Verify all tasks queued
    depth = await scheduler.get_queue_depth("available-agent")
    assert depth == 3


@pytest.mark.asyncio
async def test_schedule_config_error(scheduler, mock_task_queue, mock_scheduling_events, sample_work_item):
    """Test scheduling with unknown agent."""
    unknown_agent = create_test_agent("unknown-agent", "unknown_agent")

    result = await scheduler.schedule(sample_work_item, unknown_agent, WorkItemPriority.MEDIUM)

    # Should succeed with default config
    assert result.success is True
    assert result.action == ScheduleAction.QUEUED


# Lifecycle tests


class MockAgentExecutor:
    """Mock executor for testing scheduler lifecycle."""

    def __init__(self):
        self.executed_tasks: list[tuple[str, str]] = []  # (work_item_id, agent_id)

    async def execute(self, work_item_id: str, agent_id: str, board_id: str | None = None) -> None:
        """Record executed task."""
        self.executed_tasks.append((work_item_id, agent_id))


@pytest.mark.asyncio
async def test_scheduler_lifecycle_start_stop(mock_task_queue):
    """Test scheduler start/stop lifecycle."""
    executor = MockAgentExecutor()

    scheduler = AgentScheduler(
        task_queue=mock_task_queue,
        resource_monitor=MockResourceMonitor(),
        rate_limiter=MockRateLimiter(),
        config=MockProjectConfiguration(),
        scheduling_events=MockSchedulingEvents(),
        event_store=InMemoryEventStore(),
        agent_executor=executor,
    )

    # Should start without error
    await scheduler.start()

    try:
        # Consumer loop should be running
        assert scheduler._consumer_task is not None
        assert not scheduler._consumer_task.done()
    finally:
        # Should stop without error
        await scheduler.stop()

    # Consumer task should be cleaned up
    assert scheduler._consumer_task is None


@pytest.mark.asyncio
async def test_scheduler_start_without_executor_fails():
    """Test that start() fails if executor not set."""
    scheduler = AgentScheduler(
        task_queue=InMemoryTaskQueue(),
        resource_monitor=MockResourceMonitor(),
        rate_limiter=MockRateLimiter(),
        config=MockProjectConfiguration(),
        scheduling_events=MockSchedulingEvents(),
        event_store=InMemoryEventStore(),
        agent_executor=None,  # No executor
    )

    with pytest.raises(RuntimeError, match="Agent executor not set"):
        await scheduler.start()


@pytest.mark.asyncio
async def test_scheduler_start_twice_fails():
    """Test that start() fails if already started."""
    executor = MockAgentExecutor()

    scheduler = AgentScheduler(
        task_queue=InMemoryTaskQueue(),
        resource_monitor=MockResourceMonitor(),
        rate_limiter=MockRateLimiter(),
        config=MockProjectConfiguration(),
        scheduling_events=MockSchedulingEvents(),
        event_store=InMemoryEventStore(),
        agent_executor=executor,
    )

    await scheduler.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            await scheduler.start()
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_consumes_queued_tasks():
    """Test that scheduler consumes enqueued tasks and dispatches to executor."""
    executor = MockAgentExecutor()
    task_queue = InMemoryTaskQueue()

    scheduler = AgentScheduler(
        task_queue=task_queue,
        resource_monitor=MockResourceMonitor(),
        rate_limiter=MockRateLimiter(),
        config=MockProjectConfiguration(),
        scheduling_events=MockSchedulingEvents(),
        event_store=InMemoryEventStore(),
        agent_executor=executor,
    )

    # Start scheduler
    await scheduler.start()

    try:
        # Enqueue a task
        task = Task(
            id="test-task-1",
            agent="test-agent",
            project="test-project",
            priority=WorkItemPriority.MEDIUM,
            context={"work_item_id": "work-item-123", "work_item_title": "Test Task"},
            created_at=datetime.now(UTC),
        )
        await task_queue.enqueue(task)

        # Give consumer loop time to process the task
        await asyncio.sleep(0.5)

        # Executor should have been called
        assert len(executor.executed_tasks) == 1
        assert executor.executed_tasks[0] == ("work-item-123", "test-agent")

    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_stop_when_not_started():
    """Test that stop() is safe to call when not started."""
    scheduler = AgentScheduler(
        task_queue=InMemoryTaskQueue(),
        resource_monitor=MockResourceMonitor(),
        rate_limiter=MockRateLimiter(),
        config=MockProjectConfiguration(),
        scheduling_events=MockSchedulingEvents(),
        event_store=InMemoryEventStore(),
        agent_executor=MockAgentExecutor(),
    )

    # Should not raise
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_processes_multiple_tasks_by_priority():
    """Test that scheduler processes tasks in priority order."""
    executor = MockAgentExecutor()
    task_queue = InMemoryTaskQueue()

    scheduler = AgentScheduler(
        task_queue=task_queue,
        resource_monitor=MockResourceMonitor(),
        rate_limiter=MockRateLimiter(),
        config=MockProjectConfiguration(),
        scheduling_events=MockSchedulingEvents(),
        event_store=InMemoryEventStore(),
        agent_executor=executor,
    )

    # Enqueue tasks with different priorities BEFORE starting scheduler
    # to ensure they're all available for priority-based dequeue ordering
    now = datetime.now(UTC)
    await task_queue.enqueue(
        Task(
            id="low-priority",
            agent="test-agent",
            project="test-project",
            priority=WorkItemPriority.LOW,
            context={"work_item_id": "work-1"},
            created_at=now,
        )
    )

    await task_queue.enqueue(
        Task(
            id="high-priority",
            agent="test-agent",
            project="test-project",
            priority=WorkItemPriority.HIGH,
            context={"work_item_id": "work-2"},
            created_at=now,
        )
    )

    await task_queue.enqueue(
        Task(
            id="medium-priority",
            agent="test-agent",
            project="test-project",
            priority=WorkItemPriority.MEDIUM,
            context={"work_item_id": "work-3"},
            created_at=now,
        )
    )

    # Start scheduler after all tasks are enqueued
    await scheduler.start()

    try:
        # Give consumer loop time to process all tasks
        await asyncio.sleep(1.0)

        # All tasks should be processed
        assert len(executor.executed_tasks) == 3

        # HIGH priority should be processed first
        assert executor.executed_tasks[0][0] == "work-2"
        # MEDIUM priority next
        assert executor.executed_tasks[1][0] == "work-3"
        # LOW priority last
        assert executor.executed_tasks[2][0] == "work-1"

    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_handles_executor_errors():
    """Test that scheduler continues processing after executor error."""

    class FailingExecutor:
        def __init__(self):
            self.call_count = 0

        async def execute(self, work_item_id: str, agent_id: str, board_id: str | None = None) -> None:
            self.call_count += 1
            if self.call_count == 1:
                raise RuntimeError("Executor error")
            # Second call succeeds

    executor = FailingExecutor()
    task_queue = InMemoryTaskQueue()

    scheduler = AgentScheduler(
        task_queue=task_queue,
        resource_monitor=MockResourceMonitor(),
        rate_limiter=MockRateLimiter(),
        config=MockProjectConfiguration(),
        scheduling_events=MockSchedulingEvents(),
        event_store=InMemoryEventStore(),
        agent_executor=executor,
    )

    # Start scheduler
    await scheduler.start()

    try:
        # Enqueue two tasks
        await task_queue.enqueue(
            Task(
                id="task-1",
                agent="test-agent",
                project="test-project",
                priority=WorkItemPriority.MEDIUM,
                context={"work_item_id": "work-1"},
                created_at=datetime.now(UTC),
            )
        )

        await task_queue.enqueue(
            Task(
                id="task-2",
                agent="test-agent",
                project="test-project",
                priority=WorkItemPriority.MEDIUM,
                context={"work_item_id": "work-2"},
                created_at=datetime.now(UTC),
            )
        )

        # Give consumer loop time to process both tasks despite error
        await asyncio.sleep(1.0)

        # Both tasks should have been processed even though first one failed
        assert executor.call_count == 2

    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_handles_invalid_work_item_id():
    """Test that scheduler handles missing/invalid work_item_id gracefully."""

    class TrackingExecutor:
        def __init__(self):
            self.call_count = 0

        async def execute(self, work_item_id: str, agent_id: str, board_id: str | None = None) -> None:
            self.call_count += 1

    executor = TrackingExecutor()
    task_queue = InMemoryTaskQueue()

    scheduler = AgentScheduler(
        task_queue=task_queue,
        resource_monitor=MockResourceMonitor(),
        rate_limiter=MockRateLimiter(),
        config=MockProjectConfiguration(),
        scheduling_events=MockSchedulingEvents(),
        event_store=InMemoryEventStore(),
        agent_executor=executor,
    )

    # Start scheduler
    await scheduler.start()

    try:
        # Enqueue task with missing work_item_id
        await task_queue.enqueue(
            Task(
                id="task-bad-1",
                agent="test-agent",
                project="test-project",
                priority=WorkItemPriority.MEDIUM,
                context={"wrong_key": "value"},  # Missing work_item_id
                created_at=datetime.now(UTC),
            )
        )

        # Enqueue task with invalid work_item_id type
        await task_queue.enqueue(
            Task(
                id="task-bad-2",
                agent="test-agent",
                project="test-project",
                priority=WorkItemPriority.MEDIUM,
                context={"work_item_id": 123},  # Invalid type (int instead of str)
                created_at=datetime.now(UTC),
            )
        )

        # Enqueue valid task
        await task_queue.enqueue(
            Task(
                id="task-good-1",
                agent="test-agent",
                project="test-project",
                priority=WorkItemPriority.MEDIUM,
                context={"work_item_id": "work-1"},
                created_at=datetime.now(UTC),
            )
        )

        # Give consumer loop time to process all tasks
        await asyncio.sleep(1.0)

        # Only the valid task should have been executed
        assert executor.call_count == 1

    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_emits_task_dispatch_failed_event():
    """Test that scheduler emits TaskDispatchFailedEvent when task dispatch fails."""

    class FailingExecutor:
        async def execute(self, work_item_id: str, agent_id: str, board_id: str | None = None) -> None:
            raise RuntimeError("Executor crashed")

    executor = FailingExecutor()
    task_queue = InMemoryTaskQueue()
    scheduling_events = MockSchedulingEvents()

    scheduler = AgentScheduler(
        task_queue=task_queue,
        resource_monitor=MockResourceMonitor(),
        rate_limiter=MockRateLimiter(),
        config=MockProjectConfiguration(),
        scheduling_events=scheduling_events,
        event_store=InMemoryEventStore(),
        agent_executor=executor,
    )

    # Start scheduler
    await scheduler.start()

    try:
        # Enqueue task that will fail to dispatch
        await task_queue.enqueue(
            Task(
                id="failing-task",
                agent="test-agent",
                project="test-project",
                priority=WorkItemPriority.MEDIUM,
                context={"work_item_id": "work-item-fail"},
                created_at=datetime.now(UTC),
            )
        )

        # Give consumer loop time to process the task
        await asyncio.sleep(0.5)

        # Verify that dispatch_failed event was emitted
        assert len(scheduling_events.dispatch_failed_events) == 1
        event = scheduling_events.dispatch_failed_events[0]
        assert event["task_id"] == "failing-task"
        assert event["work_item_id"] == "work-item-fail"
        assert event["agent_id"] == "test-agent"
        assert "crashed" in event["error"]

    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_handles_event_emission_failure():
    """Test that scheduler continues when emit_task_dispatch_failed raises."""

    class FailingExecutor:
        async def execute(self, work_item_id: str, agent_id: str, board_id: str | None = None) -> None:
            raise RuntimeError("Dispatch failed")

    class FailingSchedulingEvents(MockSchedulingEvents):
        async def emit_task_dispatch_failed(
            self,
            task_id: str,
            work_item_id: str,
            agent_id: str,
            error: str,
        ) -> None:
            raise RuntimeError("Event emission failed")

    executor = FailingExecutor()
    task_queue = InMemoryTaskQueue()
    scheduling_events = FailingSchedulingEvents()

    scheduler = AgentScheduler(
        task_queue=task_queue,
        resource_monitor=MockResourceMonitor(),
        rate_limiter=MockRateLimiter(),
        config=MockProjectConfiguration(),
        scheduling_events=scheduling_events,
        event_store=InMemoryEventStore(),
        agent_executor=executor,
    )

    # Start scheduler
    await scheduler.start()

    try:
        # Enqueue two tasks
        await task_queue.enqueue(
            Task(
                id="task-1",
                agent="test-agent",
                project="test-project",
                priority=WorkItemPriority.MEDIUM,
                context={"work_item_id": "work-1"},
                created_at=datetime.now(UTC),
            )
        )

        await task_queue.enqueue(
            Task(
                id="task-2",
                agent="test-agent",
                project="test-project",
                priority=WorkItemPriority.MEDIUM,
                context={"work_item_id": "work-2"},
                created_at=datetime.now(UTC),
            )
        )

        # Give consumer loop time to attempt processing both tasks
        # Consumer should not exit despite event emission failure
        await asyncio.sleep(1.0)

        # Consumer loop should still be running
        assert scheduler._consumer_task is not None
        assert not scheduler._consumer_task.done()

    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_schedule_double_fault_emit_task_rejected_failure(mock_config):
    """Test that schedule returns original result when emit_task_rejected fails (double-fault)."""

    class FailingSchedulingEvents(MockSchedulingEvents):
        async def emit_task_rejected(self, agent: str, project: str, reason: str) -> None:
            # Event emission fails
            raise RuntimeError("Event bus is down")

    resource_monitor = MockResourceMonitor(
        dev_containers_available={"test-project": True, "blocked-project": False},
        running_agents={"busy-agent": 3, "available-agent": 0},
    )
    scheduling_events = FailingSchedulingEvents()

    scheduler = AgentScheduler(
        task_queue=InMemoryTaskQueue(),
        resource_monitor=resource_monitor,
        rate_limiter=MockRateLimiter(),
        config=mock_config,
        scheduling_events=scheduling_events,
        event_store=InMemoryEventStore(),
    )

    work_item = WorkItem(
        id="work-item-1",
        project_id="blocked-project",
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
        current_column=None,
        entered_column_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        completed_at=None,
    )

    agent = create_test_agent("dev-container-agent", "dev_container_agent", requires_dev_container=True)

    # Schedule should return RESOURCE_UNAVAILABLE result despite event emission failure
    result = await scheduler.schedule(work_item, agent, WorkItemPriority.MEDIUM)

    assert result.success is False
    assert result.action == ScheduleAction.RESOURCE_UNAVAILABLE
    assert "Dev container not available" in result.reason
    assert result.task_id is None
