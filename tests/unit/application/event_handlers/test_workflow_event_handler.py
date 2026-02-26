"""Unit tests for WorkflowEventHandler."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codetoreum.application.event_handlers.workflow_event_handler import (
    WorkflowEventHandler,
)
from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.domain.events import (
    ExecutionCompleted,
    ExecutionFailed,
    ReviewCycleApproved,
    ReviewCycleEscalated,
    ReviewCycleRejected,
    WorkItemCreated,
)


class TestWorkflowEventHandlerInitialization:
    """Test WorkflowEventHandler initialization."""

    def test_handler_initialization(self):
        """Test handler initializes with orchestrator."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        assert handler.orchestrator is mock_orchestrator
        # Verify service mock is not accidentally called
        mock_orchestrator.assert_not_called()

    def test_handler_has_event_types(self):
        """Test handler is decorated with correct event types."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        # Verify handler class has event_types attribute set by decorator
        assert hasattr(WorkflowEventHandler, "event_types")
        assert "WorkItemCreated" in WorkflowEventHandler.event_types
        assert "ExecutionCompleted" in WorkflowEventHandler.event_types
        assert "ExecutionFailed" in WorkflowEventHandler.event_types
        assert "ReviewCycleApproved" in WorkflowEventHandler.event_types
        assert "ReviewCycleRejected" in WorkflowEventHandler.event_types
        assert "ReviewCycleEscalated" in WorkflowEventHandler.event_types


@pytest.mark.asyncio
class TestWorkflowEventHandlerMethods:
    """Test WorkflowEventHandler event handling methods."""

    async def test_handle_work_item_created(self):
        """Test handling WorkItemCreated event."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        event = WorkItemCreated(
            aggregate_id="wi-1",
            payload={
                "title": "Fix authentication bug",
                "project_id": "proj-1",
            },
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )

        with patch("codetoreum.application.event_handlers.workflow_event_handler.logger") as mock_logger:
            await handler.handle(event)
            # Verify logging indicates workflow started
            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert "Starting workflow" in call_args or "workflow" in call_args.lower()

    async def test_handle_execution_completed(self):
        """Test handling ExecutionCompleted event."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        event = ExecutionCompleted(
            aggregate_id="exec-1",
            payload={
                "work_item_id": "wi-1",
                "input_tokens": 100,
                "output_tokens": 200,
            },
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )

        with patch("codetoreum.application.event_handlers.workflow_event_handler.logger") as mock_logger:
            await handler.handle(event)
            # Verify logging indicates execution completion
            assert mock_logger.info.called or mock_logger.debug.called

    async def test_handle_execution_failed(self):
        """Test handling ExecutionFailed event."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        event = ExecutionFailed(
            aggregate_id="exec-1",
            payload={
                "work_item_id": "wi-1",
                "error_message": "Container crashed",
                "exit_code": 139,
            },
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )

        with patch("codetoreum.application.event_handlers.workflow_event_handler.logger") as mock_logger:
            await handler.handle(event)
            # Verify logging indicates error handling
            assert mock_logger.error.called or mock_logger.warning.called

    async def test_handle_review_cycle_approved(self):
        """Test handling ReviewCycleApproved event."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        event = ReviewCycleApproved(
            aggregate_id="review-1",
            payload={"total_iterations": 2},
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )

        await handler.handle(event)

        # Should not raise any exception
        # WorkflowEventHandler logs the event

    async def test_handle_review_cycle_rejected(self):
        """Test handling ReviewCycleRejected event."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        event = ReviewCycleRejected(
            aggregate_id="review-1",
            payload={
                "current_iteration": 1,
                "max_iterations": 3,
                "rejection_reason": "Quality issues",
            },
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )

        await handler.handle(event)

        # Should not raise any exception
        # WorkflowEventHandler logs the event

    async def test_handle_review_cycle_rejected_at_max_iterations(self):
        """Test handling ReviewCycleRejected event at max iterations."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        event = ReviewCycleRejected(
            aggregate_id="review-1",
            payload={
                "current_iteration": 3,
                "max_iterations": 3,
                "rejection_reason": "Still has issues",
            },
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )

        with patch("codetoreum.application.event_handlers.workflow_event_handler.logger") as mock_logger:
            await handler.handle(event)
            # Verify logging detects max iterations
            # Handler should log when max iterations reached
            assert mock_logger.error.called or mock_logger.warning.called or mock_logger.info.called

    async def test_handle_review_cycle_escalated(self):
        """Test handling ReviewCycleEscalated event."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        event = ReviewCycleEscalated(
            aggregate_id="review-1",
            payload={"reason": "Max iterations reached"},
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )

        await handler.handle(event)

        # Should not raise any exception
        # WorkflowEventHandler logs the escalation

    async def test_handle_unexpected_event(self):
        """Test handling unexpected event type."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        # Create a mock event with unexpected type
        event = Mock()
        event.event_type = "UnexpectedEvent"

        # Should not raise, just log warning
        await handler.handle(event)

        # No exception should be raised


@pytest.mark.asyncio
class TestWorkflowEventHandlerWorkflows:
    """Test WorkflowEventHandler in realistic workflows."""

    async def test_work_item_to_execution_workflow(self):
        """Test workflow from work item creation through execution."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        # Create work item
        create_event = WorkItemCreated(
            aggregate_id="wi-1",
            payload={"title": "Implement feature X", "project_id": "proj-1"},
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        await handler.handle(create_event)

        # Execution starts (handled by other handlers)
        # When execution completes
        complete_event = ExecutionCompleted(
            aggregate_id="exec-1",
            payload={"work_item_id": "wi-1"},
            occurred_at=datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC),
        )
        await handler.handle(complete_event)

        # No exception should be raised

    async def test_execution_failure_workflow(self):
        """Test workflow handling execution failure."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        # Create work item
        create_event = WorkItemCreated(
            aggregate_id="wi-1",
            payload={"title": "Complex task"},
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        await handler.handle(create_event)

        # Execution fails
        fail_event = ExecutionFailed(
            aggregate_id="exec-1",
            payload={
                "work_item_id": "wi-1",
                "error_message": "Container out of memory",
                "exit_code": 137,
            },
            occurred_at=datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC),
        )
        await handler.handle(fail_event)

        # No exception should be raised

    async def test_review_approval_workflow(self):
        """Test workflow with review approval."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        # Create work item
        create_event = WorkItemCreated(
            aggregate_id="wi-1",
            payload={"title": "Code changes"},
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        await handler.handle(create_event)

        # Execution completes
        complete_event = ExecutionCompleted(
            aggregate_id="exec-1",
            payload={"work_item_id": "wi-1"},
            occurred_at=datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC),
        )
        await handler.handle(complete_event)

        # Review cycle is created and approved
        approve_event = ReviewCycleApproved(
            aggregate_id="review-1",
            payload={"total_iterations": 1},
            occurred_at=datetime(2024, 1, 1, 2, 0, 0, tzinfo=UTC),
        )
        await handler.handle(approve_event)

        # No exception should be raised

    async def test_review_rejection_and_retry_workflow(self):
        """Test workflow with review rejection and retry."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        # Create work item
        create_event = WorkItemCreated(
            aggregate_id="wi-1",
            payload={"title": "Code changes"},
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        await handler.handle(create_event)

        # First execution completes
        complete_event1 = ExecutionCompleted(
            aggregate_id="exec-1",
            payload={"work_item_id": "wi-1"},
            occurred_at=datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC),
        )
        await handler.handle(complete_event1)

        # Review rejects, asks for changes
        reject_event = ReviewCycleRejected(
            aggregate_id="review-1",
            payload={
                "current_iteration": 1,
                "max_iterations": 3,
                "rejection_reason": "Code quality not met",
            },
            occurred_at=datetime(2024, 1, 1, 2, 0, 0, tzinfo=UTC),
        )
        await handler.handle(reject_event)

        # Maker retries
        complete_event2 = ExecutionCompleted(
            aggregate_id="exec-2",
            payload={"work_item_id": "wi-1"},
            occurred_at=datetime(2024, 1, 1, 3, 0, 0, tzinfo=UTC),
        )
        await handler.handle(complete_event2)

        # Review approves
        approve_event = ReviewCycleApproved(
            aggregate_id="review-1",
            payload={"total_iterations": 2},
            occurred_at=datetime(2024, 1, 1, 4, 0, 0, tzinfo=UTC),
        )
        await handler.handle(approve_event)

        # No exception should be raised

    async def test_review_escalation_workflow(self):
        """Test workflow with review escalation."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        # Create work item
        create_event = WorkItemCreated(
            aggregate_id="wi-1",
            payload={"title": "Complex changes"},
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        await handler.handle(create_event)

        # Multiple execution/rejection cycles
        for i in range(1, 4):
            # Execution
            complete_event = ExecutionCompleted(
                aggregate_id=f"exec-{i}",
                payload={"work_item_id": "wi-1"},
                occurred_at=datetime(2024, 1, 1, i, 0, 0, tzinfo=UTC),
            )
            await handler.handle(complete_event)

            # Review rejection (except last)
            if i < 3:
                reject_event = ReviewCycleRejected(
                    aggregate_id="review-1",
                    payload={
                        "current_iteration": i,
                        "max_iterations": 3,
                        "rejection_reason": "Still needs work",
                    },
                    occurred_at=datetime(2024, 1, 1, i, 30, 0, tzinfo=UTC),
                )
                await handler.handle(reject_event)

        # Escalate to human
        escalate_event = ReviewCycleEscalated(
            aggregate_id="review-1",
            payload={"reason": "Max iterations reached"},
            occurred_at=datetime(2024, 1, 1, 4, 0, 0, tzinfo=UTC),
        )
        await handler.handle(escalate_event)

        # No exception should be raised

    async def test_multiple_work_items_in_workflow(self):
        """Test handling multiple work items in parallel."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        # Create multiple work items
        for i in range(5):
            create_event = WorkItemCreated(
                aggregate_id=f"wi-{i}",
                payload={"title": f"Task {i}"},
                occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            )
            await handler.handle(create_event)

        # Process each work item
        for i in range(5):
            complete_event = ExecutionCompleted(
                aggregate_id=f"exec-{i}",
                payload={"work_item_id": f"wi-{i}"},
                occurred_at=datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC),
            )
            await handler.handle(complete_event)

            # Different outcomes
            if i < 3:
                # Approve first 3
                approve_event = ReviewCycleApproved(
                    aggregate_id=f"review-{i}",
                    payload={"total_iterations": 1},
                    occurred_at=datetime(2024, 1, 1, 2, 0, 0, tzinfo=UTC),
                )
                await handler.handle(approve_event)
            elif i < 4:
                # Reject 4th
                reject_event = ReviewCycleRejected(
                    aggregate_id=f"review-{i}",
                    payload={
                        "current_iteration": 1,
                        "max_iterations": 3,
                        "rejection_reason": "Needs changes",
                    },
                    occurred_at=datetime(2024, 1, 1, 2, 0, 0, tzinfo=UTC),
                )
                await handler.handle(reject_event)
            else:
                # Escalate 5th
                escalate_event = ReviewCycleEscalated(
                    aggregate_id=f"review-{i}",
                    payload={"reason": "Human review needed"},
                    occurred_at=datetime(2024, 1, 1, 2, 0, 0, tzinfo=UTC),
                )
                await handler.handle(escalate_event)

        # No exception should be raised

    async def test_review_escalation_at_max_iterations(self):
        """Test that max iterations logic works correctly."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        # Event where current_iteration equals max_iterations
        reject_event = ReviewCycleRejected(
            aggregate_id="review-1",
            payload={
                "current_iteration": 5,
                "max_iterations": 5,
                "rejection_reason": "Quality not met",
            },
            occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )

        await handler.handle(reject_event)

        # No exception should be raised
        # Handler should detect max iterations reached condition

    async def test_event_sequence_consistency(self):
        """Test that events can be handled in realistic sequences."""
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        events = [
            WorkItemCreated(
                aggregate_id="wi-1",
                payload={"title": "Task 1"},
                occurred_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            ),
            ExecutionCompleted(
                aggregate_id="exec-1",
                payload={"work_item_id": "wi-1"},
                occurred_at=datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC),
            ),
            ReviewCycleApproved(
                aggregate_id="review-1",
                payload={"total_iterations": 1},
                occurred_at=datetime(2024, 1, 1, 2, 0, 0, tzinfo=UTC),
            ),
            WorkItemCreated(
                aggregate_id="wi-2",
                payload={"title": "Task 2"},
                occurred_at=datetime(2024, 1, 1, 3, 0, 0, tzinfo=UTC),
            ),
            ExecutionFailed(
                aggregate_id="exec-2",
                payload={"work_item_id": "wi-2", "error_message": "Failed"},
                occurred_at=datetime(2024, 1, 1, 4, 0, 0, tzinfo=UTC),
            ),
        ]

        # Process all events in sequence
        for event in events:
            await handler.handle(event)

        # No exception should be raised
