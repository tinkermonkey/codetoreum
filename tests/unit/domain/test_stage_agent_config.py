"""Unit tests for StageAgentConfig and stage-specific agent configuration.

Tests cover:
- Creating StageAgentConfig with various Claude Code CLI parameters
- Integrating StageAgentConfig into ColumnTemplate
- Validation of stage agent configuration values
- Immutability of stage agent configuration
"""

import pytest

from codetoreum.domain.board_workflow_template import ColumnTemplate, ColumnType, StageAgentConfig


class TestStageAgentConfig:
    """Tests for StageAgentConfig domain entity."""

    def test_create_with_all_parameters(self):
        """Test creating StageAgentConfig with all parameters."""
        config = StageAgentConfig(
            model="claude-opus-4-6",
            timeout_seconds=600,
            permission_mode="bypassPermissions",
            output_format="stream-json",
            enable_mcp=True,
            enable_tools=True,
            max_context_tokens=180000,
            verbose=False,
            prompt_template="Analyze this issue",
            tool_permissions={"git": {"allow": ["clone", "push"]}},
            metadata={"stage": "analysis", "version": "1"},
        )
        assert config.model == "claude-opus-4-6"
        assert config.timeout_seconds == 600
        assert config.permission_mode == "bypassPermissions"
        assert config.output_format == "stream-json"
        assert config.enable_mcp is True
        assert config.enable_tools is True
        assert config.max_context_tokens == 180000
        assert config.verbose is False
        assert config.prompt_template == "Analyze this issue"
        assert "git" in dict(config.tool_permissions)

    def test_create_with_minimal_parameters(self):
        """Test creating StageAgentConfig with minimal parameters (all defaults)."""
        config = StageAgentConfig()
        assert config.model is None
        assert config.timeout_seconds is None
        assert config.permission_mode is None
        assert config.enable_mcp is None
        assert config.enable_tools is None
        assert config.max_context_tokens is None
        assert config.verbose is None
        assert config.prompt_template is None

    def test_model_validation(self):
        """Test model parameter validation."""
        # Valid model names
        config1 = StageAgentConfig(model="claude-opus-4-6")
        assert config1.model == "claude-opus-4-6"

        config2 = StageAgentConfig(model="claude-sonnet-4-5")
        assert config2.model == "claude-sonnet-4-5"

        # Invalid empty string
        with pytest.raises(ValueError, match="model must be a non-empty string"):
            StageAgentConfig(model="")

    def test_timeout_validation(self):
        """Test timeout_seconds parameter validation."""
        # Valid positive timeout
        config = StageAgentConfig(timeout_seconds=300)
        assert config.timeout_seconds == 300

        # None is valid (use default)
        config = StageAgentConfig(timeout_seconds=None)
        assert config.timeout_seconds is None

        # Invalid negative timeout
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            StageAgentConfig(timeout_seconds=-1)

        # Invalid zero timeout
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            StageAgentConfig(timeout_seconds=0)

        # Invalid non-integer
        with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
            StageAgentConfig(timeout_seconds="300")  # type: ignore

    def test_permission_mode_validation(self):
        """Test permission_mode parameter validation."""
        # Valid modes
        config1 = StageAgentConfig(permission_mode="bypassPermissions")
        assert config1.permission_mode == "bypassPermissions"

        config2 = StageAgentConfig(permission_mode="askForPermissions")
        assert config2.permission_mode == "askForPermissions"

        # None is valid
        config3 = StageAgentConfig(permission_mode=None)
        assert config3.permission_mode is None

        # Invalid mode
        with pytest.raises(ValueError, match="permission_mode must be one of"):
            StageAgentConfig(permission_mode="invalidMode")

    def test_output_format_validation(self):
        """Test output_format parameter validation."""
        # Valid formats
        config1 = StageAgentConfig(output_format="stream-json")
        assert config1.output_format == "stream-json"

        config2 = StageAgentConfig(output_format="text")
        assert config2.output_format == "text"

        # None is valid
        config3 = StageAgentConfig(output_format=None)
        assert config3.output_format is None

        # Invalid format
        with pytest.raises(ValueError, match="output_format must be one of"):
            StageAgentConfig(output_format="invalid-format")

    def test_max_context_tokens_validation(self):
        """Test max_context_tokens parameter validation."""
        # Valid positive value
        config = StageAgentConfig(max_context_tokens=200000)
        assert config.max_context_tokens == 200000

        # None is valid
        config = StageAgentConfig(max_context_tokens=None)
        assert config.max_context_tokens is None

        # Invalid negative
        with pytest.raises(ValueError, match="max_context_tokens must be positive"):
            StageAgentConfig(max_context_tokens=-1)

        # Invalid zero
        with pytest.raises(ValueError, match="max_context_tokens must be positive"):
            StageAgentConfig(max_context_tokens=0)

    def test_boolean_fields_validation(self):
        """Test boolean field validation."""
        config = StageAgentConfig(enable_mcp=True, enable_tools=False, verbose=True)
        assert config.enable_mcp is True
        assert config.enable_tools is False
        assert config.verbose is True

        # None values are valid
        config2 = StageAgentConfig(enable_mcp=None, enable_tools=None, verbose=None)
        assert config2.enable_mcp is None
        assert config2.enable_tools is None
        assert config2.verbose is None

        # Invalid non-boolean
        with pytest.raises(ValueError, match="enable_mcp must be a boolean"):
            StageAgentConfig(enable_mcp="true")  # type: ignore

    def test_immutability(self):
        """Test that StageAgentConfig is frozen (immutable)."""
        config = StageAgentConfig(model="claude-opus-4-6")
        with pytest.raises(Exception):  # FrozenInstanceError
            config.model = "claude-sonnet-4-5"  # type: ignore

    def test_dict_to_mapping_proxy_coercion(self):
        """Test that dict parameters are coerced to MappingProxyType."""
        config = StageAgentConfig(
            tool_permissions={"git": {"allow": ["clone"]}},
            metadata={"version": "1"},
        )
        # MappingProxyType should be immutable
        assert isinstance(dict(config.tool_permissions), dict)
        assert config.tool_permissions["git"]["allow"] == ["clone"]


class TestColumnTemplateWithStageAgentConfig:
    """Tests for ColumnTemplate integration with StageAgentConfig."""

    def test_column_with_stage_agent_config(self):
        """Test creating column with stage agent configuration."""
        stage_config = StageAgentConfig(
            model="claude-opus-4-6",
            timeout_seconds=600,
            permission_mode="bypassPermissions",
        )
        col = ColumnTemplate(
            name="Analysis",
            type=ColumnType.AUTOMATED,
            agent_id="analyzer",
            is_pipeline_trigger=True,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=True,
            stage_agent_config=stage_config,
        )
        assert col.stage_agent_config == stage_config
        assert col.stage_agent_config.model == "claude-opus-4-6"
        assert col.stage_agent_config.timeout_seconds == 600

    def test_column_without_stage_agent_config(self):
        """Test creating column without stage agent configuration (default)."""
        col = ColumnTemplate(
            name="Backlog",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
        )
        assert col.stage_agent_config is None

    def test_stage_config_with_tool_permissions(self):
        """Test stage configuration with tool-specific permissions."""
        stage_config = StageAgentConfig(
            model="claude-opus-4-6",
            tool_permissions={
                "git": {"allow": ["clone", "commit", "push"]},
                "files": {"allow": ["read", "write"]},
            },
        )
        col = ColumnTemplate(
            name="Implementation",
            type=ColumnType.AUTOMATED,
            agent_id="maker",
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=2,
            auto_progress_on_completion=True,
            stage_agent_config=stage_config,
        )
        assert col.stage_agent_config.tool_permissions["git"]["allow"] == ["clone", "commit", "push"]
        assert col.stage_agent_config.tool_permissions["files"]["allow"] == ["read", "write"]

    def test_column_template_immutability_with_stage_config(self):
        """Test that column template is immutable even with stage config."""
        stage_config = StageAgentConfig(model="claude-opus-4-6")
        col = ColumnTemplate(
            name="Analysis",
            type=ColumnType.AUTOMATED,
            agent_id="analyzer",
            is_pipeline_trigger=True,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=True,
            stage_agent_config=stage_config,
        )
        # Attempting to modify should raise
        with pytest.raises(Exception):  # FrozenInstanceError
            col.stage_agent_config = StageAgentConfig(model="claude-sonnet-4-5")  # type: ignore

    def test_multiple_columns_with_different_stage_configs(self):
        """Test multiple columns with different stage-specific configurations."""
        analysis_config = StageAgentConfig(
            model="claude-opus-4-6",
            timeout_seconds=600,
            prompt_template="Analyze this issue",
        )
        implementation_config = StageAgentConfig(
            model="claude-opus-4-6",
            timeout_seconds=900,
            prompt_template="Implement the feature",
            tool_permissions={"git": {"allow": ["clone", "push"]}},
        )
        testing_config = StageAgentConfig(
            model="claude-sonnet-4-5",
            timeout_seconds=600,
            prompt_template="Write tests",
        )

        analysis_col = ColumnTemplate(
            name="Analysis",
            type=ColumnType.AUTOMATED,
            agent_id="analyzer",
            is_pipeline_trigger=True,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=True,
            stage_agent_config=analysis_config,
        )

        impl_col = ColumnTemplate(
            name="Implementation",
            type=ColumnType.AUTOMATED,
            agent_id="maker",
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=1,
            auto_progress_on_completion=True,
            stage_agent_config=implementation_config,
        )

        test_col = ColumnTemplate(
            name="Testing",
            type=ColumnType.AUTOMATED,
            agent_id="tester",
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=2,
            auto_progress_on_completion=True,
            stage_agent_config=testing_config,
        )

        # Verify each column has the correct configuration
        assert analysis_col.stage_agent_config.model == "claude-opus-4-6"
        assert analysis_col.stage_agent_config.timeout_seconds == 600

        assert impl_col.stage_agent_config.model == "claude-opus-4-6"
        assert impl_col.stage_agent_config.timeout_seconds == 900
        assert "git" in dict(impl_col.stage_agent_config.tool_permissions)

        assert test_col.stage_agent_config.model == "claude-sonnet-4-5"
        assert test_col.stage_agent_config.timeout_seconds == 600
