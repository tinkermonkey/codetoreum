"""Review Cycle aggregate root."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from codetoreum.domain.events import DomainEvent
from codetoreum.domain.exceptions import DomainError

# =============================================================================
# Review Cycle Events
# =============================================================================


class ReviewCycleCreated(DomainEvent):
    """Emitted when review cycle is created."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewCycleCreated event.

        Required payload fields:
        - workflow_id: str
        - stage_name: str
        - maker_agent_id: str
        - reviewer_agent_id: str
        - max_iterations: int
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewIterationStarted(DomainEvent):
    """Emitted when new iteration begins."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewIterationStarted event.

        Required payload fields:
        - iteration_number: int
        - maker_execution_id: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewFeedbackSubmitted(DomainEvent):
    """Emitted when reviewer provides feedback."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewFeedbackSubmitted event.

        Required payload fields:
        - iteration_number: int
        - decision: str
        - reviewer_execution_id: str
        - issues_count: int
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewCycleApproved(DomainEvent):
    """Emitted when review cycle is approved."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewCycleApproved event.

        Required payload fields:
        - total_iterations: int
        - approved_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewCycleEscalated(DomainEvent):
    """Emitted when review cycle is escalated to human."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewCycleEscalated event.

        Required payload fields:
        - reason: str
        - total_iterations: int
        - escalated_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


# =============================================================================
# Review Cycle Domain Model
# =============================================================================


class ReviewStatus(Enum):
    """Status of review cycle."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    ESCALATED = "escalated"


class ReviewDecision(Enum):
    """Reviewer's decision."""

    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class ReviewFeedback:
    """
    Value object for review feedback.

    Immutable representation of reviewer's feedback on an iteration.
    """

    decision: ReviewDecision
    comment: str
    issues: list[str]
    suggestions: list[str]
    timestamp: datetime


@dataclass(frozen=True)
class ReviewIteration:
    """
    Single iteration of maker-reviewer cycle.

    Represents one round of work submission and review.
    Immutable value object for aggregate consistency.
    """

    iteration_number: int
    maker_output: str
    maker_execution_id: str
    reviewer_feedback: ReviewFeedback | None
    reviewer_execution_id: str | None
    started_at: datetime
    completed_at: datetime | None


@dataclass
class ReviewCycle:
    """
    Review Cycle aggregate root.

    Manages iterative maker-checker review process where a maker agent
    produces output and a reviewer agent evaluates it. The cycle continues
    until approval, escalation, or max iterations reached.

    Encapsulation Strategy:
    - Public readonly fields: id, workflow_id, stage_name, maker_agent_id, reviewer_agent_id, max_iterations
    - Private state fields: _status, _current_iteration, _final_decision, _escalation_reason, _iterations
    - Timestamps handled via accessor methods with copy semantics
    - All mutations guarded by state machine enforcement
    """

    # Identity (readonly)
    id: str
    workflow_id: str
    stage_name: str

    # Agents (readonly)
    maker_agent_id: str
    reviewer_agent_id: str

    # Configuration (readonly)
    max_iterations: int

    # Status (private - guarded by state transitions)
    _status: ReviewStatus
    _current_iteration: int
    _created_at: datetime
    _updated_at: datetime

    # Iterations (private - immutable elements, defensive copies on access)
    _iterations: list[ReviewIteration] = field(default_factory=list, repr=False)

    # Final decision (private - set only by terminal transitions)
    _final_decision: ReviewDecision | None = field(default=None, repr=False)
    _escalation_reason: str | None = field(default=None, repr=False)

    # Completion timestamp (private - managed internally)
    _completed_at: datetime | None = field(default=None, repr=False)

    # Event tracking (private - guarded by methods)
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)
    _version: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate invariants after initialization."""
        self._validate_invariants()

    def _validate_invariants(self) -> None:
        """
        Validate domain invariants.

        Invariants:
        - Maker and reviewer must be different agents
        - Max iterations must be positive
        - Current iteration cannot exceed max iterations
        """
        if self.maker_agent_id == self.reviewer_agent_id:
            msg = "Maker and reviewer must be different agents"
            raise DomainError(msg)

        if self.max_iterations <= 0:
            msg = "Max iterations must be positive"
            raise DomainError(msg)

        if self._current_iteration > self.max_iterations:
            msg = f"Current iteration ({self._current_iteration}) cannot exceed max iterations ({self.max_iterations})"
            raise DomainError(msg)

    # =========================================================================
    # Public accessors (defensive copies / computed properties)
    # =========================================================================

    @property
    def status(self) -> ReviewStatus:
        """Get current review cycle status."""
        return self._status

    @property
    def current_iteration(self) -> int:
        """Get current iteration number."""
        return self._current_iteration

    @property
    def iterations(self) -> list[ReviewIteration]:
        """Get defensive copy of iterations list."""
        return list(self._iterations)

    @property
    def final_decision(self) -> ReviewDecision | None:
        """Get final decision (None until cycle completes)."""
        return self._final_decision

    @property
    def escalation_reason(self) -> str | None:
        """Get escalation reason (None unless escalated)."""
        return self._escalation_reason

    @property
    def created_at(self) -> datetime:
        """Get creation timestamp."""
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        """Get last update timestamp."""
        return self._updated_at

    @property
    def completed_at(self) -> datetime | None:
        """Get completion timestamp (None if not complete)."""
        return self._completed_at

    # Creation
    @classmethod
    def create(
        cls,
        workflow_id: str,
        stage_name: str,
        maker_agent_id: str,
        reviewer_agent_id: str,
        max_iterations: int = 3,
    ) -> "ReviewCycle":
        """
        Factory method to create a new review cycle.

        Args:
            workflow_id: ID of the workflow this cycle belongs to
            stage_name: Name of the workflow stage
            maker_agent_id: ID of the maker agent
            reviewer_agent_id: ID of the reviewer agent
            max_iterations: Maximum number of iterations (default: 3)

        Returns:
            Newly created ReviewCycle instance

        Raises:
            DomainError: If maker and reviewer are the same or max_iterations <= 0

        Emits: ReviewCycleCreated event
        """
        now = datetime.now(UTC)
        cycle = cls(
            id=str(uuid4()),
            workflow_id=workflow_id,
            stage_name=stage_name,
            maker_agent_id=maker_agent_id,
            reviewer_agent_id=reviewer_agent_id,
            max_iterations=max_iterations,
            _status=ReviewStatus.PENDING,
            _current_iteration=0,
            _iterations=[],
            _final_decision=None,
            _escalation_reason=None,
            _created_at=now,
            _updated_at=now,
            _completed_at=None,
        )

        event = ReviewCycleCreated(
            aggregate_id=cycle.id,
            payload={
                "workflow_id": workflow_id,
                "stage_name": stage_name,
                "maker_agent_id": maker_agent_id,
                "reviewer_agent_id": reviewer_agent_id,
                "max_iterations": max_iterations,
            },
        )
        cycle._add_event(event)

        return cycle

    # State transitions
    def start_iteration(self, maker_output: str, maker_execution_id: str) -> None:
        """
        Start new iteration with maker's output.

        Args:
            maker_output: Output produced by maker agent
            maker_execution_id: Execution ID of maker's run

        Raises:
            DomainError: If max iterations already reached

        Emits: ReviewIterationStarted event
        """
        if self._current_iteration >= self.max_iterations:
            msg = f"Exceeded max iterations ({self.max_iterations})"
            raise DomainError(msg)

        self._current_iteration += 1
        iteration = ReviewIteration(
            iteration_number=self._current_iteration,
            maker_output=maker_output,
            maker_execution_id=maker_execution_id,
            reviewer_feedback=None,
            reviewer_execution_id=None,
            started_at=datetime.now(UTC),
            completed_at=None,
        )

        self._iterations.append(iteration)
        self._status = ReviewStatus.IN_PROGRESS
        self._updated_at = datetime.now(UTC)
        self._version += 1

        event = ReviewIterationStarted(
            aggregate_id=self.id,
            payload={
                "iteration_number": self._current_iteration,
                "maker_execution_id": maker_execution_id,
            },
        )
        self._add_event(event)

    def submit_review(
        self,
        decision: ReviewDecision,
        comment: str,
        reviewer_execution_id: str,
        issues: list[str] | None = None,
        suggestions: list[str] | None = None,
    ) -> None:
        """
        Submit reviewer's feedback.

        Args:
            decision: Reviewer's decision (approve, request changes, escalate)
            comment: Reviewer's comment
            reviewer_execution_id: Execution ID of reviewer's run
            issues: List of issues found (optional)
            suggestions: List of suggestions (optional)

        Raises:
            DomainError: If no iterations to review or current iteration already reviewed

        Emits: ReviewFeedbackSubmitted event
        """
        if not self._iterations:
            msg = "No iterations to review"
            raise DomainError(msg)

        current = self._iterations[-1]
        if current.reviewer_feedback:
            msg = "Current iteration already reviewed"
            raise DomainError(msg)

        feedback = ReviewFeedback(
            decision=decision,
            comment=comment,
            issues=issues or [],
            suggestions=suggestions or [],
            timestamp=datetime.now(UTC),
        )

        # Create new immutable iteration with feedback
        now = datetime.now(UTC)
        updated_iteration = ReviewIteration(
            iteration_number=current.iteration_number,
            maker_output=current.maker_output,
            maker_execution_id=current.maker_execution_id,
            reviewer_feedback=feedback,
            reviewer_execution_id=reviewer_execution_id,
            started_at=current.started_at,
            completed_at=now,
        )

        # Replace the last iteration with the updated one
        self._iterations[-1] = updated_iteration
        self._updated_at = now
        self._version += 1

        # Add feedback event first
        event = ReviewFeedbackSubmitted(
            aggregate_id=self.id,
            payload={
                "iteration_number": self._current_iteration,
                "decision": decision.value,
                "reviewer_execution_id": reviewer_execution_id,
                "issues_count": len(issues or []),
            },
        )
        self._add_event(event)

        # Then handle decision (which may add additional events)
        if decision == ReviewDecision.APPROVE:
            self.approve()
        elif decision == ReviewDecision.REQUEST_CHANGES:
            self.request_changes()
        elif decision == ReviewDecision.ESCALATE:
            self.escalate("Reviewer escalated")

    def approve(self) -> None:
        """
        Approve the review.

        Marks the review cycle as complete and approved.

        Emits: ReviewCycleApproved event
        """
        now = datetime.now(UTC)
        self._status = ReviewStatus.APPROVED
        self._final_decision = ReviewDecision.APPROVE
        self._completed_at = now
        self._updated_at = now
        self._version += 1

        event = ReviewCycleApproved(
            aggregate_id=self.id,
            payload={
                "total_iterations": self._current_iteration,
                "approved_at": now.isoformat(),
            },
        )
        self._add_event(event)

    def request_changes(self) -> None:
        """
        Request changes from maker.

        If max iterations reached, automatically escalates.
        Otherwise, marks cycle as needing maker revision.
        """
        if self._current_iteration >= self.max_iterations:
            self.escalate("Max iterations reached")
            return

        self._status = ReviewStatus.CHANGES_REQUESTED
        self._updated_at = datetime.now(UTC)
        self._version += 1

    def escalate(self, reason: str) -> None:
        """
        Escalate to human review.

        Args:
            reason: Reason for escalation

        Emits: ReviewCycleEscalated event
        """
        now = datetime.now(UTC)
        self._status = ReviewStatus.ESCALATED
        self._final_decision = ReviewDecision.ESCALATE
        self._escalation_reason = reason
        self._completed_at = now
        self._updated_at = now
        self._version += 1

        event = ReviewCycleEscalated(
            aggregate_id=self.id,
            payload={
                "reason": reason,
                "total_iterations": self._current_iteration,
                "escalated_at": now.isoformat(),
            },
        )
        self._add_event(event)

    # Query methods
    def is_complete(self) -> bool:
        """
        Check if review cycle is complete.

        Returns:
            True if cycle is approved or escalated
        """
        return self.status in [ReviewStatus.APPROVED, ReviewStatus.ESCALATED]

    def needs_maker_revision(self) -> bool:
        """
        Check if maker needs to revise.

        Returns:
            True if changes were requested
        """
        return self.status == ReviewStatus.CHANGES_REQUESTED

    def get_latest_feedback(self) -> ReviewFeedback | None:
        """
        Get latest reviewer feedback.

        Returns:
            Most recent ReviewFeedback or None if no feedback yet
        """
        if not self.iterations:
            return None
        return self.iterations[-1].reviewer_feedback

    # Event management
    def _add_event(self, event: DomainEvent) -> None:
        """
        Add event to pending events list.

        Args:
            event: Domain event to add
        """
        self._events.append(event)

    def get_pending_events(self) -> list[DomainEvent]:
        """
        Get all pending events.

        Returns:
            Copy of the pending events list
        """
        return list(self._events)

    def clear_events(self) -> None:
        """Clear pending events (after persistence)."""
        self._events.clear()
