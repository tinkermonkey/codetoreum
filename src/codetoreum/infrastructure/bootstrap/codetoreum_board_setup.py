"""
Setup for Codetoreum's own GitHub Projects board configuration.

This module provides the board workflow template for the codetoreum repository itself,
enabling dogfooding of the orchestration platform. The board configuration maps
GitHub Projects columns to workflow automation semantics.
"""

from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)

# Codetoreum board configuration constants (used by trigger CLI and setup)
CODETOREUM_BOARD_ID = "board-codetoreum"
CODETOREUM_PROJECT_ID = "proj-codetoreum"


def create_codetoreum_board_template() -> BoardWorkflowTemplate:
    """
    Create the workflow template for the codetoreum repository board.

    The template defines these columns in order:
    - Backlog: Items not yet ready for agent work (manual input)
    - Ready: Items ready to trigger the pipeline (pipeline trigger)
    - In Progress: Agent actively working (automated execution)
    - In Review: PR created, awaiting human review (manual review)
    - Done: Merged and closed (exit column, releases pipeline lock)

    Returns:
        BoardWorkflowTemplate configured for codetoreum dogfooding
    """
    return BoardWorkflowTemplate(
        id="codetoreum-board-workflow",
        name="Codetoreum SDLC Pipeline",
        board_id=CODETOREUM_BOARD_ID,
        project_id=CODETOREUM_PROJECT_ID,
        columns=(
            ColumnTemplate(
                name="Backlog",
                type=ColumnType.MANUAL,
                agent_id=None,  # Manual column - no agent assignment
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="Ready",
                type=ColumnType.MANUAL,
                agent_id=None,  # Manual column - developer moves items here when ready
                is_pipeline_trigger=True,  # Entering this column acquires the pipeline lock
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="senior_software_engineer",  # Default agent for executing work
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=True,  # Auto-move to next column on success
            ),
            ColumnTemplate(
                name="In Review",
                type=ColumnType.MANUAL,
                agent_id=None,  # Manual column - human reviewers evaluate PR
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=3,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="Done",
                type=ColumnType.MANUAL,
                agent_id=None,  # Manual column - closed/merged items
                is_pipeline_trigger=False,
                is_exit_column=True,  # Entering this column releases the pipeline lock
                position=4,
                auto_progress_on_completion=False,
            ),
        ),
    )
