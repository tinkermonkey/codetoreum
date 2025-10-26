# Review Cycle Domain Design

## Overview

Review Cycle is an aggregate root managing iterative maker-checker review processes within workflows.

## Domain Model

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from uuid import uuid4

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

@dataclass
class ReviewFeedback:
    """Value object for review feedback."""
    decision: ReviewDecision
    comment: str
    issues: List[str]
    suggestions: List[str]
    timestamp: datetime

@dataclass
class ReviewIteration:
    """Single iteration of maker-reviewer cycle."""
    iteration_number: int
    maker_output: str
    maker_execution_id: str
    reviewer_feedback: Optional[ReviewFeedback]
    reviewer_execution_id: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]

@dataclass
class ReviewCycle:
    """
    Review Cycle aggregate root.

    Manages iterative maker-checker review process.
    """

    # Identity
    id: str
    workflow_id: str
    stage_name: str

    # Agents
    maker_agent_id: str
    reviewer_agent_id: str

    # Configuration
    max_iterations: int

    # Status
    status: ReviewStatus
    current_iteration: int

    # Iterations
    iterations: List[ReviewIteration]

    # Final decision
    final_decision: Optional[ReviewDecision]
    escalation_reason: Optional[str]

    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    # Event tracking
    _events: List[DomainEvent] = field(default_factory=list, init=False, repr=False)
    _version: int = field(default=0, init=False, repr=False)

    def __post_init__(self):
        """Validate invariants."""
        if self.maker_agent_id == self.reviewer_agent_id:
            raise DomainError("Maker and reviewer must be different agents")

        if self.max_iterations <= 0:
            raise DomainError("Max iterations must be positive")

    @classmethod
    def create(cls,
               workflow_id: str,
               stage_name: str,
               maker_agent_id: str,
               reviewer_agent_id: str,
               max_iterations: int = 3) -> 'ReviewCycle':
        """Create new review cycle."""
        cycle = cls(
            id=str(uuid4()),
            workflow_id=workflow_id,
            stage_name=stage_name,
            maker_agent_id=maker_agent_id,
            reviewer_agent_id=reviewer_agent_id,
            max_iterations=max_iterations,
            status=ReviewStatus.PENDING,
            current_iteration=0,
            iterations=[],
            final_decision=None,
            escalation_reason=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=None
        )

        event = ReviewCycleCreated(
            aggregate_id=cycle.id,
            aggregate_type="ReviewCycle",
            payload={
                "workflow_id": workflow_id,
                "stage_name": stage_name,
                "maker_agent_id": maker_agent_id,
                "reviewer_agent_id": reviewer_agent_id,
                "max_iterations": max_iterations
            }
        )
        cycle._add_event(event)

        return cycle

    def start_iteration(self, maker_output: str, maker_execution_id: str) -> None:
        """Start new iteration with maker's output."""
        if self.current_iteration >= self.max_iterations:
            raise DomainError(f"Exceeded max iterations ({self.max_iterations})")

        self.current_iteration += 1
        iteration = ReviewIteration(
            iteration_number=self.current_iteration,
            maker_output=maker_output,
            maker_execution_id=maker_execution_id,
            reviewer_feedback=None,
            reviewer_execution_id=None,
            started_at=datetime.utcnow(),
            completed_at=None
        )

        self.iterations.append(iteration)
        self.status = ReviewStatus.IN_PROGRESS
        self.updated_at = datetime.utcnow()
        self._version += 1

        event = ReviewIterationStarted(
            aggregate_id=self.id,
            aggregate_type="ReviewCycle",
            payload={
                "iteration_number": self.current_iteration,
                "maker_execution_id": maker_execution_id
            }
        )
        self._add_event(event)

    def submit_review(self,
                     decision: ReviewDecision,
                     comment: str,
                     reviewer_execution_id: str,
                     issues: Optional[List[str]] = None,
                     suggestions: Optional[List[str]] = None) -> None:
        """Submit reviewer's feedback."""
        if not self.iterations:
            raise DomainError("No iterations to review")

        current = self.iterations[-1]
        if current.reviewer_feedback:
            raise DomainError("Current iteration already reviewed")

        feedback = ReviewFeedback(
            decision=decision,
            comment=comment,
            issues=issues or [],
            suggestions=suggestions or [],
            timestamp=datetime.utcnow()
        )

        current.reviewer_feedback = feedback
        current.reviewer_execution_id = reviewer_execution_id
        current.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self._version += 1

        if decision == ReviewDecision.APPROVE:
            self.approve()
        elif decision == ReviewDecision.REQUEST_CHANGES:
            self.request_changes()
        elif decision == ReviewDecision.ESCALATE:
            self.escalate("Reviewer escalated")

        event = ReviewFeedbackSubmitted(
            aggregate_id=self.id,
            aggregate_type="ReviewCycle",
            payload={
                "iteration_number": self.current_iteration,
                "decision": decision.value,
                "reviewer_execution_id": reviewer_execution_id,
                "issues_count": len(issues or [])
            }
        )
        self._add_event(event)

    def approve(self) -> None:
        """Approve the review."""
        self.status = ReviewStatus.APPROVED
        self.final_decision = ReviewDecision.APPROVE
        self.completed_at = datetime.utcnow()
        self.updated_at = self.completed_at
        self._version += 1

        event = ReviewCycleApproved(
            aggregate_id=self.id,
            aggregate_type="ReviewCycle",
            payload={
                "total_iterations": self.current_iteration,
                "approved_at": self.completed_at.isoformat()
            }
        )
        self._add_event(event)

    def request_changes(self) -> None:
        """Request changes from maker."""
        if self.current_iteration >= self.max_iterations:
            self.escalate("Max iterations reached")
            return

        self.status = ReviewStatus.CHANGES_REQUESTED
        self.updated_at = datetime.utcnow()
        self._version += 1

    def escalate(self, reason: str) -> None:
        """Escalate to human review."""
        self.status = ReviewStatus.ESCALATED
        self.final_decision = ReviewDecision.ESCALATE
        self.escalation_reason = reason
        self.completed_at = datetime.utcnow()
        self.updated_at = self.completed_at
        self._version += 1

        event = ReviewCycleEscalated(
            aggregate_id=self.id,
            aggregate_type="ReviewCycle",
            payload={
                "reason": reason,
                "total_iterations": self.current_iteration,
                "escalated_at": self.completed_at.isoformat()
            }
        )
        self._add_event(event)

    def is_complete(self) -> bool:
        """Check if review cycle is complete."""
        return self.status in [ReviewStatus.APPROVED, ReviewStatus.ESCALATED]

    def needs_maker_revision(self) -> bool:
        """Check if maker needs to revise."""
        return self.status == ReviewStatus.CHANGES_REQUESTED

    def get_latest_feedback(self) -> Optional[ReviewFeedback]:
        """Get latest reviewer feedback."""
        if not self.iterations:
            return None
        return self.iterations[-1].reviewer_feedback

    def _add_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def get_pending_events(self) -> List[DomainEvent]:
        return self._events.copy()

    def clear_events(self) -> None:
        self._events.clear()
```

## Domain Events

- **ReviewCycleCreated**: Review cycle initialized
- **ReviewIterationStarted**: New iteration began
- **ReviewFeedbackSubmitted**: Reviewer provided feedback
- **ReviewCycleApproved**: Review approved
- **ReviewCycleEscalated**: Escalated to human

## Business Rules

1. Maker and reviewer must be different agents
2. Maximum 3 iterations by default
3. Auto-escalate if max iterations exceeded
4. Cannot approve without reviewer feedback
5. Each iteration requires both maker and reviewer execution

## Workflow Integration

```python
# In PipelineStage
if stage.requires_review:
    review_cycle = ReviewCycle.create(
        workflow_id=workflow.id,
        stage_name=stage.name,
        maker_agent_id=stage.maker_agent_id,
        reviewer_agent_id=stage.reviewer_agent_id
    )

    # Iteration loop
    while not review_cycle.is_complete():
        # Maker executes
        maker_output = execute_agent(review_cycle.maker_agent_id)
        review_cycle.start_iteration(maker_output, execution_id)

        # Reviewer evaluates
        feedback = execute_agent(review_cycle.reviewer_agent_id)
        review_cycle.submit_review(
            decision=feedback.decision,
            comment=feedback.comment,
            reviewer_execution_id=execution_id
        )
```

## Testing

```python
def test_review_cycle_approval():
    cycle = ReviewCycle.create("wf-1", "coding", "maker", "reviewer")

    cycle.start_iteration("output", "exec-1")
    cycle.submit_review(
        ReviewDecision.APPROVE,
        "Looks good",
        "exec-2"
    )

    assert cycle.is_complete()
    assert cycle.status == ReviewStatus.APPROVED

def test_max_iterations_escalation():
    cycle = ReviewCycle.create("wf-1", "coding", "maker", "reviewer", max_iterations=2)

    # Iteration 1
    cycle.start_iteration("output1", "exec-1")
    cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Fix this", "exec-2")

    # Iteration 2
    cycle.start_iteration("output2", "exec-3")
    cycle.submit_review(ReviewDecision.REQUEST_CHANGES, "Still issues", "exec-4")

    # Should escalate
    assert cycle.status == ReviewStatus.ESCALATED
```

## References

- **Pipeline Stage**: `pipeline_stage_design.md`
- **Agent Execution**: `agent_execution_design.md`
- **Value Objects**: `value_objects_design.md`
