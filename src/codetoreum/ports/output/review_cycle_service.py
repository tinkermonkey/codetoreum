"""Review cycle service port interface for orchestrating review cycles.

This interface defines the contract for review cycle management, including:
1. Starting and managing review cycles with maker-checker pattern
2. Tracking review cycle state through multiple iterations
3. Handling reviewer feedback and parsing review results
4. Supporting human escalation when needed

Review cycles manage code review loops where a maker (development agent)
creates work that a reviewer (code review agent) evaluates and provides
feedback on, potentially requiring multiple iterations before approval.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

ReviewCycleStatus = Literal[
    "initialized",
    "maker_working",
    "reviewer_working",
    "awaiting_human_feedback",
    "completed",
]
ReviewStatus = Literal["APPROVED", "CHANGES_REQUESTED", "BLOCKED"]


@dataclass(frozen=True)
class ReviewFinding:
    """A single finding from a code review.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        severity: Severity level of the finding (blocking, major, minor, suggestion)
        description: Description of the finding
        file: Optional source file the finding references
        line: Optional line number in the file (1-indexed)
    """

    severity: Literal["blocking", "major", "minor", "suggestion"]
    description: str
    file: str | None = None
    line: int | None = None

    def __post_init__(self) -> None:
        """Validate finding data."""
        if self.severity not in ("blocking", "major", "minor", "suggestion"):
            msg = f"severity must be one of: blocking, major, minor, suggestion. Got: {self.severity}"
            raise ValueError(msg)

        if not self.description or not self.description.strip():
            msg = "Finding description cannot be empty"
            raise ValueError(msg)

        if self.file is not None:
            if not isinstance(self.file, str) or not self.file:
                msg = "file must be a non-empty string or None"
                raise ValueError(msg)

        if self.line is not None:
            if isinstance(self.line, bool) or not isinstance(self.line, int) or self.line < 1:
                msg = "line must be a positive integer or None"
                raise ValueError(msg)


@dataclass(frozen=True)
class ReviewResult:
    """Parsed result from reviewer output.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Findings list is converted
    to tuple for immutability.

    Attributes:
        status: Review decision (APPROVED, CHANGES_REQUESTED, BLOCKED)
        findings: Tuple of findings from the review
        blocking_count: Number of blocking findings
        summary: Optional summary of the review
    """

    status: ReviewStatus
    findings: tuple[ReviewFinding, ...]
    blocking_count: int
    summary: str | None = None

    def __post_init__(self) -> None:
        """Validate result data."""
        if self.status not in ("APPROVED", "CHANGES_REQUESTED", "BLOCKED"):
            msg = f"status must be one of: APPROVED, CHANGES_REQUESTED, BLOCKED. Got: {self.status}"
            raise ValueError(msg)

        if not isinstance(self.findings, tuple):
            msg = "findings must be a tuple of ReviewFinding instances"
            raise ValueError(msg)

        if not all(isinstance(f, ReviewFinding) for f in self.findings):
            msg = "all findings must be ReviewFinding instances"
            raise ValueError(msg)

        if isinstance(self.blocking_count, bool) or not isinstance(self.blocking_count, int) or self.blocking_count < 0:
            msg = "blocking_count must be a non-negative integer"
            raise ValueError(msg)

        if self.summary is not None:
            if not isinstance(self.summary, str) or not self.summary:
                msg = "summary must be a non-empty string or None"
                raise ValueError(msg)


@dataclass(frozen=True)
class IterationOutput:
    """Output from a single iteration (maker or reviewer).

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        iteration: Iteration number (1-indexed)
        output: Text output from the iteration
        timestamp: ISO 8601 timestamp when iteration occurred
        post_human_feedback: Whether this output came after human feedback
    """

    iteration: int
    output: str
    timestamp: str
    post_human_feedback: bool = False

    def __post_init__(self) -> None:
        """Validate output data."""
        if isinstance(self.iteration, bool) or not isinstance(self.iteration, int) or self.iteration < 1:
            msg = "iteration must be a positive integer"
            raise ValueError(msg)

        if not isinstance(self.output, str) or not self.output:
            msg = "output must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.timestamp, str) or not self.timestamp:
            msg = "timestamp must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.post_human_feedback, bool):
            msg = "post_human_feedback must be a boolean"
            raise ValueError(msg)


@dataclass(frozen=True)
class ReviewCycleRequest:
    """Request to start a review cycle.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        work_item_id: ID of the work item being reviewed
        project_id: ID of the project
        board_id: ID of the project board
        maker_agent: Name of the maker (development) agent
        reviewer_agent: Name of the reviewer (code review) agent
        max_iterations: Maximum iterations before escalation
        auto_advance_on_approval: Whether to auto-advance on approval
        escalate_on_blocked: Whether to escalate when blocked findings appear
        previous_stage_output: Output from previous pipeline stage
        workflow_run_id: Optional pipeline execution ID
    """

    work_item_id: str
    project_id: str
    board_id: str
    maker_agent: str
    reviewer_agent: str
    max_iterations: int
    auto_advance_on_approval: bool
    escalate_on_blocked: bool
    previous_stage_output: str
    workflow_run_id: str | None = None

    def __post_init__(self) -> None:
        """Validate request data."""
        for field_name in ("work_item_id", "project_id", "board_id", "maker_agent", "reviewer_agent", "previous_stage_output"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val:
                msg = f"{field_name} must be a non-empty string"
                raise ValueError(msg)

        if isinstance(self.max_iterations, bool) or not isinstance(self.max_iterations, int) or self.max_iterations <= 0:
            msg = f"max_iterations must be positive, got {self.max_iterations}"
            raise ValueError(msg)

        if not isinstance(self.auto_advance_on_approval, bool) or not isinstance(self.escalate_on_blocked, bool):
            msg = "auto_advance_on_approval and escalate_on_blocked must be booleans"
            raise ValueError(msg)

        if self.workflow_run_id is not None:
            if not isinstance(self.workflow_run_id, str) or not self.workflow_run_id:
                msg = "workflow_run_id must be a non-empty string or None"
                raise ValueError(msg)


@dataclass(frozen=True)
class ReviewCycleState:
    """Complete state of an in-progress review cycle.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation. Output lists are converted
    to tuples for immutability.

    Attributes:
        work_item_id: ID of the work item being reviewed
        project_id: ID of the project
        board_id: ID of the project board
        maker_agent: Name of the maker agent
        reviewer_agent: Name of the reviewer agent
        max_iterations: Maximum iterations configured
        workflow_run_id: Associated pipeline run ID
        current_iteration: Current iteration number
        maker_outputs: Tuple of outputs from maker agent
        review_outputs: Tuple of outputs from reviewer agent
        status: Current state of the review cycle
        escalation_time: ISO timestamp when escalated (if applicable)
        last_escalation_comment_id: ID of escalation comment (if applicable)
        last_approved_commit: Commit hash when approved (if applicable)
        created_at: ISO timestamp when cycle was created
        updated_at: ISO timestamp when cycle was last updated
    """

    work_item_id: str
    project_id: str
    board_id: str
    maker_agent: str
    reviewer_agent: str
    max_iterations: int
    workflow_run_id: str | None
    current_iteration: int
    maker_outputs: tuple[IterationOutput, ...]
    review_outputs: tuple[IterationOutput, ...]
    status: ReviewCycleStatus
    escalation_time: str | None = None
    last_escalation_comment_id: str | None = None
    last_approved_commit: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        """Validate state data."""
        for field_name in ("work_item_id", "project_id", "board_id", "maker_agent", "reviewer_agent"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val:
                msg = f"{field_name} must be a non-empty string"
                raise ValueError(msg)

        if isinstance(self.max_iterations, bool) or not isinstance(self.max_iterations, int) or self.max_iterations <= 0:
            msg = "max_iterations must be a positive integer"
            raise ValueError(msg)

        if self.workflow_run_id is not None:
            if not isinstance(self.workflow_run_id, str):
                msg = "workflow_run_id must be a string or None"
                raise ValueError(msg)

        if isinstance(self.current_iteration, bool) or not isinstance(self.current_iteration, int) or self.current_iteration < 0:
            msg = "current_iteration must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.maker_outputs, tuple):
            msg = "maker_outputs must be a tuple of IterationOutput instances"
            raise ValueError(msg)

        if not all(isinstance(o, IterationOutput) for o in self.maker_outputs):
            msg = "all maker_outputs must be IterationOutput instances"
            raise ValueError(msg)

        if not isinstance(self.review_outputs, tuple):
            msg = "review_outputs must be a tuple of IterationOutput instances"
            raise ValueError(msg)

        if not all(isinstance(o, IterationOutput) for o in self.review_outputs):
            msg = "all review_outputs must be IterationOutput instances"
            raise ValueError(msg)

        if self.status not in ("initialized", "maker_working", "reviewer_working", "awaiting_human_feedback", "completed"):
            msg = f"status must be one of: initialized, maker_working, reviewer_working, awaiting_human_feedback, completed. Got: {self.status}"
            raise ValueError(msg)

        if self.current_iteration > self.max_iterations:
            msg = f"current_iteration ({self.current_iteration}) cannot exceed max_iterations ({self.max_iterations})"
            raise ValueError(msg)

        if self.escalation_time is not None:
            if not isinstance(self.escalation_time, str) or not self.escalation_time:
                msg = "escalation_time must be a non-empty string or None"
                raise ValueError(msg)

        if self.last_escalation_comment_id is not None:
            if not isinstance(self.last_escalation_comment_id, str) or not self.last_escalation_comment_id:
                msg = "last_escalation_comment_id must be a non-empty string or None"
                raise ValueError(msg)

        if self.last_approved_commit is not None:
            if not isinstance(self.last_approved_commit, str) or not self.last_approved_commit:
                msg = "last_approved_commit must be a non-empty string or None"
                raise ValueError(msg)


@dataclass(frozen=True)
class ReviewCycleResult:
    """Result of a completed or paused review cycle.

    Attributes:
        next_column: The column/stage to advance to next
        cycle_complete: Whether the cycle completed successfully
        final_status: Final review status (APPROVED, CHANGES_REQUESTED, BLOCKED)
        total_iterations: Number of iterations completed
        human_escalation_occurred: Whether human escalation happened
    """

    next_column: str
    cycle_complete: bool
    final_status: ReviewStatus
    total_iterations: int
    human_escalation_occurred: bool

    def __post_init__(self) -> None:
        """Validate result data."""
        if self.total_iterations <= 0:
            msg = f"total_iterations must be positive, got {self.total_iterations}"
            raise ValueError(msg)


class IReviewCycle(ABC):
    """Port interface for review cycle operations.

    Provides a vendor-agnostic interface for managing review cycles
    with maker-checker pattern, supporting:
    - Multi-iteration review loops
    - Human escalation when needed
    - State persistence and recovery
    - Review output parsing

    Example:
        # Start a review cycle
        request = ReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            maker_agent="junior_dev",
            reviewer_agent="senior_dev",
            max_iterations=3,
            auto_advance_on_approval=True,
            escalate_on_blocked=True,
            previous_stage_output="Initial development output"
        )
        result = await review_service.start_review_cycle(request)

        # Handle escalation if needed
        if result.human_escalation_occurred:
            cycle_state = await review_service.get_cycle_state(request.work_item_id)
            # Wait for human feedback
            await review_service.resume_with_human_feedback(
                cycle_state,
                "Please address reviewer feedback"
            )
    """

    @abstractmethod
    async def start_review_cycle(self, request: ReviewCycleRequest) -> ReviewCycleResult:
        """Start a new review cycle.

        Initiates a maker-checker review loop for the specified work item.
        The cycle will iterate between maker revisions and reviewer feedback
        until approval is achieved or max iterations/blocking issues are reached.

        Args:
            request: Review cycle request with configuration

        Returns:
            ReviewCycleResult with the outcome of the review cycle

        Raises:
            ValueError: If request validation fails
            ResourceNotFoundError: If work item or agents don't exist
            ExternalServiceError: If external service communication fails
        """

    @abstractmethod
    async def resume_review_cycle(self, work_item_id: str, project_id: str) -> None:
        """Resume an interrupted review cycle.

        Resumes a review cycle that was paused (e.g., due to agent timeout
        or other interruption) and continues from where it left off.

        Args:
            work_item_id: Work item ID for the cycle to resume
            project_id: Project ID containing the work item

        Raises:
            ResourceNotFoundError: If work item or cycle state not found
            InvalidStateError: If cycle is not resumable
            ExternalServiceError: If external service communication fails
        """

    @abstractmethod
    async def resume_with_human_feedback(self, cycle_state: ReviewCycleState, feedback: str) -> None:
        """Resume a blocked cycle with human feedback.

        Resumes a review cycle that was escalated to human when blocked
        findings were encountered, incorporating the human's feedback
        into the next iteration.

        Args:
            cycle_state: Current state of the paused review cycle
            feedback: Human feedback to incorporate

        Raises:
            InvalidStateError: If cycle is not awaiting human feedback
            ValueError: If feedback is empty
            ExternalServiceError: If external service communication fails
        """

    @abstractmethod
    async def get_cycle_state(self, work_item_id: str) -> ReviewCycleState | None:
        """Retrieve current state of a review cycle.

        Gets the complete state of a review cycle in progress,
        including all iterations, outputs, and escalation status.

        Args:
            work_item_id: Work item ID to get cycle state for

        Returns:
            ReviewCycleState if cycle exists, None otherwise

        Raises:
            ExternalServiceError: If state store communication fails
        """

    @abstractmethod
    async def save_cycle_state(self, state: ReviewCycleState) -> None:
        """Persist review cycle state.

        Saves the current state of a review cycle for recovery
        and inspection purposes.

        Args:
            state: Review cycle state to persist

        Raises:
            ValueError: If state is invalid
            ExternalServiceError: If state store communication fails
        """

    @abstractmethod
    async def remove_cycle_state(self, state: ReviewCycleState) -> None:
        """Remove completed cycle state.

        Removes the persisted state of a completed review cycle
        to clean up storage.

        Args:
            state: Review cycle state to remove

        Raises:
            ExternalServiceError: If state store communication fails
        """

    @abstractmethod
    async def load_active_cycles(self, project_id: str) -> list[ReviewCycleState]:
        """Load all in-progress cycles for a project.

        Retrieves all review cycles currently in progress for a project,
        useful for recovery after restarts.

        Args:
            project_id: Project ID to load cycles for

        Returns:
            List of ReviewCycleState objects for active cycles

        Raises:
            ExternalServiceError: If state store communication fails
        """

    @abstractmethod
    def parse_review(self, review_output: str) -> ReviewResult:
        """Parse reviewer output to extract status and findings.

        Parses the text output from a reviewer agent to extract:
        1. Review decision status (APPROVED, CHANGES_REQUESTED, BLOCKED)
        2. Individual findings with severity levels
        3. Count of blocking issues

        This is a synchronous operation as it only processes text.

        Args:
            review_output: Raw text output from reviewer agent

        Returns:
            ReviewResult with parsed status, findings, and counts

        Raises:
            ValueError: If output cannot be parsed
        """
