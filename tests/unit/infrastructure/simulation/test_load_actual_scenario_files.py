"""Tests that load actual scenario YAML files to validate configuration parsing.

This test suite ensures that real scenario files in the scenarios/ directory
can be loaded successfully by SimulationConfig.from_yaml(), catching any key
mismatches or parsing errors that would otherwise silently fail.
"""

from pathlib import Path

import pytest

from codetoreum.infrastructure.simulation.simulation_config import FidelityLevel, SimulationConfig


class TestLoadActualScenarioFiles:
    """Test suite for loading actual scenario YAML files."""

    def _get_scenarios_dir(self) -> Path:
        """Get the scenarios directory path.

        The test file is at: tests/unit/infrastructure/simulation/test_load_actual_scenario_files.py
        That's 5 levels deep from the project root, so we navigate up 5 parents.
        """
        # Navigate from test file location to project root, then to scenarios/
        # Test file path: tests/unit/infrastructure/simulation/test_load_actual_scenario_files.py
        # Parent levels: test_file -> simulation -> infrastructure -> unit -> tests -> workspace (5 parents)
        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent.parent.parent
        scenarios_dir = project_root / "scenarios"

        # Fallback: try from current working directory if absolute path doesn't exist
        # This depends on pytest being run from the project root
        if not scenarios_dir.exists():
            scenarios_dir = Path("scenarios").resolve()

        return scenarios_dir

    def test_load_default_scenario(self) -> None:
        """Test loading the default scenario YAML file."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_file = scenarios_dir / "default.yaml"

        if not scenario_file.exists():
            pytest.skip(f"Scenario file not found: {scenario_file}")

        config = SimulationConfig.from_yaml(scenario_file)
        assert config.scenario_name
        assert config.time.speed_multiplier > 0

    def test_load_demo_scenario(self) -> None:
        """Test loading the demo scenario YAML file."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_file = scenarios_dir / "demo.yaml"

        if not scenario_file.exists():
            pytest.skip(f"Scenario file not found: {scenario_file}")

        config = SimulationConfig.from_yaml(scenario_file)
        assert config.scenario_name
        assert config.time.speed_multiplier > 0

    def test_load_review_cycle_scenario(self) -> None:
        """Test loading the review_cycle scenario YAML file."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_file = scenarios_dir / "review_cycle.yaml"

        if not scenario_file.exists():
            pytest.skip(f"Scenario file not found: {scenario_file}")

        config = SimulationConfig.from_yaml(scenario_file)
        assert config.scenario_name
        assert config.time.speed_multiplier > 0

    def test_load_failure_recovery_scenario(self) -> None:
        """Test loading the failure_recovery scenario YAML file."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_file = scenarios_dir / "failure_recovery.yaml"

        if not scenario_file.exists():
            pytest.skip(f"Scenario file not found: {scenario_file}")

        config = SimulationConfig.from_yaml(scenario_file)
        assert config.scenario_name
        assert config.time.speed_multiplier > 0

    def test_load_stress_test_scenario(self) -> None:
        """Test loading the stress_test scenario YAML file."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_file = scenarios_dir / "stress_test.yaml"

        if not scenario_file.exists():
            pytest.skip(f"Scenario file not found: {scenario_file}")

        config = SimulationConfig.from_yaml(scenario_file)
        assert config.scenario_name
        assert config.time.speed_multiplier > 0

    def test_load_mixed_github_real_scenario(self) -> None:
        """Test loading mixed_github_real.yaml with flexible key handling.

        This file uses:
        - Nested simulation: key (speed_multiplier under simulation:)
        - agents: as list-of-objects
        - containers: (plural) instead of container:
        - fidelity: MEDIUM (uppercase)
        """
        scenarios_dir = self._get_scenarios_dir()
        scenario_file = scenarios_dir / "mixed_github_real.yaml"

        if not scenario_file.exists():
            pytest.skip(f"Scenario file not found: {scenario_file}")

        config = SimulationConfig.from_yaml(scenario_file)

        # Verify scenario name
        assert config.scenario_name == "mixed_github_real"
        assert config.scenario_description

        # Verify nested simulation: speed_multiplier was parsed
        assert config.time.speed_multiplier == 10.0

        # Verify agents were parsed from list-of-objects format
        assert "reviewer" in config.agents
        assert "analyzer" in config.agents
        assert config.agents["reviewer"].execution_delay == 0.2
        assert config.agents["reviewer"].success_rate == 0.95
        assert config.agents["analyzer"].execution_delay == 0.15
        assert config.agents["analyzer"].success_rate == 0.98

        # Verify containers: (plural) was parsed
        assert config.container.default_exit_code == 0
        assert config.container.execution_delay == 0.1

        # Verify fidelity: MEDIUM was normalized and parsed
        assert config.fidelity_level == FidelityLevel.MEDIUM

        # Verify adapters were parsed
        assert config.adapters.board == "github"
        assert config.adapters.llm == "mock"
        assert config.adapters.container == "fake"

    def test_load_mixed_full_github_scenario(self) -> None:
        """Test loading mixed_full_github.yaml with flexible key handling.

        This file uses:
        - Nested simulation: key
        - agents: as list-of-objects with 4 agents
        - containers: (plural)
        - fidelity: MEDIUM
        """
        scenarios_dir = self._get_scenarios_dir()
        scenario_file = scenarios_dir / "mixed_full_github.yaml"

        if not scenario_file.exists():
            pytest.skip(f"Scenario file not found: {scenario_file}")

        config = SimulationConfig.from_yaml(scenario_file)

        # Verify scenario name
        assert config.scenario_name == "mixed_full_github"
        assert config.scenario_description

        # Verify nested simulation: speed_multiplier
        assert config.time.speed_multiplier == 10.0

        # Verify agents were parsed (4 agents in this scenario)
        assert "reviewer" in config.agents
        assert "analyzer" in config.agents
        assert "implementer" in config.agents
        assert "tester" in config.agents

        # Verify fidelity: MEDIUM
        assert config.fidelity_level == FidelityLevel.MEDIUM

        # Verify adapters
        assert config.adapters.board == "github"
        assert config.adapters.llm == "mock"
        assert config.adapters.container == "docker"

    def test_load_mixed_full_real_scenario(self) -> None:
        """Test loading mixed_full_real.yaml with flexible key handling.

        This file uses:
        - Nested simulation: key
        - agents: as list-of-objects with 4 agents
        - containers: (plural)
        - fidelity: HIGH (uppercase)

        Note: This file references unregistered adapters (vault, prometheus, slack, git),
        but the YAML parsing should still succeed. The adapter validation happens later
        during runtime via AdapterResolver.validate_credentials().
        """
        scenarios_dir = self._get_scenarios_dir()
        scenario_file = scenarios_dir / "mixed_full_real.yaml"

        if not scenario_file.exists():
            pytest.skip(f"Scenario file not found: {scenario_file}")

        config = SimulationConfig.from_yaml(scenario_file)

        # Verify scenario name
        assert config.scenario_name == "mixed_full_real"
        assert config.scenario_description

        # Verify nested simulation: speed_multiplier
        assert config.time.speed_multiplier == 1.0

        # Verify agents were parsed (4 agents in this scenario)
        assert "reviewer" in config.agents
        assert "analyzer" in config.agents
        assert "implementer" in config.agents
        assert "tester" in config.agents

        # Verify agent token_usage was parsed
        assert config.agents["reviewer"].token_usage["input"] == 2000
        assert config.agents["implementer"].token_usage["output"] == 2000

        # Verify fidelity: HIGH
        assert config.fidelity_level == FidelityLevel.HIGH

        # Verify adapters were parsed (including unregistered ones)
        # Note: The actual adapter registry validation happens during runtime
        assert config.adapters.board == "github"
        assert config.adapters.llm == "claude_code"
        assert config.adapters.container == "docker"

    def test_all_scenario_files_are_loadable(self) -> None:
        """Test that all scenario YAML files in scenarios/ directory are loadable.

        This comprehensive test ensures no YAML parsing errors occur for any scenario file.
        """
        scenarios_dir = self._get_scenarios_dir()

        if not scenarios_dir.exists():
            pytest.skip(f"Scenarios directory not found: {scenarios_dir}")

        yaml_files = sorted(scenarios_dir.glob("*.yaml"))
        assert len(yaml_files) > 0, "No YAML files found in scenarios directory"

        loaded_configs = []
        errors = []

        for scenario_file in yaml_files:
            try:
                config = SimulationConfig.from_yaml(scenario_file)
                loaded_configs.append((scenario_file.name, config))
            except Exception as e:
                errors.append((scenario_file.name, str(e)))

        # Report any errors found
        if errors:
            error_msg = "Failed to load the following scenario files:\n"
            for filename, error in errors:
                error_msg += f"  {filename}: {error}\n"
            pytest.fail(error_msg)

        # Verify all files were loaded
        assert len(loaded_configs) == len(yaml_files), (
            f"Loaded {len(loaded_configs)} files but found {len(yaml_files)} total"
        )

        # Verify each config has required fields
        for filename, config in loaded_configs:
            assert config.scenario_name, f"{filename}: scenario_name is required"
            assert config.time.speed_multiplier > 0, (
                f"{filename}: speed_multiplier must be positive"
            )
            assert isinstance(config.fidelity_level, FidelityLevel), (
                f"{filename}: fidelity_level must be a FidelityLevel enum"
            )
