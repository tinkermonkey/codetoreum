"""Integration tests for event processing and handlers."""

from datetime import UTC, datetime

import pytest

from codetoreum.adapters.testing.fake_container_adapter import FakeContainerAdapter
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.adapters.testing.in_memory_storage_adapter import InMemoryStorageAdapter
from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.adapters.testing.mock_llm_adapter import MockLLMAdapter
from codetoreum.application.event_bus_wiring import EventBusRegistry, setup_event_bus
from codetoreum.application.event_handlers import (
    ExecutionEventHandler,
    ReviewEventHandler,
    WorkflowEventHandler,
)
from codetoreum.application.execution_service import ExecutionService
from codetoreum.application.review_service import ReviewService
from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.domain.events import (
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionInitialized,
    ExecutionStarted,
    ExecutionTimeout,
    ReviewCycleApproved,
    ReviewCycleCreated,
    ReviewCycleEscalated,
    ReviewCycleRejected,
    ReviewFeedbackSubmitted,
    ReviewIterationStarted,
    WorkItemCreated,
)
from codetoreum.domain.review_cycle import ReviewDecision
from codetoreum.domain.work_item import WorkItemPriority
from codetoreum.infrastructure.event_bus import EventBus


@pytest.fixture
def event_store():
    """Create in-memory event store."""
    store = InMemoryEventStore()
    yield store
    store.clear()


@pytest.fixture
def ticket_system():
    """Create in-memory ticket system."""
    adapter = InMemoryTicketAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def llm_provider():
    """Create mock LLM provider."""
    adapter = MockLLMAdapter()
    yield adapter
    adapter.clear_conversations()
    adapter.reset_stats()


@pytest.fixture
def container():
    """Create fake container adapter."""
    adapter = FakeContainerAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def storage():
    """Create in-memory storage adapter."""
    adapter = InMemoryStorageAdapter()
    yield adapter
    adapter.clear()


@pytest.fixture
def execution_service(llm_provider, container, event_store, storage):
    """Create execution service."""
    return ExecutionService(
        llm_provider=llm_provider,
        container=container,
        event_store=event_store,
        storage=storage,
        max_retries=3,
        retry_delay_seconds=0.1,  # Fast retries for testing
    )


@pytest.fixture
def review_service(event_store):
    """Create review service."""
    return ReviewService(event_store=event_store)


@pytest.fixture
def workflow_orchestrator(event_store, ticket_system):
    """Create workflow orchestrator with mock dependencies."""
    from codetoreum.application.workflow_orchestrator import (
        IDecisionEvents,
        IProjectConfiguration,
        ITaskQueue,
        IWorkflowStateManager,
    )

    # Create mock implementations for testing
    class MockTaskQueue(ITaskQueue):
        def __init__(self):
            self.tasks = []

        async def enqueue(self, task):
            self.tasks.append(task)
            return task.id

    class MockProjectConfiguration(IProjectConfiguration):
        async def get_workflow_config(self, project, board):
            from codetoreum.application.workflow_orchestrator import (
                ColumnConfig,
                WorkflowConfig,
            )

            return WorkflowConfig(
                name="test-workflow",
                columns=[
                    ColumnConfig(
                        name="Todo",
                        position=0,
                        agent="planner",
                        auto_advance_on_approval=False,
                        discussion_category=None,
                        stage_type="planning",
                        review_required=False,
                        reviewer_agent=None,
                    ),
                    ColumnConfig(
                        name="In Progress",
                        position=1,
                        agent="implementer",
                        auto_advance_on_approval=True,
                        discussion_category=None,
                        stage_type="implementation",
                        review_required=True,
                        reviewer_agent="reviewer",
                    ),
                ],
                workspace_type="container",
            )

        async def get_agent_config(self, agent_name):
            from codetoreum.application.workflow_orchestrator import AgentConfig

            return AgentConfig(
                id=f"agent-{agent_name}",
                name=agent_name,
                prompt_template="Test prompt",
                capabilities=["code"],
                requires_dev_container=False,
            )

    class MockWorkflowStateManager(IWorkflowStateManager):
        def __init__(self):
            self.states = {}

        async def get_workflow_state(self, issue_id):
            from codetoreum.application.workflow_orchestrator import WorkflowState

            if issue_id not in self.states:
                self.states[issue_id] = WorkflowState(in_progress_tasks={}, current_column=None, current_agent=None)
            return self.states[issue_id]

        async def update_workflow_state(self, issue_id, state):
            self.states[issue_id] = state

    class MockDecisionEvents(IDecisionEvents):
        def __init__(self):
            self.decisions = []

        async def emit_routing_decision(self, decision):
            self.decisions.append(("routing", decision))

        async def emit_progression_decision(self, decision):
            self.decisions.append(("progression", decision))

    return WorkflowOrchestrator(
        task_queue=MockTaskQueue(),
        config=MockProjectConfiguration(),
        workflow_state=MockWorkflowStateManager(),
        decision_events=MockDecisionEvents(),
        event_store=event_store,
        ticket_system=ticket_system,
    )


@pytest.fixture
def event_bus():
    """Create event bus with fast retry for testing."""
    bus = EventBus(max_retries=3, retry_delay_seconds=0.1)
    yield bus
    # Unregister all handlers to prevent memory leaks
    for handlers in list(bus._handlers.values()):
        for handler in list(handlers):
            bus.unregister_handler(handler)
    for handler in list(bus._wildcard_handlers):
        bus.unregister_handler(handler)
    bus.reset_statistics()


@pytest.fixture
def event_registry(event_bus, workflow_orchestrator, execution_service, review_service):
    """Create event bus registry with all handlers."""
    registry = EventBusRegistry(event_bus=event_bus)

    registry.register_services(
        workflow_orchestrator=workflow_orchestrator,
        execution_service=execution_service,
        review_service=review_service,
    )

    registry.register_handlers(
        register_workflow=True,
        register_execution=True,
        register_review=True,
    )

    return registry


class TestEventHandlerRegistration:
    """Test event handler registration and wiring."""

    async def test_register_all_handlers(self, event_registry):
        """Test that all handlers are registered correctly."""
        stats = event_registry.get_statistics()

        # Should have handlers for multiple event types
        assert stats["total_handlers"] > 0
        assert stats["events_published"] == 0

    async def test_get_handler_by_name(self, event_registry):
        """Test retrieving handlers by name."""
        workflow_handler = event_registry.get_handler("workflow")
        execution_handler = event_registry.get_handler("execution")
        review_handler = event_registry.get_handler("review")

        assert isinstance(workflow_handler, WorkflowEventHandler)
        assert isinstance(execution_handler, ExecutionEventHandler)
        assert isinstance(review_handler, ReviewEventHandler)

    async def test_unregister_handlers(self, event_registry):
        """Test unregistering handlers."""
        event_registry.unregister_handlers()

        stats = event_registry.get_statistics()
        assert stats["total_handlers"] == 0

    async def test_setup_event_bus_convenience(self, workflow_orchestrator, execution_service, review_service):
        """Test convenience setup function."""
        registry = setup_event_bus(
            workflow_orchestrator=workflow_orchestrator,
            execution_service=execution_service,
            review_service=review_service,
        )

        assert registry.get_handler("workflow") is not None
        assert registry.get_handler("execution") is not None
        assert registry.get_handler("review") is not None


class TestExecutionEventHandling:
    """Test execution event handler."""

    async def test_execution_initialized_event(self, event_registry):
        """Test handling ExecutionInitialized event."""
        event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-456",
                "work_item_id": "work-789",
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "model": "claude-3-5-sonnet-20241022",
            },
        )

        await event_registry.event_bus.publish(event)

        # Check handler metrics
        execution_handler = event_registry.get_handler("execution")
        metrics = execution_handler.get_metrics()

        assert metrics["total_executions"] == 1
        assert metrics["active_executions"] == 0

    async def test_execution_started_event(self, event_registry):
        """Test handling ExecutionStarted event."""
        # First initialize
        init_event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-456",
                "work_item_id": "work-789",
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "model": "claude-3-5-sonnet-20241022",
            },
        )
        await event_registry.event_bus.publish(init_event)

        # Then start
        start_event = ExecutionStarted(
            aggregate_id="exec-123",
            payload={
                "started_at": datetime.now(UTC).isoformat(),
                "container_name": "test-container",
            },
        )
        await event_registry.event_bus.publish(start_event)

        execution_handler = event_registry.get_handler("execution")
        metrics = execution_handler.get_metrics()

        assert metrics["active_executions"] == 1
        assert "exec-123" in execution_handler.get_active_executions()

    async def test_execution_completed_event(self, event_registry):
        """Test handling ExecutionCompleted event."""
        # Initialize and start
        init_event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-456",
                "work_item_id": "work-789",
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "model": "claude-3-5-sonnet-20241022",
            },
        )
        await event_registry.event_bus.publish(init_event)

        start_event = ExecutionStarted(
            aggregate_id="exec-123",
            payload={
                "started_at": datetime.now(UTC).isoformat(),
                "container_name": "test-container",
            },
        )
        await event_registry.event_bus.publish(start_event)

        # Complete
        complete_event = ExecutionCompleted(
            aggregate_id="exec-123",
            payload={
                "completed_at": datetime.now(UTC).isoformat(),
                "input_tokens": 100,
                "output_tokens": 200,
                "duration_seconds": 10.5,
                "session_id": "session-123",
            },
        )
        await event_registry.event_bus.publish(complete_event)

        execution_handler = event_registry.get_handler("execution")
        metrics = execution_handler.get_metrics()

        assert metrics["completed_executions"] == 1
        assert metrics["active_executions"] == 0
        assert metrics["success_rate"] == 100.0
        assert "exec-123" not in execution_handler.get_active_executions()

    async def test_execution_failed_event(self, event_registry):
        """Test handling ExecutionFailed event."""
        # Initialize and start
        init_event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-456",
                "work_item_id": "work-789",
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "model": "claude-3-5-sonnet-20241022",
            },
        )
        await event_registry.event_bus.publish(init_event)

        start_event = ExecutionStarted(
            aggregate_id="exec-123",
            payload={
                "started_at": datetime.now(UTC).isoformat(),
                "container_name": "test-container",
            },
        )
        await event_registry.event_bus.publish(start_event)

        # Fail
        fail_event = ExecutionFailed(
            aggregate_id="exec-123",
            payload={
                "failed_at": datetime.now(UTC).isoformat(),
                "error_message": "Test error",
                "exit_code": 1,
                "duration_seconds": 5.0,
            },
        )
        await event_registry.event_bus.publish(fail_event)

        execution_handler = event_registry.get_handler("execution")
        metrics = execution_handler.get_metrics()

        assert metrics["failed_executions"] == 1
        assert metrics["active_executions"] == 0
        assert metrics["failure_rate"] == 100.0

    async def test_execution_timeout_event(self, event_registry):
        """Test handling ExecutionTimeout event."""
        # Initialize and start
        init_event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-456",
                "work_item_id": "work-789",
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "model": "claude-3-5-sonnet-20241022",
            },
        )
        await event_registry.event_bus.publish(init_event)

        start_event = ExecutionStarted(
            aggregate_id="exec-123",
            payload={
                "started_at": datetime.now(UTC).isoformat(),
                "container_name": "test-container",
            },
        )
        await event_registry.event_bus.publish(start_event)

        # Timeout
        timeout_event = ExecutionTimeout(
            aggregate_id="exec-123",
            payload={
                "timeout_at": datetime.now(UTC).isoformat(),
                "duration_seconds": 120.0,
            },
        )
        await event_registry.event_bus.publish(timeout_event)

        execution_handler = event_registry.get_handler("execution")
        metrics = execution_handler.get_metrics()

        assert metrics["timed_out_executions"] == 1
        assert metrics["failed_executions"] == 1
        assert metrics["active_executions"] == 0
        assert metrics["timeout_rate"] == 100.0


class TestReviewEventHandling:
    """Test review event handler."""

    async def test_review_cycle_created_event(self, event_registry):
        """Test handling ReviewCycleCreated event."""
        event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "maker_agent_id": "agent-maker",
                "reviewer_agent_id": "agent-reviewer",
                "max_iterations": 3,
            },
        )

        await event_registry.event_bus.publish(event)

        review_handler = event_registry.get_handler("review")
        metrics = review_handler.get_metrics()

        assert metrics["total_reviews"] == 1
        assert metrics["active_reviews"] == 1
        assert "review-123" in review_handler.get_active_reviews()

    async def test_review_iteration_started_event(self, event_registry):
        """Test handling ReviewIterationStarted event."""
        # Create review first
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "maker_agent_id": "agent-maker",
                "reviewer_agent_id": "agent-reviewer",
                "max_iterations": 3,
            },
        )
        await event_registry.event_bus.publish(create_event)

        # Start iteration
        iteration_event = ReviewIterationStarted(
            aggregate_id="review-123",
            payload={
                "iteration_number": 1,
                "maker_execution_id": "exec-123",
            },
        )
        await event_registry.event_bus.publish(iteration_event)

        review_handler = event_registry.get_handler("review")
        metrics = review_handler.get_metrics()

        assert metrics["total_iterations"] == 1

    async def test_review_cycle_approved_event(self, event_registry):
        """Test handling ReviewCycleApproved event."""
        # Create review
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "maker_agent_id": "agent-maker",
                "reviewer_agent_id": "agent-reviewer",
                "max_iterations": 3,
            },
        )
        await event_registry.event_bus.publish(create_event)

        # Approve
        approve_event = ReviewCycleApproved(
            aggregate_id="review-123",
            payload={
                "total_iterations": 2,
                "approved_at": datetime.now(UTC).isoformat(),
            },
        )
        await event_registry.event_bus.publish(approve_event)

        review_handler = event_registry.get_handler("review")
        metrics = review_handler.get_metrics()

        assert metrics["approved_reviews"] == 1
        assert metrics["active_reviews"] == 0
        assert metrics["approval_rate"] == 100.0
        assert "review-123" not in review_handler.get_active_reviews()

    async def test_review_cycle_rejected_event(self, event_registry):
        """Test handling ReviewCycleRejected event."""
        # Create review
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "maker_agent_id": "agent-maker",
                "reviewer_agent_id": "agent-reviewer",
                "max_iterations": 3,
            },
        )
        await event_registry.event_bus.publish(create_event)

        # Reject (max iterations reached)
        reject_event = ReviewCycleRejected(
            aggregate_id="review-123",
            payload={
                "rejected_at": datetime.now(UTC).isoformat(),
                "final_iteration": 3,
                "reviewer_id": "agent-reviewer",
                "rejection_reason": "Max iterations reached",
            },
        )
        await event_registry.event_bus.publish(reject_event)

        review_handler = event_registry.get_handler("review")
        metrics = review_handler.get_metrics()

        assert metrics["rejected_reviews"] == 1
        assert metrics["active_reviews"] == 0

    async def test_review_cycle_escalated_event(self, event_registry):
        """Test handling ReviewCycleEscalated event."""
        # Create review
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "maker_agent_id": "agent-maker",
                "reviewer_agent_id": "agent-reviewer",
                "max_iterations": 3,
            },
        )
        await event_registry.event_bus.publish(create_event)

        # Escalate
        escalate_event = ReviewCycleEscalated(
            aggregate_id="review-123",
            payload={
                "reason": "Reviewer requested human review",
                "total_iterations": 2,
                "escalated_at": datetime.now(UTC).isoformat(),
            },
        )
        await event_registry.event_bus.publish(escalate_event)

        review_handler = event_registry.get_handler("review")
        metrics = review_handler.get_metrics()

        assert metrics["escalated_reviews"] == 1
        assert metrics["active_reviews"] == 0
        assert metrics["escalation_rate"] == 100.0


class TestEndToEndEventFlow:
    """Test complete event flow from work item to completion."""

    async def test_full_execution_cycle(self, event_registry):
        """Test complete execution lifecycle event flow."""
        # Work item created
        work_item_event = WorkItemCreated(
            aggregate_id="work-123",
            payload={
                "title": "Test work item",
                "description": "Test description",
                "project_id": "test/repo",
                "labels": ["feature"],
                "priority": WorkItemPriority.MEDIUM.value,
                "external_id": "42",
                "external_url": "https://github.com/test/repo/issues/42",
            },
        )
        await event_registry.event_bus.publish(work_item_event)

        # Execution initialized
        init_event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload={
                "agent_id": "agent-456",
                "work_item_id": "work-123",
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "model": "claude-3-5-sonnet-20241022",
            },
        )
        await event_registry.event_bus.publish(init_event)

        # Execution started
        start_event = ExecutionStarted(
            aggregate_id="exec-123",
            payload={
                "started_at": datetime.now(UTC).isoformat(),
                "container_name": "test-container",
            },
        )
        await event_registry.event_bus.publish(start_event)

        # Execution completed
        complete_event = ExecutionCompleted(
            aggregate_id="exec-123",
            payload={
                "completed_at": datetime.now(UTC).isoformat(),
                "input_tokens": 100,
                "output_tokens": 200,
                "duration_seconds": 10.5,
                "session_id": "session-123",
            },
        )
        await event_registry.event_bus.publish(complete_event)

        # Verify metrics
        execution_handler = event_registry.get_handler("execution")
        metrics = execution_handler.get_metrics()

        assert metrics["total_executions"] == 1
        assert metrics["completed_executions"] == 1
        assert metrics["active_executions"] == 0
        assert metrics["success_rate"] == 100.0

    async def test_full_review_cycle_approved(self, event_registry):
        """Test complete review cycle ending in approval."""
        # Review created
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "maker_agent_id": "agent-maker",
                "reviewer_agent_id": "agent-reviewer",
                "max_iterations": 3,
            },
        )
        await event_registry.event_bus.publish(create_event)

        # First iteration
        iteration_event = ReviewIterationStarted(
            aggregate_id="review-123",
            payload={
                "iteration_number": 1,
                "maker_execution_id": "exec-123",
            },
        )
        await event_registry.event_bus.publish(iteration_event)

        # Feedback submitted
        feedback_event = ReviewFeedbackSubmitted(
            aggregate_id="review-123",
            payload={
                "iteration_number": 1,
                "submitted_at": datetime.now(UTC).isoformat(),
                "feedback": "Looks good!",
                "decision": ReviewDecision.APPROVE.value,
                "reviewer_id": "exec-456",
                "issues_found": [],
            },
        )
        await event_registry.event_bus.publish(feedback_event)

        # Approved
        approve_event = ReviewCycleApproved(
            aggregate_id="review-123",
            payload={
                "total_iterations": 1,
                "approved_at": datetime.now(UTC).isoformat(),
            },
        )
        await event_registry.event_bus.publish(approve_event)

        # Verify metrics
        review_handler = event_registry.get_handler("review")
        metrics = review_handler.get_metrics()

        assert metrics["total_reviews"] == 1
        assert metrics["approved_reviews"] == 1
        assert metrics["total_iterations"] == 1
        assert metrics["approval_rate"] == 100.0
        assert metrics["avg_iterations_per_review"] == 1.0

    async def test_full_review_cycle_with_revisions(self, event_registry):
        """Test review cycle with multiple iterations."""
        # Review created
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "workflow-001",
                "stage_name": "implementation",
                "maker_agent_id": "agent-maker",
                "reviewer_agent_id": "agent-reviewer",
                "max_iterations": 3,
            },
        )
        await event_registry.event_bus.publish(create_event)

        # Iteration 1 - rejected
        iteration_1 = ReviewIterationStarted(
            aggregate_id="review-123",
            payload={
                "iteration_number": 1,
                "maker_execution_id": "exec-123",
            },
        )
        await event_registry.event_bus.publish(iteration_1)

        feedback_1 = ReviewFeedbackSubmitted(
            aggregate_id="review-123",
            payload={
                "iteration_number": 1,
                "submitted_at": datetime.now(UTC).isoformat(),
                "feedback": "Needs improvement",
                "decision": ReviewDecision.REQUEST_CHANGES.value,
                "reviewer_id": "exec-456",
                "issues_found": [{"issue": "Issue 1"}, {"issue": "Issue 2"}],
            },
        )
        await event_registry.event_bus.publish(feedback_1)

        # Iteration 2 - approved
        iteration_2 = ReviewIterationStarted(
            aggregate_id="review-123",
            payload={
                "iteration_number": 2,
                "maker_execution_id": "exec-789",
            },
        )
        await event_registry.event_bus.publish(iteration_2)

        feedback_2 = ReviewFeedbackSubmitted(
            aggregate_id="review-123",
            payload={
                "iteration_number": 2,
                "submitted_at": datetime.now(UTC).isoformat(),
                "feedback": "Much better!",
                "decision": ReviewDecision.APPROVE.value,
                "reviewer_id": "exec-012",
                "issues_found": [],
            },
        )
        await event_registry.event_bus.publish(feedback_2)

        approve_event = ReviewCycleApproved(
            aggregate_id="review-123",
            payload={
                "total_iterations": 2,
                "approved_at": datetime.now(UTC).isoformat(),
            },
        )
        await event_registry.event_bus.publish(approve_event)

        # Verify metrics
        review_handler = event_registry.get_handler("review")
        metrics = review_handler.get_metrics()

        assert metrics["total_reviews"] == 1
        assert metrics["approved_reviews"] == 1
        assert metrics["total_iterations"] == 2
        assert metrics["avg_iterations_per_review"] == 2.0

    async def test_event_bus_statistics(self, event_registry):
        """Test that event bus tracks statistics correctly."""
        # Publish multiple events
        events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={
                    "title": "Test 1",
                    "description": "Desc 1",
                    "project_id": "test/repo",
                    "labels": [],
                    "priority": WorkItemPriority.HIGH.value,
                    "external_id": "1",
                    "external_url": "https://github.com/test/repo/issues/1",
                },
            ),
            ExecutionInitialized(
                aggregate_id="exec-1",
                payload={
                    "agent_id": "agent-1",
                    "work_item_id": "work-1",
                    "workflow_id": "wf-1",
                    "stage_name": "test",
                    "model": "claude-3-5-sonnet-20241022",
                },
            ),
            ReviewCycleCreated(
                aggregate_id="review-1",
                payload={
                    "workflow_id": "wf-1",
                    "stage_name": "test",
                    "maker_agent_id": "agent-1",
                    "reviewer_agent_id": "agent-2",
                    "max_iterations": 3,
                },
            ),
        ]

        for event in events:
            await event_registry.event_bus.publish(event)

        stats = event_registry.get_statistics()

        assert stats["events_published"] == 3
        assert stats["events_handled"] > 0
        assert stats["handler_errors"] == 0


class TestEventHandlerErrorHandling:
    """Test error handling and retry logic in event handlers."""

    async def test_handler_retry_on_failure(self, event_bus):
        """Test that failing handlers are retried."""
        from codetoreum.infrastructure.event_bus import EventHandler

        call_count = 0

        class FailingHandler(EventHandler):
            async def handle(self, event):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise Exception("Simulated failure")
                # Succeed on 3rd attempt

            def get_event_types(self):
                return ["WorkItemCreated"]

        handler = FailingHandler()
        event_bus.register_handler(handler)

        event = WorkItemCreated(
            aggregate_id="work-1",
            payload={
                "title": "Test",
                "description": "Desc",
                "project_id": "test/repo",
                "labels": [],
                "priority": WorkItemPriority.MEDIUM.value,
                "external_id": "1",
                "external_url": "https://github.com/test/repo/issues/1",
            },
        )

        await event_bus.publish(event)

        # Should have been called 3 times (2 failures + 1 success)
        assert call_count == 3

        stats = event_bus.get_statistics()
        assert stats["events_published"] == 1
        assert stats["handler_errors"] == 0  # Eventual success

    async def test_handler_max_retries_exceeded(self, event_bus):
        """Test that handlers fail after max retries."""
        from codetoreum.infrastructure.event_bus import EventHandler

        call_count = 0

        class AlwaysFailingHandler(EventHandler):
            async def handle(self, event):
                nonlocal call_count
                call_count += 1
                raise Exception("Always fails")

            def get_event_types(self):
                return ["WorkItemCreated"]

        handler = AlwaysFailingHandler()
        event_bus.register_handler(handler)

        event = WorkItemCreated(
            aggregate_id="work-1",
            payload={
                "title": "Test",
                "description": "Desc",
                "project_id": "test/repo",
                "labels": [],
                "priority": WorkItemPriority.MEDIUM.value,
                "external_id": "1",
                "external_url": "https://github.com/test/repo/issues/1",
            },
        )

        await event_bus.publish(event)

        # Should have been called 4 times (initial + 3 retries)
        assert call_count == 4

        stats = event_bus.get_statistics()
        assert stats["handler_errors"] == 1
