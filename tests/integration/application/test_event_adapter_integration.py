"""Integration tests for adapter event integration with workflow orchestrator."""

import asyncio
from unittest.mock import MagicMock

import pytest

from codetoreum.application.workflow_orchestrator import (
    ColumnConfig,
    IDecisionEvents,
    IProjectConfiguration,
    ITaskQueue,
    IWorkflowStateManager,
    Task,
    WorkflowConfig,
    WorkflowOrchestrator,
)
from codetoreum.domain.events import WorkItemCreated
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.metrics_collector import MetricsCollector
from codetoreum.ports.output import IEventStore, ITicketSystem


class MockTaskQueue(ITaskQueue):
    """Mock task queue for testing."""

    def __init__(self):
        self.enqueued_tasks = []

    async def enqueue(self, task: Task) -> str:
        """Enqueue a task."""
        self.enqueued_tasks.append(task)
        task_id: str = task.id
        return task_id


class MockProjectConfiguration(IProjectConfiguration):
    """Mock project configuration."""

    def __init__(self):
        self.workflows = {}

    async def get_workflow_config(self, project: str, board: str) -> WorkflowConfig:
        """Get workflow configuration."""
        key = f"{project}:{board}"
        if key not in self.workflows:
            raise ValueError(f"Workflow not found: {key}")
        workflow = self.workflows[key]
        if not isinstance(workflow, WorkflowConfig):
            raise TypeError(f"Expected WorkflowConfig, got {type(workflow)}")
        return workflow

    async def get_agent_config(self, agent_name: str):
        """Get agent configuration."""
        return MagicMock()

    def set_workflow_config(self, project: str, board: str, config: WorkflowConfig):
        """Set workflow configuration for testing."""
        key = f"{project}:{board}"
        self.workflows[key] = config


class MockWorkflowStateManager(IWorkflowStateManager):
    """Mock workflow state manager."""

    async def get_workflow_state(self, issue_id: str):
        """Get workflow state."""
        return MagicMock()

    async def update_workflow_state(self, issue_id: str, state):
        """Update workflow state."""


class MockDecisionEvents(IDecisionEvents):
    """Mock decision events."""

    async def emit_routing_decision(self, decision):
        """Emit routing decision."""

    async def emit_progression_decision(self, decision):
        """Emit progression decision."""


@pytest.mark.asyncio
class TestEventAdapterIntegration:
    """Test suite for adapter event integration with orchestrator."""

    @pytest.fixture
    def event_bus(self):
        """Create event bus for testing."""
        return EventBus()

    @pytest.fixture
    def task_queue(self):
        """Create mock task queue."""
        return MockTaskQueue()

    @pytest.fixture
    def config(self):
        """Create mock configuration."""
        config = MockProjectConfiguration()

        # Set up a test workflow
        workflow = WorkflowConfig(
            name="test_workflow",
            columns=[
                ColumnConfig(
                    name="Backlog",
                    position=0,
                    agent="",
                    auto_advance_on_approval=False,
                    discussion_category=None,
                    stage_type="backlog",
                    review_required=False,
                    reviewer_agent=None,
                ),
                ColumnConfig(
                    name="Development",
                    position=1,
                    agent="dev_agent",
                    auto_advance_on_approval=False,
                    discussion_category=None,
                    stage_type="work",
                    review_required=True,
                    reviewer_agent="review_agent",
                ),
                ColumnConfig(
                    name="Review",
                    position=2,
                    agent="",
                    auto_advance_on_approval=True,
                    discussion_category=None,
                    stage_type="review",
                    review_required=False,
                    reviewer_agent=None,
                ),
                ColumnConfig(
                    name="Done",
                    position=3,
                    agent="",
                    auto_advance_on_approval=False,
                    discussion_category=None,
                    stage_type="done",
                    review_required=False,
                    reviewer_agent=None,
                ),
            ],
            workspace_type="dev_container",
        )

        config.set_workflow_config("test_project", "test_board", workflow)
        return config

    @pytest.fixture
    def orchestrator(self, event_bus, task_queue, config):
        """Create workflow orchestrator with event bus."""
        state_manager = MockWorkflowStateManager()
        decision_events = MockDecisionEvents()
        event_store = MagicMock(spec=IEventStore)
        ticket_system = MagicMock(spec=ITicketSystem)

        return WorkflowOrchestrator(
            task_queue=task_queue,
            config=config,
            workflow_state=state_manager,
            decision_events=decision_events,
            event_store=event_store,
            ticket_system=ticket_system,
            event_bus=event_bus,
        )

    async def test_column_change_triggers_agent(
        self, event_bus, orchestrator, task_queue
    ):
        """Test that column change event triggers agent."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "work_item_id": "work-item-123",
                "project_id": "test_project",
                "board_id": "test_board",
                "to_column": "Development",
                "from_column": "Backlog",
                "moved_by": "human",
            },
        )
        # Change event type to match subscription
        event.event_type = "workitem.column_changed"

        # Act
        await event_bus.publish(event)

        # Give handler time to execute
        await asyncio.sleep(0.1)

        # Assert
        assert len(task_queue.enqueued_tasks) > 0
        task = task_queue.enqueued_tasks[0]
        assert task.agent == "dev_agent"
        assert task.project == "test_project"
        assert task.context["work_item_id"] == "work-item-123"
        assert task.context["column"] == "Development"

    async def test_column_change_with_missing_fields(self, event_bus, task_queue):
        """Test that column change with missing fields is handled gracefully."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "work_item_id": "work-item-123",
                # Missing project_id and board_id
                "to_column": "Development",
            },
        )
        event.event_type = "workitem.column_changed"

        # Act
        await event_bus.publish(event)

        # Give handler time to execute
        await asyncio.sleep(0.1)

        # Assert - no task should be enqueued due to missing fields
        assert len(task_queue.enqueued_tasks) == 0

    async def test_comment_response_triggers_agent(
        self, event_bus, orchestrator, task_queue
    ):
        """Test that comment requiring response triggers conversational agent."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "work_item_id": "work-item-123",
                "project_id": "test_project",
                "agent_assignment": "discussion_agent",
                "comment": "Can you clarify this?",
            },
        )
        event.event_type = "comment.needs_response"

        # Act
        await event_bus.publish(event)

        # Give handler time to execute
        await asyncio.sleep(0.1)

        # Assert
        assert len(task_queue.enqueued_tasks) > 0
        task = task_queue.enqueued_tasks[0]
        assert task.agent == "discussion_agent"
        assert task.context["work_item_id"] == "work-item-123"

    async def test_lock_released_event(self, event_bus):
        """Test that lock released event is handled."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "project_id": "test_project",
                "board_id": "test_board",
                "next_in_queue": "work-item-124",
            },
        )
        event.event_type = "lock.released"

        # Act - should not raise
        await event_bus.publish(event)

        # Give handler time to execute
        await asyncio.sleep(0.1)

        # Assert - no error

    async def test_review_status_changed_event(self, event_bus, task_queue):
        """Test that review status change event is handled."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "work_item_id": "work-item-123",
                "project_id": "test_project",
                "new_status": "approved",
                "previous_status": "pending",
                "board_id": "test_board",
            },
        )
        event.event_type = "review.status_changed"

        # Act - should not raise
        await event_bus.publish(event)

        # Give handler time to execute
        await asyncio.sleep(0.1)

        # Assert - no error

    async def test_multiple_events_processed(
        self, event_bus, orchestrator, task_queue
    ):
        """Test that multiple events are processed correctly."""
        # Arrange
        event1 = WorkItemCreated(
            aggregate_id="work-item-1",
            payload={
                "work_item_id": "work-item-1",
                "project_id": "test_project",
                "board_id": "test_board",
                "to_column": "Development",
                "from_column": "Backlog",
                "moved_by": "human",
            },
        )
        event1.event_type = "workitem.column_changed"

        event2 = WorkItemCreated(
            aggregate_id="work-item-2",
            payload={
                "work_item_id": "work-item-2",
                "project_id": "test_project",
                "board_id": "test_board",
                "to_column": "Development",
                "from_column": "Backlog",
                "moved_by": "human",
            },
        )
        event2.event_type = "workitem.column_changed"

        # Act
        await event_bus.publish(event1)
        await event_bus.publish(event2)

        # Give handlers time to execute
        await asyncio.sleep(0.2)

        # Assert
        assert len(task_queue.enqueued_tasks) >= 2

    async def test_event_bus_statistics(self, event_bus, orchestrator):
        """Test that event bus tracks statistics."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "work_item_id": "work-item-123",
                "project_id": "test_project",
                "board_id": "test_board",
                "to_column": "Development",
                "from_column": "Backlog",
                "moved_by": "human",
            },
        )
        event.event_type = "workitem.column_changed"

        # Act
        await event_bus.publish(event)

        # Assert
        stats = event_bus.get_statistics()
        assert stats["events_published"] == 1
        assert stats["total_callbacks"] >= 1


@pytest.mark.asyncio
class TestMetricsCollection:
    """Test suite for metrics collection from events."""

    @pytest.fixture
    def event_bus(self):
        """Create event bus for testing."""
        return EventBus()

    @pytest.fixture
    def metrics_collector(self, event_bus):
        """Create metrics collector."""
        return MetricsCollector(event_bus)

    async def test_column_change_metrics(self, event_bus, metrics_collector):
        """Test that column change metrics are recorded."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "work_item_id": "work-item-123",
                "to_column": "Development",
                "agent_name": "dev_agent",
            },
        )
        event.event_type = "workitem.column_changed"

        # Act
        await event_bus.publish(event)

        # Give handler time to execute
        await asyncio.sleep(0.1)

        # Assert
        metrics = metrics_collector.get_metrics()
        assert "Development" in metrics["column_changes"]
        assert metrics["column_changes"]["Development"] == 1
        assert metrics["agents_triggered"] == 1

    async def test_lock_metrics(self, event_bus, metrics_collector):
        """Test that lock metrics are recorded."""
        # Arrange
        acq_event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "acquisition_method": "normal",
            },
        )
        acq_event.event_type = "lock.acquired"

        rel_event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "reason": "completed",
                "duration_ms": 5000,
            },
        )
        rel_event.event_type = "lock.released"

        # Act
        await event_bus.publish(acq_event)
        await event_bus.publish(rel_event)

        # Give handlers time to execute
        await asyncio.sleep(0.1)

        # Assert
        metrics = metrics_collector.get_metrics()
        assert metrics["lock_acquisitions"] == 1
        assert metrics["lock_releases"] == 1
        assert metrics["avg_lock_wait_ms"] == 5000

    async def test_review_metrics(self, event_bus, metrics_collector):
        """Test that review metrics are recorded."""
        # Arrange
        approved_event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"new_status": "approved"},
        )
        approved_event.event_type = "review.status_changed"

        changes_event = WorkItemCreated(
            aggregate_id="work-item-124",
            payload={"new_status": "changes_requested"},
        )
        changes_event.event_type = "review.status_changed"

        # Act
        await event_bus.publish(approved_event)
        await event_bus.publish(changes_event)

        # Give handlers time to execute
        await asyncio.sleep(0.1)

        # Assert
        metrics = metrics_collector.get_metrics()
        assert metrics["reviews_approved"] == 1
        assert metrics["reviews_changes_requested"] == 1

    async def test_comment_metrics(self, event_bus, metrics_collector):
        """Test that comment metrics are recorded."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={},
        )
        event.event_type = "comment.posted"

        # Act
        await event_bus.publish(event)

        # Give handler time to execute
        await asyncio.sleep(0.1)

        # Assert
        metrics = metrics_collector.get_metrics()
        assert metrics["comments_processed"] == 1

    async def test_error_handling_in_metrics(self, event_bus, metrics_collector):
        """Test that metrics collector handles errors gracefully."""
        # Arrange - create event with missing required fields
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={},  # Missing required fields
        )
        event.event_type = "workitem.column_changed"

        # Act - should not raise
        await event_bus.publish(event)

        # Give handler time to execute
        await asyncio.sleep(0.1)

        # Assert
        metrics = metrics_collector.get_metrics()
        assert metrics["errors"] == 0  # No error counted for validation failure
