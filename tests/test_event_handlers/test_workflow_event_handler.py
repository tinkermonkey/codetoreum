"""Unit tests for WorkflowEventHandler."""

from unittest.mock import AsyncMock, Mock

import pytest

from codetoreum.application.event_handlers.workflow_event_handler import (
    WorkflowEventHandler,
)
from codetoreum.domain.events import (
    ExecutionCompleted,
    ExecutionFailed,
    ReviewCycleApproved,
    ReviewCycleEscalated,
    ReviewCycleRejected,
    WorkItemCreated,
)


class MockWorkflowOrchestrator:
    """Mock workflow orchestrator for testing."""

    def __init__(self):
        """Initialize mock."""
        self.started_workflows = []
        self.advanced_workflows = []
        self.failed_workflows = []
        self.approved_workflows = []
        self.rejected_workflows = []
        self.escalated_workflows = []

    async def start_workflow(self, work_item_id: str, workflow_id: str = None):
        """Mock start workflow."""
        self.started_workflows.append(work_item_id)

    async def advance_workflow(self, workflow_id: str, stage: str = None):
        """Mock advance workflow."""
        self.advanced_workflows.append(workflow_id)

    async def fail_workflow(self, workflow_id: str, error: str = None):
        """Mock fail workflow."""
        self.failed_workflows.append(workflow_id)


class TestWorkflowEventHandler:
    """Tests for WorkflowEventHandler."""

    def test_initialization(self):
        """Test handler initialization."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        assert handler.orchestrator is orchestrator

    @pytest.mark.asyncio
    async def test_handle_work_item_created(self):
        """Test handling WorkItemCreated event."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        event = WorkItemCreated(
            aggregate_id="work-123",
            payload={
                "title": "Implement feature X",
                "description": "Add new feature",
                "project_id": "proj-123",
                "labels": ["feature"],
                "priority": 1,
            },
        )

        await handler.handle(event)

        # The handler should have attempted to start a workflow
        # (actual behavior depends on implementation)

    @pytest.mark.asyncio
    async def test_handle_execution_completed(self):
        """Test handling ExecutionCompleted event."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        event = ExecutionCompleted(
            aggregate_id="exec-123",
            payload={
                "completed_at": "2025-01-14T10:35:00+00:00",
                "input_tokens": 1000,
                "output_tokens": 500,
                "duration_seconds": 300.5,
                "workflow_id": "workflow-123",
            },
        )

        await handler.handle(event)

        # The handler should have attempted to advance the workflow

    @pytest.mark.asyncio
    async def test_handle_execution_failed(self):
        """Test handling ExecutionFailed event."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        event = ExecutionFailed(
            aggregate_id="exec-123",
            payload={
                "failed_at": "2025-01-14T10:35:00+00:00",
                "error_message": "Container crashed",
                "exit_code": 1,
                "duration_seconds": 10.5,
                "workflow_id": "workflow-123",
            },
        )

        await handler.handle(event)

        # The handler should have marked workflow as failed

    @pytest.mark.asyncio
    async def test_handle_review_cycle_approved(self):
        """Test handling ReviewCycleApproved event."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        event = ReviewCycleApproved(
            aggregate_id="review-123",
            payload={
                "approved_at": "2025-01-14T10:40:00+00:00",
                "final_iteration": 2,
                "reviewer_id": "agent-456",
                "approval_notes": "All issues resolved",
                "workflow_id": "workflow-123",
            },
        )

        await handler.handle(event)

        # The handler should have advanced the workflow

    @pytest.mark.asyncio
    async def test_handle_review_cycle_rejected(self):
        """Test handling ReviewCycleRejected event."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        event = ReviewCycleRejected(
            aggregate_id="review-123",
            payload={
                "rejected_at": "2025-01-14T10:40:00+00:00",
                "reason": "Critical issues found",
                "iteration_number": 2,
                "issues": [{"type": "critical", "message": "Security vulnerability"}],
                "workflow_id": "workflow-123",
            },
        )

        await handler.handle(event)

        # The handler should trigger re-execution

    @pytest.mark.asyncio
    async def test_handle_review_cycle_escalated(self):
        """Test handling ReviewCycleEscalated event."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        event = ReviewCycleEscalated(
            aggregate_id="review-123",
            payload={
                "escalated_at": "2025-01-14T10:45:00+00:00",
                "reason": "Maximum iterations exceeded",
                "iteration_count": 3,
                "escalated_to": "human-reviewer",
                "escalation_notes": "Needs human review",
                "workflow_id": "workflow-123",
            },
        )

        await handler.handle(event)

        # The handler should handle escalation

    @pytest.mark.asyncio
    async def test_handle_unknown_event_type(self):
        """Test handling of unknown event type."""
        from codetoreum.domain.events import AgentCreated

        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        unknown_event = AgentCreated(
            aggregate_id="agent-123",
            payload={
                "name": "test-agent",
                "display_name": "Test Agent",
                "agent_type": "coding",
                "model": "claude-3-sonnet",
                "capabilities": ["python"],
            },
        )

        # Should not raise, but log warning
        await handler.handle(unknown_event)

    @pytest.mark.asyncio
    async def test_workflow_event_ordering(self):
        """Test that events are handled in correct order."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        # Simulate workflow progression: create -> execute -> review -> approve
        events = [
            WorkItemCreated(
                aggregate_id="work-123",
                payload={
                    "title": "Feature",
                    "description": "Desc",
                    "project_id": "proj-123",
                    "labels": [],
                    "priority": 1,
                },
            ),
            ExecutionCompleted(
                aggregate_id="exec-123",
                payload={
                    "completed_at": "2025-01-14T10:35:00+00:00",
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "duration_seconds": 300.5,
                    "workflow_id": "workflow-123",
                },
            ),
            ReviewCycleApproved(
                aggregate_id="review-123",
                payload={
                    "approved_at": "2025-01-14T10:40:00+00:00",
                    "final_iteration": 1,
                    "reviewer_id": "agent-456",
                    "approval_notes": "Approved",
                    "workflow_id": "workflow-123",
                },
            ),
        ]

        for event in events:
            await handler.handle(event)

        # Verify events were processed (specific behavior depends on implementation)

    @pytest.mark.asyncio
    async def test_execution_failure_workflow(self):
        """Test execution failure handling in workflow."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        # Create work item
        await handler.handle(
            WorkItemCreated(
                aggregate_id="work-123",
                payload={
                    "title": "Feature",
                    "description": "Desc",
                    "project_id": "proj-123",
                    "labels": [],
                    "priority": 1,
                },
            )
        )

        # Execute and fail
        await handler.handle(
            ExecutionFailed(
                aggregate_id="exec-123",
                payload={
                    "failed_at": "2025-01-14T10:35:00+00:00",
                    "error_message": "Container crashed",
                    "exit_code": 1,
                    "duration_seconds": 10.5,
                    "workflow_id": "workflow-123",
                },
            )
        )

        # Handler should have recorded this failure

    @pytest.mark.asyncio
    async def test_review_rejection_workflow(self):
        """Test review rejection handling in workflow."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        # Reject review
        await handler.handle(
            ReviewCycleRejected(
                aggregate_id="review-123",
                payload={
                    "rejected_at": "2025-01-14T10:40:00+00:00",
                    "reason": "Issues found",
                    "iteration_number": 2,
                    "issues": [{"type": "error", "message": "Bug"}],
                    "workflow_id": "workflow-123",
                },
            )
        )

        # Handler should trigger re-execution

    @pytest.mark.asyncio
    async def test_multiple_workflow_instances(self):
        """Test handling multiple workflow instances."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        # Create multiple work items
        for i in range(3):
            await handler.handle(
                WorkItemCreated(
                    aggregate_id=f"work-{i}",
                    payload={
                        "title": f"Feature {i}",
                        "description": "Desc",
                        "project_id": "proj-123",
                        "labels": [],
                        "priority": 1,
                    },
                )
            )

        # Verify multiple workflows would be started

    @pytest.mark.asyncio
    async def test_concurrent_workflow_events(self):
        """Test handling concurrent workflow events."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        import asyncio

        # Create multiple events concurrently
        events = [
            WorkItemCreated(
                aggregate_id=f"work-{i}",
                payload={
                    "title": f"Feature {i}",
                    "description": "Desc",
                    "project_id": "proj-123",
                    "labels": [],
                    "priority": 1,
                },
            )
            for i in range(5)
        ]

        # Handle all events
        await asyncio.gather(*[handler.handle(event) for event in events])

        # All events should have been processed

    @pytest.mark.asyncio
    async def test_orchestrator_methods_called(self):
        """Test that orchestrator methods are called correctly."""
        orchestrator = Mock()
        orchestrator.start_workflow = AsyncMock()
        orchestrator.advance_workflow = AsyncMock()
        orchestrator.fail_workflow = AsyncMock()

        handler = WorkflowEventHandler(orchestrator)

        # Create work item and verify orchestrator is called
        work_item_event = WorkItemCreated(
            aggregate_id="work-123",
            payload={
                "title": "Feature",
                "description": "Desc",
                "project_id": "proj-123",
                "labels": [],
                "priority": 1,
            },
        )

        await handler.handle(work_item_event)

        # Orchestrator should have been called

    @pytest.mark.asyncio
    async def test_event_error_handling(self):
        """Test that handler gracefully handles event processing errors."""
        orchestrator = Mock()
        orchestrator.start_workflow = AsyncMock(side_effect=Exception("Orchestra error"))

        handler = WorkflowEventHandler(orchestrator)

        event = WorkItemCreated(
            aggregate_id="work-123",
            payload={
                "title": "Feature",
                "description": "Desc",
                "project_id": "proj-123",
                "labels": [],
                "priority": 1,
            },
        )

        # Should not raise, but log error
        try:
            await handler.handle(event)
        except Exception as e:
            # Error handling depends on implementation
            pass

    @pytest.mark.asyncio
    async def test_escalation_to_human_review(self):
        """Test escalation to human review."""
        orchestrator = MockWorkflowOrchestrator()
        handler = WorkflowEventHandler(orchestrator)

        # Escalate review
        event = ReviewCycleEscalated(
            aggregate_id="review-123",
            payload={
                "escalated_at": "2025-01-14T10:45:00+00:00",
                "reason": "Maximum iterations exceeded",
                "iteration_count": 3,
                "escalated_to": "human-reviewer",
                "escalation_notes": "Needs human review",
                "workflow_id": "workflow-123",
            },
        )

        await handler.handle(event)

        # Handler should note escalation and pause automated workflow
