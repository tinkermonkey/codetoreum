"""Codetoreum dogfood pipeline configuration.

Defines the 7-column workflow template for the Codetoreum project itself,
demonstrating the complete SDLC pipeline with agent assignments.

This configuration is used to seed the board workflow template for the
Codetoreum GitHub Projects v2 board.

Pipeline Stages:
1. Backlog (manual) - Work items awaiting triage
2. Analysis (analyzer agent) - Agent decomposes requirements
3. Implementation (maker agent) - Agent writes code
4. Testing (tester agent) - Agent writes and runs tests
5. Review (PR review cycle) - Human review with feedback
6. Blocked (manual) - Work item failed or stuck
7. Done (exit column) - Work item complete

Each column configuration includes:
- Type (manual vs automated)
- Agent assignment (for automated columns)
- Pipeline lock semantics (trigger/exit columns)
- Auto-progression settings
- Failure handling (on_failure_column)
"""

from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)


def create_codetoreum_pipeline_template() -> BoardWorkflowTemplate:
    """Create the Codetoreum dogfood pipeline configuration.

    Returns:
        BoardWorkflowTemplate configured for Codetoreum's self-hosting
    """
    # Define the 7 columns
    backlog = ColumnTemplate(
        name="Backlog",
        type=ColumnType.MANUAL,
        agent_id=None,
        is_pipeline_trigger=False,
        is_exit_column=False,
        position=0,
        auto_progress_on_completion=False,
        sla_seconds=None,
        on_failure_column=None,
        sla_escalation_column=None,
        execution_type="task_queue",
    )

    analysis = ColumnTemplate(
        name="Analysis",
        type=ColumnType.AUTOMATED,
        agent_id="analyzer",
        is_pipeline_trigger=True,  # Acquiring lock when item enters
        is_exit_column=False,
        position=1,
        auto_progress_on_completion=True,  # Auto-move to next column on success
        sla_seconds=3600,  # 1 hour SLA
        on_failure_column="Blocked",
        sla_escalation_column="Blocked",
        execution_type="task_queue",
    )

    implementation = ColumnTemplate(
        name="Implementation",
        type=ColumnType.AUTOMATED,
        agent_id="maker",
        is_pipeline_trigger=False,
        is_exit_column=False,
        position=2,
        auto_progress_on_completion=True,
        sla_seconds=7200,  # 2 hour SLA
        on_failure_column="Blocked",
        sla_escalation_column="Blocked",
        execution_type="task_queue",
    )

    testing = ColumnTemplate(
        name="Testing",
        type=ColumnType.AUTOMATED,
        agent_id="tester",
        is_pipeline_trigger=False,
        is_exit_column=False,
        position=3,
        auto_progress_on_completion=True,
        sla_seconds=3600,  # 1 hour SLA
        on_failure_column="Blocked",
        sla_escalation_column="Blocked",
        execution_type="task_queue",
    )

    review = ColumnTemplate(
        name="Review",
        type=ColumnType.MANUAL,  # Manual review - requires human approval
        agent_id=None,
        is_pipeline_trigger=False,
        is_exit_column=False,
        position=4,
        auto_progress_on_completion=False,  # Manual approval required
        sla_seconds=86400,  # 24 hour SLA for review
        on_failure_column="Blocked",
        sla_escalation_column=None,
        execution_type="task_queue",
    )

    blocked = ColumnTemplate(
        name="Blocked",
        type=ColumnType.MANUAL,
        agent_id=None,
        is_pipeline_trigger=False,
        is_exit_column=False,
        position=5,
        auto_progress_on_completion=False,
        sla_seconds=None,
        on_failure_column=None,
        sla_escalation_column=None,
        execution_type="task_queue",
    )

    done = ColumnTemplate(
        name="Done",
        type=ColumnType.MANUAL,
        agent_id=None,
        is_pipeline_trigger=False,
        is_exit_column=True,  # Releasing lock when item enters
        position=6,
        auto_progress_on_completion=False,
        sla_seconds=None,
        on_failure_column=None,
        sla_escalation_column=None,
        execution_type="task_queue",
    )

    # Create the complete template
    template = BoardWorkflowTemplate(
        id="codetoreum-pipeline-v1",
        name="Codetoreum SDLC Pipeline",
        board_id="codetoreum-main",  # Matches the main Codetoreum board
        project_id="codetoreum",  # Project identifier
        columns=(backlog, analysis, implementation, testing, review, blocked, done),
    )

    return template
