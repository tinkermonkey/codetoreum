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
        """Test loading the smoke scenario directory."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_dir = scenarios_dir / "smoke"

        if not scenario_dir.is_dir():
            pytest.skip(f"Scenario directory not found: {scenario_dir}")

        config = SimulationConfig.from_yaml(scenario_dir)
        assert config.scenario_name
        assert config.time.speed_multiplier > 0

    def test_load_demo_scenario(self) -> None:
        """Test loading the sdlc_pipeline scenario directory."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_dir = scenarios_dir / "sdlc_pipeline"

        if not scenario_dir.is_dir():
            pytest.skip(f"Scenario directory not found: {scenario_dir}")

        config = SimulationConfig.from_yaml(scenario_dir)
        assert config.scenario_name
        assert config.time.speed_multiplier > 0

    def test_load_review_cycle_scenario(self) -> None:
        """Test loading the review_cycle scenario directory."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_dir = scenarios_dir / "review_cycle"

        if not scenario_dir.is_dir():
            pytest.skip(f"Scenario directory not found: {scenario_dir}")

        config = SimulationConfig.from_yaml(scenario_dir)
        assert config.scenario_name
        assert config.time.speed_multiplier > 0

    def test_load_failure_recovery_scenario(self) -> None:
        """Test loading the failure_recovery scenario directory."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_dir = scenarios_dir / "failure_recovery"

        if not scenario_dir.is_dir():
            pytest.skip(f"Scenario directory not found: {scenario_dir}")

        config = SimulationConfig.from_yaml(scenario_dir)
        assert config.scenario_name
        assert config.time.speed_multiplier > 0

    def test_load_stress_test_scenario(self) -> None:
        """Test loading the stress_test scenario directory."""
        scenarios_dir = self._get_scenarios_dir()
        scenario_dir = scenarios_dir / "stress_test"

        if not scenario_dir.is_dir():
            pytest.skip(f"Scenario directory not found: {scenario_dir}")

        config = SimulationConfig.from_yaml(scenario_dir)
        assert config.scenario_name
        assert config.time.speed_multiplier > 0

    def test_load_mixed_github_real_scenario(self) -> None:
        """Test loading mixed_github/ directory with flexible key handling.

        The directory uses:
        - Nested simulation: key (speed_multiplier under simulation:)
        - agents: as list-of-objects
        - containers: (plural) instead of container:
        - fidelity: MEDIUM (uppercase)
        """
        scenarios_dir = self._get_scenarios_dir()
        scenario_dir = scenarios_dir / "mixed_github"

        if not scenario_dir.is_dir():
            pytest.skip(f"Scenario directory not found: {scenario_dir}")

        config = SimulationConfig.from_yaml(scenario_dir)

        # Verify scenario name
        assert config.scenario_name == "mixed_github"
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
        """Test loading mixed_full_github/ directory with flexible key handling.

        The directory uses:
        - Nested simulation: key
        - agents: as list-of-objects with 4 agents
        - containers: (plural)
        - fidelity: MEDIUM
        """
        scenarios_dir = self._get_scenarios_dir()
        scenario_dir = scenarios_dir / "mixed_full_github"

        if not scenario_dir.is_dir():
            pytest.skip(f"Scenario directory not found: {scenario_dir}")

        config = SimulationConfig.from_yaml(scenario_dir)

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
        """Test loading mixed_full_real/ directory with flexible key handling.

        The directory uses:
        - Nested simulation: key
        - agents: as list-of-objects with 4 agents
        - containers: (plural)
        - fidelity: HIGH (uppercase)

        Note: This directory references unregistered adapters (vault, prometheus, slack, git),
        but the YAML parsing should still succeed. The adapter validation happens later
        during runtime via AdapterResolver.validate_credentials().
        """
        scenarios_dir = self._get_scenarios_dir()
        scenario_dir = scenarios_dir / "mixed_full_real"

        if not scenario_dir.is_dir():
            pytest.skip(f"Scenario directory not found: {scenario_dir}")

        config = SimulationConfig.from_yaml(scenario_dir)

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
        """Test that all scenario directories in scenarios/ are loadable.

        Each scenario is now a directory containing per-adapter YAML files.
        This comprehensive test ensures no YAML parsing errors occur for any scenario.
        """
        scenarios_dir = self._get_scenarios_dir()

        if not scenarios_dir.exists():
            pytest.skip(f"Scenarios directory not found: {scenarios_dir}")

        scenario_dirs = sorted(
            p for p in scenarios_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
        assert len(scenario_dirs) > 0, "No scenario directories found in scenarios/"

        loaded_configs = []
        errors = []

        for scenario_dir in scenario_dirs:
            scenario_label = scenario_dir.name
            try:
                config = SimulationConfig.from_yaml(scenario_dir)
                loaded_configs.append((scenario_label, config))
            except Exception as e:
                errors.append((scenario_label, str(e)))

        # Report any errors found
        if errors:
            error_msg = "Failed to load the following scenario directories:\n"
            for dirname, error in errors:
                error_msg += f"  {dirname}/: {error}\n"
            pytest.fail(error_msg)

        # Verify all directories were loaded
        assert len(loaded_configs) == len(
            scenario_dirs
        ), f"Loaded {len(loaded_configs)} scenarios but found {len(scenario_dirs)} directories"

        # Verify each config has required fields
        for dirname, config in loaded_configs:
            assert config.scenario_name, f"{dirname}/: scenario_name is required"
            assert config.time.speed_multiplier > 0, f"{dirname}/: speed_multiplier must be positive"
            assert isinstance(
                config.fidelity_level, FidelityLevel
            ), f"{dirname}/: fidelity_level must be a FidelityLevel enum"
