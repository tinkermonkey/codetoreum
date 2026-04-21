"""PR Review Cycle domain types and value objects.

Establishes the foundational domain model for the PR review cycle, including enums,
value objects, and configuration types. All types are immutable (frozen dataclasses)
following the pure domain layer pattern with no external dependencies.

The PR review cycle automates code review through a four-phase pipeline:
1. Phase 1: Code Review Agent analyzes PR and provides initial review
2. Phase 2.x: Verifier Agent validates against specified context sources
3. Phase 3: CI/CD check validation (optional gate)
4. Phase 4: Consolidation Agent synthesizes findings and routes result

Tracks cycle count for outer re-trigger enforcement and enforces maximum cycles.

**Immutability Pattern**: All types use @dataclass(frozen=True) for immutability:
- Frozen dataclasses are hashable and thread-safe
- Tuples instead of lists for collection fields
- All fields are read-only after construction
- Attempting to modify raises FrozenInstanceError
- Events represent immutable facts in the audit trail

Reference: repair_cycle_types.py for enum and dataclass patterns
"""

from dataclasses import dataclass
from enum import Enum


class PRReviewOutcome(str, Enum):
    """Outcome of a PR review cycle.

    Represents the final result after all phases complete.

    **Enum Values:**
    - ISSUES_FOUND: Review identified issues requiring fixes (creates sub-issues)
    - APPROVED: PR approved without issues (progresses to next column)
    - MAX_CYCLES_REACHED: Maximum outer cycles exceeded (escalates to reviewer)

    **Serialization**: Inherits from `str, Enum` for direct JSON serialization
    without `.value` access.
    """

    ISSUES_FOUND = "issues_found"
    APPROVED = "approved"
    MAX_CYCLES_REACHED = "max_cycles"


class PRReviewStatus(str, Enum):
    """Status of a PR review cycle.

    Represents the current phase or state of review.

    **Enum Values:**
    - PENDING: Waiting to start (queued)
    - PHASE_1_CODE_REVIEW: Phase 1 code review in progress
    - PHASE_2_VERIFICATION: Phase 2 verification in progress
    - PHASE_3_CI_CHECK: Phase 3 CI check in progress
    - PHASE_4_CONSOLIDATION: Phase 4 consolidation in progress
    - COMPLETED: Cycle completed (has outcome)
    - ESCALATED: Escalated to human reviewer

    **Serialization**: Inherits from `str, Enum` for direct JSON serialization.
    """

    PENDING = "pending"
    PHASE_1_CODE_REVIEW = "phase_1_code_review"
    PHASE_2_VERIFICATION = "phase_2_verification"
    PHASE_3_CI_CHECK = "phase_3_ci_check"
    PHASE_4_CONSOLIDATION = "phase_4_consolidation"
    COMPLETED = "completed"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class PRReviewFinding:
    """Represents a single finding from the PR review.

    Immutable record of a code issue, suggestion, or observation found during
    the review process.

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Attempting to modify any field raises FrozenInstanceError.

    Attributes:
        title: Short title of the finding
        description: Detailed description of the finding
        severity: Severity level (must be one of: "critical", "high", "medium", "low")
        phase: Name of the phase where finding was discovered (e.g., "code_review", "verification")
        context_source: Optional source context for the finding (e.g., "parent_issue", "ba_output")
    """

    title: str
    description: str
    severity: str
    phase: str
    context_source: str | None = None

    # Allowed severity values
    ALLOWED_SEVERITIES = frozenset(["critical", "high", "medium", "low"])

    def __post_init__(self) -> None:
        """Validate finding after initialization."""
        if not self.title:
            msg = "title is required"
            raise ValueError(msg)
        if not self.description:
            msg = "description is required"
            raise ValueError(msg)
        if not self.severity:
            msg = "severity is required"
            raise ValueError(msg)
        if self.severity not in self.ALLOWED_SEVERITIES:
            msg = f"severity must be one of {sorted(self.ALLOWED_SEVERITIES)}, got '{self.severity}'"
            raise ValueError(msg)
        if not self.phase:
            msg = "phase is required"
            raise ValueError(msg)


@dataclass(frozen=True)
class PRReviewPhaseOutput:
    """Output from a single phase in the PR review cycle.

    Immutable record of phase execution results, including findings and metadata.

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Collections stored as immutable Tuples instead of Lists.

    Attributes:
        phase_name: Name of the phase (e.g., "code_review", "verification", "ci_check", "consolidation")
        phase_index: Position in phase sequence (1-based)
        success: Whether the phase completed successfully
        findings: Immutable tuple of PRReviewFinding objects discovered in this phase
        summary: Human-readable summary of phase results
        duration_seconds: Time taken to execute this phase (non-negative)
        context_source: Optional context source for this phase (e.g., "parent_issue", "ba_output")
        comment_id: Optional ID of comment associated with this phase
        error: Optional error message if phase failed, None if successful
    """

    phase_name: str
    phase_index: int
    success: bool
    findings: tuple[PRReviewFinding, ...]
    summary: str
    duration_seconds: float
    context_source: str | None = None
    comment_id: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        """Validate phase output after initialization."""
        if not self.phase_name:
            msg = "phase_name is required"
            raise ValueError(msg)
        if self.phase_index < 1:
            msg = "phase_index must be >= 1"
            raise ValueError(msg)
        if not isinstance(self.findings, tuple):
            msg = "findings must be a tuple (immutable)"
            raise ValueError(msg)
        if not self.summary:
            msg = "summary is required"
            raise ValueError(msg)
        if self.duration_seconds < 0:
            msg = "duration_seconds must be non-negative"
            raise ValueError(msg)

        # Consistency check: success state must align with error
        if self.success and self.error is not None:
            msg = f"success=True but error is set: '{self.error}' (contradiction)"
            raise ValueError(msg)

        # Consistency check: failure without explanation
        if not self.success and self.error is None:
            msg = "success=False but error is not set (failure must have explanation for audit trail)"
            raise ValueError(msg)


@dataclass(frozen=True)
class PRReviewCycleConfig:
    """Configuration for PR review cycle execution.

    Immutable configuration controlling how the PR review cycle is executed,
    including phases to run, timeouts, and context sources for verification.

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Collections stored as immutable Tuples instead of Lists.

    Attributes:
        max_outer_cycles: Maximum number of complete cycles before escalation
                         (must be >= 1, default 3)
        verifier_context_sources: Immutable tuple of context sources to use during
                                 verification phase (e.g., "parent_issue", "ba_output",
                                 "arch_spec"). Must be non-empty.
        code_review_timeout_seconds: Timeout for Phase 1 code review (default 600)
        verification_timeout_seconds: Timeout per verification context source (default 300)
        ci_check_enabled: Whether to perform Phase 3 CI check (default True)
        ci_check_timeout_seconds: Timeout for CI status check (default 300).
                                 Must be > 0 when ci_check_enabled=True.
        consolidation_timeout_seconds: Timeout for Phase 4 consolidation (default 600)
        sub_issue_target_board: Board ID where sub-issues will be created (optional)
        sub_issue_creation: Whether to create sub-issues when findings are found (default True)
        sub_issue_labels: Immutable tuple of labels to apply to created sub-issues
        sub_issue_initial_column: Column to place created sub-issues in (default "Backlog")
        on_issues_found_column: Column to move item to when issues are found (required)
        on_approved_column: Column to move item to when approved (required)
        on_failure_column: Column to move item to when CI checks fail (optional)
        code_review_agent: ID of the agent to execute Phase 1 code review
        verifier_agent: ID of the agent to execute Phase 2 verification
        consolidation_agent: ID of the agent to execute Phase 4 consolidation
    """

    max_outer_cycles: int = 3
    verifier_context_sources: tuple[str, ...] = ("parent_issue",)
    code_review_timeout_seconds: int = 600
    verification_timeout_seconds: int = 300
    ci_check_enabled: bool = True
    ci_check_timeout_seconds: int = 300
    consolidation_timeout_seconds: int = 600
    sub_issue_target_board: str | None = None
    sub_issue_creation: bool = True
    sub_issue_labels: tuple[str, ...] = ()
    sub_issue_initial_column: str = "Backlog"
    on_issues_found_column: str = ""
    on_approved_column: str = ""
    on_failure_column: str | None = None
    code_review_agent: str = ""
    verifier_agent: str = ""
    consolidation_agent: str = ""

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.max_outer_cycles < 1:
            msg = f"max_outer_cycles must be >= 1, got {self.max_outer_cycles}"
            raise ValueError(msg)

        if not self.verifier_context_sources:
            msg = "verifier_context_sources must not be empty"
            raise ValueError(msg)

        if not isinstance(self.verifier_context_sources, tuple):
            msg = "verifier_context_sources must be a tuple (immutable)"
            raise ValueError(msg)

        if not isinstance(self.sub_issue_labels, tuple):
            msg = "sub_issue_labels must be a tuple (immutable)"
            raise ValueError(msg)

        if not self.on_issues_found_column:
            msg = "on_issues_found_column is required"
            raise ValueError(msg)

        if not self.on_approved_column:
            msg = "on_approved_column is required"
            raise ValueError(msg)

        if not self.code_review_agent:
            msg = "code_review_agent is required"
            raise ValueError(msg)

        if not self.verifier_agent:
            msg = "verifier_agent is required"
            raise ValueError(msg)

        if not self.consolidation_agent:
            msg = "consolidation_agent is required"
            raise ValueError(msg)

        if not self.sub_issue_initial_column:
            msg = "sub_issue_initial_column is required"
            raise ValueError(msg)

        # Only validate ci_check_timeout_seconds > 0 if ci_check is enabled
        if self.ci_check_enabled and self.ci_check_timeout_seconds <= 0:
            msg = (
                f"ci_check_timeout_seconds must be > 0 when ci_check_enabled=True, got {self.ci_check_timeout_seconds}"
            )
            raise ValueError(msg)

        if self.code_review_timeout_seconds <= 0:
            msg = f"code_review_timeout_seconds must be > 0, got {self.code_review_timeout_seconds}"
            raise ValueError(msg)

        if self.verification_timeout_seconds <= 0:
            msg = f"verification_timeout_seconds must be > 0, got {self.verification_timeout_seconds}"
            raise ValueError(msg)

        if self.consolidation_timeout_seconds <= 0:
            msg = f"consolidation_timeout_seconds must be > 0, got {self.consolidation_timeout_seconds}"
            raise ValueError(msg)


@dataclass(frozen=True)
class PRReviewCycleResult:
    """Overall result from a complete PR review cycle.

    Immutable record of the entire PR review cycle execution, containing results
    for each phase and the final outcome.

    **Immutability**: Frozen dataclass - all fields read-only after construction.
    Collections stored as immutable Tuples instead of Lists.

    Attributes:
        cycle_number: Iteration count (1-based) for outer re-trigger tracking
        workflow_run_id: ID of the workflow run that executed this cycle
        outcome: Final outcome (PRReviewOutcome enum)
        phase_outputs: Immutable tuple of PRReviewPhaseOutput for each executed phase
        all_findings: Immutable tuple of all PRReviewFinding objects from all phases
        sub_issue_ids: Immutable tuple of created sub-issue IDs (empty if approved/max_cycles)
        ci_passed: CI check result (True if passed, False if failed, None if not checked)
        total_findings: Total number of findings across all phases
        critical_count: Number of critical severity findings
        high_count: Number of high severity findings
        medium_count: Number of medium severity findings
        low_count: Number of low severity findings
        total_duration_seconds: Total time for entire cycle (non-negative)
        timestamp: ISO 8601 timestamp when cycle started
        next_column: Name of the column to move item to (determined by outcome)
    """

    cycle_number: int
    workflow_run_id: str
    outcome: PRReviewOutcome
    phase_outputs: tuple[PRReviewPhaseOutput, ...]
    all_findings: tuple[PRReviewFinding, ...]
    sub_issue_ids: tuple[str, ...]
    ci_passed: bool | None
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    total_duration_seconds: float
    timestamp: str
    next_column: str

    def __post_init__(self) -> None:
        """Validate cycle result after initialization."""
        if self.cycle_number < 1:
            msg = f"cycle_number must be >= 1, got {self.cycle_number}"
            raise ValueError(msg)

        if not self.workflow_run_id:
            msg = "workflow_run_id is required"
            raise ValueError(msg)

        if not isinstance(self.outcome, PRReviewOutcome):
            msg = "outcome must be a PRReviewOutcome enum"
            raise ValueError(msg)

        if not isinstance(self.phase_outputs, tuple):
            msg = "phase_outputs must be a tuple (immutable)"
            raise ValueError(msg)

        if not self.phase_outputs:
            msg = "phase_outputs must not be empty"
            raise ValueError(msg)

        if not isinstance(self.all_findings, tuple):
            msg = "all_findings must be a tuple (immutable)"
            raise ValueError(msg)

        if not isinstance(self.sub_issue_ids, tuple):
            msg = "sub_issue_ids must be a tuple (immutable)"
            raise ValueError(msg)

        if self.total_findings < 0:
            msg = f"total_findings must be non-negative, got {self.total_findings}"
            raise ValueError(msg)

        if self.critical_count < 0:
            msg = f"critical_count must be non-negative, got {self.critical_count}"
            raise ValueError(msg)

        if self.high_count < 0:
            msg = f"high_count must be non-negative, got {self.high_count}"
            raise ValueError(msg)

        if self.medium_count < 0:
            msg = f"medium_count must be non-negative, got {self.medium_count}"
            raise ValueError(msg)

        if self.low_count < 0:
            msg = f"low_count must be non-negative, got {self.low_count}"
            raise ValueError(msg)

        # Validate severity counts sum to total
        severity_total = self.critical_count + self.high_count + self.medium_count + self.low_count
        if severity_total != self.total_findings:
            msg = f"Severity counts ({severity_total}) must sum to total_findings ({self.total_findings})"
            raise ValueError(msg)

        # Validate total_findings matches actual findings count
        if self.total_findings != len(self.all_findings):
            msg = f"total_findings ({self.total_findings}) must match len(all_findings) ({len(self.all_findings)})"
            raise ValueError(msg)

        if self.total_duration_seconds < 0:
            msg = f"total_duration_seconds must be non-negative, got {self.total_duration_seconds}"
            raise ValueError(msg)

        if not self.timestamp:
            msg = "timestamp is required"
            raise ValueError(msg)

        if not self.next_column:
            msg = "next_column is required"
            raise ValueError(msg)

        # Consistency check: ISSUES_FOUND should have sub_issue_ids and findings
        if self.outcome == PRReviewOutcome.ISSUES_FOUND and not self.sub_issue_ids:
            msg = "outcome=ISSUES_FOUND but sub_issue_ids is empty (expected sub-issues)"
            raise ValueError(msg)

        # Consistency check: APPROVED should have no sub_issue_ids
        if self.outcome == PRReviewOutcome.APPROVED and self.sub_issue_ids:
            msg = f"outcome=APPROVED but sub_issue_ids is non-empty: {self.sub_issue_ids} (contradiction)"
            raise ValueError(msg)


@dataclass
class PRReviewCycleState:
    """Mutable state for in-progress PR review cycle.

    Tracks the current state of a PR review cycle during execution.
    This is a mutable dataclass (not frozen) since state changes during execution.

    Attributes:
        cycle_id: Unique identifier for this cycle instance
        pr_id: GitHub PR identifier
        work_item_id: ID of the work item being reviewed
        project_id: ID of the project
        board_id: ID of the project board
        status: Current status (PRReviewStatus enum)
        cycle_number: Iteration count (1-based)
        current_phase: Name of currently executing phase
        findings: Mutable list of findings discovered so far
        phase_outputs: Mutable list of completed phase outputs
        config: PR review cycle configuration
        discussion_id: Optional ID of associated discussion/thread
        started_at: ISO 8601 timestamp when cycle started
        updated_at: ISO 8601 timestamp of last status change
    """

    cycle_id: str
    pr_id: str
    work_item_id: str
    project_id: str
    board_id: str
    status: PRReviewStatus
    cycle_number: int
    current_phase: str
    findings: list[PRReviewFinding]
    phase_outputs: list[PRReviewPhaseOutput]
    config: "PRReviewCycleConfig"
    started_at: str
    updated_at: str
    discussion_id: str | None = None

    def __post_init__(self) -> None:
        """Validate state after initialization."""
        if not self.cycle_id:
            msg = "cycle_id is required"
            raise ValueError(msg)
        if not self.pr_id:
            msg = "pr_id is required"
            raise ValueError(msg)
        if not self.work_item_id:
            msg = "work_item_id is required"
            raise ValueError(msg)
        if not self.project_id:
            msg = "project_id is required"
            raise ValueError(msg)
        if not self.board_id:
            msg = "board_id is required"
            raise ValueError(msg)
        if not isinstance(self.status, PRReviewStatus):
            msg = "status must be a PRReviewStatus enum"
            raise ValueError(msg)
        if self.cycle_number < 1:
            msg = f"cycle_number must be >= 1, got {self.cycle_number}"
            raise ValueError(msg)
        if not self.current_phase:
            msg = "current_phase is required"
            raise ValueError(msg)
        if not isinstance(self.findings, list):
            msg = "findings must be a list"
            raise ValueError(msg)
        if not isinstance(self.phase_outputs, list):
            msg = "phase_outputs must be a list"
            raise ValueError(msg)
        if not isinstance(self.config, PRReviewCycleConfig):
            msg = "config must be a PRReviewCycleConfig instance"
            raise ValueError(msg)
        if not self.started_at:
            msg = "started_at is required"
            raise ValueError(msg)
        if not self.updated_at:
            msg = "updated_at is required"
            raise ValueError(msg)
