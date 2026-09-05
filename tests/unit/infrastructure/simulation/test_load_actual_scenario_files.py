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

    def test_all_scenario_files_are_loadable(self) -> None:
        """Test that all scenario directories in scenarios/ are loadable.

        Each scenario is now a directory containing per-adapter YAML files.
        This comprehensive test ensures no YAML parsing errors occur for any scenario.
        """
        scenarios_dir = self._get_scenarios_dir()

        if not scenarios_dir.exists():
            pytest.skip(f"Scenarios directory not found: {scenarios_dir}")

        scenario_dirs = sorted(p for p in scenarios_dir.iterdir() if p.is_dir() and not p.name.startswith("."))
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
