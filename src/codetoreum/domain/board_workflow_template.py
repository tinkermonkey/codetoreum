"""Board workflow template domain entity with column-based semantics.

This module defines the domain models for column-based workflow orchestration,
where board position (not labels) determines workflow state and agent triggers.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ColumnType(Enum):
    """Type of workflow column."""

    MANUAL = "manual"
    AUTOMATED = "automated"


@dataclass
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


@dataclass
class BoardWorkflowTemplate:
    """Workflow template with column-based semantics.

    Defines a workflow where work items progress through board columns,
    with each column optionally triggering an agent or requiring manual action.

    Attributes:
        id: Unique identifier for the workflow template
        name: Display name
        pipeline_trigger_columns: Column names that acquire pipeline lock
        exit_columns: Column names that release pipeline lock
        columns: Ordered list of column configurations
    """

    id: str
    name: str
    pipeline_trigger_columns: List[str]
    exit_columns: List[str]
    columns: List[ColumnTemplate]

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


@dataclass
class BoardConfig:
    """Configuration for reconciling a board with workflow template.

    Attributes:
        workflow_template_id: ID of the workflow template to apply
        board_id: ID of the board to reconcile
        project_id: ID of the project containing the board
    """

    workflow_template_id: str
    board_id: str
    project_id: str
