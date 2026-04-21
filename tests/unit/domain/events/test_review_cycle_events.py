"""Unit tests for review cycle domain events."""

import pytest

from codetoreum.domain.events import (
    ReviewCycleApprovedEvent,
    ReviewCycleEscalatedToHumanEvent,
    ReviewCycleHumanFeedbackReceivedEvent,
    ReviewCycleIterationCompletedEvent,
    ReviewCycleMakerRevisionEvent,
    ReviewCycleMaxIterationsReachedEvent,
    ReviewCycleStartedEvent,
    now_iso,
)

# For immutability tests
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    FrozenInstanceError = AttributeError  # type: ignore


class TestReviewCycleStartedEvent:
    """Test ReviewCycleStartedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid review cycle started event."""
        event = ReviewCycleStartedEvent(
            type="review_cycle.started",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            project_id="proj-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=3,
        )

        assert event.review_cycle_id == "cycle-1"
        assert event.work_item_id == "item-1"
        assert event.project_id == "proj-1"
        assert event.maker_agent == "junior_dev"
        assert event.reviewer_agent == "senior_dev"
        assert event.max_iterations == 3

    def test_missing_work_item_id(self):
        """Test validation requires work_item_id."""
        with pytest.raises(ValueError, match="work_item_id is required"):
            ReviewCycleStartedEvent(
                type="review_cycle.started",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="",
                project_id="proj-1",
                maker_agent="junior_dev",
                reviewer_agent="senior_dev",
                max_iterations=3,
            )

    def test_missing_review_cycle_id(self):
        """Test validation requires review_cycle_id."""
        with pytest.raises(ValueError, match="review_cycle_id is required"):
            ReviewCycleStartedEvent(
                type="review_cycle.started",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="",
                work_item_id="item-1",
                project_id="proj-1",
                maker_agent="junior_dev",
                reviewer_agent="senior_dev",
                max_iterations=3,
            )

    def test_missing_project_id(self):
        """Test validation requires project_id."""
        with pytest.raises(ValueError, match="project_id is required"):
            ReviewCycleStartedEvent(
                type="review_cycle.started",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                project_id="",
                maker_agent="junior_dev",
                reviewer_agent="senior_dev",
                max_iterations=3,
            )

    def test_missing_maker_agent(self):
        """Test validation requires maker_agent."""
        with pytest.raises(ValueError, match="maker_agent is required"):
            ReviewCycleStartedEvent(
                type="review_cycle.started",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                project_id="proj-1",
                maker_agent="",
                reviewer_agent="senior_dev",
                max_iterations=3,
            )

    def test_missing_reviewer_agent(self):
        """Test validation requires reviewer_agent."""
        with pytest.raises(ValueError, match="reviewer_agent is required"):
            ReviewCycleStartedEvent(
                type="review_cycle.started",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                project_id="proj-1",
                maker_agent="junior_dev",
                reviewer_agent="",
                max_iterations=3,
            )

    def test_invalid_max_iterations(self):
        """Test validation requires max_iterations > 0."""
        with pytest.raises(ValueError, match="max_iterations must be greater than 0"):
            ReviewCycleStartedEvent(
                type="review_cycle.started",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                project_id="proj-1",
                maker_agent="junior_dev",
                reviewer_agent="senior_dev",
                max_iterations=0,
            )

    def test_event_immutability(self):
        """Test that events are immutable (frozen dataclass)."""
        event = ReviewCycleStartedEvent(
            type="review_cycle.started",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            project_id="proj-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=3,
        )

        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "item-2"  # type: ignore

    def test_serialization(self):
        """Test event serialization to dictionary."""
        event = ReviewCycleStartedEvent(
            type="review_cycle.started",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            project_id="proj-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=3,
        )

        d = event.to_dict()
        assert d["review_cycle_id"] == "cycle-1"
        assert d["work_item_id"] == "item-1"
        assert d["max_iterations"] == 3

    def test_deserialization(self):
        """Test event deserialization from dictionary."""
        data = {
            "type": "review_cycle.started",
            "timestamp": now_iso(),
            "source": "mock_adapter",
            "review_cycle_id": "cycle-1",
            "work_item_id": "item-1",
            "project_id": "proj-1",
            "maker_agent": "junior_dev",
            "reviewer_agent": "senior_dev",
            "max_iterations": 3,
        }

        event = ReviewCycleStartedEvent.from_dict(data)
        assert event.review_cycle_id == "cycle-1"
        assert event.work_item_id == "item-1"


class TestReviewCycleIterationCompletedEvent:
    """Test ReviewCycleIterationCompletedEvent."""

    def test_create_approved_status(self):
        """Test creating event with APPROVED status."""
        event = ReviewCycleIterationCompletedEvent(
            type="review_cycle.iteration_completed",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            iteration=1,
            status="APPROVED",
            blocking_count=0,
        )

        assert event.status == "APPROVED"
        assert event.blocking_count == 0

    def test_create_changes_requested_status(self):
        """Test creating event with CHANGES_REQUESTED status."""
        event = ReviewCycleIterationCompletedEvent(
            type="review_cycle.iteration_completed",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            iteration=2,
            status="CHANGES_REQUESTED",
            blocking_count=0,
        )

        assert event.status == "CHANGES_REQUESTED"

    def test_create_blocked_status(self):
        """Test creating event with BLOCKED status."""
        event = ReviewCycleIterationCompletedEvent(
            type="review_cycle.iteration_completed",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            iteration=1,
            status="BLOCKED",
            blocking_count=2,
        )

        assert event.status == "BLOCKED"
        assert event.blocking_count == 2

    def test_invalid_status(self):
        """Test validation rejects invalid status."""
        with pytest.raises(ValueError, match="status must be one of"):
            ReviewCycleIterationCompletedEvent(
                type="review_cycle.iteration_completed",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                iteration=1,
                status="INVALID_STATUS",
                blocking_count=0,
            )

    def test_invalid_iteration(self):
        """Test validation requires iteration > 0."""
        with pytest.raises(ValueError, match="iteration must be greater than 0"):
            ReviewCycleIterationCompletedEvent(
                type="review_cycle.iteration_completed",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                iteration=0,
                status="APPROVED",
                blocking_count=0,
            )

    def test_invalid_blocking_count(self):
        """Test validation requires blocking_count >= 0."""
        with pytest.raises(ValueError, match="blocking_count must be non-negative"):
            ReviewCycleIterationCompletedEvent(
                type="review_cycle.iteration_completed",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                iteration=1,
                status="BLOCKED",
                blocking_count=-1,
            )


class TestReviewCycleMakerRevisionEvent:
    """Test ReviewCycleMakerRevisionEvent."""

    def test_create_valid_event(self):
        """Test creating a valid maker revision event."""
        event = ReviewCycleMakerRevisionEvent(
            type="review_cycle.maker_revision",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            iteration=1,
        )

        assert event.iteration == 1
        assert event.review_cycle_id == "cycle-1"

    def test_invalid_iteration(self):
        """Test validation requires iteration > 0."""
        with pytest.raises(ValueError, match="iteration must be greater than 0"):
            ReviewCycleMakerRevisionEvent(
                type="review_cycle.maker_revision",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                iteration=0,
            )


class TestReviewCycleEscalatedToHumanEvent:
    """Test ReviewCycleEscalatedToHumanEvent."""

    def test_create_blocked_escalation(self):
        """Test creating event with BLOCKED escalation reason."""
        event = ReviewCycleEscalatedToHumanEvent(
            type="review_cycle.escalated_to_human",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            iteration=2,
            blocking_count=3,
            escalation_reason="BLOCKED",
        )

        assert event.escalation_reason == "BLOCKED"
        assert event.blocking_count == 3

    def test_create_max_iterations_escalation(self):
        """Test creating event with MAX_ITERATIONS escalation reason."""
        event = ReviewCycleEscalatedToHumanEvent(
            type="review_cycle.escalated_to_human",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            iteration=3,
            blocking_count=0,
            escalation_reason="MAX_ITERATIONS",
        )

        assert event.escalation_reason == "MAX_ITERATIONS"

    def test_invalid_escalation_reason(self):
        """Test validation rejects invalid escalation reason."""
        with pytest.raises(ValueError, match="escalation_reason must be one of"):
            ReviewCycleEscalatedToHumanEvent(
                type="review_cycle.escalated_to_human",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                iteration=1,
                blocking_count=0,
                escalation_reason="INVALID_REASON",
            )

    def test_invalid_blocking_count(self):
        """Test validation requires blocking_count >= 0."""
        with pytest.raises(ValueError, match="blocking_count must be non-negative"):
            ReviewCycleEscalatedToHumanEvent(
                type="review_cycle.escalated_to_human",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                iteration=1,
                blocking_count=-1,
                escalation_reason="BLOCKED",
            )


class TestReviewCycleHumanFeedbackReceivedEvent:
    """Test ReviewCycleHumanFeedbackReceivedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid human feedback event."""
        event = ReviewCycleHumanFeedbackReceivedEvent(
            type="review_cycle.human_feedback_received",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            feedback="Use async/await pattern instead of callbacks",
        )

        assert event.feedback == "Use async/await pattern instead of callbacks"

    def test_missing_feedback(self):
        """Test validation requires non-empty feedback."""
        with pytest.raises(ValueError, match="feedback is required"):
            ReviewCycleHumanFeedbackReceivedEvent(
                type="review_cycle.human_feedback_received",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                feedback="",
            )


class TestReviewCycleMaxIterationsReachedEvent:
    """Test ReviewCycleMaxIterationsReachedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid max iterations event."""
        event = ReviewCycleMaxIterationsReachedEvent(
            type="review_cycle.max_iterations_reached",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            max_iterations=3,
        )

        assert event.max_iterations == 3

    def test_invalid_max_iterations(self):
        """Test validation requires max_iterations > 0."""
        with pytest.raises(ValueError, match="max_iterations must be greater than 0"):
            ReviewCycleMaxIterationsReachedEvent(
                type="review_cycle.max_iterations_reached",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                max_iterations=0,
            )


class TestReviewCycleApprovedEvent:
    """Test ReviewCycleApprovedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid approved event."""
        event = ReviewCycleApprovedEvent(
            type="review_cycle.approved",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            total_iterations=2,
        )

        assert event.total_iterations == 2

    def test_invalid_total_iterations(self):
        """Test validation requires total_iterations > 0."""
        with pytest.raises(ValueError, match="total_iterations must be greater than 0"):
            ReviewCycleApprovedEvent(
                type="review_cycle.approved",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                total_iterations=0,
            )

    def test_single_iteration_approval(self):
        """Test approval after single iteration."""
        event = ReviewCycleApprovedEvent(
            type="review_cycle.approved",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            total_iterations=1,
        )

        assert event.total_iterations == 1

    def test_multiple_iterations_approval(self):
        """Test approval after multiple iterations."""
        event = ReviewCycleApprovedEvent(
            type="review_cycle.approved",
            timestamp=now_iso(),
            source="mock_adapter",
            review_id="cycle-1",
            work_item_id="item-1",
            total_iterations=5,
        )

        assert event.total_iterations == 5


class TestEventHierarchy:
    """Test event hierarchy and relationships."""

    def test_all_events_inherit_from_codetoreum_event(self):
        """Test that all review cycle events inherit from CodetoreumEvent."""
        from codetoreum.domain.events import CodetoreumEvent

        events = [
            ReviewCycleStartedEvent(
                type="review_cycle.started",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                project_id="proj-1",
                maker_agent="junior_dev",
                reviewer_agent="senior_dev",
                max_iterations=3,
            ),
            ReviewCycleIterationCompletedEvent(
                type="review_cycle.iteration_completed",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                iteration=1,
                status="APPROVED",
                blocking_count=0,
            ),
            ReviewCycleMakerRevisionEvent(
                type="review_cycle.maker_revision",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                iteration=1,
            ),
            ReviewCycleEscalatedToHumanEvent(
                type="review_cycle.escalated_to_human",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                iteration=1,
                blocking_count=1,
                escalation_reason="BLOCKED",
            ),
            ReviewCycleHumanFeedbackReceivedEvent(
                type="review_cycle.human_feedback_received",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                feedback="feedback",
            ),
            ReviewCycleMaxIterationsReachedEvent(
                type="review_cycle.max_iterations_reached",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                max_iterations=3,
            ),
            ReviewCycleApprovedEvent(
                type="review_cycle.approved",
                timestamp=now_iso(),
                source="mock_adapter",
                review_id="cycle-1",
                work_item_id="item-1",
                total_iterations=2,
            ),
        ]

        for event in events:
            assert isinstance(event, CodetoreumEvent)

    def test_event_typing(self):
        """Test that events have correct type field."""
        event_types = [
            (
                ReviewCycleStartedEvent(
                    type="review_cycle.started",
                    timestamp=now_iso(),
                    source="mock_adapter",
                    review_id="cycle-1",
                    work_item_id="item-1",
                    project_id="proj-1",
                    maker_agent="junior_dev",
                    reviewer_agent="senior_dev",
                    max_iterations=3,
                ),
                "review_cycle.started",
            ),
            (
                ReviewCycleIterationCompletedEvent(
                    type="review_cycle.iteration_completed",
                    timestamp=now_iso(),
                    source="mock_adapter",
                    review_id="cycle-1",
                    work_item_id="item-1",
                    iteration=1,
                    status="APPROVED",
                    blocking_count=0,
                ),
                "review_cycle.iteration_completed",
            ),
            (
                ReviewCycleMakerRevisionEvent(
                    type="review_cycle.maker_revision",
                    timestamp=now_iso(),
                    source="mock_adapter",
                    review_id="cycle-1",
                    work_item_id="item-1",
                    iteration=1,
                ),
                "review_cycle.maker_revision",
            ),
            (
                ReviewCycleEscalatedToHumanEvent(
                    type="review_cycle.escalated_to_human",
                    timestamp=now_iso(),
                    source="mock_adapter",
                    review_id="cycle-1",
                    work_item_id="item-1",
                    iteration=1,
                    blocking_count=1,
                    escalation_reason="BLOCKED",
                ),
                "review_cycle.escalated_to_human",
            ),
            (
                ReviewCycleHumanFeedbackReceivedEvent(
                    type="review_cycle.human_feedback_received",
                    timestamp=now_iso(),
                    source="mock_adapter",
                    review_id="cycle-1",
                    work_item_id="item-1",
                    feedback="feedback",
                ),
                "review_cycle.human_feedback_received",
            ),
            (
                ReviewCycleMaxIterationsReachedEvent(
                    type="review_cycle.max_iterations_reached",
                    timestamp=now_iso(),
                    source="mock_adapter",
                    review_id="cycle-1",
                    work_item_id="item-1",
                    max_iterations=3,
                ),
                "review_cycle.max_iterations_reached",
            ),
            (
                ReviewCycleApprovedEvent(
                    type="review_cycle.approved",
                    timestamp=now_iso(),
                    source="mock_adapter",
                    review_id="cycle-1",
                    work_item_id="item-1",
                    total_iterations=2,
                ),
                "review_cycle.approved",
            ),
        ]

        for event, expected_type in event_types:
            assert event.type == expected_type
