"""End-to-end simulation test for the planning_design_pipeline scenario.

Exercises the full Planning & Design pipeline:
    human move (Backlog → Research) →
    Research (conversational: idea_researcher, CLO initializes loop) →
    human advance → Requirements (conversational: business_analyst) →
    human advance → Design (conversational: software_architect) →
    human advance → Work Breakdown (task_queue: work_breakdown_agent) →
    auto-advance → In Development (exit column)

Conversational columns use ConversationalLoopOrchestrator to initialize discussion
monitoring sessions.  The test manually advances items through conversational columns
(simulating human review of agent responses) and waits for the Work Breakdown agent
to complete, which triggers auto-progression to In Development.

No version-control operations are expected: this is a planning board, not an SDLC
board, so the test asserts that no branch-creation events are emitted.

Switchyard benchmark run: 6a5ddb21-f7ac-45e4-be3a-8c98000db2d7
"""

from pathlib import Path
from typing import cast

import pytest

from codetoreum.adapters.testing.capturing_mock_event_emitter import (
    CapturingMockEventEmitter,
)
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.ports.output.board_service import MovedByType
from tests.simulation.helpers import wait_for_column

SCENARIO_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios" / "planning_design_pipeline"

# Work item from external/work_items.yaml
WORK_ITEM_TITLE = "Optimize the Regression Test Cycle"

# Column names as defined in board_policy.yaml
COL_BACKLOG = "Backlog"
COL_RESEARCH = "Research"
COL_REQUIREMENTS = "Requirements"
COL_DESIGN = "Design"
COL_WORK_BREAKDOWN = "Work Breakdown"
COL_IN_DEVELOPMENT = "In Development"

# Expected number of ConversationalLoopStartedEvent emissions (one per conversational column)
EXPECTED_CLO_STARTS = 3

# Timeout for the final In Development assertion (covers 3 conversational advances + agent delay)
FINAL_COLUMN_TIMEOUT = 30.0


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def planning_env(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
):
    """Bootstrap + seed the planning_design_pipeline scenario."""
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)

    # Speed up agent execution delay for the task_queue Work Breakdown agent
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.05

    # Seed scenario from YAML
    await simulation_seeder.seed_from_yaml(SCENARIO_DIR)

    return simulation_bootstrap, simulation_seeder


# ============================================================================
# Helpers
# ============================================================================


def _find_work_item_id(seeder: SimulationDataSeeder, title_prefix: str) -> str | None:
    """Return the work_item_id for the first seeded item whose title starts with title_prefix."""
    for item_id in seeder.created_items.work_items:
        work_item = seeder._ticket_adapter._work_items.get(item_id)
        if work_item and work_item.title.startswith(title_prefix):
            return item_id  # type: ignore[no-any-return]
    return None


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_pipeline_reaches_in_development(planning_env):
    """Work item flows Backlog → Research → Requirements → Design → Work Breakdown → In Development.

    The three conversational columns each receive a ConversationalLoopStartedEvent.
    The Work Breakdown agent (task_queue) completes automatically and auto-progression
    moves the item to In Development.
    """
    bootstrap, seeder = planning_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = cast("MockBoardAdapter", adapters.board)

    work_item_id = _find_work_item_id(seeder, WORK_ITEM_TITLE)
    assert work_item_id, f"Could not find work item '{WORK_ITEM_TITLE}' in seeded items"

    # Confirm starting position
    pos = await board.get_item_position(work_item_id)
    assert pos.column_name == COL_BACKLOG, f"Expected item in Backlog, got '{pos.column_name}'"

    # ── Step 1: Human moves item to Research (pipeline trigger column) ────────
    await board.move_item_to_column(work_item_id, COL_RESEARCH, MovedByType.HUMAN)
    reached_research = await wait_for_column(board, work_item_id, COL_RESEARCH, timeout=5.0)
    assert reached_research, "Item did not reach Research column"

    # Brief pause to allow async CLO initialization to complete
    import asyncio

    await asyncio.sleep(0.2)

    # ── Step 2: Human advances item Research → Requirements ───────────────────
    await board.move_item_to_column(work_item_id, COL_REQUIREMENTS, MovedByType.HUMAN)
    reached_requirements = await wait_for_column(board, work_item_id, COL_REQUIREMENTS, timeout=5.0)
    assert reached_requirements, "Item did not reach Requirements column"

    await asyncio.sleep(0.2)

    # ── Step 3: Human advances item Requirements → Design ─────────────────────
    await board.move_item_to_column(work_item_id, COL_DESIGN, MovedByType.HUMAN)
    reached_design = await wait_for_column(board, work_item_id, COL_DESIGN, timeout=5.0)
    assert reached_design, "Item did not reach Design column"

    await asyncio.sleep(0.2)

    # ── Step 4: Human advances item Design → Work Breakdown ───────────────────
    # Work Breakdown uses task_queue execution; agent auto-completes and advances
    # item to In Development via auto_progress_on_completion.
    await board.move_item_to_column(work_item_id, COL_WORK_BREAKDOWN, MovedByType.HUMAN)

    # Wait for Work Breakdown agent to complete + auto-progression to In Development
    reached_in_development = await wait_for_column(
        board, work_item_id, COL_IN_DEVELOPMENT, timeout=FINAL_COLUMN_TIMEOUT
    )
    assert reached_in_development, (
        f"Item did not reach '{COL_IN_DEVELOPMENT}' within timeout. "
        f"Current position: {(await board.get_item_position(work_item_id)).column_name}"
    )


@pytest.mark.asyncio
async def test_conversational_loop_started_for_each_conversational_column(planning_env):
    """ConversationalLoopStartedEvent is emitted once for each conversational column.

    Research, Requirements, and Design are all conversational columns.  The
    ConversationalLoopOrchestrator should emit one ConversationalLoopStartedEvent per
    column when the work item enters it, for a total of three events.
    """
    import asyncio

    bootstrap, seeder = planning_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = cast("MockBoardAdapter", adapters.board)
    event_emitter = cast("CapturingMockEventEmitter", adapters.event_emitter_as_capturing())

    work_item_id = _find_work_item_id(seeder, WORK_ITEM_TITLE)
    assert work_item_id

    # Drive the item through all three conversational columns
    await board.move_item_to_column(work_item_id, COL_RESEARCH, MovedByType.HUMAN)
    await asyncio.sleep(0.2)
    await board.move_item_to_column(work_item_id, COL_REQUIREMENTS, MovedByType.HUMAN)
    await asyncio.sleep(0.2)
    await board.move_item_to_column(work_item_id, COL_DESIGN, MovedByType.HUMAN)
    await asyncio.sleep(0.2)

    clo_events = event_emitter.get_events_by_type("conversational_loop.started")
    assert len(clo_events) == EXPECTED_CLO_STARTS, (
        f"Expected {EXPECTED_CLO_STARTS} ConversationalLoopStartedEvent(s), "
        f"got {len(clo_events)}: {[e.column_name for e in clo_events]}"
    )

    # Verify agent assignments match the board_policy.yaml configuration
    agent_assignments = [e.agent_assignment for e in clo_events]
    assert "idea_researcher" in agent_assignments, "idea_researcher not found in CLO events"
    assert "business_analyst" in agent_assignments, "business_analyst not found in CLO events"
    assert "software_architect" in agent_assignments, "software_architect not found in CLO events"


@pytest.mark.asyncio
async def test_movement_history_shows_full_pipeline_path(planning_env):
    """Movement history reflects the complete column sequence."""
    import asyncio

    bootstrap, seeder = planning_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = cast("MockBoardAdapter", adapters.board)

    work_item_id = _find_work_item_id(seeder, WORK_ITEM_TITLE)
    assert work_item_id

    await board.move_item_to_column(work_item_id, COL_RESEARCH, MovedByType.HUMAN)
    await asyncio.sleep(0.2)
    await board.move_item_to_column(work_item_id, COL_REQUIREMENTS, MovedByType.HUMAN)
    await asyncio.sleep(0.2)
    await board.move_item_to_column(work_item_id, COL_DESIGN, MovedByType.HUMAN)
    await asyncio.sleep(0.2)
    await board.move_item_to_column(work_item_id, COL_WORK_BREAKDOWN, MovedByType.HUMAN)
    await wait_for_column(board, work_item_id, COL_IN_DEVELOPMENT, timeout=FINAL_COLUMN_TIMEOUT)

    history = board.get_movement_history(work_item_id)
    columns_visited = [history[0].from_column] + [m.to_column for m in history]

    assert columns_visited == [
        COL_BACKLOG,
        COL_RESEARCH,
        COL_REQUIREMENTS,
        COL_DESIGN,
        COL_WORK_BREAKDOWN,
        COL_IN_DEVELOPMENT,
    ], f"Unexpected column path: {columns_visited}"

    # First four moves are HUMAN; Work Breakdown → In Development is ORCHESTRATOR
    for move in history[:4]:
        assert (
            move.moved_by == MovedByType.HUMAN
        ), f"Expected HUMAN for {move.from_column}→{move.to_column}, got {move.moved_by}"
    assert (
        history[4].moved_by == MovedByType.ORCHESTRATOR
    ), f"Expected ORCHESTRATOR for Work Breakdown→In Development, got {history[4].moved_by}"


@pytest.mark.asyncio
async def test_no_version_control_operations(planning_env):
    """No branch or commit events should be emitted during the Planning & Design pipeline.

    This is a planning board: agents produce discussion content only, not code commits.
    """
    import asyncio

    bootstrap, seeder = planning_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = cast("MockBoardAdapter", adapters.board)
    event_emitter = cast("CapturingMockEventEmitter", adapters.event_emitter_as_capturing())

    work_item_id = _find_work_item_id(seeder, WORK_ITEM_TITLE)
    assert work_item_id

    await board.move_item_to_column(work_item_id, COL_RESEARCH, MovedByType.HUMAN)
    await asyncio.sleep(0.2)
    await board.move_item_to_column(work_item_id, COL_REQUIREMENTS, MovedByType.HUMAN)
    await asyncio.sleep(0.2)
    await board.move_item_to_column(work_item_id, COL_DESIGN, MovedByType.HUMAN)
    await asyncio.sleep(0.2)
    await board.move_item_to_column(work_item_id, COL_WORK_BREAKDOWN, MovedByType.HUMAN)
    await wait_for_column(board, work_item_id, COL_IN_DEVELOPMENT, timeout=FINAL_COLUMN_TIMEOUT)

    all_events = event_emitter.get_events()
    vcs_event_types = {
        "branch.created",
        "branch.pushed",
        "commit.created",
        "version_control.branch_created",
        "version_control.committed",
    }
    vcs_events = [e for e in all_events if getattr(e, "type", "") in vcs_event_types]

    assert not vcs_events, f"Unexpected VCS events emitted during planning pipeline: " f"{[e.type for e in vcs_events]}"
