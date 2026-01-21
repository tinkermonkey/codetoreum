"""Unit tests for Review Event Handler.

Tests the review event handler with mock review service to verify:
- Review cycle lifecycle tracking (created, iteration started, feedback submitted, approved, rejected, escalated)
- Approval/rejection/escalation metrics
- Active review tracking
- Iteration counting
- Proper logging and error handling
"""

from unittest.mock import MagicMock

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


@pytest.fixture
def mock_review_service():
    """Create mock review service."""
    service = MagicMock(spec=ReviewService)
    return service


@pytest.fixture
def handler(mock_review_service):
    """Create review event handler."""
    return ReviewEventHandler(mock_review_service)


class TestReviewEventHandlerInitialization:
    """Tests for handler initialization and metrics setup."""

    def test_handler_initialization(self, handler):
        """Test handler initializes with zero metrics."""
        # Assert
        assert handler._metrics["total_reviews"] == 0
        assert handler._metrics["active_reviews"] == 0
        assert handler._metrics["approved_reviews"] == 0
        assert handler._metrics["rejected_reviews"] == 0
        assert handler._metrics["escalated_reviews"] == 0
        assert handler._metrics["total_iterations"] == 0
        assert len(handler._active_reviews) == 0

    def test_get_metrics_initial(self, handler):
        """Test get_metrics returns initialized metrics."""
        # Act
        metrics = handler.get_metrics()

        # Assert
        assert metrics["total_reviews"] == 0
        assert metrics["approved_reviews"] == 0
        assert metrics["rejected_reviews"] == 0
        assert metrics["escalated_reviews"] == 0
        assert metrics["total_iterations"] == 0

    def test_get_active_reviews_initial(self, handler):
        """Test get_active_reviews returns empty dict initially."""
        # Act
        active = handler.get_active_reviews()

        # Assert
        assert active == {}
        assert isinstance(active, dict)


class TestReviewCycleCreatedEvent:
    """Tests for ReviewCycleCreated event handling."""

    async def test_handle_review_cycle_created(self, handler):
        """Test handling of ReviewCycleCreated event."""
        # Arrange
        event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )

        # Act
        await handler.handle(event)

        # Assert
        assert handler._metrics["total_reviews"] == 1
        assert handler._metrics["active_reviews"] == 1
        assert "review-123" in handler._active_reviews
        assert handler._active_reviews["review-123"] == "wf-789"

    async def test_handle_multiple_review_cycles_created(self, handler):
        """Test handling multiple ReviewCycleCreated events."""
        # Arrange
        events = [
            ReviewCycleCreated(
                aggregate_id=f"review-{i}",
                payload={
                    "workflow_id": f"wf-{i}",
                    "work_item_id": f"wi-{i}",
                    "required_approvers": 1,
                },
            )
            for i in range(3)
        ]

        # Act
        for event in events:
            await handler.handle(event)

        # Assert
        assert handler._metrics["total_reviews"] == 3
        assert handler._metrics["active_reviews"] == 3
        assert len(handler._active_reviews) == 3


class TestReviewIterationStartedEvent:
    """Tests for ReviewIterationStarted event handling."""

    async def test_handle_review_iteration_started(self, handler):
        """Test handling of ReviewIterationStarted event."""
        # Arrange - Create review first
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )
        iteration_event = ReviewIterationStarted(
            aggregate_id="review-123",
            payload={
                "iteration_number": 1,
                "reviewer_names": ["reviewer1"],
            },
        )

        # Act
        await handler.handle(create_event)
        await handler.handle(iteration_event)

        # Assert
        assert handler._metrics["total_iterations"] == 1

    async def test_multiple_iterations_same_review(self, handler):
        """Test multiple iterations for the same review."""
        # Arrange
        review_id = "review-123"
        create_event = ReviewCycleCreated(
            aggregate_id=review_id,
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )
        await handler.handle(create_event)

        # Act - Start 3 iterations
        for i in range(1, 4):
            iteration = ReviewIterationStarted(
                aggregate_id=review_id,
                payload={
                    "iteration_number": i,
                    "reviewer_names": [f"reviewer{i}"],
                },
            )
            await handler.handle(iteration)

        # Assert
        assert handler._metrics["total_iterations"] == 3
        assert handler._metrics["active_reviews"] == 1


class TestReviewFeedbackSubmittedEvent:
    """Tests for ReviewFeedbackSubmitted event handling."""

    async def test_handle_review_feedback_submitted(self, handler):
        """Test handling of ReviewFeedbackSubmitted event."""
        # Arrange
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )
        feedback_event = ReviewFeedbackSubmitted(
            aggregate_id="review-123",
            payload={
                "reviewer_id": "reviewer-1",
                "feedback_text": "Looks good!",
                "suggestions_count": 2,
            },
        )

        # Act
        await handler.handle(create_event)
        await handler.handle(feedback_event)

        # Assert - Review should still be active
        assert handler._metrics["active_reviews"] == 1
        assert "review-123" in handler._active_reviews

    async def test_feedback_submitted_preserves_active_status(self, handler):
        """Test that feedback submission doesn't change active status."""
        # Arrange
        create = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )
        feedback = ReviewFeedbackSubmitted(
            aggregate_id="review-123",
            payload={
                "reviewer_id": "reviewer-1",
                "feedback_text": "Need changes",
                "suggestions_count": 5,
            },
        )

        # Act
        await handler.handle(create)
        active_before = handler._metrics["active_reviews"]
        await handler.handle(feedback)
        active_after = handler._metrics["active_reviews"]

        # Assert
        assert active_before == active_after
        assert active_after == 1


class TestReviewCycleApprovedEvent:
    """Tests for ReviewCycleApproved event handling."""

    async def test_handle_review_cycle_approved(self, handler):
        """Test handling of ReviewCycleApproved event."""
        # Arrange
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )
        approve_event = ReviewCycleApproved(
            aggregate_id="review-123",
            payload={
                "approver_id": "reviewer-1",
                "approved_at": "2024-01-01T12:00:00Z",
            },
        )

        # Act
        await handler.handle(create_event)
        await handler.handle(approve_event)

        # Assert
        assert handler._metrics["approved_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-123" not in handler._active_reviews

    async def test_approval_removes_from_active_tracking(self, handler):
        """Test that approval removes review from active tracking."""
        # Arrange
        review_id = "review-123"
        create = ReviewCycleCreated(
            aggregate_id=review_id,
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )
        approve = ReviewCycleApproved(
            aggregate_id=review_id,
            payload={
                "approver_id": "reviewer-1",
                "approved_at": "2024-01-01T12:00:00Z",
            },
        )

        # Act
        await handler.handle(create)
        assert review_id in handler._active_reviews
        await handler.handle(approve)

        # Assert
        assert review_id not in handler._active_reviews
        assert handler._metrics["approved_reviews"] == 1


class TestReviewCycleRejectedEvent:
    """Tests for ReviewCycleRejected event handling."""

    async def test_handle_review_cycle_rejected(self, handler):
        """Test handling of ReviewCycleRejected event."""
        # Arrange
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )
        reject_event = ReviewCycleRejected(
            aggregate_id="review-123",
            payload={
                "reviewer_id": "reviewer-1",
                "rejection_reason": "Needs more testing",
                "rejected_at": "2024-01-01T12:00:00Z",
            },
        )

        # Act
        await handler.handle(create_event)
        await handler.handle(reject_event)

        # Assert
        assert handler._metrics["rejected_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-123" not in handler._active_reviews

    async def test_rejection_removes_from_active_tracking(self, handler):
        """Test that rejection removes review from active tracking."""
        # Arrange
        review_id = "review-456"
        create = ReviewCycleCreated(
            aggregate_id=review_id,
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )
        reject = ReviewCycleRejected(
            aggregate_id=review_id,
            payload={
                "reviewer_id": "reviewer-1",
                "rejection_reason": "Needs more testing",
                "rejected_at": "2024-01-01T12:00:00Z",
            },
        )

        # Act
        await handler.handle(create)
        assert review_id in handler._active_reviews
        await handler.handle(reject)

        # Assert
        assert review_id not in handler._active_reviews
        assert handler._metrics["rejected_reviews"] == 1


class TestReviewCycleEscalatedEvent:
    """Tests for ReviewCycleEscalated event handling."""

    async def test_handle_review_cycle_escalated(self, handler):
        """Test handling of ReviewCycleEscalated event."""
        # Arrange
        create_event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )
        escalate_event = ReviewCycleEscalated(
            aggregate_id="review-123",
            payload={
                "escalation_reason": "Multiple rejections",
                "escalated_to": "tech-lead",
                "escalated_at": "2024-01-01T12:00:00Z",
            },
        )

        # Act
        await handler.handle(create_event)
        await handler.handle(escalate_event)

        # Assert
        assert handler._metrics["escalated_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-123" not in handler._active_reviews

    async def test_escalation_removes_from_active_tracking(self, handler):
        """Test that escalation removes review from active tracking."""
        # Arrange
        review_id = "review-789"
        create = ReviewCycleCreated(
            aggregate_id=review_id,
            payload={
                "workflow_id": "wf-789",
                "work_item_id": "wi-456",
                "required_approvers": 1,
            },
        )
        escalate = ReviewCycleEscalated(
            aggregate_id=review_id,
            payload={
                "escalation_reason": "Unable to reach consensus",
                "escalated_to": "manager",
                "escalated_at": "2024-01-01T12:00:00Z",
            },
        )

        # Act
        await handler.handle(create)
        assert review_id in handler._active_reviews
        await handler.handle(escalate)

        # Assert
        assert review_id not in handler._active_reviews
        assert handler._metrics["escalated_reviews"] == 1


class TestReviewMetricsTracking:
    """Tests for comprehensive review metrics tracking."""

    async def test_mixed_review_outcomes(self, handler):
        """Test tracking mix of approved, rejected, and escalated reviews."""
        # Arrange - Create 5 reviews with different outcomes
        for i in range(5):
            review_id = f"review-{i}"
            create = ReviewCycleCreated(
                aggregate_id=review_id,
                payload={
                    "workflow_id": f"wf-{i}",
                    "work_item_id": f"wi-{i}",
                    "required_approvers": 1,
                },
            )
            await handler.handle(create)

            # Outcome varies: approve, reject, escalate, approve, reject
            if i % 3 == 0 or i == 3:
                event = ReviewCycleApproved(
                    aggregate_id=review_id,
                    payload={"approver_id": "reviewer", "approved_at": "2024-01-01T12:00:00Z"},
                )
            elif i % 3 == 1:
                event = ReviewCycleRejected(
                    aggregate_id=review_id,
                    payload={
                        "reviewer_id": "reviewer",
                        "rejection_reason": "Needs work",
                        "rejected_at": "2024-01-01T12:00:00Z",
                    },
                )
            else:
                event = ReviewCycleEscalated(
                    aggregate_id=review_id,
                    payload={
                        "escalation_reason": "Conflict",
                        "escalated_to": "manager",
                        "escalated_at": "2024-01-01T12:00:00Z",
                    },
                )
            await handler.handle(event)

        # Assert
        metrics = handler.get_metrics()
        assert metrics["total_reviews"] == 5
        assert metrics["active_reviews"] == 0
        assert metrics["approved_reviews"] == 2
        assert metrics["rejected_reviews"] == 2
        assert metrics["escalated_reviews"] == 1

    async def test_approval_rate_calculation(self, handler):
        """Test calculation of approval rate."""
        # Arrange - Create reviews with specific outcomes
        outcomes = [
            ("review-1", ReviewCycleApproved(aggregate_id="review-1", payload={"approver_id": "r1", "approved_at": "2024-01-01T12:00:00Z"})),
            ("review-2", ReviewCycleApproved(aggregate_id="review-2", payload={"approver_id": "r1", "approved_at": "2024-01-01T12:00:00Z"})),
            ("review-3", ReviewCycleRejected(aggregate_id="review-3", payload={"reviewer_id": "r1", "rejection_reason": "No", "rejected_at": "2024-01-01T12:00:00Z"})),
        ]

        # Act
        for review_id, outcome in outcomes:
            create = ReviewCycleCreated(
                aggregate_id=review_id,
                payload={"workflow_id": f"wf-{review_id}", "work_item_id": f"wi-{review_id}", "required_approvers": 1},
            )
            await handler.handle(create)
            await handler.handle(outcome)

        # Assert
        metrics = handler.get_metrics()
        approval_rate = metrics["approved_reviews"] / metrics["total_reviews"] * 100
        assert approval_rate == pytest.approx(66.66, abs=0.1)


class TestReviewEventHandlerErrors:
    """Tests for error handling in event handler."""

    async def test_handle_unexpected_event_type(self, handler):
        """Test handling of unexpected event type."""
        # Arrange - Create a different event type
        from codetoreum.domain.events import WorkItemCreated

        event = WorkItemCreated(
            aggregate_id="wi-123",
            payload={"title": "Test"},
        )

        # Act - Should not raise, just log warning
        await handler.handle(event)

        # Assert - Should not change any metrics
        assert handler._metrics["total_reviews"] == 0

    async def test_handle_all_event_types(self, handler):
        """Test that handler can process all supported event types."""
        # Arrange
        review_id = "review-123"
        events = [
            ReviewCycleCreated(
                aggregate_id=review_id,
                payload={
                    "workflow_id": "wf-789",
                    "work_item_id": "wi-456",
                    "required_approvers": 1,
                },
            ),
            ReviewIterationStarted(
                aggregate_id=review_id,
                payload={"iteration_number": 1, "reviewer_names": ["reviewer1"]},
            ),
            ReviewFeedbackSubmitted(
                aggregate_id=review_id,
                payload={
                    "reviewer_id": "reviewer-1",
                    "feedback_text": "Good",
                    "suggestions_count": 1,
                },
            ),
        ]

        # Act - Should handle all without error
        for event in events:
            await handler.handle(event)

        # Assert
        assert handler._metrics["total_reviews"] == 1
        assert handler._metrics["total_iterations"] == 1


class TestReviewEventHandlerConcurrency:
    """Tests for concurrent review handling."""

    async def test_concurrent_reviews_tracked_independently(self, handler):
        """Test multiple concurrent reviews are tracked independently."""
        # Arrange - Create 3 concurrent reviews
        review_ids = ["review-a", "review-b", "review-c"]
        for review_id in review_ids:
            create = ReviewCycleCreated(
                aggregate_id=review_id,
                payload={
                    "workflow_id": f"wf-{review_id}",
                    "work_item_id": f"wi-{review_id}",
                    "required_approvers": 1,
                },
            )
            await handler.handle(create)

        # Act - Approve first review
        approve = ReviewCycleApproved(
            aggregate_id="review-a",
            payload={"approver_id": "reviewer", "approved_at": "2024-01-01T12:00:00Z"},
        )
        await handler.handle(approve)

        # Assert
        assert handler._metrics["active_reviews"] == 2
        assert "review-a" not in handler._active_reviews
        assert "review-b" in handler._active_reviews
        assert "review-c" in handler._active_reviews
