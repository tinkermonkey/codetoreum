"""Tests for SimulationConfig and related classes."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from codetoreum.infrastructure.simulation.simulation_config import (
    AgentBehaviorConfig,
    ContainerBehaviorConfig,
    FidelityLevel,
    MetricsConfig,
    NotificationConfig,
    SimulationConfig,
    TimeConfig,
)


class TestFidelityLevel:
    """Test suite for FidelityLevel enum."""

    def test_fidelity_levels_defined(self) -> None:
        """Test that all expected fidelity levels are defined."""
        assert FidelityLevel.LOW.value == "low"
        assert FidelityLevel.MEDIUM.value == "medium"
        assert FidelityLevel.HIGH.value == "high"


class TestAgentBehaviorConfig:
    """Test suite for AgentBehaviorConfig."""

    def test_create_valid_config(self) -> None:
        """Test creating a valid agent behavior config."""
        config = AgentBehaviorConfig(agent_id="test_agent")
        assert config.agent_id == "test_agent"
        assert config.execution_delay == 0.1
        assert config.success_rate == 1.0
        assert config.response_patterns == {}

    def test_validation_fails_without_agent_id(self) -> None:
        """Test that empty agent_id raises ValueError."""
        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            AgentBehaviorConfig(agent_id="")

    def test_validation_fails_negative_delay(self) -> None:
        """Test that negative execution_delay raises ValueError."""
        with pytest.raises(ValueError, match="execution_delay must be non-negative"):
            AgentBehaviorConfig(agent_id="test", execution_delay=-0.1)

    def test_validation_fails_invalid_success_rate(self) -> None:
        """Test that success_rate outside [0.0, 1.0] raises ValueError."""
        with pytest.raises(ValueError, match="success_rate must be between 0.0 and 1.0"):
            AgentBehaviorConfig(agent_id="test", success_rate=1.5)

        with pytest.raises(ValueError, match="success_rate must be between 0.0 and 1.0"):
            AgentBehaviorConfig(agent_id="test", success_rate=-0.1)


class TestContainerBehaviorConfig:
    """Test suite for ContainerBehaviorConfig."""

    def test_create_valid_config(self) -> None:
        """Test creating a valid container behavior config."""
        config = ContainerBehaviorConfig()
        assert config.default_exit_code == 0
        assert config.execution_delay == 0.1

    def test_validation_fails_negative_delay(self) -> None:
        """Test that negative execution_delay raises ValueError."""
        with pytest.raises(ValueError, match="execution_delay must be non-negative"):
            ContainerBehaviorConfig(execution_delay=-0.1)


class TestNotificationConfig:
    """Test suite for NotificationConfig."""

    def test_create_valid_config(self) -> None:
        """Test creating a valid notification config."""
        config = NotificationConfig()
        assert config.send_delay == 0.01
        assert config.simulate_failures is False
        assert config.failure_rate == 0.0

    def test_validation_fails_negative_delay(self) -> None:
        """Test that negative send_delay raises ValueError."""
        with pytest.raises(ValueError, match="send_delay must be non-negative"):
            NotificationConfig(send_delay=-0.01)

    def test_validation_fails_invalid_failure_rate(self) -> None:
        """Test that failure_rate outside [0.0, 1.0] raises ValueError."""
        with pytest.raises(ValueError, match="failure_rate must be between 0.0 and 1.0"):
            NotificationConfig(failure_rate=1.5)


class TestTimeConfig:
    """Test suite for TimeConfig."""

    def test_create_valid_config(self) -> None:
        """Test creating a valid time config."""
        config = TimeConfig()
        assert config.speed_multiplier == 10.0
        assert config.start_time is None
        assert config.auto_advance is False

    def test_validation_fails_zero_speed(self) -> None:
        """Test that zero speed_multiplier raises ValueError."""
        with pytest.raises(ValueError, match="speed_multiplier must be positive"):
            TimeConfig(speed_multiplier=0.0)

    def test_validation_fails_negative_speed(self) -> None:
        """Test that negative speed_multiplier raises ValueError."""
        with pytest.raises(ValueError, match="speed_multiplier must be positive"):
            TimeConfig(speed_multiplier=-10.0)


class TestMetricsConfig:
    """Test suite for MetricsConfig."""

    def test_create_valid_config(self) -> None:
        """Test creating a valid metrics config."""
        config = MetricsConfig()
        assert config.enabled is True
        assert len(config.tracked_metrics) > 0


class TestSimulationConfig:
    """Test suite for SimulationConfig."""

    def test_create_minimal_config(self) -> None:
        """Test creating a minimal valid config."""
        config = SimulationConfig(scenario_name="test")
        assert config.scenario_name == "test"
        assert config.fidelity_level == FidelityLevel.LOW

    def test_validation_fails_without_scenario_name(self) -> None:
        """Test that empty scenario_name raises ValueError."""
        with pytest.raises(ValueError, match="scenario_name cannot be empty"):
            SimulationConfig(scenario_name="")

    def test_validation_fails_negative_timing_params(self) -> None:
        """Test that negative timing parameters raise ValueError."""
        with pytest.raises(ValueError, match="ms_per_token must be non-negative"):
            SimulationConfig(scenario_name="test", ms_per_token=-1.0)

        with pytest.raises(ValueError, match="ms_per_file_operation must be non-negative"):
            SimulationConfig(scenario_name="test", ms_per_file_operation=-1.0)

        with pytest.raises(ValueError, match="ms_per_event must be non-negative"):
            SimulationConfig(scenario_name="test", ms_per_event=-1.0)

    def test_get_agent_config_returns_default_for_missing_agent(self) -> None:
        """Test that get_agent_config returns default for missing agent."""
        config = SimulationConfig(scenario_name="test")
        agent_config = config.get_agent_config("missing_agent")

        assert agent_config.agent_id == "missing_agent"
        assert agent_config.execution_delay == 0.1

    def test_get_agent_config_returns_existing_agent(self) -> None:
        """Test that get_agent_config returns existing agent config."""
        config = SimulationConfig(scenario_name="test")
        original = AgentBehaviorConfig(agent_id="test_agent", execution_delay=0.5)
        config.set_agent_config("test_agent", original)

        retrieved = config.get_agent_config("test_agent")
        assert retrieved.execution_delay == 0.5

    def test_set_agent_config_validates_agent_id_match(self) -> None:
        """Test that set_agent_config validates agent_id match."""
        config = SimulationConfig(scenario_name="test")
        agent_config = AgentBehaviorConfig(agent_id="agent_a")

        with pytest.raises(ValueError, match="config.agent_id .* does not match"):
            config.set_agent_config("agent_b", agent_config)

    def test_add_agent_response_pattern(self) -> None:
        """Test adding a response pattern for an agent."""
        config = SimulationConfig(scenario_name="test")
        config.add_agent_response_pattern("test_agent", "error.*", "Error occurred")

        agent_config = config.get_agent_config("test_agent")
        assert "error.*" in agent_config.response_patterns
        assert agent_config.response_patterns["error.*"] == "Error occurred"

    def test_set_container_command_result(self) -> None:
        """Test setting container command result."""
        config = SimulationConfig(scenario_name="test")
        config.set_container_command_result("git clone", 0, "Cloning...", "")

        assert "git clone" in config.container.command_exit_codes
        assert config.container.command_exit_codes["git clone"] == 0
        assert config.container.command_outputs["git clone"]["stdout"] == "Cloning..."

    def test_create_fast_config(self) -> None:
        """Test creating fast config."""
        config = SimulationConfig.create_fast_config("test_scenario")
        assert config.scenario_name == "test_scenario"
        assert config.time.speed_multiplier == 100.0
        assert config.fidelity_level == FidelityLevel.LOW
        assert config.container.execution_delay == 0.0

    def test_create_fast_config_with_custom_fidelity(self) -> None:
        """Test creating fast config with custom fidelity level."""
        config = SimulationConfig.create_fast_config(
            "test_scenario",
            fidelity_level=FidelityLevel.MEDIUM,
            ms_per_token=100.0,
        )
        assert config.fidelity_level == FidelityLevel.MEDIUM
        assert config.ms_per_token == 100.0

    def test_create_realistic_config(self) -> None:
        """Test creating realistic config."""
        config = SimulationConfig.create_realistic_config("test_scenario")
        assert config.scenario_name == "test_scenario"
        assert config.time.speed_multiplier == 10.0
        assert config.fidelity_level == FidelityLevel.MEDIUM

    def test_create_high_fidelity_config(self) -> None:
        """Test creating high fidelity config."""
        config = SimulationConfig.create_high_fidelity_config("test_scenario")
        assert config.scenario_name == "test_scenario"
        assert config.fidelity_level == FidelityLevel.HIGH
        assert config.notifications.simulate_failures is True

    def test_to_dict(self) -> None:
        """Test converting config to dictionary."""
        config = SimulationConfig.create_fast_config("test")
        data = config.to_dict()

        assert data["scenario_name"] == "test"
        assert data["fidelity_level"] == "low"
        assert data["ms_per_token"] == 50.0
        assert data["ms_per_file_operation"] == 10.0
        assert data["ms_per_event"] == 1.0

    def test_from_dict_preserves_timing_params(self) -> None:
        """Test that from_dict preserves timing parameters."""
        data = {
            "scenario_name": "test",
            "fidelity_level": "medium",
            "ms_per_token": 100.0,
            "ms_per_file_operation": 20.0,
            "ms_per_event": 5.0,
        }

        config = SimulationConfig.from_dict(data)
        assert config.fidelity_level == FidelityLevel.MEDIUM
        assert config.ms_per_token == 100.0
        assert config.ms_per_file_operation == 20.0
        assert config.ms_per_event == 5.0

    def test_from_dict_uses_defaults_when_missing(self) -> None:
        """Test that from_dict uses defaults for missing timing parameters."""
        data = {"scenario_name": "test"}

        config = SimulationConfig.from_dict(data)
        assert config.fidelity_level == FidelityLevel.LOW
        assert config.ms_per_token == 50.0
        assert config.ms_per_file_operation == 10.0
        assert config.ms_per_event == 1.0

    def test_from_yaml_basic(self) -> None:
        """Test loading config from YAML file."""
        yaml_content = """name: TestScenario
description: Test simulation scenario
speed_multiplier: 20.0
auto_advance: false
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            assert config.scenario_name == "TestScenario"
            assert config.scenario_description == "Test simulation scenario"
            assert config.time.speed_multiplier == 20.0
            assert config.fidelity_level == FidelityLevel.LOW
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_with_timing_params(self) -> None:
        """Test that from_yaml preserves timing parameters."""
        yaml_content = """name: TimingTest
fidelity_level: medium
ms_per_token: 75.0
ms_per_file_operation: 15.0
ms_per_event: 2.5
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            assert config.fidelity_level == FidelityLevel.MEDIUM
            assert config.ms_per_token == 75.0
            assert config.ms_per_file_operation == 15.0
            assert config.ms_per_event == 2.5
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_with_all_params(self) -> None:
        """Test loading YAML with all parameters."""
        yaml_content = """name: FullConfig
description: Full configuration test
speed_multiplier: 50.0
auto_advance: true
fidelity_level: high
ms_per_token: 100.0
ms_per_file_operation: 25.0
ms_per_event: 5.0
container:
  default_exit_code: 1
  execution_delay: 0.5
notifications:
  send_delay: 0.05
  simulate_failures: true
  failure_rate: 0.1
metrics:
  enabled: true
metadata:
  project_id: "test-project"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            assert config.scenario_name == "FullConfig"
            assert config.time.speed_multiplier == 50.0
            assert config.time.auto_advance is True
            assert config.fidelity_level == FidelityLevel.HIGH
            assert config.ms_per_token == 100.0
            assert config.ms_per_file_operation == 25.0
            assert config.ms_per_event == 5.0
            assert config.container.default_exit_code == 1
            assert config.container.execution_delay == 0.5
            assert config.notifications.send_delay == 0.05
            assert config.notifications.simulate_failures is True
            assert config.notifications.failure_rate == 0.1
            assert config.metadata["project_id"] == "test-project"
            assert "yaml_file" in config.metadata
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_missing_file_raises_error(self) -> None:
        """Test that missing YAML file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Scenario file not found"):
            SimulationConfig.from_yaml("/nonexistent/file.yaml")

    def test_from_yaml_empty_file_raises_error(self) -> None:
        """Test that empty YAML file raises ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Empty YAML file"):
                SimulationConfig.from_yaml(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_missing_name_raises_error(self) -> None:
        """Test that missing name field raises ValueError."""
        yaml_content = """description: No name provided
speed_multiplier: 10.0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="must contain 'name' field"):
                SimulationConfig.from_yaml(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_adds_yaml_file_to_metadata(self) -> None:
        """Test that from_yaml adds yaml_file path to metadata."""
        yaml_content = """name: MetadataTest
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            assert "yaml_file" in config.metadata
            assert config.metadata["yaml_file"] == str(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_roundtrip_to_dict_from_dict(self) -> None:
        """Test that config survives roundtrip through dict."""
        original = SimulationConfig.create_realistic_config(
            "roundtrip_test",
            fidelity_level=FidelityLevel.MEDIUM,
            ms_per_token=75.0,
            ms_per_file_operation=15.0,
            ms_per_event=2.5,
        )
        original.metadata["custom_key"] = "custom_value"

        data = original.to_dict()
        restored = SimulationConfig.from_dict(data)

        assert restored.scenario_name == original.scenario_name
        assert restored.time.speed_multiplier == original.time.speed_multiplier
        assert restored.fidelity_level == original.fidelity_level
        assert restored.ms_per_token == original.ms_per_token
        assert restored.ms_per_file_operation == original.ms_per_file_operation
        assert restored.ms_per_event == original.ms_per_event
        assert restored.metadata["custom_key"] == "custom_value"
