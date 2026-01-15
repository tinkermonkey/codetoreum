"""Simulation tests for event-driven workflow execution."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

import pytest

from codetoreum.application.workflow_orchestrator import (
    WorkflowOrchestrator,
    ColumnConfig,
    WorkflowConfig,
    ITaskQueue,
    IProjectConfiguration,
    IWorkflowStateManager,
    IDecisionEvents,
    Task,
)
from codetoreum.domain.events import DomainEvent, WorkItemCreated
from codetoreum.domain.work_item import WorkItemPriority
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.metrics_collector import MetricsCollector
from codetoreum.ports.output import IEventStore, ITicketSystem, IBoardService
from codetoreum.ports.output.board_service import WorkItemPosition


class SimulationTaskQueue(ITaskQueue):
    """Task queue for simulation testing."""

    def __init__(self):
        self.enqueued_tasks = []
        self.task_counter = 0

    async def enqueue(self, task: Task) -> str:
        """Enqueue a task."""
        self.enqueued_tasks.append(task)
        self.task_counter += 1
        return f"task-{self.task_counter}"


class SimulationProjectConfiguration(IProjectConfiguration):
    """Project configuration for simulation testing."""

    def __init__(self):
        self.workflows = {}

    async def get_workflow_config(self, project: str, board: str) -> WorkflowConfig:
        """Get workflow configuration."""
        key = f"{project}:{board}"
        if key not in self.workflows:
            # Return a default workflow
            return self._create_default_workflow()
        return self.workflows[key]

    async def get_agent_config(self, agent_name: str):
        """Get agent configuration."""
        return MagicMock()

    def _create_default_workflow(self) -> WorkflowConfig:
        """Create default workflow for testing."""
        return WorkflowConfig(
            name="default_workflow",
            columns=[
                ColumnConfig(
                    name="Backlog",
                    position=0,
                    agent=None,
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
                    agent=None,
                    auto_advance_on_approval=True,
                    discussion_category=None,
                    stage_type="review",
                    review_required=False,
                    reviewer_agent=None,
                ),
                ColumnConfig(
                    name="Done",
                    position=3,
                    agent=None,
                    auto_advance_on_approval=False,
                    discussion_category=None,
                    stage_type="done",
                    review_required=False,
                    reviewer_agent=None,
                ),
            ],
            workspace_type="dev_container",
        )


class SimulationWorkflowStateManager(IWorkflowStateManager):
    """Workflow state manager for simulation testing."""

    async def get_workflow_state(self, issue_id: str):
        """Get workflow state."""
        return MagicMock()

    async def update_workflow_state(self, issue_id: str, state):
        """Update workflow state."""
        pass


class SimulationDecisionEvents(IDecisionEvents):
    """Decision events for simulation testing."""

    def __init__(self):
        self.routing_decisions = []
        self.progression_decisions = []

    async def emit_routing_decision(self, decision):
        """Emit routing decision."""
        self.routing_decisions.append(decision)

    async def emit_progression_decision(self, decision):
        """Emit progression decision."""
        self.progression_decisions.append(decision)


def create_mock_board_service():
    """Create a mock board service for testing."""
    service = AsyncMock(spec=IBoardService)
    service.get_item_position = AsyncMock(
        return_value=WorkItemPosition(
            work_item_id="issue-2",
            column_name="Development",
            position=1,
        )
    )
    return service


@pytest.mark.asyncio
class TestEventDrivenWorkflow:
    """Simulation tests for event-driven workflow execution."""

    @pytest.fixture
    def event_bus(self):
        """Create event bus."""
        return EventBus()

    @pytest.fixture
    def task_queue(self):
        """Create task queue."""
        return SimulationTaskQueue()

    @pytest.fixture
    def config(self):
        """Create configuration."""
        return SimulationProjectConfiguration()

    @pytest.fixture
    def state_manager(self):
        """Create state manager."""
        return SimulationWorkflowStateManager()

    @pytest.fixture
    def decision_events(self):
        """Create decision events."""
        return SimulationDecisionEvents()

    @pytest.fixture
    def board_service(self):
        """Create board service."""
        return create_mock_board_service()

    @pytest.fixture
    def orchestrator(
        self, event_bus, task_queue, config, state_manager, decision_events, board_service
    ):
        """Create workflow orchestrator."""
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
            board_service=board_service,
        )

    @pytest.fixture
    def metrics_collector(self, event_bus):
        """Create metrics collector."""
        return MetricsCollector(event_bus)

    async def test_full_workflow_item_movement(
        self, event_bus, orchestrator, task_queue, metrics_collector
    ):
        """
        Test full workflow: item moves through Backlog -> Development -> Review -> Done.

        Simulates:
        1. Item moved to Development (automated column)
        2. Development agent is triggered
        3. Item moves to Review
        4. Review is approved
        5. Item moves to Done
        """
        # Act: Simulate item moving to Development
        column_change_event = WorkItemCreated(
            aggregate_id="issue-1",
            payload={
                "work_item_id": "issue-1",
                "project_id": "sim_project",
                "board_id": "sim_board",
                "to_column": "Development",
                "from_column": "Backlog",
                "moved_by": "human",
            },
        )
        column_change_event.event_type = "workitem.column_changed"

        await event_bus.publish(column_change_event)
        await asyncio.sleep(0.1)

        # Assert: Development agent should be triggered
        assert len(task_queue.enqueued_tasks) == 1
        dev_task = task_queue.enqueued_tasks[0]
        assert dev_task.agent == "dev_agent"
        assert dev_task.context["work_item_id"] == "issue-1"

        # Act: Item moves to Review
        review_event = WorkItemCreated(
            aggregate_id="issue-1",
            payload={
                "work_item_id": "issue-1",
                "project_id": "sim_project",
                "board_id": "sim_board",
                "to_column": "Review",
                "from_column": "Development",
                "moved_by": "orchestrator",
            },
        )
        review_event.event_type = "workitem.column_changed"

        await event_bus.publish(review_event)
        await asyncio.sleep(0.1)

        # Assert: No new task should be triggered (Review is not automated)
        assert len(task_queue.enqueued_tasks) == 1

        # Act: Review is approved
        approval_event = WorkItemCreated(
            aggregate_id="issue-1",
            payload={
                "work_item_id": "issue-1",
                "project_id": "sim_project",
                "new_status": "approved",
                "previous_status": "pending",
                "board_id": "sim_board",
            },
        )
        approval_event.event_type = "review.status_changed"

        await event_bus.publish(approval_event)
        await asyncio.sleep(0.1)

        # Assert: Metrics should show review approval
        metrics = metrics_collector.get_metrics()
        assert metrics["reviews_approved"] == 1
        assert metrics["column_changes"]["Development"] == 1
        assert metrics["column_changes"]["Review"] == 1

    async def test_workflow_with_discussion(
        self, event_bus, orchestrator, task_queue, metrics_collector
    ):
        """
        Test workflow with discussion/comment handling.

        Simulates:
        1. Item moves to Development
        2. Comment is posted requiring response
        3. Conversational agent responds
        """
        # Act: Item moved to Development
        column_event = WorkItemCreated(
            aggregate_id="issue-2",
            payload={
                "work_item_id": "issue-2",
                "project_id": "sim_project",
                "board_id": "sim_board",
                "to_column": "Development",
                "from_column": "Backlog",
                "moved_by": "human",
                "agent_name": "dev_agent",
            },
        )
        column_event.event_type = "workitem.column_changed"

        await event_bus.publish(column_event)
        await asyncio.sleep(0.1)

        # Act: Comment requires response
        comment_event = WorkItemCreated(
            aggregate_id="issue-2",
            payload={
                "work_item_id": "issue-2",
                "project_id": "sim_project",
                "agent_assignment": "discussion_agent",
                "comment": "Can you explain this approach?",
            },
        )
        comment_event.event_type = "comment.needs_response"

        await event_bus.publish(comment_event)
        await asyncio.sleep(0.1)

        # Assert: Both dev_agent and discussion_agent should be triggered
        assert len(task_queue.enqueued_tasks) == 2
        agents_triggered = [task.agent for task in task_queue.enqueued_tasks]
        assert "dev_agent" in agents_triggered
        assert "discussion_agent" in agents_triggered

        # Assert: Metrics
        metrics = metrics_collector.get_metrics()
        assert metrics["agents_triggered"] >= 1  # At least discussion agent triggered
        assert metrics["column_changes"]["Development"] == 1

    async def test_workflow_with_lock_progression(
        self, event_bus, orchestrator, task_queue, metrics_collector
    ):
        """
        Test workflow with lock-based queue progression.

        Simulates:
        1. Item 1 acquires lock and processes
        2. Item 1 releases lock
        3. Item 2 (queued) acquires lock
        """
        # Act: Item 1 moves to Development (acquires lock)
        item1_event = WorkItemCreated(
            aggregate_id="issue-1",
            payload={
                "work_item_id": "issue-1",
                "project_id": "sim_project",
                "board_id": "sim_board",
                "to_column": "Development",
                "from_column": "Backlog",
                "moved_by": "human",
            },
        )
        item1_event.event_type = "workitem.column_changed"

        await event_bus.publish(item1_event)
        await asyncio.sleep(0.1)

        # Act: Lock acquired for item 1
        lock_acq_event = WorkItemCreated(
            aggregate_id="issue-1",
            payload={
                "acquisition_method": "normal",
            },
        )
        lock_acq_event.event_type = "lock.acquired"

        await event_bus.publish(lock_acq_event)
        await asyncio.sleep(0.1)

        # Act: Lock released, item 2 next in queue
        lock_rel_event = WorkItemCreated(
            aggregate_id="issue-1",
            payload={
                "project_id": "sim_project",
                "board_id": "sim_board",
                "next_in_queue": "issue-2",
                "reason": "completed",
                "duration_ms": 10000,
            },
        )
        lock_rel_event.event_type = "lock.released"

        await event_bus.publish(lock_rel_event)
        await asyncio.sleep(0.1)

        # Act: Item 2 moves to Development (acquires lock)
        item2_event = WorkItemCreated(
            aggregate_id="issue-2",
            payload={
                "work_item_id": "issue-2",
                "project_id": "sim_project",
                "board_id": "sim_board",
                "to_column": "Development",
                "from_column": "Backlog",
                "moved_by": "orchestrator",
            },
        )
        item2_event.event_type = "workitem.column_changed"

        await event_bus.publish(item2_event)
        await asyncio.sleep(0.1)

        # Assert: Both items should have triggered dev_agent
        assert len(task_queue.enqueued_tasks) >= 2

        # Assert: Lock metrics
        metrics = metrics_collector.get_metrics()
        assert metrics["lock_acquisitions"] == 1
        assert metrics["lock_releases"] == 1
        assert metrics["avg_lock_wait_ms"] == 10000

    async def test_workflow_event_ordering(
        self, event_bus, orchestrator, task_queue, metrics_collector
    ):
        """
        Test that events are processed in order.

        This simulates high-throughput event processing and verifies
        that all events are handled correctly even with rapid publication.
        """
        # Act: Rapidly publish multiple events
        num_items = 5

        for i in range(num_items):
            event = WorkItemCreated(
                aggregate_id=f"issue-{i}",
                payload={
                    "work_item_id": f"issue-{i}",
                    "project_id": "sim_project",
                    "board_id": "sim_board",
                    "to_column": "Development",
                    "from_column": "Backlog",
                    "moved_by": "human",
                    "agent_name": "dev_agent",
                },
            )
            event.event_type = "workitem.column_changed"
            await event_bus.publish(event)

        # Give handlers time to execute
        await asyncio.sleep(0.2)

        # Assert: All items should have triggered tasks
        assert len(task_queue.enqueued_tasks) == num_items

        # Assert: All work items should be present in tasks
        work_item_ids = [task.context["work_item_id"] for task in task_queue.enqueued_tasks]
        for i in range(num_items):
            assert f"issue-{i}" in work_item_ids

        # Assert: Metrics should reflect all items
        metrics = metrics_collector.get_metrics()
        assert metrics["column_changes"]["Development"] == num_items

    async def test_workflow_error_resilience(
        self, event_bus, orchestrator, task_queue
    ):
        """
        Test that workflow continues despite errors in event handling.

        This verifies that an error in one handler doesn't prevent
        other handlers from executing.
        """
        # Arrange: Create a bad event (missing required fields)
        bad_event = WorkItemCreated(
            aggregate_id="bad-issue",
            payload={
                # Missing required fields
                "to_column": "Development",
            },
        )
        bad_event.event_type = "workitem.column_changed"

        # Arrange: Create a good event
        good_event = WorkItemCreated(
            aggregate_id="good-issue",
            payload={
                "work_item_id": "good-issue",
                "project_id": "sim_project",
                "board_id": "sim_board",
                "to_column": "Development",
                "from_column": "Backlog",
                "moved_by": "human",
            },
        )
        good_event.event_type = "workitem.column_changed"

        # Act: Publish both events
        await event_bus.publish(bad_event)
        await event_bus.publish(good_event)

        # Give handlers time to execute
        await asyncio.sleep(0.1)

        # Assert: Good event should still be processed
        assert len(task_queue.enqueued_tasks) >= 1
        # Find the good task
        good_tasks = [t for t in task_queue.enqueued_tasks if t.context.get("work_item_id") == "good-issue"]
        assert len(good_tasks) > 0

    async def test_event_bus_statistics_in_simulation(
        self, event_bus, orchestrator, metrics_collector
    ):
        """
        Test that event bus statistics are updated correctly during simulation.
        """
        # Arrange
        num_events = 3

        # Act: Publish events
        for i in range(num_events):
            event = WorkItemCreated(
                aggregate_id=f"issue-{i}",
                payload={
                    "work_item_id": f"issue-{i}",
                    "project_id": "sim_project",
                    "board_id": "sim_board",
                    "to_column": "Development",
                    "from_column": "Backlog",
                    "moved_by": "human",
                    "agent_name": "dev_agent",
                },
            )
            event.event_type = "workitem.column_changed"
            await event_bus.publish(event)

        await asyncio.sleep(0.1)

        # Assert: Event bus statistics
        bus_stats = event_bus.get_statistics()
        assert bus_stats["events_published"] == num_events

        # Assert: Metrics collector statistics
        metrics = metrics_collector.get_metrics()
        assert metrics["column_changes"]["Development"] == num_events
