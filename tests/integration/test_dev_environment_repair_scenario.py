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

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig, RepairTestRunConfig, RepairTestType
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder


@dataclass
class _RepairCycleContextImpl:
    """Test implementation of RepairCycleContext protocol."""

    stage_name: str
    workflow_run_id: str
    work_item_id: str
    project_id: str
    board_id: str
    test_configs: tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int
    agent_config: RepairCycleAgentConfig | None = None


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


@pytest.mark.asyncio
async def test_dev_environment_repair_end_to_end_agent_dispatch(
    simulation_bootstrap: SimulationApplicationBootstrap,
    simulation_seeder: SimulationDataSeeder,
) -> None:
    """End-to-end test: Verify repair cycle dispatches correct agents for each sub-task.

    This test exercises the full repair cycle flow:
    1. Seed the dev_environment_repair scenario with repair_cycle_agents configured
    2. Create a repair cycle context with agent assignments from column template
    3. Configure repair cycle adapter with test failures to trigger all sub-tasks
    4. Execute repair cycle and verify all 6 sub-tasks used correct agents
    5. Verify the mock adapter recorded the correct agent selections
    """
    # Seed the dev_environment_repair scenario
    scenarios_dir = Path(__file__).parent.parent.parent / "scenarios" / "dev_environment_repair"
    await simulation_seeder.seed_from_yaml(file_path=scenarios_dir)

    adapters = cast("SimulationAdapters", simulation_bootstrap.adapters)
    repair_cycle_adapter = adapters.repair_cycle
    repair_cycle_adapter.current_project = "test-project"

    # Configure systemic analysis to trigger both CODE_DEFECT (systemic fix) and ENVIRONMENT_ISSUE (env rebuild/verify)
    # This ensures all 6 sub-tasks are invoked: test_execution, code_fix, systemic_analysis,
    # systemic_fix (from CODE_DEFECT), env_rebuild, env_verification (from ENVIRONMENT_ISSUE)
    from codetoreum.domain.repair_cycle_types import FailureClassification, SystemicAnalysisResult
    mock_analysis = adapters.systemic_analysis_service_as_mock()
    mock_analysis.set_results([
        # Iteration 1: CODE_DEFECT with cross_cutting=True triggers systemic_fix
        SystemicAnalysisResult(
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.9,
            reasoning="Cross-cutting architectural issue",
            affected_files=("api.py", "models.py", "services.py"),
            recommended_action="Update API contract consistently",
            cross_cutting=True,
        ),
        # Iteration 2: ENVIRONMENT_ISSUE triggers env_rebuild and env_verification
        SystemicAnalysisResult(
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.9,
            reasoning="Environment misconfiguration after code changes",
            affected_files=(),
            recommended_action="Rebuild and verify environment",
            cross_cutting=True,  # Also mark as cross_cutting since it affects the whole system
        ),
    ])

    # Configure repair cycle with test failures to enable agent routing verification.
    # By setting UNIT tests to fail 3 times, we ensure code_fix is invoked multiple
    # times. The mock adapter's run_test_cycle loop will invoke both test_execution
    # and code_fix, and the configuration allows all 6 sub-tasks to be asserted.
    repair_cycle_adapter.set_iterations_until_success(RepairTestType.UNIT, 3)
    # INTEGRATION takes 1 iteration (passes)
    repair_cycle_adapter.set_iterations_until_success(RepairTestType.INTEGRATION, 1)
    # E2E takes 1 iteration (passes)
    repair_cycle_adapter.set_iterations_until_success(RepairTestType.E2E, 1)

    # Get the workflow config to retrieve the repair_cycle_agents from the column template
    workflow_config = adapters.workflow_config
    template = await workflow_config.get_board_workflow_template("dev-board-1")
    testing_column = template.get_column_config("Testing")
    agent_config = testing_column.repair_cycle_agents

    # Create a repair cycle context with the agent configuration from the column template
    # This simulates what the RepairCycleEventHandler does when it invokes the repair cycle
    context = _RepairCycleContextImpl(
        workflow_run_id="test-workflow-run",
        stage_name="Testing",
        work_item_id="work-item-dev-1",
        project_id="test-project",
        board_id="dev-board-1",
        agent_name="qa_engineer",  # Default agent for the Testing column
        agent_config=agent_config,  # This carries all 6 sub-task agent assignments
        test_configs=(
            RepairTestRunConfig(test_type=RepairTestType.UNIT, max_iterations=5, review_warnings=False),
            RepairTestRunConfig(test_type=RepairTestType.INTEGRATION, max_iterations=3, review_warnings=False),
            RepairTestRunConfig(test_type=RepairTestType.E2E, max_iterations=3, review_warnings=False),
        ),
        max_total_agent_calls=100,
        checkpoint_interval=2,
    )

    # Execute the repair cycle directly
    result = await repair_cycle_adapter.execute(context)

    # Verify that the repair cycle completed successfully
    assert result.overall_success, f"Expected repair cycle to succeed, but got: {result}"

    # Verify agent routing for all 6 repair cycle sub-tasks
    repair_cycle_adapter.assert_subtask_used_agent("test_execution", "qa_engineer")
    repair_cycle_adapter.assert_subtask_used_agent("code_fix", "senior_software_engineer")
    repair_cycle_adapter.assert_subtask_used_agent("systemic_analysis", "senior_software_engineer")
    repair_cycle_adapter.assert_subtask_used_agent("systemic_fix", "senior_software_engineer")
    repair_cycle_adapter.assert_subtask_used_agent("env_rebuild", "devops_engineer")
    repair_cycle_adapter.assert_subtask_used_agent("env_verification", "qa_engineer")
