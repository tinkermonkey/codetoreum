"""Tests for SimulationConfig and related classes."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from codetoreum.infrastructure.simulation.simulation_config import (
    AdapterSelectionConfig,
    AgentBehaviorConfig,
    ContainerBehaviorConfig,
    FidelityLevel,
    MetricsConfig,
    NotificationConfig,
    SimulationConfig,
    TimeConfig,
)


class TestAdapterSelectionConfig:
    """Test suite for AdapterSelectionConfig."""

    def test_create_default_config(self) -> None:
        """Test creating adapter selection config with all defaults."""
        config = AdapterSelectionConfig()
        assert config.board == "mock"
        assert config.ticket == "in_memory"
        assert config.llm == "mock"
        assert config.version_control == "in_memory"
        assert config.container == "fake"
        assert config.event_store == "in_memory"
        assert config.metrics == "in_memory"
        assert config.storage == "in_memory"
        assert config.config_store == "in_memory"
        assert config.notifier == "mock"
        assert config.encryption == "simple"
        assert config.discussion_adapter == "mock"
        assert config.review_cycle == "mock"
        assert config.repair_cycle == "mock"
        assert config.project_manager == "mock"
        assert config.lock_service == "in_memory"
        assert config.workflow_config == "in_memory"
        assert config.queue_service == "in_memory"
        assert config.event_emitter == "capturing"
        assert config.message_broker == "in_memory"
        assert config.identity_service == "configurable"
        assert config.checkpoint_store == "in_memory"
        assert config.agent_repository == "in_memory"
        assert config.run_registry == "in_memory"
        assert config.branch_tracker == "in_memory"
        assert config.work_item_service == "mock"
        assert config.repository == "in_memory"

    def test_all_33_adapter_slots_present(self) -> None:
        """Test that all 33 adapter slots are defined."""
        config = AdapterSelectionConfig()
        field_names = set(config.__dataclass_fields__.keys())
        expected_adapters = {
            "board",
            "ticket",
            "llm",
            "version_control",
            "container",
            "event_store",
            "metrics",
            "storage",
            "config_store",
            "notifier",
            "encryption",
            "discussion_adapter",
            "review_cycle",
            "repair_cycle",
            "code_review",
            "project_manager",
            "lock_service",
            "workflow_config",
            "queue_service",
            "event_emitter",
            "message_broker",
            "identity_service",
            "checkpoint_store",
            "agent_repository",
            "run_registry",
            "branch_tracker",
            "work_item_service",
            "repository",
            "container_recovery",
            "systemic_analysis",
            "environment_repair",
            "ci_pipeline",
            "pr_review_cycle",
        }
        assert field_names == expected_adapters
        assert len(field_names) == 33

    def test_create_with_custom_values(self) -> None:
        """Test creating adapter selection config with custom values."""
        config = AdapterSelectionConfig(
            board="github",
            llm="claude_code",
            container="docker",
            event_store="elasticsearch",
        )
        assert config.board == "github"
        assert config.ticket == "in_memory"  # default
        assert config.llm == "claude_code"
        assert config.container == "docker"
        assert config.event_store == "elasticsearch"
        assert config.metrics == "in_memory"  # default

    def test_is_frozen(self) -> None:
        """Test that AdapterSelectionConfig is immutable."""
        config = AdapterSelectionConfig()
        with pytest.raises(AttributeError):
            config.board = "github"  # type: ignore

    def test_validation_fails_for_empty_string(self) -> None:
        """Test that empty string value raises ValueError."""
        with pytest.raises(ValueError, match="must be a non-empty string"):
            AdapterSelectionConfig(board="")

    def test_validation_fails_for_none(self) -> None:
        """Test that None value raises ValueError."""
        with pytest.raises(ValueError, match="must be a non-empty string"):
            AdapterSelectionConfig(board=None)  # type: ignore

    def test_validation_fails_for_non_string_type(self) -> None:
        """Test that non-string type raises ValueError."""
        with pytest.raises(ValueError, match="must be a non-empty string"):
            AdapterSelectionConfig(board=123)  # type: ignore

    def test_validation_fails_for_whitespace_only_string(self) -> None:
        """Test that whitespace-only string value raises ValueError."""
        with pytest.raises(ValueError, match="must be a non-empty string"):
            AdapterSelectionConfig(board="   ")
        with pytest.raises(ValueError, match="must be a non-empty string"):
            AdapterSelectionConfig(ticket="\t\n")
        with pytest.raises(ValueError, match="must be a non-empty string"):
            AdapterSelectionConfig(llm="  \t  ")


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
        with pytest.raises(FileNotFoundError, match="Scenario path not found"):
            SimulationConfig.from_yaml("/nonexistent/file.yaml")

    def test_from_yaml_empty_file_raises_error(self) -> None:
        """Test that empty YAML file raises ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Empty scenario"):
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


class TestAdapterSelectionConfigIntegration:
    """Test suite for AdapterSelectionConfig integration with SimulationConfig."""

    def test_simulation_config_has_default_adapters(self) -> None:
        """Test that SimulationConfig includes default AdapterSelectionConfig."""
        config = SimulationConfig(scenario_name="test")
        assert isinstance(config.adapters, AdapterSelectionConfig)
        assert config.adapters.board == "mock"
        assert config.adapters.llm == "mock"
        assert config.adapters.container == "fake"

    def test_simulation_config_accepts_custom_adapters(self) -> None:
        """Test that SimulationConfig can accept custom AdapterSelectionConfig."""
        adapters = AdapterSelectionConfig(board="github", llm="claude_code")
        config = SimulationConfig(scenario_name="test", adapters=adapters)
        assert config.adapters.board == "github"
        assert config.adapters.llm == "claude_code"
        assert config.adapters.ticket == "in_memory"  # default

    def test_to_dict_includes_adapters(self) -> None:
        """Test that to_dict includes adapters configuration."""
        adapters = AdapterSelectionConfig(board="github", llm="claude_code")
        config = SimulationConfig(scenario_name="test", adapters=adapters)
        data = config.to_dict()

        assert "adapters" in data
        assert data["adapters"]["board"] == "github"
        assert data["adapters"]["llm"] == "claude_code"
        assert data["adapters"]["ticket"] == "in_memory"

    def test_from_dict_parses_adapters(self) -> None:
        """Test that from_dict correctly parses adapter configuration."""
        data = {
            "scenario_name": "test",
            "adapters": {
                "board": "github",
                "llm": "claude_code",
                "container": "docker",
            },
        }
        config = SimulationConfig.from_dict(data)

        assert config.adapters.board == "github"
        assert config.adapters.llm == "claude_code"
        assert config.adapters.container == "docker"
        assert config.adapters.ticket == "in_memory"  # default

    def test_from_dict_uses_adapter_defaults_when_missing(self) -> None:
        """Test that from_dict uses adapter defaults when adapters key is absent."""
        data = {"scenario_name": "test"}
        config = SimulationConfig.from_dict(data)

        assert config.adapters.board == "mock"
        assert config.adapters.llm == "mock"
        assert config.adapters.container == "fake"

    def test_from_dict_merges_partial_adapter_config(self) -> None:
        """Test that from_dict merges partial adapter config with defaults."""
        data = {
            "scenario_name": "test",
            "adapters": {
                "board": "github",
                "llm": "claude_code",
            },
        }
        config = SimulationConfig.from_dict(data)

        # Overridden values
        assert config.adapters.board == "github"
        assert config.adapters.llm == "claude_code"
        # Default values
        assert config.adapters.ticket == "in_memory"
        assert config.adapters.container == "fake"

    def test_roundtrip_adapters_through_dict(self) -> None:
        """Test that adapter config survives roundtrip through dict."""
        adapters = AdapterSelectionConfig(
            board="github",
            llm="claude_code",
            container="docker",
            event_store="elasticsearch",
            metrics="prometheus",
        )
        original = SimulationConfig(scenario_name="test", adapters=adapters)

        data = original.to_dict()
        restored = SimulationConfig.from_dict(data)

        assert restored.adapters.board == "github"
        assert restored.adapters.llm == "claude_code"
        assert restored.adapters.container == "docker"
        assert restored.adapters.event_store == "elasticsearch"
        assert restored.adapters.metrics == "prometheus"
        # Verify unmodified defaults are preserved
        assert restored.adapters.ticket == "in_memory"

    def test_from_yaml_parses_adapters_section(self) -> None:
        """Test that from_yaml parses adapters YAML key."""
        yaml_content = """name: AdapterTest
adapters:
  board: github
  llm: claude_code
  container: docker
  event_store: elasticsearch
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            assert config.adapters.board == "github"
            assert config.adapters.llm == "claude_code"
            assert config.adapters.container == "docker"
            assert config.adapters.event_store == "elasticsearch"
            # Verify defaults are preserved for non-specified adapters
            assert config.adapters.ticket == "in_memory"
            assert config.adapters.metrics == "in_memory"
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_falls_back_to_defaults_when_adapters_absent(self) -> None:
        """Test that from_yaml falls back to adapter defaults when adapters key is missing."""
        yaml_content = """name: NoAdaptersTest
description: Scenario without adapters section
speed_multiplier: 15.0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            # All adapters should use defaults
            assert config.adapters.board == "mock"
            assert config.adapters.llm == "mock"
            assert config.adapters.container == "fake"
            assert config.adapters.ticket == "in_memory"
            # Other config should still be parsed
            assert config.scenario_name == "NoAdaptersTest"
            assert config.time.speed_multiplier == 15.0
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_rejects_unknown_adapter_keys(self) -> None:
        """Test that from_yaml rejects unknown adapter keys with helpful error message."""
        yaml_content = """name: UnknownAdaptersTest
adapters:
  board: github
  unknown_adapter: some_value
  llm: claude_code
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Unknown adapter keys in configuration"):
                SimulationConfig.from_yaml(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_from_dict_rejects_unknown_adapter_keys(self) -> None:
        """Test that from_dict rejects unknown adapter keys with helpful error message."""
        data = {
            "scenario_name": "test",
            "adapters": {
                "board": "github",
                "unknown_adapter": "some_value",
                "llm": "claude_code",
            },
        }
        with pytest.raises(ValueError, match="Unknown adapter keys in configuration: unknown_adapter"):
            SimulationConfig.from_dict(data)

    def test_from_dict_accepts_correct_field_name(self) -> None:
        """Test that from_dict accepts discussion_adapter (not discussion)."""
        data = {
            "scenario_name": "test",
            "adapters": {
                "discussion_adapter": "github",
                "board": "mock",
            },
        }
        config = SimulationConfig.from_dict(data)
        assert config.adapters.discussion_adapter == "github"
        assert config.adapters.board == "mock"

    def test_create_fast_config_has_default_adapters(self) -> None:
        """Test that create_fast_config factory method has default adapters."""
        config = SimulationConfig.create_fast_config("test_scenario")
        assert config.adapters.board == "mock"
        assert config.adapters.llm == "mock"
        assert config.adapters.container == "fake"

    def test_create_realistic_config_has_default_adapters(self) -> None:
        """Test that create_realistic_config factory method has default adapters."""
        config = SimulationConfig.create_realistic_config("test_scenario")
        assert config.adapters.board == "mock"
        assert config.adapters.llm == "mock"
        assert config.adapters.container == "fake"

    def test_create_high_fidelity_config_has_default_adapters(self) -> None:
        """Test that create_high_fidelity_config factory method has default adapters."""
        config = SimulationConfig.create_high_fidelity_config("test_scenario")
        assert config.adapters.board == "mock"
        assert config.adapters.llm == "mock"
        assert config.adapters.container == "fake"

    def test_from_yaml_with_nested_simulation_section(self) -> None:
        """Test that from_yaml handles speed_multiplier nested under 'simulation:' key."""
        yaml_content = """name: NestedSimulation
description: Test nested simulation section
simulation:
  speed_multiplier: 25.0
  auto_advance: true
  start_time: null
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            assert config.scenario_name == "NestedSimulation"
            assert config.time.speed_multiplier == 25.0
            assert config.time.auto_advance is True
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_with_agents_as_list(self) -> None:
        """Test that from_yaml handles agents as list-of-objects format."""
        yaml_content = """name: AgentsListTest
agents:
  - agent_id: reviewer
    execution_delay: 0.2
    success_rate: 0.95
    response_patterns:
      code_review: "Code review completed"
  - agent_id: analyzer
    execution_delay: 0.15
    success_rate: 0.98
    response_patterns:
      analysis: "Analysis complete"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            assert "reviewer" in config.agents
            assert "analyzer" in config.agents
            assert config.agents["reviewer"].execution_delay == 0.2
            assert config.agents["reviewer"].success_rate == 0.95
            assert config.agents["analyzer"].execution_delay == 0.15
            assert config.agents["analyzer"].success_rate == 0.98
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_with_containers_plural_key(self) -> None:
        """Test that from_yaml handles 'containers:' (plural) as well as 'container:'."""
        yaml_content = """name: ContainersPluralTest
containers:
  default_exit_code: 1
  execution_delay: 0.5
  command_exit_codes:
    "pytest": 0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            assert config.container.default_exit_code == 1
            assert config.container.execution_delay == 0.5
            assert config.container.command_exit_codes["pytest"] == 0
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_with_fidelity_uppercase_normalized(self) -> None:
        """Test that from_yaml normalizes uppercase fidelity values to lowercase."""
        yaml_content = """name: FidelityUppercaseTest
fidelity: MEDIUM
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            assert config.fidelity_level == FidelityLevel.MEDIUM
        finally:
            Path(temp_path).unlink()

    def test_from_yaml_with_fidelity_level_key(self) -> None:
        """Test that from_yaml accepts 'fidelity_level' key."""
        yaml_content = """name: FidelityLevelKeyTest
fidelity_level: high
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = f.name

        try:
            config = SimulationConfig.from_yaml(temp_path)
            assert config.fidelity_level == FidelityLevel.HIGH
        finally:
            Path(temp_path).unlink()

    def test_from_dict_with_agents_as_list(self) -> None:
        """Test that from_dict handles agents as list-of-objects format."""
        data = {
            "scenario_name": "AgentsListDictTest",
            "agents": [
                {
                    "agent_id": "reviewer",
                    "execution_delay": 0.2,
                    "success_rate": 0.95,
                },
                {
                    "agent_id": "analyzer",
                    "execution_delay": 0.15,
                    "success_rate": 0.98,
                },
            ],
        }
        config = SimulationConfig.from_dict(data)
        assert "reviewer" in config.agents
        assert "analyzer" in config.agents
        assert config.agents["reviewer"].execution_delay == 0.2
        assert config.agents["analyzer"].execution_delay == 0.15
