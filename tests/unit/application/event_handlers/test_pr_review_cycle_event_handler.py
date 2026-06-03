"""Unit tests for PRReviewCycleEventHandler."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from codetoreum.application.event_handlers.pr_review_cycle_event_handler import (
    PRReviewCycleEventHandler,
)
from codetoreum.domain.events.pr_review_cycle_events import (
    PRReviewCycleApprovedEvent,
    PRReviewCycleIssuesFoundEvent,
    PRReviewCycleMaxCyclesReachedEvent,
)
from codetoreum.ports.exceptions import ExternalServiceError, ResourceNotFoundError
from codetoreum.ports.output.board_service import IBoardService, MovedByType


class TestPRReviewCycleEventHandlerInitialization:
    """Test PRReviewCycleEventHandler initialization."""

    def test_handler_initialization(self):
        """Test handler initializes with board service."""
        mock_service = AsyncMock(spec=IBoardService)
        handler = PRReviewCycleEventHandler(mock_service)

        assert handler.board_service is mock_service

    def test_handler_has_event_types(self):
        """Test handler is decorated with correct event types."""
        mock_service = AsyncMock(spec=IBoardService)
        handler = PRReviewCycleEventHandler(mock_service)

        # Check that event_handler decorator adds get_event_types method
        assert hasattr(handler, "get_event_types")
        event_types = handler.get_event_types()
        assert event_types == [
            "PRReviewCycleApprovedEvent",
            "PRReviewCycleIssuesFoundEvent",
            "PRReviewCycleMaxCyclesReachedEvent",
        ]


@pytest.mark.asyncio
class TestPRReviewCycleEventHandlerApprovedPath:
    """Test PRReviewCycleEventHandler for approved event path."""

    async def test_handle_approved_event_moves_item(self):
        """Test handling PRReviewCycleApprovedEvent moves item to next column."""
        mock_service = AsyncMock(spec=IBoardService)
        handler = PRReviewCycleEventHandler(mock_service)

        event = PRReviewCycleApprovedEvent(
            type="pr_review_cycle.approved",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            pr_id="PR-123",
            work_item_id="item-1",
            cycle_number=1,
            next_column="Done",
            workflow_run_id="run-1",
        )

        await handler.handle(event)

        # Verify move_item_to_column was called with correct arguments
        mock_service.move_item_to_column.assert_called_once_with("item-1", "Done", MovedByType.ORCHESTRATOR)

    async def test_approved_event_correct_move_by_type(self):
        """Test handler uses MovedByType.ORCHESTRATOR when moving item."""
        mock_service = AsyncMock(spec=IBoardService)
        handler = PRReviewCycleEventHandler(mock_service)

        event = PRReviewCycleApprovedEvent(
            type="pr_review_cycle.approved",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            pr_id="PR-999",
            work_item_id="item-99",
            cycle_number=1,
            next_column="Review",
            workflow_run_id="run-99",
        )

        await handler.handle(event)

        # Verify MovedByType.ORCHESTRATOR is used
        call_args = mock_service.move_item_to_column.call_args
        assert call_args[0][2] == MovedByType.ORCHESTRATOR


@pytest.mark.asyncio
class TestPRReviewCycleEventHandlerIssuesFoundPath:
    """Test PRReviewCycleEventHandler for issues found event path."""

    async def test_handle_issues_found_event_moves_item(self):
        """Test handling PRReviewCycleIssuesFoundEvent moves item to next column."""
        mock_service = AsyncMock(spec=IBoardService)
        handler = PRReviewCycleEventHandler(mock_service)

        event = PRReviewCycleIssuesFoundEvent(
            type="pr_review_cycle.issues_found",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            pr_id="PR-456",
            work_item_id="item-2",
            cycle_number=2,
            total=3,
            critical=1,
            high=1,
            medium=1,
            low=0,
            sub_issue_count=2,
            next_column="In Development",
            workflow_run_id="run-2",
        )

        await handler.handle(event)

        # Verify move_item_to_column was called with correct arguments
        mock_service.move_item_to_column.assert_called_once_with("item-2", "In Development", MovedByType.ORCHESTRATOR)

    async def test_issues_found_event_multiple_findings(self):
        """Test issues found event with multiple findings moves item correctly."""
        mock_service = AsyncMock(spec=IBoardService)
        handler = PRReviewCycleEventHandler(mock_service)

        event = PRReviewCycleIssuesFoundEvent(
            type="pr_review_cycle.issues_found",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            pr_id="PR-789",
            work_item_id="item-3",
            cycle_number=3,
            total=5,
            critical=1,
            high=2,
            medium=2,
            low=0,
            sub_issue_count=4,
            next_column="Review",
            workflow_run_id="run-3",
        )

        await handler.handle(event)

        # Verify move_item_to_column was called
        mock_service.move_item_to_column.assert_called_once()


@pytest.mark.asyncio
class TestPRReviewCycleEventHandlerMaxCyclesPath:
    """Test PRReviewCycleEventHandler for max cycles reached event path."""

    async def test_handle_max_cycles_event_moves_item(self):
        """Test handling PRReviewCycleMaxCyclesReachedEvent moves item to escalation column."""
        mock_service = AsyncMock(spec=IBoardService)
        handler = PRReviewCycleEventHandler(mock_service)

        event = PRReviewCycleMaxCyclesReachedEvent(
            type="pr_review_cycle.max_cycles_reached",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            pr_id="PR-789",
            work_item_id="item-3",
            cycle_number=3,
            max_cycles=2,
            next_column="Review",
            workflow_run_id="run-3",
        )

        await handler.handle(event)

        # Verify move_item_to_column was called with escalation column
        mock_service.move_item_to_column.assert_called_once_with("item-3", "Review", MovedByType.ORCHESTRATOR)

    async def test_max_cycles_event_escalates_to_human_review(self):
        """Test max cycles event escalates item to human review column."""
        mock_service = AsyncMock(spec=IBoardService)
        handler = PRReviewCycleEventHandler(mock_service)

        event = PRReviewCycleMaxCyclesReachedEvent(
            type="pr_review_cycle.max_cycles_reached",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            pr_id="PR-555",
            work_item_id="item-5",
            cycle_number=5,
            max_cycles=4,
            next_column="Human Review",
            workflow_run_id="run-5",
        )

        await handler.handle(event)

        # Should move to Human Review column
        mock_service.move_item_to_column.assert_called_once_with("item-5", "Human Review", MovedByType.ORCHESTRATOR)


@pytest.mark.asyncio
class TestPRReviewCycleEventHandlerErrorHandling:
    """Test PRReviewCycleEventHandler error handling paths."""

    async def test_resource_not_found_error_handling(self):
        """Test handler raises error when work item not found."""
        mock_service = AsyncMock(spec=IBoardService)
        mock_service.move_item_to_column.side_effect = ResourceNotFoundError("WorkItem", "item-1")
        handler = PRReviewCycleEventHandler(mock_service)

        event = PRReviewCycleApprovedEvent(
            type="pr_review_cycle.approved",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            pr_id="PR-123",
            work_item_id="item-1",
            cycle_number=1,
            next_column="Done",
            workflow_run_id="run-1",
        )

        # Should raise error after logging
        with pytest.raises(ResourceNotFoundError):
            await handler.handle(event)

        # Verify move_item_to_column was attempted
        mock_service.move_item_to_column.assert_called_once()

    async def test_external_service_error_handling(self):
        """Test handler raises error when board service fails."""
        mock_service = AsyncMock(spec=IBoardService)
        mock_service.move_item_to_column.side_effect = ExternalServiceError(
            service="BoardService", message="Board service unavailable"
        )
        handler = PRReviewCycleEventHandler(mock_service)

        event = PRReviewCycleIssuesFoundEvent(
            type="pr_review_cycle.issues_found",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            pr_id="PR-456",
            work_item_id="item-2",
            cycle_number=2,
            total=3,
            critical=1,
            high=1,
            medium=1,
            low=0,
            sub_issue_count=2,
            next_column="In Development",
            workflow_run_id="run-2",
        )

        # Should raise error after logging
        with pytest.raises(ExternalServiceError):
            await handler.handle(event)

        # Verify move_item_to_column was attempted
        mock_service.move_item_to_column.assert_called_once()

    async def test_generic_exception_handling(self):
        """Test handler raises error for generic exceptions."""
        mock_service = AsyncMock(spec=IBoardService)
        mock_service.move_item_to_column.side_effect = Exception("Unexpected error")
        handler = PRReviewCycleEventHandler(mock_service)

        event = PRReviewCycleMaxCyclesReachedEvent(
            type="pr_review_cycle.max_cycles_reached",
            timestamp="2026-04-21T12:00:00+00:00",
            source="test",
            pr_id="PR-789",
            work_item_id="item-3",
            cycle_number=3,
            max_cycles=2,
            next_column="Review",
            workflow_run_id="run-3",
        )

        # Should raise error after logging
        with pytest.raises(Exception, match="Unexpected error"):
            await handler.handle(event)

        # Verify move_item_to_column was attempted
        mock_service.move_item_to_column.assert_called_once()

    async def test_unexpected_event_type(self):
        """Test handler logs warning for unexpected event type."""
        mock_service = AsyncMock(spec=IBoardService)
        handler = PRReviewCycleEventHandler(mock_service)

        # Create a mock event with unexpected type
        event = Mock()
        event.event_type = "UnexpectedEvent"

        # Should not raise, just log warning
        await handler.handle(event)

        # Should not call move_item_to_column for unexpected event
        mock_service.move_item_to_column.assert_not_called()


@pytest.mark.asyncio
class TestPRReviewCycleEventHandlerMultipleEvents:
    """Test PRReviewCycleEventHandler processing multiple events."""

    async def test_handle_multiple_events_in_sequence(self):
        """Test handler processes multiple events correctly."""
        mock_service = AsyncMock(spec=IBoardService)
        handler = PRReviewCycleEventHandler(mock_service)

        events = [
            PRReviewCycleApprovedEvent(
                type="pr_review_cycle.approved",
                timestamp="2026-04-21T12:00:00+00:00",
                source="test",
                pr_id="PR-1",
                work_item_id="item-1",
                cycle_number=1,
                next_column="Done",
                workflow_run_id="run-1",
            ),
            PRReviewCycleIssuesFoundEvent(
                type="pr_review_cycle.issues_found",
                timestamp="2026-04-21T12:05:00+00:00",
                source="test",
                pr_id="PR-2",
                work_item_id="item-2",
                cycle_number=1,
                total=2,
                critical=1,
                high=1,
                medium=0,
                low=0,
                sub_issue_count=1,
                next_column="In Development",
                workflow_run_id="run-2",
            ),
            PRReviewCycleMaxCyclesReachedEvent(
                type="pr_review_cycle.max_cycles_reached",
                timestamp="2026-04-21T12:10:00+00:00",
                source="test",
                pr_id="PR-3",
                work_item_id="item-3",
                cycle_number=3,
                max_cycles=2,
                next_column="Review",
                workflow_run_id="run-3",
            ),
        ]

        for event in events:
            await handler.handle(event)

        # Verify all events were processed
        assert mock_service.move_item_to_column.call_count == 3

        # Verify each call had correct arguments
        calls = mock_service.move_item_to_column.call_args_list
        assert calls[0][0] == ("item-1", "Done", MovedByType.ORCHESTRATOR)
        assert calls[1][0] == ("item-2", "In Development", MovedByType.ORCHESTRATOR)
        assert calls[2][0] == ("item-3", "Review", MovedByType.ORCHESTRATOR)
