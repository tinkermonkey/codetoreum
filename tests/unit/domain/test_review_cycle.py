"""Unit tests for ReviewCycle aggregate root."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from codetoreum.domain.events.review_cycle_events import (
    ReviewCycleApprovedEvent,
    ReviewCycleCreatedEvent,
    ReviewCycleEscalatedToHumanEvent,
    ReviewCycleFeedbackSubmittedEvent,
    ReviewCycleIterationStartedEvent,
)
from codetoreum.domain.exceptions import DomainError
from codetoreum.domain.review_cycle import (
    ReviewCycle,
    ReviewDecision,
    ReviewFeedback,
    ReviewStatus,
)


class TestReviewCycleCreation:
    """Tests for ReviewCycle creation."""

    def test_create_review_cycle(self):
        """Test creating review cycle with default max iterations."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        assert cycle.id is not None
        assert cycle.workflow_id == "wf-1"
        assert cycle.stage_name == "coding"
        assert cycle.maker_agent_id == "maker-1"
        assert cycle.reviewer_agent_id == "reviewer-1"
        assert cycle.max_iterations == 3
        assert cycle.status == ReviewStatus.PENDING
        assert cycle.current_iteration == 0
        assert cycle.iterations == []
        assert cycle.final_decision is None
        assert cycle.escalation_reason is None
        assert isinstance(cycle.created_at, datetime)
        assert isinstance(cycle.updated_at, datetime)
        assert cycle.completed_at is None

    def test_create_review_cycle_with_custom_max_iterations(self):
        """Test creating review cycle with custom max iterations."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
            max_iterations=5,
        )

        assert cycle.max_iterations == 5

    def test_create_emits_event(self):
        """Test that creation emits ReviewCycleCreated event."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        events = cycle.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ReviewCycleCreatedEvent)
        assert events[0].review_cycle_id == cycle.id
        assert events[0].workflow_id == "wf-1"
        assert events[0].maker_agent_id == "maker-1"
        assert events[0].reviewer_agent_id == "reviewer-1"

    def test_create_with_same_maker_and_reviewer_raises_error(self):
        """Test that creating with same maker and reviewer raises error."""
        with pytest.raises(DomainError, match="Maker and reviewer must be different"):
            ReviewCycle.create(
                workflow_id="wf-1",
                stage_name="coding",
                maker_agent_id="agent-1",
                reviewer_agent_id="agent-1",
            )

    def test_create_with_zero_max_iterations_raises_error(self):
        """Test that creating with zero max iterations raises error."""
        with pytest.raises(DomainError, match="Max iterations must be positive"):
            ReviewCycle.create(
                workflow_id="wf-1",
                stage_name="coding",
                maker_agent_id="maker-1",
                reviewer_agent_id="reviewer-1",
                max_iterations=0,
            )

    def test_create_with_negative_max_iterations_raises_error(self):
        """Test that creating with negative max iterations raises error."""
        with pytest.raises(DomainError, match="Max iterations must be positive"):
            ReviewCycle.create(
                workflow_id="wf-1",
                stage_name="coding",
                maker_agent_id="maker-1",
                reviewer_agent_id="reviewer-1",
                max_iterations=-1,
            )


class TestIterationManagement:
    """Tests for iteration management."""

    def test_start_iteration(self):
        """Test starting a new iteration."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.clear_events()

        cycle.start_iteration("output1", "exec-1")

        assert cycle.current_iteration == 1
        assert cycle.status == ReviewStatus.IN_PROGRESS
        assert len(cycle.iterations) == 1

        iteration = cycle.iterations[0]
        assert iteration.iteration_number == 1
        assert iteration.maker_output == "output1"
        assert iteration.maker_execution_id == "exec-1"
        assert iteration.reviewer_feedback is None
        assert iteration.reviewer_execution_id is None
        assert isinstance(iteration.started_at, datetime)
        assert iteration.completed_at is None

        events = cycle.get_pending_events()
        assert len(events) == 1
        assert isinstance(events[0], ReviewCycleIterationStartedEvent)
        assert events[0].iteration_number == 1
        assert events[0].maker_execution_id == "exec-1"

    def test_start_multiple_iterations(self):
        """Test starting multiple iterations."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Fix this", "exec-2")
        cycle.start_iteration("output2", "exec-3")

        assert cycle.current_iteration == 2
        assert len(cycle.iterations) == 2
        assert cycle.iterations[0].maker_output == "output1"
        assert cycle.iterations[1].maker_output == "output2"

    def test_start_iteration_exceeding_max_raises_error(self):
        """Test that starting iteration beyond max raises error."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
            max_iterations=2,
        )

        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Fix this", "exec-2")
        cycle.start_iteration("output2", "exec-3")
        cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Still issues", "exec-4")

        # After max iterations with REQUEST_CHANGES, cycle auto-escalates
        # Attempting to start new iteration should fail because cycle is now ESCALATED
        with pytest.raises(DomainError, match="Cannot start iteration on escalated cycle"):
            cycle.start_iteration("output3", "exec-5")


class TestReviewSubmission:
    """Tests for review submission."""

    def test_submit_review_with_approval(self):
        """Test submitting review with approval decision."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")
        cycle.clear_events()

        cycle.submit_review(
            decision=ReviewDecision.APPROVE,
            comment="Looks good!",
            reviewer_execution_id="exec-2",
            issues=[],
            suggestions=["Consider adding more tests"],
        )

        iteration = cycle.iterations[0]
        assert iteration.reviewer_feedback is not None
        assert iteration.reviewer_feedback.decision == ReviewDecision.APPROVE
        assert iteration.reviewer_feedback.comment == "Looks good!"
        assert iteration.reviewer_feedback.issues == ()
        assert iteration.reviewer_feedback.suggestions == ("Consider adding more tests",)
        assert isinstance(iteration.reviewer_feedback.timestamp, datetime)
        assert iteration.reviewer_execution_id == "exec-2"
        assert isinstance(iteration.completed_at, datetime)

        assert cycle.status == ReviewStatus.APPROVED
        assert cycle.final_decision == ReviewDecision.APPROVE
        assert cycle.is_complete()

        events = cycle.get_pending_events()
        assert len(events) == 2  # ReviewFeedbackSubmitted + ReviewCycleApproved
        assert isinstance(events[0], ReviewCycleFeedbackSubmittedEvent)
        assert isinstance(events[1], ReviewCycleApprovedEvent)

    def test_submit_review_with_request_changes(self):
        """Test submitting review with request changes decision."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")
        cycle.clear_events()

        cycle.submit_review(
            decision=ReviewDecision.REQUEST_CHANGES,
            comment="Please fix these issues",
            reviewer_execution_id="exec-2",
            issues=["Missing error handling", "Incomplete tests"],
            suggestions=["Add try-catch blocks"],
        )

        iteration = cycle.iterations[0]
        assert iteration.reviewer_feedback is not None
        assert iteration.reviewer_feedback.decision == ReviewDecision.REQUEST_CHANGES
        assert len(iteration.reviewer_feedback.issues) == 2
        assert "Missing error handling" in iteration.reviewer_feedback.issues

        assert cycle.status == ReviewStatus.CHANGES_REQUESTED
        assert cycle.needs_maker_revision()
        assert not cycle.is_complete()

        events = cycle.get_pending_events()
        assert len(events) == 1  # Only ReviewFeedbackSubmitted
        assert isinstance(events[0], ReviewCycleFeedbackSubmittedEvent)

    def test_submit_review_with_escalate(self):
        """Test submitting review with escalate decision."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")
        cycle.clear_events()

        cycle.submit_review(
            decision=ReviewDecision.ESCALATE,
            comment="This needs human review",
            reviewer_execution_id="exec-2",
        )

        assert cycle.status == ReviewStatus.ESCALATED
        assert cycle.final_decision == ReviewDecision.ESCALATE
        assert cycle.escalation_reason == "Reviewer escalated"
        assert cycle.is_complete()

        events = cycle.get_pending_events()
        assert len(events) == 2  # ReviewFeedbackSubmitted + ReviewCycleEscalated
        assert isinstance(events[1], ReviewCycleEscalatedToHumanEvent)

    def test_submit_review_without_issues_or_suggestions(self):
        """Test submitting review without issues or suggestions."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")

        cycle.submit_review(decision=ReviewDecision.APPROVE, comment="Perfect", reviewer_execution_id="exec-2")

        feedback = cycle.get_latest_feedback()
        assert feedback is not None
        assert feedback.issues == ()
        assert feedback.suggestions == ()

    def test_submit_review_without_iteration_raises_error(self):
        """Test that submitting review without iteration raises error."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        with pytest.raises(DomainError, match="No iterations to review"):
            cycle.submit_review(decision=ReviewDecision.APPROVE, comment="Good", reviewer_execution_id="exec-1")

    def test_submit_review_twice_raises_error(self):
        """Test that submitting review twice for same iteration raises error."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(decision=ReviewDecision.APPROVE, comment="Good", reviewer_execution_id="exec-2")

        # Cannot submit review again for same iteration
        with pytest.raises(DomainError, match="already reviewed"):
            cycle.submit_review(
                decision=ReviewDecision.APPROVE,
                comment="Good again",
                reviewer_execution_id="exec-3",
            )


class TestApprovalFlow:
    """Tests for approval flow."""

    def test_approve_on_first_iteration(self):
        """Test approving on first iteration."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(ReviewDecision.APPROVE, "Great work", "exec-2")

        assert cycle.status == ReviewStatus.APPROVED
        assert cycle.final_decision == ReviewDecision.APPROVE
        assert cycle.current_iteration == 1
        assert isinstance(cycle.completed_at, datetime)

    def test_approve_from_pending_raises_error(self):
        """Test that approving from PENDING state raises error."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        with pytest.raises(DomainError, match="Can only approve cycle in IN_PROGRESS state"):
            cycle.approve()

    def test_approve_from_changes_requested_raises_error(self):
        """Test that approving from CHANGES_REQUESTED state raises error."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Fix this", "exec-2")

        with pytest.raises(DomainError, match="Can only approve cycle in IN_PROGRESS state"):
            cycle.approve()

    def test_approve_twice_raises_error(self):
        """Test that approving twice raises error."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")
        cycle.approve()

        with pytest.raises(DomainError, match="Can only approve cycle in IN_PROGRESS state"):
            cycle.approve()


class TestEscalationFlow:
    """Tests for escalation flow."""

    def test_escalate_manually(self):
        """Test manual escalation by reviewer."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(ReviewDecision.ESCALATE, "Too complex", "exec-2")

        assert cycle.status == ReviewStatus.ESCALATED
        assert cycle.escalation_reason == "Reviewer escalated"

    def test_escalate_on_max_iterations(self):
        """Test automatic escalation when max iterations reached."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
            max_iterations=2,
        )

        # Iteration 1
        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Fix this", "exec-2")

        status_after_iter1 = cycle.status
        assert status_after_iter1 == ReviewStatus.CHANGES_REQUESTED

        # Iteration 2
        cycle.start_iteration("output2", "exec-3")
        cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Still issues", "exec-4")

        # Should escalate automatically
        status_after_iter2 = cycle.status
        assert status_after_iter2 == ReviewStatus.ESCALATED
        assert cycle.escalation_reason == "Max iterations reached"
        assert cycle.current_iteration == 2

    def test_escalate_from_approved_raises_error(self):
        """Test that escalating an already-approved cycle raises error."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(ReviewDecision.APPROVE, "Great work", "exec-2")

        with pytest.raises(DomainError, match="Cannot escalate approved cycle"):
            cycle.escalate("Too late")

    def test_escalate_twice_raises_error(self):
        """Test that escalating twice raises error."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.start_iteration("output1", "exec-1")
        cycle.escalate("First escalation")

        with pytest.raises(DomainError, match="Cannot escalate escalated cycle"):
            cycle.escalate("Second escalation")


class TestIterativeFlow:
    """Tests for full iterative flow."""

    def test_multiple_iterations_until_approval(self):
        """Test multiple iterations until final approval."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        # Iteration 1: Changes requested
        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(
            ReviewDecision.REQUEST_CHANGES,
            "Add error handling",
            "exec-2",
            issues=["Missing error handling"],
        )

        assert cycle.current_iteration == 1
        assert cycle.needs_maker_revision()

        # Iteration 2: Changes requested again
        cycle.start_iteration("output2", "exec-3")
        cycle.submit_review(
            ReviewDecision.REQUEST_CHANGES,
            "Add more tests",
            "exec-4",
            issues=["Insufficient test coverage"],
        )

        assert cycle.current_iteration == 2
        assert cycle.needs_maker_revision()

        # Iteration 3: Approved
        cycle.start_iteration("output3", "exec-5")
        cycle.submit_review(ReviewDecision.APPROVE, "Perfect now", "exec-6")

        assert cycle.current_iteration == 3
        assert cycle.is_complete()
        assert cycle.status == ReviewStatus.APPROVED
        assert len(cycle.iterations) == 3


class TestQueryMethods:
    """Tests for query methods."""

    def test_is_complete(self):
        """Test is_complete query method."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        assert not cycle.is_complete()

        cycle.start_iteration("output1", "exec-1")
        assert not cycle.is_complete()

        cycle.submit_review(ReviewDecision.APPROVE, "Good", "exec-2")
        assert cycle.is_complete()

    def test_needs_maker_revision(self):
        """Test needs_maker_revision query method."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        assert not cycle.needs_maker_revision()

        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Fix this", "exec-2")

        assert cycle.needs_maker_revision()

    def test_get_latest_feedback(self):
        """Test get_latest_feedback query method."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        assert cycle.get_latest_feedback() is None

        cycle.start_iteration("output1", "exec-1")
        assert cycle.get_latest_feedback() is None

        cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Fix this", "exec-2")
        feedback = cycle.get_latest_feedback()
        assert feedback is not None
        assert feedback.decision == ReviewDecision.REQUEST_CHANGES
        assert feedback.comment == "Fix this"


class TestEventManagement:
    """Tests for event management."""

    def test_get_pending_events_returns_copy(self):
        """Test that get_pending_events returns a copy."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        events1 = cycle.get_pending_events()
        events2 = cycle.get_pending_events()

        assert events1 is not events2
        assert events1 == events2

    def test_clear_events(self):
        """Test clearing pending events."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        assert len(cycle.get_pending_events()) == 1

        cycle.clear_events()

        assert len(cycle.get_pending_events()) == 0

    def test_multiple_operations_accumulate_events(self):
        """Test that multiple operations accumulate events."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )
        cycle.clear_events()

        cycle.start_iteration("output1", "exec-1")
        cycle.submit_review(ReviewDecision.APPROVE, "Good", "exec-2")

        events = cycle.get_pending_events()
        assert len(events) == 3  # StartIteration + FeedbackSubmitted + Approved


class TestVersioning:
    """Tests for aggregate versioning."""

    def test_initial_version_is_zero(self):
        """Test that initial version is 0."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        assert cycle._version == 0

    def test_version_increments_on_mutation(self):
        """Test that version increments on each mutation."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        cycle.start_iteration("output1", "exec-1")
        assert cycle._version == 1

        cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Fix", "exec-2")
        assert cycle._version == 3  # submit_review + request_changes

        cycle.start_iteration("output2", "exec-3")
        assert cycle._version == 4


class TestReviewFeedbackValueObject:
    """Tests for ReviewFeedback value object."""

    def test_review_feedback_is_immutable(self):
        """Test that ReviewFeedback is immutable (frozen)."""
        feedback = ReviewFeedback(
            decision=ReviewDecision.APPROVE,
            comment="Good",
            issues=[],
            suggestions=[],
            timestamp=datetime.now(UTC),
        )

        with pytest.raises(FrozenInstanceError):
            feedback.comment = "Changed"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            feedback.decision = ReviewDecision.REQUEST_CHANGES  # type: ignore[misc]

    def test_review_feedback_issues_are_tuples(self):
        """Test that ReviewFeedback converts list issues to immutable tuples."""
        feedback = ReviewFeedback(
            decision=ReviewDecision.APPROVE,
            comment="Good",
            issues=["issue1", "issue2"],
            suggestions=["suggestion1"],
            timestamp=datetime.now(UTC),
        )

        assert isinstance(feedback.issues, tuple)
        assert isinstance(feedback.suggestions, tuple)
        assert feedback.issues == ("issue1", "issue2")
        assert feedback.suggestions == ("suggestion1",)

        # Tuples prevent mutation attempts
        with pytest.raises((TypeError, AttributeError)):
            feedback.issues.append("new_issue")  # type: ignore[union-attr]


class TestIdentityFieldProtection:
    """Tests for identity field protection."""

    def test_identity_fields_cannot_be_modified(self):
        """Test that identity fields are protected from external modification."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        # Try to modify identity fields
        with pytest.raises(AttributeError, match="Cannot modify identity field 'id'"):
            cycle.id = "hacked"  # type: ignore[misc]

        with pytest.raises(AttributeError, match="Cannot modify identity field 'workflow_id'"):
            cycle.workflow_id = "hacked"  # type: ignore[misc]

        with pytest.raises(AttributeError, match="Cannot modify identity field 'stage_name'"):
            cycle.stage_name = "hacked"  # type: ignore[misc]

        with pytest.raises(AttributeError, match="Cannot modify identity field 'maker_agent_id'"):
            cycle.maker_agent_id = "hacked"  # type: ignore[misc]

        with pytest.raises(AttributeError, match="Cannot modify identity field 'reviewer_agent_id'"):
            cycle.reviewer_agent_id = "hacked"  # type: ignore[misc]

        with pytest.raises(AttributeError, match="Cannot modify identity field 'max_iterations'"):
            cycle.max_iterations = 999  # type: ignore[misc]

    def test_identity_fields_set_during_creation(self):
        """Test that identity fields can be set during creation (via __init__)."""
        cycle = ReviewCycle.create(
            workflow_id="wf-1",
            stage_name="coding",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
            max_iterations=5,
        )

        assert cycle.workflow_id == "wf-1"
        assert cycle.stage_name == "coding"
        assert cycle.maker_agent_id == "maker-1"
        assert cycle.reviewer_agent_id == "reviewer-1"
        assert cycle.max_iterations == 5
