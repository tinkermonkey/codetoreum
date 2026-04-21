"""PR Review Cycle service port interface for orchestrating PR review cycles.

This interface defines the contract for PR review cycle management, including:
1. Starting and managing PR review cycles through multiple phases
2. Tracking PR review cycle state through iterations
3. Handling cycle state persistence and recovery
4. Supporting active cycle discovery for recovery scenarios

PR review cycles manage automated code review through a multi-phase pipeline:
- Phase 1: Code review analysis of PR changes
- Phase 2: Verification against context sources
- Phase 3: CI/CD check validation (optional)
- Phase 4: Consolidation of findings and routing

Cycles track iteration count for outer re-trigger enforcement and support
maximum cycle limits to prevent infinite loops.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig, PRReviewCycleResult, PRReviewCycleState


@dataclass(frozen=True)
class PRReviewCycleRequest:
    """Request to start a PR review cycle.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation after creation.

    Attributes:
        work_item_id: ID of the work item being reviewed
        project_id: ID of the project
        board_id: ID of the project board
        pr_id: GitHub PR identifier (can be None before PR creation)
        pr_url: URL of the pull request (can be None before PR creation)
        discussion_id: ID of the discussion thread (can be None if no discussion yet)
        cycle_number: Iteration count (1-based) for outer re-trigger tracking
        config: PR review cycle configuration with phase settings and timeouts
        workflow_run_id: ID for correlating this cycle with workflow context. Contains the work_item_id
            for use in outcome events (PRReviewCycleApprovedEvent, etc.) where the event handler
            extracts this value to determine which work item to move to the next column.
    """

    work_item_id: str
    project_id: str
    board_id: str
    pr_id: str | None
    pr_url: str | None
    discussion_id: str | None
    cycle_number: int
    config: PRReviewCycleConfig
    workflow_run_id: str

    def __post_init__(self) -> None:
        """Validate request data."""
        for field_name in ("work_item_id", "project_id", "board_id", "workflow_run_id"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val:
                msg = f"{field_name} must be a non-empty string"
                raise ValueError(msg)

        if isinstance(self.cycle_number, bool) or not isinstance(self.cycle_number, int) or self.cycle_number < 1:
            msg = f"cycle_number must be a positive integer (1-based), got {self.cycle_number}"
            raise ValueError(msg)

        # pr_id, pr_url, discussion_id can be None or non-empty strings
        for field_name in ("pr_id", "pr_url", "discussion_id"):
            val = getattr(self, field_name)
            if val is not None and (not isinstance(val, str) or not val):
                msg = f"{field_name} must be a non-empty string or None"
                raise ValueError(msg)

        if not isinstance(self.config, PRReviewCycleConfig):
            msg = "config must be a PRReviewCycleConfig instance"
            raise ValueError(msg)


@dataclass(frozen=True)
class PRReviewCycleStateData:
    """Complete state of an in-progress PR review cycle.

    All fields are validated at construction to ensure contract boundary integrity.
    Frozen to prevent accidental mutation of this wrapper's attributes after creation.

    **Immutability Limitation**: While PRReviewCycleStateData itself is frozen (preventing
    assignment to attributes like `data.work_item_id = ...`), the `cycle_state` field
    holds a reference to a mutable PRReviewCycleState object. Code like
    `data.cycle_state.status = "new_value"` will succeed, bypassing the frozen constraint.
    Callers must treat cycle_state as mutable and only modify it through appropriate
    service interfaces, not by direct field assignment.

    Attributes:
        work_item_id: ID of the work item being reviewed
        project_id: ID of the project
        board_id: ID of the project board
        cycle_number: Current iteration count (1-based)
        cycle_state: Mutable state object tracking phase progression (see immutability limitation above)
        created_at: ISO timestamp when cycle was created
        updated_at: ISO timestamp when cycle was last updated
    """

    work_item_id: str
    project_id: str
    board_id: str
    cycle_number: int
    cycle_state: PRReviewCycleState
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        """Validate state data."""
        for field_name in ("work_item_id", "project_id", "board_id"):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not val:
                msg = f"{field_name} must be a non-empty string"
                raise ValueError(msg)

        if isinstance(self.cycle_number, bool) or not isinstance(self.cycle_number, int) or self.cycle_number < 1:
            msg = "cycle_number must be a positive integer (1-based)"
            raise ValueError(msg)

        if not isinstance(self.cycle_state, PRReviewCycleState):
            msg = "cycle_state must be a PRReviewCycleState instance"
            raise ValueError(msg)

        if not isinstance(self.created_at, str) or not self.created_at:
            msg = "created_at must be a non-empty ISO timestamp string"
            raise ValueError(msg)

        if not isinstance(self.updated_at, str) or not self.updated_at:
            msg = "updated_at must be a non-empty ISO timestamp string"
            raise ValueError(msg)


class IPRReviewCycle(ABC):
    """Port interface for PR review cycle operations.

    Provides a vendor-agnostic interface for managing PR review cycles,
    supporting:
    - Multi-phase review pipeline (code review, verification, CI check, consolidation)
    - Outer cycle iteration tracking for re-trigger enforcement
    - State persistence and recovery
    - Active cycle discovery for restart scenarios

    Example:
        # Start a PR review cycle
        request = PRReviewCycleRequest(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            pr_id="123",
            pr_url="https://github.com/owner/repo/pull/123",
            discussion_id="discussion-1",
            cycle_number=1,
            config=PRReviewCycleConfig(max_outer_cycles=3),
            workflow_run_id="run-1"
        )
        state = await review_service.start_pr_review_cycle(request)

        # Retrieve cycle state for monitoring or recovery
        current_state = await review_service.get_cycle_state(
            "item-1", "proj-1"
        )

        # Save state for persistence
        await review_service.save_cycle_state(current_state)

        # Load all active cycles for a project (e.g., during recovery)
        active_cycles = await review_service.load_active_cycles("proj-1")
    """

    @abstractmethod
    async def start_pr_review_cycle(self, request: PRReviewCycleRequest) -> PRReviewCycleResult:
        """Start a new PR review cycle.

        Initiates a PR review cycle, beginning with Phase 1 (code review).
        The cycle will progress through phases (verification, CI check, consolidation)
        until completion or max cycles is reached.

        Args:
            request: PR review cycle request with configuration

        Returns:
            PRReviewCycleResult with complete cycle execution result

        Raises:
            ValueError: If request validation fails
            ResourceNotFoundError: If work item or PR doesn't exist
            ExternalServiceError: If external service communication fails
        """

    @abstractmethod
    async def get_cycle_state(self, work_item_id: str, project_id: str) -> PRReviewCycleStateData | None:
        """Retrieve current state of a PR review cycle.

        Gets the complete state of a PR review cycle in progress,
        including current phase, findings accumulated so far, and status.

        Args:
            work_item_id: Work item ID to get cycle state for
            project_id: Project ID containing the work item

        Returns:
            PRReviewCycleStateData if cycle exists, None otherwise

        Raises:
            ExternalServiceError: If state store communication fails
        """

    @abstractmethod
    async def save_cycle_state(self, state: PRReviewCycleStateData) -> None:
        """Persist PR review cycle state.

        Saves the current state of a PR review cycle for recovery
        and inspection purposes. Used to checkpoint state during execution
        and enable recovery after failures.

        Args:
            state: PR review cycle state to persist

        Raises:
            ValueError: If state is invalid
            ExternalServiceError: If state store communication fails
        """

    @abstractmethod
    async def remove_cycle_state(self, work_item_id: str, project_id: str) -> None:
        """Remove completed cycle state.

        Removes the persisted state of a completed PR review cycle
        to clean up storage after successful completion.

        Args:
            work_item_id: Work item ID of the cycle to remove
            project_id: Project ID containing the work item

        Raises:
            ExternalServiceError: If state store communication fails
        """

    @abstractmethod
    async def load_active_cycles(self, project_id: str) -> list[PRReviewCycleStateData]:
        """Load all in-progress cycles for a project.

        Retrieves all PR review cycles currently in progress for a project,
        useful for recovery after restarts and monitoring active work.

        Args:
            project_id: Project ID to load cycles for

        Returns:
            List of PRReviewCycleStateData objects for active cycles (empty list if none)

        Raises:
            ExternalServiceError: If state store communication fails
        """
