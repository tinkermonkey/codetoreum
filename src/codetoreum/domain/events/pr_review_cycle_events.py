"""PR Review Cycle domain events for automated code review and verification.

Events track the lifecycle of the PR review cycle where AI agents iteratively
review code, verify against context sources, check CI status, and consolidate
findings into actionable results.

The PR review cycle executes in four phases:
1. Code Review: Initial PR analysis by code review agent
2. Verification (2.x): Verification against each context source
3. CI Check: Optional CI/CD pipeline status validation
4. Consolidation: Synthesis of findings and outcome determination

**Immutability**: All events are immutable (frozen dataclasses) to maintain
event sourcing audit trail integrity. Events represent immutable facts
about review execution and outcomes—they cannot be modified after creation.
"""

from dataclasses import dataclass
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class PRReviewCycleStartedEvent(CodetoreumEvent):
    """Emitted when PR review cycle starts.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Attempting to modify any field will raise `FrozenInstanceError`.

    Attributes:
        type (str): Fixed to "pr_review_cycle.started"
        pr_id (str): GitHub PR identifier
        work_item_id (str): Work item being reviewed
        cycle_number (int): Iteration number (1-based) for outer re-trigger
        max_outer_cycles (int): Maximum cycles allowed before escalation
        verifier_context_sources (tuple[str, ...]): Context sources for verification
        phases_planned (int): Number of phases planned for this cycle
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp when cycle started
    """

    pr_id: str = ""
    work_item_id: str = ""
    cycle_number: int = 0
    max_outer_cycles: int = 0
    verifier_context_sources: tuple[str, ...] = ()
    phases_planned: int = 0
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if self.cycle_number < 1:
            msg = "cycle_number must be >= 1"
            raise ValueError(msg)
        if self.max_outer_cycles < 1:
            msg = "max_outer_cycles must be >= 1"
            raise ValueError(msg)
        if not self.verifier_context_sources:
            msg = "verifier_context_sources must not be empty"
            raise ValueError(msg)
        if self.phases_planned < 1:
            msg = "phases_planned must be >= 1"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "work_item_id": self.work_item_id,
                "cycle_number": self.cycle_number,
                "max_outer_cycles": self.max_outer_cycles,
                "verifier_context_sources": list(self.verifier_context_sources),
                "phases_planned": self.phases_planned,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleStartedEvent":
        """Deserialize from dictionary with backward compatibility."""
        verifier_context_sources = tuple(data.get("verifier_context_sources", []))
        return cls(
            type=data.get("type", "pr_review_cycle.started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            work_item_id=data.get("work_item_id", ""),
            cycle_number=data.get("cycle_number", 0),
            max_outer_cycles=data.get("max_outer_cycles", 0),
            verifier_context_sources=verifier_context_sources,
            phases_planned=data.get("phases_planned", 0),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCyclePhaseStartedEvent(CodetoreumEvent):
    """Emitted when any PR review cycle phase starts.

    Unified event for phase initiation, replacing phase-specific events.
    Emitted at the beginning of each phase (code review, verification, CI check, consolidation).

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.phase_started"
        pr_id (str): GitHub PR identifier
        phase_name (str): Name of the phase starting (e.g., "code_review", "verification", "ci_check", "consolidation")
        phase_index (int): Position in phase sequence (1-based)
        agent_id (str): ID of the agent executing this phase
        context_source (str): Context source for this phase (e.g., "pr_diff", "parent_issue", "ba_output", None for CI/consolidation)
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    phase_name: str = ""
    phase_index: int = 0
    agent_id: str = ""
    context_source: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if not self.phase_name:
            msg = "phase_name is required"
            raise ValueError(msg)
        if self.phase_index < 1:
            msg = "phase_index must be >= 1"
            raise ValueError(msg)
        if not self.agent_id:
            msg = "agent_id is required"
            raise ValueError(msg)
        if not isinstance(self.context_source, str):
            msg = "context_source must be a string"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "phase_name": self.phase_name,
                "phase_index": self.phase_index,
                "agent_id": self.agent_id,
                "context_source": self.context_source,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCyclePhaseStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.phase_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            phase_name=data.get("phase_name", ""),
            phase_index=data.get("phase_index", 0),
            agent_id=data.get("agent_id", ""),
            context_source=data.get("context_source", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCycleCodeReviewStartedEvent(CodetoreumEvent):
    """Emitted when Phase 1 code review starts.

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.code_review_started"
        pr_id (str): GitHub PR identifier
        workflow_run_id (str): ID of the workflow run
        timeout_seconds (int): Timeout for code review (in seconds)
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    workflow_run_id: str = ""
    timeout_seconds: int = 0

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)
        if self.timeout_seconds <= 0:
            msg = "timeout_seconds must be > 0"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "workflow_run_id": self.workflow_run_id,
                "timeout_seconds": self.timeout_seconds,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleCodeReviewStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.code_review_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
            timeout_seconds=data.get("timeout_seconds", 0),
        )


@dataclass(frozen=True)
class PRReviewCycleVerificationStartedEvent(CodetoreumEvent):
    """Emitted when Phase 2 verification starts for a context source.

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.verification_started"
        pr_id (str): GitHub PR identifier
        context_source (str): The context source being verified (e.g., "parent_issue")
        source_index (int): Position in verification sequence (1-based)
        total_sources (int): Total number of context sources
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    context_source: str = ""
    source_index: int = 0
    total_sources: int = 0
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if not self.context_source:
            msg = "context_source is required"
            raise ValueError(msg)
        if self.source_index < 1:
            msg = "source_index must be >= 1"
            raise ValueError(msg)
        if self.total_sources < 1:
            msg = "total_sources must be >= 1"
            raise ValueError(msg)
        if self.source_index > self.total_sources:
            msg = "source_index cannot exceed total_sources"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "context_source": self.context_source,
                "source_index": self.source_index,
                "total_sources": self.total_sources,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleVerificationStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.verification_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            context_source=data.get("context_source", ""),
            source_index=data.get("source_index", 0),
            total_sources=data.get("total_sources", 0),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCycleCICheckCompletedEvent(CodetoreumEvent):
    """Emitted when Phase 3 CI check completes.

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.ci_check_completed"
        pr_id (str): GitHub PR identifier
        ci_passed (bool): Whether CI check passed
        failures_count (int): Number of failing CI checks
        pending_count (int): Number of pending CI checks
        duration_seconds (float): Time taken for CI check
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    ci_passed: bool = False
    failures_count: int = 0
    pending_count: int = 0
    duration_seconds: float = 0.0
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if self.failures_count < 0:
            msg = "failures_count must be non-negative"
            raise ValueError(msg)
        if self.pending_count < 0:
            msg = "pending_count must be non-negative"
            raise ValueError(msg)
        if self.duration_seconds < 0:
            msg = "duration_seconds must be non-negative"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "ci_passed": self.ci_passed,
                "failures_count": self.failures_count,
                "pending_count": self.pending_count,
                "duration_seconds": self.duration_seconds,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleCICheckCompletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.ci_check_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            ci_passed=data.get("ci_passed", False),
            failures_count=data.get("failures_count", 0),
            pending_count=data.get("pending_count", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCycleConsolidationStartedEvent(CodetoreumEvent):
    """Emitted when Phase 4 consolidation starts.

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.consolidation_started"
        pr_id (str): GitHub PR identifier
        finding_count (int): Number of findings to consolidate
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    finding_count: int = 0
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if self.finding_count < 0:
            msg = "finding_count must be non-negative"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "finding_count": self.finding_count,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleConsolidationStartedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.consolidation_started"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            finding_count=data.get("finding_count", 0),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCycleApprovedEvent(CodetoreumEvent):
    """Emitted when PR is approved (no issues found).

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.approved"
        pr_id (str): GitHub PR identifier
        cycle_number (int): Iteration number (1-based)
        cycle_duration_seconds (float): Total time for this cycle
        next_column (str): Column to move item to
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    cycle_number: int = 0
    cycle_duration_seconds: float = 0.0
    next_column: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if self.cycle_number < 1:
            msg = "cycle_number must be >= 1"
            raise ValueError(msg)
        if self.cycle_duration_seconds < 0:
            msg = "cycle_duration_seconds must be non-negative"
            raise ValueError(msg)
        if not self.next_column:
            msg = "next_column is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "cycle_number": self.cycle_number,
                "cycle_duration_seconds": self.cycle_duration_seconds,
                "next_column": self.next_column,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleApprovedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.approved"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            cycle_number=data.get("cycle_number", 0),
            cycle_duration_seconds=data.get("cycle_duration_seconds", 0.0),
            next_column=data.get("next_column", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCycleIssuesFoundEvent(CodetoreumEvent):
    """Emitted when issues are found in review.

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.issues_found"
        pr_id (str): GitHub PR identifier
        cycle_number (int): Iteration number (1-based)
        finding_count (int): Total number of findings
        critical_count (int): Number of critical severity findings
        high_count (int): Number of high severity findings
        medium_count (int): Number of medium severity findings
        low_count (int): Number of low severity findings
        sub_issue_count (int): Number of created sub-issues
        cycle_duration_seconds (float): Total time for this cycle
        next_column (str): Column to move item to
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    cycle_number: int = 0
    finding_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    sub_issue_count: int = 0
    cycle_duration_seconds: float = 0.0
    next_column: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if self.cycle_number < 1:
            msg = "cycle_number must be >= 1"
            raise ValueError(msg)
        if self.finding_count < 1:
            msg = "finding_count must be >= 1 when issues found"
            raise ValueError(msg)
        if self.critical_count < 0:
            msg = "critical_count must be non-negative"
            raise ValueError(msg)
        if self.high_count < 0:
            msg = "high_count must be non-negative"
            raise ValueError(msg)
        if self.medium_count < 0:
            msg = "medium_count must be non-negative"
            raise ValueError(msg)
        if self.low_count < 0:
            msg = "low_count must be non-negative"
            raise ValueError(msg)
        severity_total = self.critical_count + self.high_count + self.medium_count + self.low_count
        if severity_total != self.finding_count:
            msg = f"Severity counts ({severity_total}) must sum to finding_count ({self.finding_count})"
            raise ValueError(msg)
        if self.sub_issue_count < 1:
            msg = "sub_issue_count must be >= 1 when issues found"
            raise ValueError(msg)
        if self.cycle_duration_seconds < 0:
            msg = "cycle_duration_seconds must be non-negative"
            raise ValueError(msg)
        if not self.next_column:
            msg = "next_column is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "cycle_number": self.cycle_number,
                "finding_count": self.finding_count,
                "critical_count": self.critical_count,
                "high_count": self.high_count,
                "medium_count": self.medium_count,
                "low_count": self.low_count,
                "sub_issue_count": self.sub_issue_count,
                "cycle_duration_seconds": self.cycle_duration_seconds,
                "next_column": self.next_column,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleIssuesFoundEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.issues_found"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            cycle_number=data.get("cycle_number", 0),
            finding_count=data.get("finding_count", 0),
            critical_count=data.get("critical_count", 0),
            high_count=data.get("high_count", 0),
            medium_count=data.get("medium_count", 0),
            low_count=data.get("low_count", 0),
            sub_issue_count=data.get("sub_issue_count", 0),
            cycle_duration_seconds=data.get("cycle_duration_seconds", 0.0),
            next_column=data.get("next_column", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCycleMaxCyclesReachedEvent(CodetoreumEvent):
    """Emitted when maximum review cycles reached.

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.max_cycles_reached"
        pr_id (str): GitHub PR identifier
        cycle_number (int): Iteration number (1-based) that exceeded limit
        max_outer_cycles (int): Maximum cycles configured
        next_column (str): Column to move item to (escalation column)
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    cycle_number: int = 0
    max_outer_cycles: int = 0
    next_column: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if self.cycle_number < 1:
            msg = "cycle_number must be >= 1"
            raise ValueError(msg)
        if self.max_outer_cycles < 1:
            msg = "max_outer_cycles must be >= 1"
            raise ValueError(msg)
        if self.cycle_number <= self.max_outer_cycles:
            msg = "cycle_number must exceed max_outer_cycles"
            raise ValueError(msg)
        if not self.next_column:
            msg = "next_column is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "cycle_number": self.cycle_number,
                "max_outer_cycles": self.max_outer_cycles,
                "next_column": self.next_column,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleMaxCyclesReachedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.max_cycles_reached"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            cycle_number=data.get("cycle_number", 0),
            max_outer_cycles=data.get("max_outer_cycles", 0),
            next_column=data.get("next_column", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCycleEscalatedEvent(CodetoreumEvent):
    """Emitted when cycle is escalated to human reviewer.

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.escalated"
        pr_id (str): GitHub PR identifier
        reason (str): Reason for escalation (e.g., "max_cycles_reached")
        cycle_number (int): Iteration number when escalation occurred
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    reason: str = ""
    cycle_number: int = 0
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if not self.reason:
            msg = "reason is required"
            raise ValueError(msg)
        if self.cycle_number < 1:
            msg = "cycle_number must be >= 1"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "reason": self.reason,
                "cycle_number": self.cycle_number,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleEscalatedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.escalated"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            reason=data.get("reason", ""),
            cycle_number=data.get("cycle_number", 0),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCycleSubIssuesCreatedEvent(CodetoreumEvent):
    """Emitted when sub-issues are created during PR review cycle.

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.sub_issues_created"
        pr_id (str): GitHub PR identifier
        cycle_number (int): Iteration number (1-based)
        count (int): Number of sub-issues created
        sub_issue_ids (tuple[str, ...]): IDs of created sub-issues
        target_board (str): Board ID where sub-issues were created
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    cycle_number: int = 0
    count: int = 0
    sub_issue_ids: tuple[str, ...] = ()
    target_board: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if self.cycle_number < 1:
            msg = "cycle_number must be >= 1"
            raise ValueError(msg)
        if self.count < 1:
            msg = "count must be >= 1 when sub-issues created"
            raise ValueError(msg)
        if len(self.sub_issue_ids) != self.count:
            msg = f"sub_issue_ids count ({len(self.sub_issue_ids)}) must match count ({self.count})"
            raise ValueError(msg)
        if not self.target_board:
            msg = "target_board is required"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "cycle_number": self.cycle_number,
                "count": self.count,
                "sub_issue_ids": list(self.sub_issue_ids),
                "target_board": self.target_board,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleSubIssuesCreatedEvent":
        """Deserialize from dictionary."""
        sub_issue_ids = tuple(data.get("sub_issue_ids", []))
        return cls(
            type=data.get("type", "pr_review_cycle.sub_issues_created"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            cycle_number=data.get("cycle_number", 0),
            count=data.get("count", 0),
            sub_issue_ids=sub_issue_ids,
            target_board=data.get("target_board", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCyclePhaseCompletedEvent(CodetoreumEvent):
    """Emitted when a PR review cycle phase completes.

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.phase_completed"
        pr_id (str): GitHub PR identifier
        phase_name (str): Name of the completed phase
        phase_index (int): Position in phase sequence (1-based)
        findings_count (int): Number of findings in this phase
        comment_id (str): ID of comment associated with phase (if any)
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    phase_name: str = ""
    phase_index: int = 0
    findings_count: int = 0
    comment_id: str = ""
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if not self.phase_name:
            msg = "phase_name is required"
            raise ValueError(msg)
        if self.phase_index < 1:
            msg = "phase_index must be >= 1"
            raise ValueError(msg)
        if self.findings_count < 0:
            msg = "findings_count must be non-negative"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "phase_name": self.phase_name,
                "phase_index": self.phase_index,
                "findings_count": self.findings_count,
                "comment_id": self.comment_id,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCyclePhaseCompletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.phase_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            phase_name=data.get("phase_name", ""),
            phase_index=data.get("phase_index", 0),
            findings_count=data.get("findings_count", 0),
            comment_id=data.get("comment_id", ""),
            workflow_run_id=data.get("workflow_run_id", ""),
        )


@dataclass(frozen=True)
class PRReviewCycleConsolidationCompletedEvent(CodetoreumEvent):
    """Emitted when PR review cycle consolidation phase completes.

    **Immutability**: This is an immutable event (frozen dataclass).

    Attributes:
        type (str): Fixed to "pr_review_cycle.consolidation_completed"
        pr_id (str): GitHub PR identifier
        total_findings (int): Total number of findings across all phases
        critical_count (int): Number of critical severity findings
        high_count (int): Number of high severity findings
        medium_count (int): Number of medium severity findings
        low_count (int): Number of low severity findings
        consolidation_duration_seconds (float): Time taken for consolidation
        workflow_run_id (str): ID of the workflow run
        timestamp (str): ISO 8601 timestamp
    """

    pr_id: str = ""
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    consolidation_duration_seconds: float = 0.0
    workflow_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if self.total_findings < 0:
            msg = "total_findings must be non-negative"
            raise ValueError(msg)
        if self.critical_count < 0:
            msg = "critical_count must be non-negative"
            raise ValueError(msg)
        if self.high_count < 0:
            msg = "high_count must be non-negative"
            raise ValueError(msg)
        if self.medium_count < 0:
            msg = "medium_count must be non-negative"
            raise ValueError(msg)
        if self.low_count < 0:
            msg = "low_count must be non-negative"
            raise ValueError(msg)
        severity_total = self.critical_count + self.high_count + self.medium_count + self.low_count
        if severity_total != self.total_findings:
            msg = f"Severity counts ({severity_total}) must sum to total_findings ({self.total_findings})"
            raise ValueError(msg)
        if self.consolidation_duration_seconds < 0:
            msg = "consolidation_duration_seconds must be non-negative"
            raise ValueError(msg)
        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update(
            {
                "pr_id": self.pr_id,
                "total_findings": self.total_findings,
                "critical_count": self.critical_count,
                "high_count": self.high_count,
                "medium_count": self.medium_count,
                "low_count": self.low_count,
                "consolidation_duration_seconds": self.consolidation_duration_seconds,
                "workflow_run_id": self.workflow_run_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PRReviewCycleConsolidationCompletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "pr_review_cycle.consolidation_completed"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            pr_id=data.get("pr_id", ""),
            total_findings=data.get("total_findings", 0),
            critical_count=data.get("critical_count", 0),
            high_count=data.get("high_count", 0),
            medium_count=data.get("medium_count", 0),
            low_count=data.get("low_count", 0),
            consolidation_duration_seconds=data.get("consolidation_duration_seconds", 0.0),
            workflow_run_id=data.get("workflow_run_id", ""),
        )
