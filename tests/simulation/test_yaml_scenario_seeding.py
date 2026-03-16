"""Phase 7: YAML Scenario Seeding Test.

Verifies that loading default.yaml via seed_from_yaml() produces a fully
functional simulation environment: projects, agents, work items, board with
workflow template, and proper board placements are all created and wired.

After seeding, moving a work item to the pipeline trigger column should cause
it to cascade through all automated columns and land in Done.
"""

import asyncio
from pathlib import Path
from typing import cast

import pytest

from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder
from codetoreum.ports.output.board_service import MovedByType
from tests.conftest import assert_condition
from tests.simulation.helpers import wait_for_column

# Path to the default scenario YAML relative to this file's location
_SCENARIOS_DIR = Path(__file__).parent.parent.parent / "scenarios"
_DEFAULT_YAML = _SCENARIOS_DIR / "default.yaml"


@pytest.mark.asyncio
async def test_yaml_scenario_seeding_and_cascade(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> None:
    """Load default.yaml, seed, trigger a work item, assert cascade to Done.

    This is the canonical Phase 7 test that exercises the full YAML seeding
    path: file load → Pydantic validation → project/agent/work item creation
    → board creation → workflow template registration → board placements.

    After seeding, moving the first work item to 'Ready' should trigger the
    board automation cascade and the item should reach 'Done'.
    """
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    seeder = SimulationDataSeeder(
        simulation_bootstrap,
        track_items=True,
        agent_repository=adapters.agent_repository,
        work_item_service=adapters.work_item_service,
    )
    if adapters.agent_executor is not None:
        adapters.agent_executor._execution_delay = 0.1

    # Verify the scenario file exists before attempting to load it
    assert _DEFAULT_YAML.exists(), (
        f"default.yaml not found at {_DEFAULT_YAML}. " "The scenarios/ directory must contain default.yaml."
    )

    # Load scenario from YAML — this exercises the full seeding pipeline
    await seeder.seed_from_yaml(_DEFAULT_YAML)

    if seeder.created_items.work_items:
        # At least one work item was seeded: trigger cascade and assert completion
        work_item_id = seeder.created_items.work_items[0]
        board = adapters.board

        await board.move_item_to_column(work_item_id, "Ready", MovedByType.HUMAN)

        reached_done = await wait_for_column(board, work_item_id, "Done", timeout=10.0)
        assert reached_done, (
            f"Work item did not reach 'Done' after YAML seeding. "
            f"Current position: {(await board.get_item_position(work_item_id)).column_name}"
        )

        # Wait for all agents to be triggered and recorded
        async def all_agents_executed():
            executions = adapters.agent_executor.executions
            item_executions = [e for e in executions if e["work_item_id"] == work_item_id]
            # Should have executed all 3 agents
            return len(item_executions) == 3

        await assert_condition(
            all_agents_executed,
            timeout=5.0,
            poll_interval=0.05,
            message="All agents should be executed and recorded"
        )

        # Verify all 3 agents were triggered in the correct order
        executions = adapters.agent_executor.executions
        item_executions = [e for e in executions if e["work_item_id"] == work_item_id]
        agent_order = [e["agent_id"] for e in item_executions]
        assert agent_order == [
            "architect",
            "coder",
            "tester",
        ], (
            f"Expected agents [architect, coder, tester] from YAML scenario, " f"got {agent_order}"
        )
    else:
        # No work items were seeded — at least verify that projects were created
        assert seeder.created_items.projects, (
            "YAML seeding produced neither work items nor projects. "
            "default.yaml should produce at least one project."
        )


@pytest.mark.asyncio
async def test_yaml_seeding_creates_expected_structure(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> None:
    """Verify YAML seeding creates all expected data structures from default.yaml.

    Checks that default.yaml seeds exactly:
    - 1 project
    - 3 agents (architect, coder, tester)
    - 3 work items
    - 1 board (board-1) with 5 columns
    """
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    seeder = SimulationDataSeeder(
        simulation_bootstrap,
        track_items=True,
        agent_repository=adapters.agent_repository,
        work_item_service=adapters.work_item_service,
    )

    assert _DEFAULT_YAML.exists(), f"default.yaml not found at {_DEFAULT_YAML}"

    await seeder.seed_from_yaml(_DEFAULT_YAML)

    # Verify project count
    assert (
        len(seeder.created_items.projects) == 1
    ), f"Expected 1 project from default.yaml, got {len(seeder.created_items.projects)}"

    # Verify agent count
    assert len(seeder.created_items.agents) == 3, (
        f"Expected 3 agents (architect, coder, tester) from default.yaml, "
        f"got {len(seeder.created_items.agents)}: {seeder.created_items.agents}"
    )
    assert set(seeder.created_items.agents) == {"architect", "coder", "tester"}, (
        f"Expected agent names {{architect, coder, tester}}, " f"got {set(seeder.created_items.agents)}"
    )

    # Verify work item count (default.yaml has 3 items)
    assert len(seeder.created_items.work_items) == 3, (
        f"Expected 3 work items from default.yaml, " f"got {len(seeder.created_items.work_items)}"
    )

    # Verify board was created
    assert (
        len(seeder.created_items.boards) == 1
    ), f"Expected 1 board from default.yaml, got {len(seeder.created_items.boards)}"
    assert (
        "board-1" in seeder.created_items.boards
    ), f"Expected board-1 to be created, got {seeder.created_items.boards}"

    # Verify all work items were placed on the board in Backlog
    board = adapters.board
    for work_item_id in seeder.created_items.work_items:
        pos = await board.get_item_position(work_item_id)
        assert pos.column_name == "Backlog", (
            f"Work item {work_item_id} should be in Backlog after seeding, " f"found in '{pos.column_name}'"
        )


@pytest.mark.asyncio
async def test_yaml_seeding_registers_workflow_template(
    simulation_bootstrap: SimulationApplicationBootstrap,
) -> None:
    """Verify YAML seeding registers a workflow template for board automation.

    The workflow template is what makes board automation work. Without it,
    moving a work item to a trigger column would not start any agent execution.
    """
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    seeder = SimulationDataSeeder(
        simulation_bootstrap,
        track_items=True,
        agent_repository=adapters.agent_repository,
        work_item_service=adapters.work_item_service,
    )

    assert _DEFAULT_YAML.exists(), f"default.yaml not found at {_DEFAULT_YAML}"

    await seeder.seed_from_yaml(_DEFAULT_YAML)

    # Verify the workflow template was registered for board-1
    workflow_config = adapters.workflow_config
    template = await workflow_config.get_board_workflow_template("board-1")

    assert template is not None, (
        "No workflow template registered for board-1 after YAML seeding. "
        "seed_from_yaml should call register_workflow_template() for each board."
    )

    # Verify the template has the correct columns
    column_names = [col.name for col in template.columns]
    assert "Backlog" in column_names, f"Backlog column not in template: {column_names}"
    assert "Done" in column_names, f"Done column not in template: {column_names}"

    # Verify at least one column is the pipeline trigger
    trigger_columns = [col for col in template.columns if col.is_pipeline_trigger]
    assert len(trigger_columns) >= 1, (
        "No pipeline trigger column found in workflow template. "
        "The 'Ready' column should be marked as is_pipeline_trigger=True."
    )

    # The pipeline trigger should be the "Ready" column
    trigger_names = [col.name for col in trigger_columns]
    assert "Ready" in trigger_names, (
        f"Expected 'Ready' to be the pipeline trigger column, " f"found trigger columns: {trigger_names}"
    )

    # Verify exit column
    exit_columns = [col for col in template.columns if col.is_exit_column]
    assert len(exit_columns) >= 1, (
        "No exit column found in workflow template. " "The 'Done' column should be marked as is_exit_column=True."
    )
    exit_names = [col.name for col in exit_columns]
    assert "Done" in exit_names, f"Expected 'Done' to be the exit column, found: {exit_names}"
