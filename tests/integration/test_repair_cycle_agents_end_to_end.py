"""Integration test: repair_cycle_agents from YAML flows through to RepairCycleContext."""

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest

from codetoreum.domain.events import WorkItemColumnChangedEvent, now_iso
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder


@pytest.mark.asyncio
async def test_repair_cycle_agents_from_yaml_to_context(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Verify repair_cycle_agents from YAML reaches ColumnTemplate and is preserved."""
    # Seed the repair_cycle_test scenario which has repair_cycle_agents configured
    scenarios_dir = Path(__file__).parent.parent.parent / "scenarios" / "repair_cycle_test"
    await simulation_seeder.seed_from_yaml(file_path=scenarios_dir)

    # Verify the workflow template has repair_cycle_agents on the Testing column
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    workflow_config = adapters.workflow_config
    template = await workflow_config.get_board_workflow_template("test-board-1")
    assert template, "Expected workflow template for test-board-1"

    # Find Testing column
    testing_column = template.get_column_config("Testing")
    assert testing_column, "Expected Testing column in template"
    assert testing_column.repair_cycle_agents, "Expected repair_cycle_agents on Testing column"

    # Verify the agents match what was in the YAML
    agent_config = testing_column.repair_cycle_agents
    assert (
        agent_config.test_execution == "qa_engineer"
    ), f"Expected test_execution='qa_engineer', got '{agent_config.test_execution}'"
    assert (
        agent_config.code_fix == "senior_software_engineer"
    ), f"Expected code_fix='senior_software_engineer', got '{agent_config.code_fix}'"
    assert (
        agent_config.env_rebuild == "devops_engineer"
    ), f"Expected env_rebuild='devops_engineer', got '{agent_config.env_rebuild}'"
    assert (
        agent_config.env_verification == "qa_engineer"
    ), f"Expected env_verification='qa_engineer', got '{agent_config.env_verification}'"
    # These were not specified in the YAML
    assert agent_config.systemic_analysis is None
    assert agent_config.systemic_fix is None


@pytest.mark.asyncio
async def test_repair_cycle_handler_extracts_agents_from_column_template(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Verify RepairCycleEventHandler retrieves and uses agents from column template."""
    # Seed scenario
    scenarios_dir = Path(__file__).parent.parent.parent / "scenarios" / "repair_cycle_test"
    await simulation_seeder.seed_from_yaml(file_path=scenarios_dir)

    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)

    # Mock the repair cycle adapter to capture the context
    captured_contexts: list[Any] = []
    original_execute = adapters.repair_cycle.execute

    async def capture_execute(context: Any) -> Any:
        captured_contexts.append(context)
        return await original_execute(context)

    adapters.repair_cycle.execute = capture_execute

    # Publish a WorkItemColumnChanged event for an item entering Testing column
    event = WorkItemColumnChangedEvent(
        type="workitem.column_changed",
        timestamp=now_iso(),
        source="test",
        work_item_id="work-item-1",
        board_id="test-board-1",
        project_id="test-project",
        from_column="Backlog",
        to_column="Testing",
        moved_by="orchestrator",
    )

    # Publish event through the event bus
    event_bus = simulation_bootstrap.infrastructure.event_bus
    await event_bus.publish(event)

    # Allow async processing
    await asyncio.sleep(0.5)

    # Verify the context has the agent_config from the column template
    assert captured_contexts, "Expected repair cycle to be invoked"
    context = captured_contexts[0]
    assert context.agent_config is not None, "Expected agent_config in RepairCycleContext"
    assert (
        context.agent_config.test_execution == "qa_engineer"
    ), f"Expected test_execution='qa_engineer', got '{context.agent_config.test_execution}'"
    assert (
        context.agent_config.code_fix == "senior_software_engineer"
    ), f"Expected code_fix='senior_software_engineer', got '{context.agent_config.code_fix}'"
    assert (
        context.agent_config.env_rebuild == "devops_engineer"
    ), f"Expected env_rebuild='devops_engineer', got '{context.agent_config.env_rebuild}'"
    assert (
        context.agent_config.env_verification == "qa_engineer"
    ), f"Expected env_verification='qa_engineer', got '{context.agent_config.env_verification}'"


@pytest.mark.asyncio
async def test_repair_cycle_agents_backward_compatible_without_config(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Verify backward compatibility: columns without repair_cycle_agents still work."""
    # Seed a simple scenario with no repair_cycle_agents
    await simulation_seeder.seed_default_scenario()

    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)

    # Check that the default scenario's columns don't have repair_cycle_agents
    workflow_config = adapters.workflow_config
    template = await workflow_config.get_board_workflow_template("board-1")
    assert template, "Expected workflow template for board-1"

    # All columns should have repair_cycle_agents=None
    for column in template.columns:
        assert column.repair_cycle_agents is None, (
            f"Column '{column.name}' should have repair_cycle_agents=None, " f"got {column.repair_cycle_agents}"
        )
