"""Unit tests for ReviewEventHandler."""

from unittest.mock import AsyncMock, Mock

import pytest

from codetoreum.application.event_handlers.review_event_handler import (
    ReviewEventHandler,
)
from codetoreum.application.review_service import ReviewService
from codetoreum.domain.events import (
    ReviewCycleApproved,
    ReviewCycleCreated,
    ReviewCycleEscalated,
    ReviewCycleRejected,
    ReviewFeedbackSubmitted,
    ReviewIterationStarted,
)


class TestReviewEventHandlerInitialization:
    """Test ReviewEventHandler initialization."""

    def test_handler_initialization(self):
        """Test handler initializes with review service."""
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
        # Verify service mock is not called during initialization
        mock_service.assert_not_called()

    def test_handler_has_event_types(self):
        """Test handler is decorated with correct event types."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Check that event_handler decorator adds get_event_types method
        assert hasattr(handler, "get_event_types")
        event_types = handler.get_event_types()
        assert event_types == [
            "ReviewCycleCreated",
            "ReviewIterationStarted",
            "ReviewFeedbackSubmitted",
            "ReviewCycleApproved",
            "ReviewCycleRejected",
            "ReviewCycleEscalated",
        ]


@pytest.mark.asyncio
class TestReviewEventHandlerMethods:
    """Test ReviewEventHandler event handling methods."""

    async def test_handle_review_cycle_created(self):
        """Test handling ReviewCycleCreated event."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        event = ReviewCycleCreated(
            aggregate_id="review-1",
            payload={
                "workflow_id": "wf-1",
                "stage_name": "Review",
                "maker_agent_id": "agent-1",
                "reviewer_agent_id": "agent-2",
                "max_iterations": 3,
            },
        )

        await handler.handle(event)

        assert handler._metrics["total_reviews"] == 1
        assert handler._metrics["active_reviews"] == 1
        assert "review-1" in handler._active_reviews
        assert handler._active_reviews["review-1"] == "wf-1"

    async def test_handle_review_iteration_started(self):
        """Test handling ReviewIterationStarted event."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._metrics["total_reviews"] = 1

        event = ReviewIterationStarted(
            aggregate_id="review-1",
            payload={
                "iteration_number": 1,
                "maker_execution_id": "exec-1",
            },
        )

        await handler.handle(event)

        assert handler._metrics["total_iterations"] == 1

    async def test_handle_review_feedback_submitted(self):
        """Test handling ReviewFeedbackSubmitted event."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        event = ReviewFeedbackSubmitted(
            aggregate_id="review-1",
            payload={
                "iteration_number": 1,
                "decision": "REQUEST_CHANGES",
                "issues_found": ["bug-1", "bug-2"],
                "feedback": "Fix these issues",
            },
        )

        await handler.handle(event)

        # Feedback submission doesn't change metrics directly
        assert handler._metrics["total_reviews"] == 0

    async def test_handle_review_cycle_approved(self):
        """Test handling ReviewCycleApproved event."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Set up initial state
        handler._metrics["total_reviews"] = 1
        handler._metrics["active_reviews"] = 1
        handler._active_reviews["review-1"] = "wf-1"

        event = ReviewCycleApproved(
            aggregate_id="review-1",
            payload={"total_iterations": 2},
        )

        await handler.handle(event)

        assert handler._metrics["approved_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-1" not in handler._active_reviews

    async def test_handle_review_cycle_rejected(self):
        """Test handling ReviewCycleRejected event."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Set up initial state
        handler._metrics["total_reviews"] = 1
        handler._metrics["active_reviews"] = 1
        handler._active_reviews["review-1"] = "wf-1"

        event = ReviewCycleRejected(
            aggregate_id="review-1",
            payload={
                "final_iteration": 2,
                "rejection_reason": "Code quality not met",
            },
        )

        await handler.handle(event)

        assert handler._metrics["rejected_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-1" not in handler._active_reviews

    async def test_handle_review_cycle_escalated(self):
        """Test handling ReviewCycleEscalated event."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Set up initial state
        handler._metrics["total_reviews"] = 1
        handler._metrics["active_reviews"] = 1
        handler._active_reviews["review-1"] = "wf-1"

        event = ReviewCycleEscalated(
            aggregate_id="review-1",
            payload={"reason": "Max iterations reached"},
        )

        await handler.handle(event)

        assert handler._metrics["escalated_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-1" not in handler._active_reviews

    async def test_handle_unexpected_event(self):
        """Test handling unexpected event type."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Create a mock event with unexpected type
        event = Mock()
        event.event_type = "UnexpectedEvent"

        # Should not raise, just log warning
        await handler.handle(event)

        assert handler._metrics["total_reviews"] == 0


@pytest.mark.asyncio
class TestReviewEventHandlerMetrics:
    """Test ReviewEventHandler metrics calculations."""

    async def test_get_metrics_initial_state(self):
        """Test get_metrics returns correct initial state."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        metrics = handler.get_metrics()

        assert metrics["total_reviews"] == 0
        assert metrics["active_reviews"] == 0
        assert metrics["approved_reviews"] == 0
        assert metrics["rejected_reviews"] == 0
        assert metrics["escalated_reviews"] == 0
        assert metrics["total_iterations"] == 0
        assert metrics["approval_rate"] == 0.0
        assert metrics["rejection_rate"] == 0.0
        assert metrics["escalation_rate"] == 0.0
        assert metrics["avg_iterations_per_review"] == 0.0

    async def test_approval_rate_calculation(self):
        """Test approval rate calculation."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._metrics["total_reviews"] = 10
        handler._metrics["approved_reviews"] = 7

        metrics = handler.get_metrics()
        assert metrics["approval_rate"] == 70.0

    async def test_rejection_rate_calculation(self):
        """Test rejection rate calculation."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._metrics["total_reviews"] = 10
        handler._metrics["rejected_reviews"] = 2

        metrics = handler.get_metrics()
        assert metrics["rejection_rate"] == 20.0

    async def test_escalation_rate_calculation(self):
        """Test escalation rate calculation."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._metrics["total_reviews"] = 10
        handler._metrics["escalated_reviews"] = 1

        metrics = handler.get_metrics()
        assert metrics["escalation_rate"] == 10.0

    async def test_average_iterations_calculation(self):
        """Test average iterations per review calculation."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._metrics["total_reviews"] = 10
        handler._metrics["total_iterations"] = 25

        metrics = handler.get_metrics()
        assert metrics["avg_iterations_per_review"] == 2.5

    async def test_average_iterations_with_zero_reviews(self):
        """Test average iterations when no reviews have occurred."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._metrics["total_reviews"] = 0
        handler._metrics["total_iterations"] = 0

        metrics = handler.get_metrics()
        assert metrics["avg_iterations_per_review"] == 0.0

    async def test_metrics_with_zero_total_reviews(self):
        """Test metrics when no reviews have occurred."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Explicitly set total_reviews to 0
        handler._metrics["total_reviews"] = 0

        metrics = handler.get_metrics()
        assert metrics["approval_rate"] == 0.0
        assert metrics["rejection_rate"] == 0.0
        assert metrics["escalation_rate"] == 0.0


@pytest.mark.asyncio
class TestReviewEventHandlerActiveReviews:
    """Test ReviewEventHandler active review tracking."""

    async def test_get_active_reviews_empty(self):
        """Test get_active_reviews returns empty dict initially."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        active = handler.get_active_reviews()

        assert active == {}

    async def test_get_active_reviews_populated(self):
        """Test get_active_reviews returns tracking data."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._active_reviews["review-1"] = "wf-1"
        handler._active_reviews["review-2"] = "wf-2"

        active = handler.get_active_reviews()

        assert len(active) == 2
        assert "review-1" in active
        assert "review-2" in active

    async def test_get_active_reviews_returns_copy(self):
        """Test get_active_reviews returns a copy, not reference."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        handler._active_reviews["review-1"] = "wf-1"

        active = handler.get_active_reviews()
        active["review-2"] = "wf-2"

        # Original should not be modified
        assert len(handler._active_reviews) == 1
        assert "review-2" not in handler._active_reviews


@pytest.mark.asyncio
class TestReviewEventHandlerWorkflow:
    """Test ReviewEventHandler in realistic workflows."""

    async def test_complete_review_approval_workflow(self):
        """Test a complete review approval workflow."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Create review cycle
        create_event = ReviewCycleCreated(
            aggregate_id="review-1",
            payload={
                "workflow_id": "wf-1",
                "stage_name": "Review",
                "maker_agent_id": "agent-1",
                "reviewer_agent_id": "agent-2",
                "max_iterations": 3,
            },
        )
        await handler.handle(create_event)

        assert handler._metrics["total_reviews"] == 1
        assert handler._metrics["active_reviews"] == 1

        # Start iteration
        iter_event = ReviewIterationStarted(
            aggregate_id="review-1",
            payload={"iteration_number": 1, "maker_execution_id": "exec-1"},
        )
        await handler.handle(iter_event)

        assert handler._metrics["total_iterations"] == 1

        # Submit feedback
        feedback_event = ReviewFeedbackSubmitted(
            aggregate_id="review-1",
            payload={
                "iteration_number": 1,
                "decision": "APPROVE",
                "issues_found": [],
                "feedback": "Looks good",
            },
        )
        await handler.handle(feedback_event)

        # Approve cycle
        approve_event = ReviewCycleApproved(
            aggregate_id="review-1",
            payload={"total_iterations": 1},
        )
        await handler.handle(approve_event)

        metrics = handler.get_metrics()
        assert metrics["approved_reviews"] == 1
        assert metrics["active_reviews"] == 0
        assert metrics["approval_rate"] == 100.0
        assert metrics["avg_iterations_per_review"] == 1.0

    async def test_multiple_concurrent_reviews(self):
        """Test multiple concurrent reviews."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Create multiple reviews
        for i in range(3):
            create_event = ReviewCycleCreated(
                aggregate_id=f"review-{i}",
                payload={"workflow_id": f"wf-{i}", "max_iterations": 3},
            )
            await handler.handle(create_event)

        assert handler._metrics["total_reviews"] == 3
        assert handler._metrics["active_reviews"] == 3
        assert len(handler.get_active_reviews()) == 3

        # Approve first two reviews
        for i in range(2):
            approve_event = ReviewCycleApproved(
                aggregate_id=f"review-{i}",
                payload={"total_iterations": 1},
            )
            await handler.handle(approve_event)

        assert handler._metrics["approved_reviews"] == 2
        assert handler._metrics["active_reviews"] == 1

        # Reject third review
        reject_event = ReviewCycleRejected(
            aggregate_id="review-2",
            payload={"final_iteration": 2, "rejection_reason": "Quality issues"},
        )
        await handler.handle(reject_event)

        metrics = handler.get_metrics()
        assert metrics["approved_reviews"] == 2
        assert metrics["rejected_reviews"] == 1
        assert metrics["approval_rate"] == 66.66666666666666  # 2/3

    async def test_review_rejection_workflow(self):
        """Test review rejection workflow."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Create review
        create_event = ReviewCycleCreated(
            aggregate_id="review-1",
            payload={"workflow_id": "wf-1", "max_iterations": 3},
        )
        await handler.handle(create_event)

        # Start iteration 1
        iter1_event = ReviewIterationStarted(
            aggregate_id="review-1",
            payload={"iteration_number": 1},
        )
        await handler.handle(iter1_event)

        # Reject with issues
        reject_event = ReviewCycleRejected(
            aggregate_id="review-1",
            payload={
                "final_iteration": 1,
                "rejection_reason": "Code quality not met",
            },
        )
        await handler.handle(reject_event)

        assert handler._metrics["rejected_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert handler.get_metrics()["rejection_rate"] == 100.0

    async def test_review_escalation_workflow(self):
        """Test review escalation workflow."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Create review
        create_event = ReviewCycleCreated(
            aggregate_id="review-1",
            payload={"workflow_id": "wf-1", "max_iterations": 2},
        )
        await handler.handle(create_event)

        # Start and reject iterations until escalation
        for i in range(1, 3):
            iter_event = ReviewIterationStarted(
                aggregate_id="review-1",
                payload={"iteration_number": i},
            )
            await handler.handle(iter_event)

            if i < 3:
                reject_event = ReviewCycleRejected(
                    aggregate_id="review-1",
                    payload={
                        "final_iteration": i,
                        "rejection_reason": "Still has issues",
                    },
                )
                await handler.handle(reject_event)

        # Create new review and escalate immediately
        create_event = ReviewCycleCreated(
            aggregate_id="review-2",
            payload={"workflow_id": "wf-2", "max_iterations": 3},
        )
        await handler.handle(create_event)

        escalate_event = ReviewCycleEscalated(
            aggregate_id="review-2",
            payload={"reason": "Human review required"},
        )
        await handler.handle(escalate_event)

        metrics = handler.get_metrics()
        assert metrics["escalated_reviews"] == 1

    async def test_mixed_review_outcomes(self):
        """Test metrics with mixed review outcomes."""
        mock_service = Mock(spec=ReviewService)
        handler = ReviewEventHandler(mock_service)

        # Create 10 reviews with mixed outcomes
        # 6 approved, 3 rejected, 1 escalated
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
            # Create review
            create_event = ReviewCycleCreated(
                aggregate_id=review_id,
                payload={"workflow_id": f"wf-{review_id}"},
            )
            await handler.handle(create_event)

            # Add iterations based on outcome
            if outcome == "approved":
                iter_count = 1
            elif outcome == "rejected":
                iter_count = 2
            else:  # escalated
                iter_count = 1

            for i in range(1, iter_count + 1):
                iter_event = ReviewIterationStarted(
                    aggregate_id=review_id,
                    payload={"iteration_number": i},
                )
                await handler.handle(iter_event)
                iterations += 1

            # Complete with outcome
            if outcome == "approved":
                complete_event = ReviewCycleApproved(
                    aggregate_id=review_id,
                    payload={"total_iterations": iter_count},
                )
            elif outcome == "rejected":
                complete_event = ReviewCycleRejected(
                    aggregate_id=review_id,
                    payload={
                        "final_iteration": iter_count,
                        "rejection_reason": "Quality issues",
                    },
                )
            else:  # escalated
                complete_event = ReviewCycleEscalated(
                    aggregate_id=review_id,
                    payload={"reason": "Human review required"},
                )

            await handler.handle(complete_event)

        metrics = handler.get_metrics()
        assert metrics["total_reviews"] == 10
        assert metrics["approved_reviews"] == 6
        assert metrics["rejected_reviews"] == 3
        assert metrics["escalated_reviews"] == 1
        assert metrics["total_iterations"] == iterations
        assert metrics["approval_rate"] == 60.0
        assert metrics["rejection_rate"] == 30.0
        assert metrics["escalation_rate"] == 10.0
