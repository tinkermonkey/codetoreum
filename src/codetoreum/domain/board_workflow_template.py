"""Board workflow template domain entity with column-based semantics.

This module defines the domain models for column-based workflow orchestration,
where board position (not labels) determines workflow state and agent triggers.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


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
                                     after agent completion
    """

    name: str
    type: ColumnType
    agent_id: Optional[str]
    is_pipeline_trigger: bool
    is_exit_column: bool
    position: int
    auto_progress_on_completion: bool

    def __post_init__(self) -> None:
        """Validate column template invariants."""
        # Validate name
        if not self.name or not self.name.strip():
            raise ValueError("Column name cannot be empty")

        # Validate position
        if self.position < 0:
            raise ValueError(f"Position must be non-negative, got {self.position}")

        # Validate agent_id correlation with type
        if self.type == ColumnType.AUTOMATED and not self.agent_id:
            raise ValueError(
                f"Automated column '{self.name}' must have an agent_id"
            )

        if self.type == ColumnType.MANUAL and self.agent_id:
            raise ValueError(
                f"Manual column '{self.name}' cannot have an agent_id"
            )

        # Validate auto_progress only for automated columns
        if self.auto_progress_on_completion and self.type != ColumnType.AUTOMATED:
            raise ValueError(
                f"auto_progress_on_completion only valid for automated columns, "
                f"column '{self.name}' is {self.type.value}"
            )


@dataclass(frozen=True)
class BoardWorkflowTemplate:
    """Workflow template with column-based semantics.

    Defines a workflow where work items progress through board columns,
    with each column optionally triggering an agent or requiring manual action.

    Attributes:
        id: Unique identifier for the workflow template
        name: Display name
        pipeline_trigger_columns: Column names that acquire pipeline lock
        exit_columns: Column names that release pipeline lock
        columns: Ordered tuple of column configurations (immutable)

    Raises:
        ValueError: If validation fails (empty ID/name, invalid columns, etc.)
    """

    id: str
    name: str
    pipeline_trigger_columns: Tuple[str, ...]
    exit_columns: Tuple[str, ...]
    columns: Tuple[ColumnTemplate, ...]

    def __post_init__(self) -> None:
        """Validate workflow template invariants."""
        # Validate ID and name
        if not self.id or not self.id.strip():
            raise ValueError("Template ID cannot be empty")
        if not self.name or not self.name.strip():
            raise ValueError("Template name cannot be empty")

        # Require at least one column
        if not self.columns:
            raise ValueError("Workflow must have at least one column")

        # Validate column positions are unique and sequential
        positions = sorted([col.position for col in self.columns])
        expected = list(range(len(self.columns)))

        if positions != expected:
            raise ValueError(
                f"Column positions must be unique and sequential starting at 0. "
                f"Got {positions}, expected {expected}"
            )

        # Validate column names are unique
        names = [col.name for col in self.columns]
        if len(names) != len(set(names)):
            duplicates = [n for n in names if names.count(n) > 1]
            raise ValueError(f"Column names must be unique, duplicates: {duplicates}")

        # Validate trigger/exit columns exist in columns list
        column_names = {col.name for col in self.columns}
        for trigger_col in self.pipeline_trigger_columns:
            if trigger_col not in column_names:
                raise ValueError(
                    f"pipeline_trigger_columns references non-existent column: {trigger_col}"
                )

        for exit_col in self.exit_columns:
            if exit_col not in column_names:
                raise ValueError(
                    f"exit_columns references non-existent column: {exit_col}"
                )

    def get_column_config(self, column_name: str) -> Optional[ColumnTemplate]:
        """Get configuration for a specific column by name.

        Args:
            column_name: Name of the column to find

        Returns:
            ColumnTemplate if found, None otherwise
        """
        return next((c for c in self.columns if c.name == column_name), None)

    def get_next_column(self, current: str) -> Optional[str]:
        """Get the next column by position order.

        Args:
            current: Current column name

        Returns:
            Name of the next column by position, or None if current is the last
        """
        current_config = self.get_column_config(current)
        if not current_config:
            return None
        next_pos = current_config.position + 1
        return next(
            (c.name for c in self.columns if c.position == next_pos), None
        )


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
            raise ValueError("workflow_template_id cannot be empty")
        if not self.board_id or not self.board_id.strip():
            raise ValueError("board_id cannot be empty")
        if not self.project_id or not self.project_id.strip():
            raise ValueError("project_id cannot be empty")
