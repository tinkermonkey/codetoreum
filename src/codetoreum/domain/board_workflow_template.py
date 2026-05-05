"""Board workflow template domain entity with column-based semantics.

This module defines the domain models for column-based workflow orchestration,
where board position (not labels) determines workflow state and agent triggers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType

from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig, RepairTestType


class ColumnType(Enum):
    """Type of workflow column."""

    MANUAL = "manual"
    AUTOMATED = "automated"


class PermissionMode(Enum):
    """Vendor-neutral permission modes for agent execution.

    This enum represents permission modes in a vendor-agnostic way.
    Adapters translate these to vendor-specific values at the boundary
    (e.g., BYPASS → "bypassPermissions" for Claude Code CLI).
    """

    BYPASS = "bypass"
    ASK = "ask"


@dataclass(frozen=True)
class StageAgentConfig:
    """Stage-specific agent configuration for pipeline execution.

    Specifies agent parameters that override defaults for a specific
    pipeline stage (column). This enables different agents to use different models,
    permission modes, tool configurations, etc. Values are vendor-neutral;
    adapters translate them to vendor-specific values at system boundaries.

    Attributes:
        model: Agent model to use for this stage (e.g., "claude-opus-4-6")
        timeout_seconds: Execution timeout in seconds
        permission_mode: Permission mode for agent execution (PermissionMode enum)
        output_format: Output format from agent ("stream-json" or "text")
        enable_mcp: Whether to enable MCP (Model Context Protocol) for this stage
        enable_tools: Whether to allow tool usage in this stage
        max_context_tokens: Maximum context tokens for this stage
        verbose: Enable verbose logging for this stage
        prompt_template: Optional custom prompt template for this stage
        tool_permissions: Optional dict of tool-specific permissions/restrictions
        metadata: Additional stage-specific configuration (immutable dict)
    """

    model: str | None = None  # None means use default from agent config
    timeout_seconds: int | None = None  # None means use default
    permission_mode: PermissionMode | None = None  # Vendor-neutral permission mode
    output_format: str | None = None  # e.g., "stream-json"
    enable_mcp: bool | None = None
    enable_tools: bool | None = None
    max_context_tokens: int | None = None
    verbose: bool | None = None
    prompt_template: str | None = None
    tool_permissions: dict | MappingProxyType = field(
        default_factory=lambda: MappingProxyType({})
    )
    metadata: dict | MappingProxyType = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        """Validate stage agent configuration."""
        # Coerce dict to MappingProxyType for tool_permissions
        if isinstance(self.tool_permissions, dict):
            object.__setattr__(self, "tool_permissions", MappingProxyType(self.tool_permissions))

        # Coerce dict to MappingProxyType for metadata
        if isinstance(self.metadata, dict):
            object.__setattr__(self, "metadata", MappingProxyType(self.metadata))

        # Validate timeout if provided
        if self.timeout_seconds is not None:
            if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int):
                msg = "timeout_seconds must be a positive integer or None"
                raise ValueError(msg)
            if self.timeout_seconds <= 0:
                msg = f"timeout_seconds must be positive, got {self.timeout_seconds}"
                raise ValueError(msg)

        # Validate model if provided
        if self.model is not None and (not isinstance(self.model, str) or not self.model):
            msg = "model must be a non-empty string or None"
            raise ValueError(msg)

        # Validate permission_mode if provided
        if self.permission_mode is not None:
            if not isinstance(self.permission_mode, PermissionMode):
                msg = f"permission_mode must be a PermissionMode enum value or None, got {type(self.permission_mode).__name__}"
                raise ValueError(msg)

        # Validate output_format if provided
        if self.output_format is not None:
            valid_formats = {"stream-json", "text"}
            if self.output_format not in valid_formats:
                msg = f"output_format must be one of {valid_formats}, got {self.output_format!r}"
                raise ValueError(msg)

        # Validate max_context_tokens if provided
        if self.max_context_tokens is not None:
            if isinstance(self.max_context_tokens, bool) or not isinstance(self.max_context_tokens, int):
                msg = "max_context_tokens must be a positive integer or None"
                raise ValueError(msg)
            if self.max_context_tokens <= 0:
                msg = f"max_context_tokens must be positive, got {self.max_context_tokens}"
                raise ValueError(msg)

        # Validate boolean fields if provided
        for bool_field in ("enable_mcp", "enable_tools", "verbose"):
            val = getattr(self, bool_field)
            if val is not None and not isinstance(val, bool):
                msg = f"{bool_field} must be a boolean or None"
                raise ValueError(msg)

        if not isinstance(self.tool_permissions, MappingProxyType):
            msg = "tool_permissions must be a dict or MappingProxyType"
            raise ValueError(msg)

        if not isinstance(self.metadata, MappingProxyType):
            msg = "metadata must be a dict or MappingProxyType"
            raise ValueError(msg)


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
        stage_agent_config: Optional stage-specific Claude Code CLI configuration for the agent
                           on this column. Specifies model, timeout, permissions, and other
                           CLI parameters that override defaults for this specific stage.
                           None means use default agent configuration.
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
    stage_agent_config: StageAgentConfig | None = None
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
        if self.type == ColumnType.AUTOMATED and not self.agent_id and self.pr_review_cycle_config is None:
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
