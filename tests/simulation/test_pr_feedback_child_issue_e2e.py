"""End-to-end simulation test for the pr_feedback_child_issue scenario.

Exercises the full pipeline for a PR feedback child issue:
    human move (Backlog → Development) → Development agent →
    Code Review agent → Testing repair cycle → Staged

The repair cycle (Testing column) uses MockRepairCycleAdapter configured to pass
immediately for all three default test types (UNIT, INTEGRATION, E2E).  After the
repair cycle succeeds the WorkflowOrchestrator receives a RepairCycleCompletedEvent
and advances the item to Staged.

Board trigger note: In Codetoreum simulation the pipeline trigger column must be
type: automated so BoardColumnEventHandler fires agent dispatch on entry.  The
human moves the item directly from Backlog to Development (the trigger column).

Switchyard benchmark run: 5d4a562b-39bc-49f9-a5d2-0861868e76c9
"""

from pathlib import Path
from typing import cast

import pytest

from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.domain.repair_cycle_types import RepairTestType
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.ports.output.board_service import MovedByType
from tests.simulation.helpers import wait_for_column

SCENARIO_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios" / "pr_feedback_child_issue"

# Board and column constants derived from scenario YAML
CHILD_ITEM_TITLE = "[PR Feedback] Test Coverage Gaps"


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def pr_feedback_env(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
):
    """Bootstrap + seed PR feedback scenario with fast repair cycle."""
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)

    # Speed up agent execution delay
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.05

    # Seed scenario from YAML
    await simulation_seeder.seed_from_yaml(SCENARIO_DIR)

    # Configure repair cycle to pass immediately on first call.
    # The Testing column has no explicit repair_cycle_test_types, so the
    # RepairCycleEventHandler falls back to UNIT → INTEGRATION → E2E.
    repair_cycle = adapters.repair_cycle_as_mock()
    for test_type in (RepairTestType.UNIT, RepairTestType.INTEGRATION, RepairTestType.E2E):
        repair_cycle.set_pass_immediately(test_type, total_tests=1)

    return simulation_bootstrap, simulation_seeder


# ============================================================================
# Tests
# ============================================================================


@pytest.mark.asyncio
async def test_child_issue_cascades_through_repair_cycle_to_staged(pr_feedback_env):
    """Child issue moves Backlog → Development → Code Review → Testing → Staged.

    The repair cycle succeeds on the first pass. The WorkflowOrchestrator responds to
    the RepairCycleCompletedEvent and advances the item to Staged.
    """
    bootstrap, seeder = pr_feedback_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = cast("MockBoardAdapter", adapters.board)

    # Locate the child work item seeded from external/work_items.yaml
    work_item_id = _find_work_item_id(seeder, CHILD_ITEM_TITLE)
    assert work_item_id, f"Could not find work item '{CHILD_ITEM_TITLE}' in seeded items"

    # Confirm starting position
    pos = await board.get_item_position(work_item_id)
    assert pos.column_name == "Backlog", f"Expected item in Backlog, got '{pos.column_name}'"

    # Human moves item from Backlog → Development (pipeline trigger)
    await board.move_item_to_column(work_item_id, "Development", MovedByType.HUMAN)

    # Wait for full cascade including repair cycle → Staged
    reached_staged = await wait_for_column(board, work_item_id, "Staged", timeout=20.0)
    assert reached_staged, (
        f"Item did not reach 'Staged' within timeout. "
        f"Current position: {(await board.get_item_position(work_item_id)).column_name}"
    )


@pytest.mark.asyncio
async def test_movement_history_shows_full_pipeline_path(pr_feedback_env):
    """Movement history reflects the Backlog → Development → Code Review → Testing → Staged path."""
    bootstrap, seeder = pr_feedback_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = cast("MockBoardAdapter", adapters.board)

    work_item_id = _find_work_item_id(seeder, CHILD_ITEM_TITLE)
    assert work_item_id

    await board.move_item_to_column(work_item_id, "Development", MovedByType.HUMAN)
    await wait_for_column(board, work_item_id, "Staged", timeout=20.0)

    history = board.get_movement_history(work_item_id)
    columns_visited = [history[0].from_column] + [m.to_column for m in history]

    assert columns_visited == [
        "Backlog",
        "Development",
        "Code Review",
        "Testing",
        "Staged",
    ], f"Unexpected column path: {columns_visited}"

    # First move is HUMAN; all subsequent moves are ORCHESTRATOR
    assert history[0].moved_by == MovedByType.HUMAN, "First move should be HUMAN"
    for move in history[1:]:
        assert (
            move.moved_by == MovedByType.ORCHESTRATOR
        ), f"Expected ORCHESTRATOR for {move.from_column}→{move.to_column}, got {move.moved_by}"


@pytest.mark.asyncio
async def test_repair_cycle_was_executed(pr_feedback_env):
    """MockRepairCycleAdapter recorded at least one repair cycle execution."""
    bootstrap, seeder = pr_feedback_env
    adapters = cast("SimulationAdapters", bootstrap.adapters)
    board = cast("MockBoardAdapter", adapters.board)
    repair_cycle = adapters.repair_cycle_as_mock()

    work_item_id = _find_work_item_id(seeder, CHILD_ITEM_TITLE)
    assert work_item_id

    await board.move_item_to_column(work_item_id, "Development", MovedByType.HUMAN)
    await wait_for_column(board, work_item_id, "Staged", timeout=20.0)

    # total_agent_calls > 0 confirms the repair cycle executed at least one test round
    # (total_iterations counts fix iterations; on a pass-immediately scenario it stays 0)
    assert (
        repair_cycle.total_agent_calls > 0
    ), f"Repair cycle was never executed (total_agent_calls={repair_cycle.total_agent_calls})"


# ============================================================================
# Helpers
# ============================================================================


def _find_work_item_id(seeder: SimulationDataSeeder, title_prefix: str) -> str | None:
    """Return the work_item_id for the first created item whose title starts with title_prefix.

    The seeder appends ' #N' to titles, so we match by prefix rather than exact equality.
    """
    for item_id in seeder.created_items.work_items:
        work_item = seeder._ticket_adapter._work_items.get(item_id)
        if work_item and work_item.title.startswith(title_prefix):
            return item_id
    return None
