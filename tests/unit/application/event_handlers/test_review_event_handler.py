"""Unit tests for ReviewEventHandler."""

from unittest.mock import Mock

import pytest

from codetoreum.application.event_handlers.review_event_handler import (
    ReviewEventHandler,
)
from codetoreum.application.review_service import ReviewService
from codetoreum.domain.events import (
    ReviewCycleApprovedEvent,
    ReviewCycleCreatedEvent,
    ReviewCycleEscalatedToHumanEvent,
    ReviewCycleFeedbackSubmittedEvent,
    ReviewCycleIterationStartedEvent,
    ReviewCycleRejectedEvent,
)
from codetoreum.domain.events.adapter_events import now_iso


def _created(review_id: str, workflow_id: str = "wf-1", max_iterations: int = 3) -> ReviewCycleCreatedEvent:
    return ReviewCycleCreatedEvent(
        type="review_cycle.created",
        timestamp=now_iso(),
        source="test",
        review_cycle_id=review_id,
        workflow_id=workflow_id,
        stage_name="Review",
        maker_agent_id="agent-1",
        reviewer_agent_id="agent-2",
        max_iterations=max_iterations,
    )


def _iter_started(review_id: str, iteration: int = 1, exec_id: str = "exec-1") -> ReviewCycleIterationStartedEvent:
    return ReviewCycleIterationStartedEvent(
        type="review_cycle.iteration_started",
        timestamp=now_iso(),
        source="test",
        review_cycle_id=review_id,
        iteration_number=iteration,
        maker_execution_id=exec_id,
    )


def _feedback(review_id: str, iteration: int = 1, decision: str = "APPROVE") -> ReviewCycleFeedbackSubmittedEvent:
    return ReviewCycleFeedbackSubmittedEvent(
        type="review_cycle.feedback_submitted",
        timestamp=now_iso(),
        source="test",
        review_cycle_id=review_id,
        iteration_number=iteration,
        decision=decision,
        reviewer_execution_id="rev-exec-1",
        issues_count=0,
    )


def _approved(review_id: str, total_iterations: int = 1) -> ReviewCycleApprovedEvent:
    return ReviewCycleApprovedEvent(
        type="review_cycle.approved",
        timestamp=now_iso(),
        source="test",
        review_cycle_id=review_id,
        work_item_id="wi-1",
        total_iterations=total_iterations,
    )


def _rejected(review_id: str, final_iteration: int = 1, reason: str = "Quality issues") -> ReviewCycleRejectedEvent:
    return ReviewCycleRejectedEvent(
        type="review_cycle.rejected",
        timestamp=now_iso(),
        source="test",
        review_cycle_id=review_id,
        final_iteration=final_iteration,
        rejection_reason=reason,
    )


def _escalated(review_id: str, reason: str = "MAX_ITERATIONS") -> ReviewCycleEscalatedToHumanEvent:
    return ReviewCycleEscalatedToHumanEvent(
        type="review_cycle.escalated_to_human",
        timestamp=now_iso(),
        source="test",
        review_cycle_id=review_id,
        work_item_id="wi-1",
        iteration=1,
        escalation_reason=reason,
    )


class TestReviewEventHandlerInitialization:
    """Test ReviewEventHandler initialization."""

    def test_handler_initialization(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        assert handler.review_service is mock_service
        assert handler._metrics == {
            "total_reviews": 0,
            "active_reviews": 0,
            "approved_reviews": 0,
            "rejected_reviews": 0,
            "escalated_reviews": 0,
            "total_iterations": 0,
        }
        assert handler._active_reviews == {}
        mock_service.assert_not_called()

    def test_handler_has_event_types(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        assert hasattr(handler, "get_event_types")
        event_types = handler.get_event_types()
        assert "ReviewCycleCreatedEvent" in event_types
        assert "ReviewCycleIterationStartedEvent" in event_types
        assert "ReviewCycleFeedbackSubmittedEvent" in event_types
        assert "ReviewCycleApprovedEvent" in event_types
        assert "ReviewCycleRejectedEvent" in event_types
        assert "ReviewCycleEscalatedToHumanEvent" in event_types


@pytest.mark.asyncio
class TestReviewEventHandlerMethods:
    """Test ReviewEventHandler event handling methods."""

    async def test_handle_review_cycle_created(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        await handler.handle(_created("review-1", "wf-1"))

        assert handler._metrics["total_reviews"] == 1
        assert handler._metrics["active_reviews"] == 1
        assert "review-1" in handler._active_reviews
        assert handler._active_reviews["review-1"] == "wf-1"

    async def test_handle_review_iteration_started(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)
        handler._metrics["total_reviews"] = 1

        await handler.handle(_iter_started("review-1", iteration=1))

        assert handler._metrics["total_iterations"] == 1

    async def test_handle_review_feedback_submitted(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        await handler.handle(_feedback("review-1", iteration=1, decision="REQUEST_CHANGES"))

        assert handler._metrics["total_reviews"] == 0

    async def test_handle_review_cycle_approved(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._metrics["total_reviews"] = 1
        handler._metrics["active_reviews"] = 1
        handler._active_reviews["review-1"] = "wf-1"

        await handler.handle(_approved("review-1", total_iterations=2))

        assert handler._metrics["approved_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-1" not in handler._active_reviews

    async def test_handle_review_cycle_rejected(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._metrics["total_reviews"] = 1
        handler._metrics["active_reviews"] = 1
        handler._active_reviews["review-1"] = "wf-1"

        await handler.handle(_rejected("review-1", final_iteration=2, reason="Code quality not met"))

        assert handler._metrics["rejected_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-1" not in handler._active_reviews

    async def test_handle_review_cycle_escalated(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._metrics["total_reviews"] = 1
        handler._metrics["active_reviews"] = 1
        handler._active_reviews["review-1"] = "wf-1"

        await handler.handle(_escalated("review-1", "MAX_ITERATIONS"))

        assert handler._metrics["escalated_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-1" not in handler._active_reviews

    async def test_handle_unexpected_event(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        event = Mock()
        event.event_type = "UnexpectedEvent"
        await handler.handle(event)

        assert handler._metrics["total_reviews"] == 0


@pytest.mark.asyncio
class TestReviewEventHandlerMetrics:
    """Test ReviewEventHandler metrics calculations."""

    async def test_get_metrics_initial_state(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        metrics = handler.get_metrics()
        assert metrics["total_reviews"] == 0
        assert metrics["approval_rate"] == 0.0
        assert metrics["rejection_rate"] == 0.0
        assert metrics["escalation_rate"] == 0.0
        assert metrics["avg_iterations_per_review"] == 0.0

    async def test_approval_rate_calculation(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)
        handler._metrics["total_reviews"] = 10
        handler._metrics["approved_reviews"] = 7
        assert handler.get_metrics()["approval_rate"] == 70.0

    async def test_rejection_rate_calculation(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)
        handler._metrics["total_reviews"] = 10
        handler._metrics["rejected_reviews"] = 2
        assert handler.get_metrics()["rejection_rate"] == 20.0

    async def test_escalation_rate_calculation(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)
        handler._metrics["total_reviews"] = 10
        handler._metrics["escalated_reviews"] = 1
        assert handler.get_metrics()["escalation_rate"] == 10.0

    async def test_average_iterations_calculation(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)
        handler._metrics["total_reviews"] = 10
        handler._metrics["total_iterations"] = 25
        assert handler.get_metrics()["avg_iterations_per_review"] == 2.5

    async def test_average_iterations_with_zero_reviews(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)
        assert handler.get_metrics()["avg_iterations_per_review"] == 0.0


@pytest.mark.asyncio
class TestReviewEventHandlerActiveReviews:
    """Test ReviewEventHandler active review tracking."""

    async def test_get_active_reviews_empty(self):
        mock_service = Mock(spec=ReviewService)
        assert ReviewEventHandler(mock_service).get_active_reviews() == {}

    async def test_get_active_reviews_populated(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)
        handler._active_reviews["review-1"] = "wf-1"
        handler._active_reviews["review-2"] = "wf-2"
        active = handler.get_active_reviews()
        assert len(active) == 2
        assert "review-1" in active

    async def test_get_active_reviews_returns_copy(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)
        handler._active_reviews["review-1"] = "wf-1"
        active = handler.get_active_reviews()
        active["review-2"] = "wf-2"
        assert len(handler._active_reviews) == 1


@pytest.mark.asyncio
class TestReviewEventHandlerWorkflow:
    """Test ReviewEventHandler in realistic workflows."""

    async def test_complete_review_approval_workflow(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        await handler.handle(_created("review-1", "wf-1"))
        await handler.handle(_iter_started("review-1", 1))
        await handler.handle(_feedback("review-1", 1, "APPROVE"))
        await handler.handle(_approved("review-1", total_iterations=1))

        metrics = handler.get_metrics()
        assert metrics["approved_reviews"] == 1
        assert metrics["active_reviews"] == 0
        assert metrics["approval_rate"] == 100.0
        assert metrics["avg_iterations_per_review"] == 1.0

    async def test_multiple_concurrent_reviews(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        for i in range(3):
            await handler.handle(_created(f"review-{i}", f"wf-{i}"))

        assert handler._metrics["total_reviews"] == 3
        assert handler._metrics["active_reviews"] == 3

        for i in range(2):
            await handler.handle(_approved(f"review-{i}", total_iterations=1))

        assert handler._metrics["approved_reviews"] == 2

        await handler.handle(_rejected("review-2", final_iteration=2, reason="Quality issues"))

        metrics = handler.get_metrics()
        assert metrics["approved_reviews"] == 2
        assert metrics["rejected_reviews"] == 1

    async def test_mixed_outcomes_metrics(self):
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        outcomes = [
            ("review-1", "approved"),
            ("review-2", "approved"),
            ("review-3", "approved"),
            ("review-4", "approved"),
            ("review-5", "approved"),
            ("review-6", "approved"),
            ("review-7", "rejected"),
            ("review-8", "rejected"),
            ("review-9", "rejected"),
            ("review-10", "escalated"),
        ]

        iterations = 0
        for review_id, outcome in outcomes:
            await handler.handle(_created(review_id, f"wf-{review_id}"))
            iter_count = 1 if outcome == "approved" else 2 if outcome == "rejected" else 1
            for i in range(1, iter_count + 1):
                await handler.handle(_iter_started(review_id, i, exec_id=f"exec-{i}"))
                iterations += 1

            if outcome == "approved":
                await handler.handle(_approved(review_id, total_iterations=iter_count))
            elif outcome == "rejected":
                await handler.handle(_rejected(review_id, final_iteration=iter_count, reason="Quality issues"))
            else:
                await handler.handle(_escalated(review_id, "MAX_ITERATIONS"))

        metrics = handler.get_metrics()
        assert metrics["total_reviews"] == 10
        assert metrics["approved_reviews"] == 6
        assert metrics["rejected_reviews"] == 3
        assert metrics["escalated_reviews"] == 1
        assert metrics["total_iterations"] == iterations
        assert metrics["approval_rate"] == 60.0
        assert metrics["rejection_rate"] == 30.0
        assert metrics["escalation_rate"] == 10.0
