"""Unit tests for ReviewEventHandler."""

from unittest.mock import Mock

import pytest

from codetoreum.application.event_handlers.review_event_handler import (
    ReviewEventHandler,
)
from codetoreum.domain.events import (
    ReviewCycleApproved,
    ReviewCycleCreated,
    ReviewCycleEscalated,
    ReviewCycleRejected,
    ReviewFeedbackSubmitted,
    ReviewIterationStarted,
)


class MockReviewService:
    """Mock review service for testing."""

    def __init__(self):
        """Initialize mock."""
        self.created_reviews = []
        self.started_iterations = []
        self.submitted_feedback = []
        self.approved_reviews = []
        self.rejected_reviews = []
        self.escalated_reviews = []


class TestReviewEventHandler:
    """Tests for ReviewEventHandler."""

    def test_initialization(self):
        """Test handler initialization."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        assert handler.review_service is service
        assert handler._metrics["total_reviews"] == 0
        assert handler._metrics["active_reviews"] == 0
        assert handler._metrics["approved_reviews"] == 0
        assert handler._metrics["rejected_reviews"] == 0
        assert handler._metrics["escalated_reviews"] == 0
        assert handler._metrics["total_iterations"] == 0
        assert len(handler._active_reviews) == 0

    @pytest.mark.asyncio
    async def test_handle_review_cycle_created(self):
        """Test handling ReviewCycleCreated event."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload={
                "work_item_id": "work-123",
                "workflow_id": "workflow-123",
                "stage_name": "review",
                "execution_id": "exec-123",
                "max_iterations": 3,
                "review_type": "automated",
            },
        )

        await handler.handle(event)

        assert handler._metrics["total_reviews"] == 1
        assert handler._metrics["active_reviews"] == 1
        assert "review-123" in handler._active_reviews

    @pytest.mark.asyncio
    async def test_handle_review_iteration_started(self):
        """Test handling ReviewIterationStarted event."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        # Create review first
        await handler.handle(
            ReviewCycleCreated(
                aggregate_id="review-123",
                payload={
                    "work_item_id": "work-123",
                    "workflow_id": "workflow-123",
                    "stage_name": "review",
                    "execution_id": "exec-123",
                    "max_iterations": 3,
                    "review_type": "automated",
                },
            )
        )

        # Start iteration
        event = ReviewIterationStarted(
            aggregate_id="review-123",
            payload={
                "iteration_number": 1,
                "started_at": "2025-01-14T10:30:00+00:00",
                "reviewer_agent_id": "agent-456",
            },
        )

        await handler.handle(event)

        assert handler._metrics["total_iterations"] == 1

    @pytest.mark.asyncio
    async def test_handle_review_feedback_submitted(self):
        """Test handling ReviewFeedbackSubmitted event."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        # Create and start review
        await handler.handle(
            ReviewCycleCreated(
                aggregate_id="review-123",
                payload={
                    "work_item_id": "work-123",
                    "workflow_id": "workflow-123",
                    "stage_name": "review",
                    "execution_id": "exec-123",
                    "max_iterations": 3,
                    "review_type": "automated",
                },
            )
        )

        await handler.handle(
            ReviewIterationStarted(
                aggregate_id="review-123",
                payload={
                    "iteration_number": 1,
                    "started_at": "2025-01-14T10:30:00+00:00",
                    "reviewer_agent_id": "agent-456",
                },
            )
        )

        # Submit feedback
        event = ReviewFeedbackSubmitted(
            aggregate_id="review-123",
            payload={
                "iteration_number": 1,
                "submitted_at": "2025-01-14T10:35:00+00:00",
                "feedback": "Please fix the error handling",
                "decision": "needs_changes",
                "reviewer_id": "agent-456",
                "issues_found": [{"type": "error", "message": "Missing error handling"}],
            },
        )

        await handler.handle(event)

        # Metrics should track this
        assert handler._metrics["active_reviews"] == 1

    @pytest.mark.asyncio
    async def test_handle_review_cycle_approved(self):
        """Test handling ReviewCycleApproved event."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        # Create review
        await handler.handle(
            ReviewCycleCreated(
                aggregate_id="review-123",
                payload={
                    "work_item_id": "work-123",
                    "workflow_id": "workflow-123",
                    "stage_name": "review",
                    "execution_id": "exec-123",
                    "max_iterations": 3,
                    "review_type": "automated",
                },
            )
        )

        # Approve
        event = ReviewCycleApproved(
            aggregate_id="review-123",
            payload={
                "approved_at": "2025-01-14T10:40:00+00:00",
                "final_iteration": 1,
                "reviewer_id": "agent-456",
                "approval_notes": "All issues resolved",
            },
        )

        await handler.handle(event)

        assert handler._metrics["approved_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-123" not in handler._active_reviews

    @pytest.mark.asyncio
    async def test_handle_review_cycle_rejected(self):
        """Test handling ReviewCycleRejected event."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        # Create review
        await handler.handle(
            ReviewCycleCreated(
                aggregate_id="review-123",
                payload={
                    "work_item_id": "work-123",
                    "workflow_id": "workflow-123",
                    "stage_name": "review",
                    "execution_id": "exec-123",
                    "max_iterations": 3,
                    "review_type": "automated",
                },
            )
        )

        # Reject
        event = ReviewCycleRejected(
            aggregate_id="review-123",
            payload={
                "rejected_at": "2025-01-14T10:40:00+00:00",
                "reason": "Critical issues found",
                "iteration_number": 2,
                "issues": [{"type": "critical", "message": "Security vulnerability"}],
            },
        )

        await handler.handle(event)

        assert handler._metrics["rejected_reviews"] == 1

    @pytest.mark.asyncio
    async def test_handle_review_cycle_escalated(self):
        """Test handling ReviewCycleEscalated event."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        # Create review
        await handler.handle(
            ReviewCycleCreated(
                aggregate_id="review-123",
                payload={
                    "work_item_id": "work-123",
                    "workflow_id": "workflow-123",
                    "stage_name": "review",
                    "execution_id": "exec-123",
                    "max_iterations": 3,
                    "review_type": "automated",
                },
            )
        )

        # Escalate
        event = ReviewCycleEscalated(
            aggregate_id="review-123",
            payload={
                "escalated_at": "2025-01-14T10:45:00+00:00",
                "reason": "Maximum iterations exceeded",
                "iteration_count": 3,
                "escalated_to": "human-reviewer",
                "escalation_notes": "Needs human review",
            },
        )

        await handler.handle(event)

        assert handler._metrics["escalated_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0

    @pytest.mark.asyncio
    async def test_metrics_tracking_multiple_reviews(self):
        """Test metrics tracking for multiple reviews."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        # Create multiple reviews
        for i in range(5):
            await handler.handle(
                ReviewCycleCreated(
                    aggregate_id=f"review-{i}",
                    payload={
                        "work_item_id": f"work-{i}",
                        "workflow_id": "workflow-123",
                        "stage_name": "review",
                        "execution_id": f"exec-{i}",
                        "max_iterations": 3,
                        "review_type": "automated",
                    },
                )
            )

        assert handler._metrics["total_reviews"] == 5
        assert handler._metrics["active_reviews"] == 5

        # Approve some
        for i in range(2):
            await handler.handle(
                ReviewCycleApproved(
                    aggregate_id=f"review-{i}",
                    payload={
                        "approved_at": "2025-01-14T10:40:00+00:00",
                        "final_iteration": 1,
                        "reviewer_id": "agent-456",
                        "approval_notes": "Approved",
                    },
                )
            )

        assert handler._metrics["approved_reviews"] == 2
        assert handler._metrics["active_reviews"] == 3

        # Reject some
        for i in range(2, 4):
            await handler.handle(
                ReviewCycleRejected(
                    aggregate_id=f"review-{i}",
                    payload={
                        "rejected_at": "2025-01-14T10:40:00+00:00",
                        "reason": "Issues found",
                        "iteration_number": 2,
                        "issues": [],
                    },
                )
            )

        assert handler._metrics["rejected_reviews"] == 2
        assert handler._metrics["active_reviews"] == 1

    @pytest.mark.asyncio
    async def test_active_reviews_tracking(self):
        """Test tracking of active reviews by ID."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        # Create multiple reviews
        for i in range(3):
            await handler.handle(
                ReviewCycleCreated(
                    aggregate_id=f"review-{i}",
                    payload={
                        "work_item_id": f"work-{i}",
                        "workflow_id": "workflow-123",
                        "stage_name": "review",
                        "execution_id": f"exec-{i}",
                        "max_iterations": 3,
                        "review_type": "automated",
                    },
                )
            )

        # Verify active reviews
        assert len(handler._active_reviews) == 3
        for i in range(3):
            assert f"review-{i}" in handler._active_reviews

    @pytest.mark.asyncio
    async def test_iteration_tracking(self):
        """Test tracking of review iterations."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        # Create review
        await handler.handle(
            ReviewCycleCreated(
                aggregate_id="review-123",
                payload={
                    "work_item_id": "work-123",
                    "workflow_id": "workflow-123",
                    "stage_name": "review",
                    "execution_id": "exec-123",
                    "max_iterations": 3,
                    "review_type": "automated",
                },
            )
        )

        # Start multiple iterations
        for i in range(1, 4):
            await handler.handle(
                ReviewIterationStarted(
                    aggregate_id="review-123",
                    payload={
                        "iteration_number": i,
                        "started_at": "2025-01-14T10:30:00+00:00",
                        "reviewer_agent_id": "agent-456",
                    },
                )
            )

        assert handler._metrics["total_iterations"] == 3

    @pytest.mark.asyncio
    async def test_handle_unknown_event_type(self):
        """Test handling of unknown event type."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        from codetoreum.domain.events import WorkItemCreated

        unknown_event = WorkItemCreated(
            aggregate_id="work-123",
            payload={
                "title": "Test Work Item",
                "description": "Test description",
                "project_id": "proj-123",
            },
        )

        # Should not raise, but log warning
        await handler.handle(unknown_event)

        # Metrics should remain unchanged
        assert handler._metrics["total_reviews"] == 0

    @pytest.mark.asyncio
    async def test_review_lifecycle_approved(self):
        """Test complete review lifecycle ending in approval."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        # Create
        await handler.handle(
            ReviewCycleCreated(
                aggregate_id="review-123",
                payload={
                    "work_item_id": "work-123",
                    "workflow_id": "workflow-123",
                    "stage_name": "review",
                    "execution_id": "exec-123",
                    "max_iterations": 3,
                    "review_type": "automated",
                },
            )
        )
        assert handler._metrics["active_reviews"] == 1

        # Start iteration
        await handler.handle(
            ReviewIterationStarted(
                aggregate_id="review-123",
                payload={
                    "iteration_number": 1,
                    "started_at": "2025-01-14T10:30:00+00:00",
                    "reviewer_agent_id": "agent-456",
                },
            )
        )
        assert handler._metrics["total_iterations"] == 1

        # Approve
        await handler.handle(
            ReviewCycleApproved(
                aggregate_id="review-123",
                payload={
                    "approved_at": "2025-01-14T10:40:00+00:00",
                    "final_iteration": 1,
                    "reviewer_id": "agent-456",
                    "approval_notes": "Approved",
                },
            )
        )

        assert handler._metrics["approved_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
        assert "review-123" not in handler._active_reviews

    @pytest.mark.asyncio
    async def test_review_lifecycle_escalated(self):
        """Test complete review lifecycle ending in escalation."""
        service = MockReviewService()
        handler = ReviewEventHandler(service)

        # Create
        await handler.handle(
            ReviewCycleCreated(
                aggregate_id="review-123",
                payload={
                    "work_item_id": "work-123",
                    "workflow_id": "workflow-123",
                    "stage_name": "review",
                    "execution_id": "exec-123",
                    "max_iterations": 3,
                    "review_type": "automated",
                },
            )
        )

        # Escalate
        await handler.handle(
            ReviewCycleEscalated(
                aggregate_id="review-123",
                payload={
                    "escalated_at": "2025-01-14T10:45:00+00:00",
                    "reason": "Maximum iterations exceeded",
                    "iteration_count": 3,
                    "escalated_to": "human-reviewer",
                    "escalation_notes": "Needs human review",
                },
            )
        )

        assert handler._metrics["escalated_reviews"] == 1
        assert handler._metrics["active_reviews"] == 0
