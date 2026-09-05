"""Review cycle domain events for maker-checker review orchestration.

Events track the lifecycle and state transitions of review cycles,
capturing the maker-checker feedback loop from initialization through
completion or escalation.

**Event Immutability**: All events are frozen dataclasses. This is a
foundational architectural principle ensuring event sourcing audit trail
integrity. Events represent immutable facts about state changes—they
cannot and must not be modified after creation. Attempting to modify
any field will raise `FrozenInstanceError`. This immutability guarantee
is critical for maintaining a reliable event sourcing system where events
serve as the single source of truth for the system's history.
"""

from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class ReviewCycleStartedEvent(CodetoreumEvent):
    """Emitted when a review cycle begins.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.started"
        review_cycle_id (str): Unique identifier for this review cycle
        work_item_id (str): ID of the work item being reviewed
        project_id (str): ID of the project
        maker_agent (str): Name of the maker (development) agent
        reviewer_agent (str): Name of the reviewer (code review) agent
        max_iterations (int): Maximum iterations before escalation

    Example:
        >>> event = ReviewCycleStartedEvent(
        ...     type="review_cycle.started",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock_adapter",
        ...     review_cycle_id="cycle-1",
        ...     work_item_id="item-1",
        ...     project_id="proj-1",
        ...     maker_agent="junior_dev",
        ...     reviewer_agent="senior_dev",
        ...     max_iterations=3
        ... )
    """

    review_cycle_id: str = ""
    work_item_id: str = ""
    project_id: str = ""
    maker_agent: str = ""
    reviewer_agent: str = ""
    max_iterations: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.maker_agent:
            msg = "maker_agent is required"
            raise ValueError(msg)
        if not self.reviewer_agent:
            msg = "reviewer_agent is required"
            raise ValueError(msg)
        if self.max_iterations <= 0:
            msg = "max_iterations must be greater than 0"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "work_item_id": self.work_item_id,
                "project_id": self.project_id,
                "maker_agent": self.maker_agent,
                "reviewer_agent": self.reviewer_agent,
                "max_iterations": self.max_iterations,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleStartedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (review_cycle_id, work_item_id, project_id,
                     maker_agent, reviewer_agent, max_iterations) are missing.
        """
        return cls(
            type=data.get("type", "review_cycle.started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            work_item_id=data["work_item_id"],
            project_id=data["project_id"],
            maker_agent=data["maker_agent"],
            reviewer_agent=data["reviewer_agent"],
            max_iterations=data["max_iterations"],
        )


@dataclass(frozen=True)
class ReviewCycleIterationCompletedEvent(CodetoreumEvent):
    """Emitted when a review iteration completes.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.iteration_completed"
        review_cycle_id (str): ID of the review cycle
        work_item_id (str): ID of the work item being reviewed
        iteration (int): Iteration number (1-indexed)
        status (Literal): Review decision ("APPROVED", "CHANGES_REQUESTED", "BLOCKED")
        blocking_count (int): Number of blocking findings in this iteration

    Example:
        >>> event = ReviewCycleIterationCompletedEvent(
        ...     type="review_cycle.iteration_completed",
        ...     timestamp="2025-01-14T10:35:00+00:00",
        ...     source="mock_adapter",
        ...     review_cycle_id="cycle-1",
        ...     work_item_id="item-1",
        ...     iteration=1,
        ...     status="CHANGES_REQUESTED",
        ...     blocking_count=0
        ... )
    """

    review_cycle_id: str = ""
    work_item_id: str = ""
    iteration: int = 0
    status: Literal["APPROVED", "CHANGES_REQUESTED", "BLOCKED"] = "APPROVED"
    blocking_count: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        if self.iteration <= 0:
            msg = "iteration must be greater than 0"
            raise ValueError(msg)
        valid_statuses = {"APPROVED", "CHANGES_REQUESTED", "BLOCKED"}
        if self.status not in valid_statuses:
            msg = f"status must be one of {valid_statuses}, got {self.status}"
            raise ValueError(msg)
        if self.blocking_count < 0:
            msg = "blocking_count must be non-negative"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "work_item_id": self.work_item_id,
                "iteration": self.iteration,
                "status": self.status,
                "blocking_count": self.blocking_count,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleIterationCompletedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (review_cycle_id, iteration, status) are missing.
        """
        return cls(
            type=data.get("type", "review_cycle.iteration_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            work_item_id=data.get("work_item_id", ""),
            iteration=data["iteration"],
            status=data["status"],
            blocking_count=data.get("blocking_count", 0),
        )


@dataclass(frozen=True)
class ReviewCycleMakerRevisionEvent(CodetoreumEvent):
    """Emitted when maker completes a revision.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.maker_revision"
        review_cycle_id (str): ID of the review cycle
        work_item_id (str): ID of the work item being revised
        iteration (int): Iteration number (1-indexed)

    Example:
        >>> event = ReviewCycleMakerRevisionEvent(
        ...     type="review_cycle.maker_revision",
        ...     timestamp="2025-01-14T10:40:00+00:00",
        ...     source="mock_adapter",
        ...     review_cycle_id="cycle-1",
        ...     work_item_id="item-1",
        ...     iteration=1
        ... )
    """

    review_cycle_id: str = ""
    work_item_id: str = ""
    iteration: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        if self.iteration <= 0:
            msg = "iteration must be greater than 0"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "work_item_id": self.work_item_id,
                "iteration": self.iteration,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleMakerRevisionEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (review_cycle_id, work_item_id,
                     iteration) are missing.
        """
        return cls(
            type=data.get("type", "review_cycle.maker_revision"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            work_item_id=data["work_item_id"],
            iteration=data["iteration"],
        )


@dataclass(frozen=True)
class ReviewCycleEscalatedToHumanEvent(CodetoreumEvent):
    """Emitted when review is blocked and escalated to human.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.escalated_to_human"
        review_cycle_id (str): ID of the review cycle
        work_item_id (str): ID of the work item
        iteration (int): Iteration when escalation occurred
        blocking_count (int): Number of blocking findings
        escalation_reason (str): Reason for escalation (BLOCKED or MAX_ITERATIONS)

    Example:
        >>> event = ReviewCycleEscalatedToHumanEvent(
        ...     type="review_cycle.escalated_to_human",
        ...     timestamp="2025-01-14T10:45:00+00:00",
        ...     source="mock_adapter",
        ...     review_cycle_id="cycle-1",
        ...     work_item_id="item-1",
        ...     iteration=3,
        ...     blocking_count=2,
        ...     escalation_reason="BLOCKED"
        ... )
    """

    review_cycle_id: str = ""
    work_item_id: str = ""
    iteration: int = 0
    blocking_count: int = 0
    escalation_reason: Literal["BLOCKED", "MAX_ITERATIONS"] = ""  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        valid_reasons = {"BLOCKED", "MAX_ITERATIONS"}
        if self.escalation_reason not in valid_reasons:
            msg = f"escalation_reason must be one of {valid_reasons}, got {self.escalation_reason}"
            raise ValueError(msg)
        if self.blocking_count < 0:
            msg = "blocking_count must be non-negative"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "work_item_id": self.work_item_id,
                "iteration": self.iteration,
                "blocking_count": self.blocking_count,
                "escalation_reason": self.escalation_reason,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleEscalatedToHumanEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (review_cycle_id, work_item_id,
                     iteration, escalation_reason) are missing.
        """
        return cls(
            type=data.get("type", "review_cycle.escalated_to_human"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            work_item_id=data["work_item_id"],
            iteration=data["iteration"],
            blocking_count=data.get("blocking_count", 0),
            escalation_reason=data["escalation_reason"],
        )


@dataclass(frozen=True)
class ReviewCycleHumanFeedbackReceivedEvent(CodetoreumEvent):
    """Emitted when human feedback is detected on an escalated cycle.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.human_feedback_received"
        review_cycle_id (str): ID of the review cycle
        work_item_id (str): ID of the work item
        feedback (str): The human feedback provided

    Example:
        >>> event = ReviewCycleHumanFeedbackReceivedEvent(
        ...     type="review_cycle.human_feedback_received",
        ...     timestamp="2025-01-14T11:00:00+00:00",
        ...     source="mock_adapter",
        ...     review_cycle_id="cycle-1",
        ...     work_item_id="item-1",
        ...     feedback="Use async/await pattern instead"
        ... )
    """

    review_cycle_id: str = ""
    work_item_id: str = ""
    feedback: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        if not self.feedback:
            msg = "feedback is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "work_item_id": self.work_item_id,
                "feedback": self.feedback,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleHumanFeedbackReceivedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (review_cycle_id, work_item_id,
                     feedback) are missing.
        """
        return cls(
            type=data.get("type", "review_cycle.human_feedback_received"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            work_item_id=data["work_item_id"],
            feedback=data["feedback"],
        )


@dataclass(frozen=True)
class ReviewCycleMaxIterationsReachedEvent(CodetoreumEvent):
    """Emitted when max iterations reached without approval.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.max_iterations_reached"
        review_cycle_id (str): ID of the review cycle
        work_item_id (str): ID of the work item
        max_iterations (int): Maximum iterations configured

    Example:
        >>> event = ReviewCycleMaxIterationsReachedEvent(
        ...     type="review_cycle.max_iterations_reached",
        ...     timestamp="2025-01-14T11:05:00+00:00",
        ...     source="mock_adapter",
        ...     review_cycle_id="cycle-1",
        ...     work_item_id="item-1",
        ...     max_iterations=3
        ... )
    """

    review_cycle_id: str = ""
    work_item_id: str = ""
    max_iterations: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        if self.max_iterations <= 0:
            msg = "max_iterations must be greater than 0"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "work_item_id": self.work_item_id,
                "max_iterations": self.max_iterations,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleMaxIterationsReachedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (review_cycle_id, work_item_id,
                     max_iterations) are missing.
        """
        return cls(
            type=data.get("type", "review_cycle.max_iterations_reached"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            work_item_id=data["work_item_id"],
            max_iterations=data["max_iterations"],
        )


@dataclass(frozen=True)
class ReviewCycleApprovedEvent(CodetoreumEvent):
    """Emitted when review cycle completes with approval.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.approved"
        review_cycle_id (str): ID of the review cycle
        work_item_id (str): ID of the work item
        total_iterations (int): Number of iterations completed

    Example:
        >>> event = ReviewCycleApprovedEvent(
        ...     type="review_cycle.approved",
        ...     timestamp="2025-01-14T11:10:00+00:00",
        ...     source="mock_adapter",
        ...     review_cycle_id="cycle-1",
        ...     work_item_id="item-1",
        ...     total_iterations=2
        ... )
    """

    review_cycle_id: str = ""
    work_item_id: str = ""
    total_iterations: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        if self.total_iterations <= 0:
            msg = "total_iterations must be greater than 0"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "work_item_id": self.work_item_id,
                "total_iterations": self.total_iterations,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleApprovedEvent":
        """Deserialize from dictionary.

        Raises:
            KeyError: If required fields (review_cycle_id, work_item_id,
                     total_iterations) are missing.
        """
        return cls(
            type=data.get("type", "review_cycle.approved"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            work_item_id=data.get("work_item_id", ""),
            total_iterations=data["total_iterations"],
        )


@dataclass(frozen=True)
class ReviewCycleCreatedEvent(CodetoreumEvent):
    """Emitted when a review cycle is created.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.created"
        review_cycle_id (str): Unique identifier for this review cycle
        workflow_id (str): ID of the workflow this cycle belongs to
        stage_name (str): Name of the workflow stage
        maker_agent_id (str): ID of the maker agent
        reviewer_agent_id (str): ID of the reviewer agent
        max_iterations (int): Maximum iterations before escalation
        source (str): Always "review_service"
    """

    review_cycle_id: str = ""
    workflow_id: str = ""
    stage_name: str = ""
    maker_agent_id: str = ""
    reviewer_agent_id: str = ""
    max_iterations: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        if not self.workflow_id:
            msg = "workflow_id is required"
            raise ValueError(msg)
        if not self.stage_name:
            msg = "stage_name is required"
            raise ValueError(msg)
        if not self.maker_agent_id:
            msg = "maker_agent_id is required"
            raise ValueError(msg)
        if not self.reviewer_agent_id:
            msg = "reviewer_agent_id is required"
            raise ValueError(msg)
        if self.max_iterations <= 0:
            msg = "max_iterations must be greater than 0"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "workflow_id": self.workflow_id,
                "stage_name": self.stage_name,
                "maker_agent_id": self.maker_agent_id,
                "reviewer_agent_id": self.reviewer_agent_id,
                "max_iterations": self.max_iterations,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleCreatedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "review_cycle.created"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "review_service"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            workflow_id=data["workflow_id"],
            stage_name=data["stage_name"],
            maker_agent_id=data["maker_agent_id"],
            reviewer_agent_id=data["reviewer_agent_id"],
            max_iterations=data["max_iterations"],
        )


@dataclass(frozen=True)
class ReviewCycleIterationStartedEvent(CodetoreumEvent):
    """Emitted when a new review iteration begins.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.iteration_started"
        review_cycle_id (str): ID of the review cycle
        iteration_number (int): The iteration number (1-indexed)
        maker_execution_id (str): Execution ID of the maker's run
        source (str): Always "review_service"
    """

    review_cycle_id: str = ""
    iteration_number: int = 0
    maker_execution_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        if self.iteration_number <= 0:
            msg = "iteration_number must be greater than 0"
            raise ValueError(msg)
        if not self.maker_execution_id:
            msg = "maker_execution_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "iteration_number": self.iteration_number,
                "maker_execution_id": self.maker_execution_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleIterationStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "review_cycle.iteration_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "review_service"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            iteration_number=data["iteration_number"],
            maker_execution_id=data["maker_execution_id"],
        )


@dataclass(frozen=True)
class ReviewCycleFeedbackSubmittedEvent(CodetoreumEvent):
    """Emitted when reviewer provides feedback on an iteration.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.feedback_submitted"
        review_cycle_id (str): ID of the review cycle
        iteration_number (int): The iteration number (1-indexed)
        decision (str): Reviewer decision ("approve", "request_changes", "escalate")
        reviewer_execution_id (str): Execution ID of the reviewer's run
        issues_count (int): Number of issues found
        source (str): Always "review_service"
    """

    review_cycle_id: str = ""
    iteration_number: int = 0
    decision: str = ""
    reviewer_execution_id: str = ""
    issues_count: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        if self.iteration_number <= 0:
            msg = "iteration_number must be greater than 0"
            raise ValueError(msg)
        if not self.decision:
            msg = "decision is required"
            raise ValueError(msg)
        if not self.reviewer_execution_id:
            msg = "reviewer_execution_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "iteration_number": self.iteration_number,
                "decision": self.decision,
                "reviewer_execution_id": self.reviewer_execution_id,
                "issues_count": self.issues_count,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleFeedbackSubmittedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "review_cycle.feedback_submitted"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "review_service"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            iteration_number=data["iteration_number"],
            decision=data["decision"],
            reviewer_execution_id=data["reviewer_execution_id"],
            issues_count=data.get("issues_count", 0),
        )


@dataclass(frozen=True)
class ReviewCycleRejectedEvent(CodetoreumEvent):
    """Emitted when a review cycle is rejected (max iterations reached).

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity.

    Attributes:
        type (str): Fixed to "review_cycle.rejected"
        review_cycle_id (str): ID of the review cycle
        final_iteration (int): The final iteration number
        rejection_reason (str): Reason for rejection
        source (str): Always "review_service"
    """

    review_cycle_id: str = ""
    final_iteration: int = 0
    rejection_reason: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.review_cycle_id:
            msg = "review_cycle_id is required"
            raise ValueError(msg)
        if self.final_iteration <= 0:
            msg = "final_iteration must be greater than 0"
            raise ValueError(msg)
        if not self.rejection_reason:
            msg = "rejection_reason is required"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "review_cycle_id": self.review_cycle_id,
                "final_iteration": self.final_iteration,
                "rejection_reason": self.rejection_reason,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewCycleRejectedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "review_cycle.rejected"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", "review_service"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            review_cycle_id=data["review_cycle_id"],
            final_iteration=data["final_iteration"],
            rejection_reason=data["rejection_reason"],
        )
