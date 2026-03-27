"""Integration test: dev_environment_repair scenario with repair_cycle_agents configuration.

Verifies that the dev_environment_repair scenario:
1. Loads without Pydantic validation errors
2. Properly configures repair_cycle_agents for the Testing column
3. Uses specialized agents for each repair cycle sub-task
   - test_execution: qa_engineer (runs tests, parses results)
   - code_fix: senior_software_engineer (fixes code-level failures)
   - systemic_analysis: senior_software_engineer (classifies root causes)
   - systemic_fix: senior_software_engineer (applies cross-cutting fixes)
   - env_rebuild: devops_engineer (rebuilds Docker environment)
   - env_verification: qa_engineer (verifies environment health)
"""

from pathlib import Path
from typing import cast

import pytest

from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder


@pytest.mark.asyncio
async def test_dev_environment_repair_scenario_loads_without_errors(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Verify dev_environment_repair scenario loads without Pydantic validation errors."""
    scenarios_dir = Path(__file__).parent.parent.parent / "scenarios" / "dev_environment_repair"

    # Should load without raising any exceptions
    await simulation_seeder.seed_from_yaml(file_path=scenarios_dir)

    # Verify basic structure was seeded
    created_items = simulation_seeder.created_items
    assert len(created_items.projects) == 1, "Expected 1 project"
    assert len(created_items.agents) == 4, "Expected 4 agents (qa_engineer, senior_software_engineer, devops_engineer, code_reviewer)"
    assert len(created_items.boards) == 1, "Expected 1 board"


@pytest.mark.asyncio
async def test_dev_environment_repair_repair_cycle_agents_configuration(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Verify repair_cycle_agents configuration reaches the Testing column template."""
    # Seed the dev_environment_repair scenario
    scenarios_dir = Path(__file__).parent.parent.parent / "scenarios" / "dev_environment_repair"
    await simulation_seeder.seed_from_yaml(file_path=scenarios_dir)

    # Verify the workflow template has repair_cycle_agents on the Testing column
    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    workflow_config = adapters.workflow_config
    template = await workflow_config.get_board_workflow_template("dev-board-1")
    assert template, "Expected workflow template for dev-board-1"

    # Find Testing column
    testing_column = template.get_column_config("Testing")
    assert testing_column, "Expected Testing column in template"
    assert testing_column.repair_cycle_agents, "Expected repair_cycle_agents on Testing column"

    # Verify all six agent assignments match the Switchyard run db1dbf2a observations
    agent_config = testing_column.repair_cycle_agents

    # test_execution: qa_engineer (runs tests, parses results)
    assert agent_config.test_execution == "qa_engineer", (
        f"Expected test_execution='qa_engineer', got '{agent_config.test_execution}'"
    )

    # code_fix: senior_software_engineer (fixes code-level failures)
    assert agent_config.code_fix == "senior_software_engineer", (
        f"Expected code_fix='senior_software_engineer', got '{agent_config.code_fix}'"
    )

    # systemic_analysis: senior_software_engineer (classifies root causes)
    assert agent_config.systemic_analysis == "senior_software_engineer", (
        f"Expected systemic_analysis='senior_software_engineer', got '{agent_config.systemic_analysis}'"
    )

    # systemic_fix: senior_software_engineer (applies cross-cutting fixes)
    assert agent_config.systemic_fix == "senior_software_engineer", (
        f"Expected systemic_fix='senior_software_engineer', got '{agent_config.systemic_fix}'"
    )

    # env_rebuild: devops_engineer (rebuilds Docker environment)
    assert agent_config.env_rebuild == "devops_engineer", (
        f"Expected env_rebuild='devops_engineer', got '{agent_config.env_rebuild}'"
    )

    # env_verification: qa_engineer (verifies environment health)
    assert agent_config.env_verification == "qa_engineer", (
        f"Expected env_verification='qa_engineer', got '{agent_config.env_verification}'"
    )


@pytest.mark.asyncio
async def test_dev_environment_repair_all_agents_exist(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """Verify all agents referenced in repair_cycle_agents exist in agents.yaml."""
    # Seed the scenario
    scenarios_dir = Path(__file__).parent.parent.parent / "scenarios" / "dev_environment_repair"
    await simulation_seeder.seed_from_yaml(file_path=scenarios_dir)

    # Get created agents
    created_items = simulation_seeder.created_items
    agent_names = created_items.agents

    # Verify required agents exist
    required_agents = {"qa_engineer", "senior_software_engineer", "devops_engineer"}
    assert required_agents.issubset(set(agent_names)), (
        f"Expected agents {required_agents}, got {set(agent_names)}"
    )
