"""Board workflow template domain entity with column-based semantics.

This module defines the domain models for column-based workflow orchestration,
where board position (not labels) determines workflow state and agent triggers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig, RepairTestType


class ColumnType(Enum):
    """Type of workflow column."""

    MANUAL = "manual"
    AUTOMATED = "automated"


@dataclass(frozen=True)
class ColumnTemplate:
    """Template for a board column with workflow semantics.

    Attributes:
        name: Display name of the column (e.g., "Backlog", "In Progress", "Done")
        type: Whether column is manual or automated
        agent_id: ID of agent to trigger when item enters (None for manual columns)
        is_pipeline_trigger: If True, acquiring lock when item enters column
        is_exit_column: If True, releasing lock when item enters column
        position: Column order (0 = leftmost/first)
        auto_progress_on_completion: If True, automatically move to next column
                                     after agent completion (success path)
        sla_seconds: Optional SLA threshold in seconds. If set, work items in this
                     column exceeding this duration will trigger SLA expiry events.
                     None means no SLA enforcement for this column.
        on_failure_column: Name of the column to move the work item to when the
                           agent execution fails. None means the item stays in the
                           current column (pipeline lock is still released).
                           Validated against the parent template's column names.
        sla_escalation_column: Name of the column to move the work item to when
                                the SLA expires. None means only an event is emitted
                                (no automatic move). Validated against parent columns.
        repair_cycle_agents: Optional specialized agent configuration for repair cycle
                           stages on this column. When set, maps sub-task types to
                           specific agents. None means use default stage agent.
        repair_cycle_test_types: Optional ordered tuple of RepairTestType values defining
                                 which test types to run when this column triggers a repair
                                 cycle. When None, the handler falls back to the default
                                 sequence (UNIT → INTEGRATION → E2E).
        pr_review_cycle_config: Optional configuration for PR review cycle on this column.
                               When set, triggers PR review cycle instead of agent execution.
                               Mutually exclusive with repair_cycle_agents.
        execution_type: Execution mode for the agent on this column. One of "task_queue"
                       (default, standard container execution) or "conversational"
                       (multi-turn dialogue via IDiscussionAdapter).
    """

    name: str
    type: ColumnType
    agent_id: str | None
    is_pipeline_trigger: bool
    is_exit_column: bool
    position: int
    auto_progress_on_completion: bool
    sla_seconds: int | None = None
    on_failure_column: str | None = None
    sla_escalation_column: str | None = None
    repair_cycle_agents: RepairCycleAgentConfig | None = None
    repair_cycle_test_types: tuple[RepairTestType, ...] | None = None
    pr_review_cycle_config: PRReviewCycleConfig | None = None
    execution_type: str = "task_queue"

    def __post_init__(self) -> None:
        """Validate column template invariants."""
        # Validate name
        if not self.name or not self.name.strip():
            msg = "Column name cannot be empty"
            raise ValueError(msg)

        # Validate position
        if self.position < 0:
            msg = f"Position must be non-negative, got {self.position}"
            raise ValueError(msg)

        # Validate agent_id correlation with type
        # Exception: Automated columns with pr_review_cycle_config don't need agent_id
        if (
            self.type == ColumnType.AUTOMATED
            and not self.agent_id
            and self.pr_review_cycle_config is None
        ):
            msg = f"Automated column '{self.name}' must have an agent_id"
            raise ValueError(msg)

        if self.type == ColumnType.MANUAL and self.agent_id:
            msg = f"Manual column '{self.name}' cannot have an agent_id"
            raise ValueError(msg)

        # Validate auto_progress only for automated columns
        if self.auto_progress_on_completion and self.type != ColumnType.AUTOMATED:
            msg = (
                f"auto_progress_on_completion only valid for automated columns, "
                f"column '{self.name}' is {self.type.value}"
            )
            raise ValueError(msg)

        # Validate SLA threshold
        if self.sla_seconds is not None and self.sla_seconds <= 0:
            msg = f"SLA threshold must be positive, got {self.sla_seconds} seconds"
            raise ValueError(msg)

        # on_failure_column and sla_escalation_column cannot equal this column's
        # own name (would create an infinite loop / no-op move)
        if self.on_failure_column and self.on_failure_column == self.name:
            msg = f"Column '{self.name}': on_failure_column cannot reference itself"
            raise ValueError(msg)

        if self.sla_escalation_column and self.sla_escalation_column == self.name:
            msg = f"Column '{self.name}': sla_escalation_column cannot reference itself"
            raise ValueError(msg)

        valid_execution_types = {"task_queue", "conversational"}
        if self.execution_type not in valid_execution_types:
            msg = f"execution_type must be one of {valid_execution_types}, got {self.execution_type!r}"
            raise ValueError(msg)

        # Mutual exclusivity: cannot have both repair_cycle_agents and pr_review_cycle_config
        if self.repair_cycle_agents is not None and self.pr_review_cycle_config is not None:
            msg = (
                f"Column '{self.name}': cannot have both repair_cycle_agents and "
                "pr_review_cycle_config (mutually exclusive)"
            )
            raise ValueError(msg)


@dataclass(frozen=True)
class BoardWorkflowTemplate:
    """Workflow template with column-based semantics.

    Defines a workflow where work items progress through board columns,
    with each column optionally triggering an agent or requiring manual action.

    ``pipeline_trigger_columns`` and ``exit_columns`` are **computed properties**
    derived from the ``columns`` tuple (columns where ``is_pipeline_trigger`` or
    ``is_exit_column`` is True).  There is no separate stored field for them —
    ``ColumnTemplate`` flags are the single source of truth.

    Attributes:
        id: Unique identifier for the workflow template
        name: Display name
        board_id: The board this template configures (lookup key for IWorkflowConfigService)
        project_id: The project that owns this board (used for per-project listing)
        columns: Ordered tuple of column configurations (immutable, single source of truth)
        created_at: When this template was first persisted (None if not yet saved)
        updated_at: When this template was last modified (None if not yet saved)

    Raises:
        ValueError: If validation fails (empty ID/name/board_id/project_id,
                    non-sequential positions, duplicate names, or invalid
                    on_failure_column / sla_escalation_column references)
    """

    id: str
    name: str
    board_id: str
    project_id: str
    columns: tuple[ColumnTemplate, ...]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # ── Computed properties (derived from columns — no stored redundancy) ────

    @property
    def pipeline_trigger_columns(self) -> tuple[str, ...]:
        """Column names where entering acquires the pipeline lock."""
        return tuple(c.name for c in self.columns if c.is_pipeline_trigger)

    @property
    def exit_columns(self) -> tuple[str, ...]:
        """Column names where entering releases the pipeline lock."""
        return tuple(c.name for c in self.columns if c.is_exit_column)

    # ── Invariant validation ─────────────────────────────────────────────────

    def __post_init__(self) -> None:
        """Validate workflow template invariants."""
        if not self.id or not self.id.strip():
            msg = "Template ID cannot be empty"
            raise ValueError(msg)
        if not self.name or not self.name.strip():
            msg = "Template name cannot be empty"
            raise ValueError(msg)
        if not self.board_id or not self.board_id.strip():
            msg = "board_id cannot be empty"
            raise ValueError(msg)
        if not self.project_id or not self.project_id.strip():
            msg = "project_id cannot be empty"
            raise ValueError(msg)

        if not self.columns:
            msg = "Workflow must have at least one column"
            raise ValueError(msg)

        # Column positions must be unique and sequential starting at 0
        positions = sorted(col.position for col in self.columns)
        expected = list(range(len(self.columns)))
        if positions != expected:
            msg = (
                f"Column positions must be unique and sequential starting at 0. "
                f"Got {positions}, expected {expected}"
            )
            raise ValueError(msg)

        # Column names must be unique
        names = [col.name for col in self.columns]
        if len(names) != len(set(names)):
            duplicates = [n for n in names if names.count(n) > 1]
            msg = f"Column names must be unique, duplicates: {duplicates}"
            raise ValueError(msg)

        # Cross-column reference validation: on_failure_column and
        # sla_escalation_column must name columns that exist in this template
        column_names = {col.name for col in self.columns}
        for col in self.columns:
            if col.on_failure_column and col.on_failure_column not in column_names:
                msg = f"Column '{col.name}' references unknown on_failure_column " f"'{col.on_failure_column}'"
                raise ValueError(msg)
            if col.sla_escalation_column and col.sla_escalation_column not in column_names:
                msg = f"Column '{col.name}' references unknown sla_escalation_column " f"'{col.sla_escalation_column}'"
                raise ValueError(msg)

    # ── Query helpers ────────────────────────────────────────────────────────

    def get_column_config(self, column_name: str) -> ColumnTemplate | None:
        """Return the ColumnTemplate for *column_name*, or None if not found."""
        return next((c for c in self.columns if c.name == column_name), None)

    def get_next_column(self, current: str) -> str | None:
        """Return the column name immediately after *current* by position.

        Returns None if *current* is not found or is the last column.
        """
        current_config = self.get_column_config(current)
        if not current_config:
            return None
        next_pos = current_config.position + 1
        return next((c.name for c in self.columns if c.position == next_pos), None)


@dataclass(frozen=True)
class BoardReconciliationConfig:
    """Configuration for reconciling a board with workflow template.

    Domain entity for specifying how to reconcile a board's structure
    with a workflow template. Used to ensure board columns match expected
    workflow stages and agent assignments.

    Attributes:
        workflow_template_id: ID of the workflow template to apply
        board_id: ID of the board to reconcile
        project_id: ID of the project containing the board
    """

    workflow_template_id: str
    board_id: str
    project_id: str

    def __post_init__(self) -> None:
        """Validate reconciliation config."""
        if not self.workflow_template_id or not self.workflow_template_id.strip():
            msg = "workflow_template_id cannot be empty"
            raise ValueError(msg)
        if not self.board_id or not self.board_id.strip():
            msg = "board_id cannot be empty"
            raise ValueError(msg)
        if not self.project_id or not self.project_id.strip():
            msg = "project_id cannot be empty"
            raise ValueError(msg)
