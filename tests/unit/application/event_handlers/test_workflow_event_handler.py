"""Unit tests for WorkflowEventHandler."""

from unittest.mock import Mock, patch

import pytest

from codetoreum.application.event_handlers.workflow_event_handler import (
    WorkflowEventHandler,
)
from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.domain.events import (
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
    ReviewCycleApprovedEvent,
    ReviewCycleEscalatedToHumanEvent,
    ReviewCycleRejectedEvent,
    WorkItemCreatedEvent,
)
from codetoreum.domain.events.adapter_events import now_iso


def _work_item_created(work_item_id: str = "wi-1", title: str = "Test Task") -> WorkItemCreatedEvent:
    return WorkItemCreatedEvent(
        type="workitem.created",
        timestamp=now_iso(),
        source="test",
        work_item_id=work_item_id,
        project_id="proj-1",
        title=title,
    )


def _exec_completed(exec_id: str = "exec-1", work_item_id: str = "wi-1") -> ExecutionCompletedEvent:
    return ExecutionCompletedEvent(
        type="execution.completed",
        timestamp=now_iso(),
        source="test",
        execution_id=exec_id,
        work_item_id=work_item_id,
        agent_id="agent-1",
        input_tokens=100,
        output_tokens=200,
    )


def _exec_failed(exec_id: str = "exec-1", work_item_id: str = "wi-1", error: str = "Failed") -> ExecutionFailedEvent:
    return ExecutionFailedEvent(
        type="execution.failed",
        timestamp=now_iso(),
        source="test",
        execution_id=exec_id,
        work_item_id=work_item_id,
        agent_id="agent-1",
        error=error,
    )


def _review_approved(review_id: str = "review-1", total_iterations: int = 1) -> ReviewCycleApprovedEvent:
    return ReviewCycleApprovedEvent(
        type="review_cycle.approved",
        timestamp=now_iso(),
        source="test",
        review_cycle_id=review_id,
        work_item_id="wi-1",
        total_iterations=total_iterations,
    )


def _review_rejected(
    review_id: str = "review-1", final_iteration: int = 1, reason: str = "Quality issues"
) -> ReviewCycleRejectedEvent:
    return ReviewCycleRejectedEvent(
        type="review_cycle.rejected",
        timestamp=now_iso(),
        source="test",
        review_cycle_id=review_id,
        final_iteration=final_iteration,
        rejection_reason=reason,
    )


def _review_escalated(review_id: str = "review-1", reason: str = "MAX_ITERATIONS") -> ReviewCycleEscalatedToHumanEvent:
    return ReviewCycleEscalatedToHumanEvent(
        type="review_cycle.escalated_to_human",
        timestamp=now_iso(),
        source="test",
        review_cycle_id=review_id,
        work_item_id="wi-1",
        iteration=1,
        escalation_reason=reason,
    )


class TestWorkflowEventHandlerInitialization:
    """Test WorkflowEventHandler initialization."""

    def test_handler_initialization(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        assert handler.orchestrator is mock_orchestrator
        mock_orchestrator.assert_not_called()

    def test_handler_has_event_types(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        assert hasattr(WorkflowEventHandler, "event_types")
        assert "WorkItemCreatedEvent" in WorkflowEventHandler.event_types
        assert "ExecutionCompletedEvent" in WorkflowEventHandler.event_types
        assert "ExecutionFailedEvent" in WorkflowEventHandler.event_types
        assert "ReviewCycleApprovedEvent" in WorkflowEventHandler.event_types
        assert "ReviewCycleRejectedEvent" in WorkflowEventHandler.event_types
        assert "ReviewCycleEscalatedToHumanEvent" in WorkflowEventHandler.event_types


@pytest.mark.asyncio
class TestWorkflowEventHandlerMethods:
    """Test WorkflowEventHandler event handling methods."""

    async def test_handle_work_item_created(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        with patch("codetoreum.application.event_handlers.workflow_event_handler.logger") as mock_logger:
            await handler.handle(_work_item_created("wi-1", "Fix authentication bug"))
            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert "workflow" in call_args.lower() or "work item" in call_args.lower()

    async def test_handle_execution_completed(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        with patch("codetoreum.application.event_handlers.workflow_event_handler.logger") as mock_logger:
            await handler.handle(_exec_completed())
            assert mock_logger.info.called or mock_logger.debug.called

    async def test_handle_execution_failed(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        with patch("codetoreum.application.event_handlers.workflow_event_handler.logger") as mock_logger:
            await handler.handle(_exec_failed(error="Container crashed"))
            assert mock_logger.error.called or mock_logger.warning.called

    async def test_handle_review_cycle_approved(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)
        await handler.handle(_review_approved(total_iterations=2))

    async def test_handle_review_cycle_rejected(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)
        await handler.handle(_review_rejected(reason="Quality issues"))

    async def test_handle_review_cycle_rejected_at_max_iterations(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        with patch("codetoreum.application.event_handlers.workflow_event_handler.logger") as mock_logger:
            await handler.handle(_review_rejected(final_iteration=3, reason="Still has issues"))
            assert mock_logger.error.called or mock_logger.warning.called or mock_logger.info.called

    async def test_handle_review_cycle_escalated(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)
        await handler.handle(_review_escalated())

    async def test_handle_unexpected_event(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        event = Mock()
        event.event_type = "UnexpectedEvent"
        await handler.handle(event)


@pytest.mark.asyncio
class TestWorkflowEventHandlerWorkflows:
    """Test WorkflowEventHandler in realistic workflows."""

    async def test_work_item_to_execution_workflow(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)
        await handler.handle(_work_item_created("wi-1", "Implement feature X"))
        await handler.handle(_exec_completed("exec-1", "wi-1"))

    async def test_execution_failure_workflow(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)
        await handler.handle(_work_item_created("wi-1", "Complex task"))
        await handler.handle(_exec_failed("exec-1", "wi-1", "Container out of memory"))

    async def test_review_approval_workflow(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)
        await handler.handle(_work_item_created("wi-1", "Code changes"))
        await handler.handle(_exec_completed("exec-1", "wi-1"))
        await handler.handle(_review_approved("review-1", 1))

    async def test_review_rejection_and_retry_workflow(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)
        await handler.handle(_work_item_created("wi-1", "Code changes"))
        await handler.handle(_exec_completed("exec-1", "wi-1"))
        await handler.handle(_review_rejected("review-1", final_iteration=1, reason="Code quality not met"))
        await handler.handle(_exec_completed("exec-2", "wi-1"))
        await handler.handle(_review_approved("review-1", total_iterations=2))

    async def test_review_escalation_workflow(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)
        await handler.handle(_work_item_created("wi-1", "Complex changes"))

        for i in range(1, 4):
            await handler.handle(_exec_completed(f"exec-{i}", "wi-1"))
            if i < 3:
                await handler.handle(_review_rejected("review-1", final_iteration=i, reason="Still needs work"))

        await handler.handle(_review_escalated("review-1", "MAX_ITERATIONS"))

    async def test_multiple_work_items_in_workflow(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        for i in range(5):
            await handler.handle(_work_item_created(f"wi-{i}", f"Task {i}"))

        for i in range(5):
            await handler.handle(_exec_completed(f"exec-{i}", f"wi-{i}"))
            if i < 3:
                await handler.handle(_review_approved(f"review-{i}", total_iterations=1))
            elif i < 4:
                await handler.handle(_review_rejected(f"review-{i}", final_iteration=1, reason="Needs changes"))
            else:
                await handler.handle(_review_escalated(f"review-{i}", "MAX_ITERATIONS"))

    async def test_event_sequence_consistency(self):
        mock_orchestrator = Mock(spec=WorkflowOrchestrator)
        handler = WorkflowEventHandler(mock_orchestrator)

        events = [
            _work_item_created("wi-1", "Task 1"),
            _exec_completed("exec-1", "wi-1"),
            _review_approved("review-1", 1),
            _work_item_created("wi-2", "Task 2"),
            _exec_failed("exec-2", "wi-2", "Failed"),
        ]

        for event in events:
            await handler.handle(event)
