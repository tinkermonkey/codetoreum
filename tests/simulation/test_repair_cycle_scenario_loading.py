"""Test that repair_cycle_test scenario with repair_cycle_agents loads correctly.

This test verifies:
- repair_cycle_test scenario directory can be loaded
- Board policy with repair_cycle_agents parses correctly
- RepairCycleAgentConfigModel is properly instantiated from YAML
- to_domain() produces valid domain objects
"""

from pathlib import Path

import pytest

from codetoreum.infrastructure.simulation.scenario_models import OrchestratorConfigModel
from codetoreum.infrastructure.simulation.seeding import _merge_yaml_dir


class TestRepairCycleScenarioLoading:
    """Test loading repair_cycle_test scenario with repair_cycle_agents."""

    @staticmethod
    def _get_scenarios_dir() -> Path:
        """Get the scenarios directory path."""
        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent
        scenarios_dir = project_root / "scenarios"
        return scenarios_dir

    @pytest.fixture
    def orch_config(self) -> OrchestratorConfigModel:
        """Load and parse repair_cycle_test orchestrator config once for the class."""
        orch_dir = self._get_scenarios_dir() / "repair_cycle_test" / "orchestrator"
        orch_data = _merge_yaml_dir(orch_dir)
        return OrchestratorConfigModel(**orch_data)

    def test_repair_cycle_scenario_exists(self) -> None:
        """Verify repair_cycle_test scenario directory exists."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_dir = scenarios_dir / "repair_cycle_test"
        assert scenario_dir.is_dir(), f"repair_cycle_test scenario directory not found at {scenario_dir}"

    def test_repair_cycle_orchestrator_files_exist(self) -> None:
        """Verify all required orchestrator YAML files exist."""
        scenarios_dir = self._get_scenarios_dir()
        orch_dir = scenarios_dir / "repair_cycle_test" / "orchestrator"
        assert orch_dir.is_dir(), "orchestrator/ directory not found"
        assert (orch_dir / "simulation.yaml").is_file(), "simulation.yaml missing"
        assert (orch_dir / "agents.yaml").is_file(), "agents.yaml missing"
        assert (orch_dir / "workflows.yaml").is_file(), "workflows.yaml missing"
        assert (orch_dir / "board_policy.yaml").is_file(), "board_policy.yaml missing"

    def test_repair_cycle_orchestrator_config_loads(self) -> None:
        """Load orchestrator config from repair_cycle_test scenario."""
        scenarios_dir = self._get_scenarios_dir()
        orch_dir = scenarios_dir / "repair_cycle_test" / "orchestrator"

        orch_data = _merge_yaml_dir(orch_dir)
        assert orch_data is not None, "Failed to merge orchestrator YAML files"
        assert len(orch_data) > 0, "Orchestrator data is empty"

    def test_repair_cycle_orchestrator_model_parses(self, orch_config: OrchestratorConfigModel) -> None:
        """Parse orchestrator config as OrchestratorConfigModel."""
        assert orch_config.name == "repair_cycle_test"
        assert len(orch_config.agents) == 3
        assert len(orch_config.board_policies) == 1

    def test_repair_cycle_board_policy_has_repair_cycle_agents(self, orch_config: OrchestratorConfigModel) -> None:
        """Verify board policy column has repair_cycle_agents configured."""
        policy = orch_config.board_policies[0]
        assert policy.board_id == "test-board-1"

        # Find the "Testing" column
        testing_col = None
        for col in policy.column_configs:
            if col.name == "Testing":
                testing_col = col
                break

        assert testing_col is not None, "Testing column not found"
        assert testing_col.repair_cycle_agents is not None, "repair_cycle_agents not set"

    def test_repair_cycle_agents_fields_populated(self, orch_config: OrchestratorConfigModel) -> None:
        """Verify all repair_cycle_agents fields are populated correctly."""
        policy = orch_config.board_policies[0]
        testing_col = next((col for col in policy.column_configs if col.name == "Testing"), None)
        assert testing_col is not None

        rc = testing_col.repair_cycle_agents
        assert rc is not None
        assert rc.test_execution == "qa_engineer"
        assert rc.code_fix == "senior_software_engineer"
        assert rc.systemic_analysis is None
        assert rc.systemic_fix is None
        assert rc.env_rebuild == "devops_engineer"
        assert rc.env_verification == "qa_engineer"

    def test_repair_cycle_agents_to_domain(self, orch_config: OrchestratorConfigModel) -> None:
        """Verify repair_cycle_agents.to_domain() produces valid domain objects."""
        policy = orch_config.board_policies[0]
        testing_col = next((col for col in policy.column_configs if col.name == "Testing"), None)
        assert testing_col is not None

        rc = testing_col.repair_cycle_agents
        assert rc is not None

        # Convert to domain
        domain_rc = rc.to_domain()

        # Verify domain object
        assert domain_rc.test_execution == "qa_engineer"
        assert domain_rc.code_fix == "senior_software_engineer"
        assert domain_rc.systemic_analysis is None
        assert domain_rc.systemic_fix is None
        assert domain_rc.env_rebuild == "devops_engineer"
        assert domain_rc.env_verification == "qa_engineer"

    def test_repair_cycle_agents_validation_passes(self, orch_config: OrchestratorConfigModel) -> None:
        """Verify cross-field validation passes for repair_cycle_test scenario."""
        # The fact that OrchestratorConfigModel(**orch_data) succeeded proves validation passed
        assert orch_config is not None
        assert len(orch_config.agents) > 0
        assert len(orch_config.board_policies) > 0
