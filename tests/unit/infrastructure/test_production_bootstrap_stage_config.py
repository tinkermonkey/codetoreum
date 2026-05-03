"""Unit tests for Production Bootstrap with stage-specific agent configuration.

Tests cover:
- ProductionProjectConfigurationWrapper querying configuration service
- Stage-specific Claude Code CLI parameters in pipeline configuration
- Integration of stage_agent_config with ColumnTemplate
"""

import pytest

from codetoreum.config.codetoreum_pipeline import create_codetoreum_pipeline_template
from codetoreum.infrastructure.bootstrap.production_bootstrap import (
    ProductionProjectConfigurationWrapper,
)
from codetoreum.ports.output.config_store import AgentConfig


class MockConfigStore:
    """Mock configuration store for testing."""

    async def get_agent_config(self, project_id: str, agent_name: str) -> AgentConfig:
        """Return agent config based on agent name."""
        configs = {
            "analyzer": AgentConfig(
                project_id=project_id,
                agent_name="analyzer",
                model="claude-opus-4-6",
                timeout=600,
                requires_docker=True,
                makes_code_changes=False,
                mcp_servers=("artifact", "file"),
                capabilities=("analysis", "planning"),
            ),
            "maker": AgentConfig(
                project_id=project_id,
                agent_name="maker",
                model="claude-opus-4-6",
                timeout=900,
                requires_docker=True,
                makes_code_changes=True,
                mcp_servers=("artifact", "file", "git"),
                capabilities=("implementation", "refactoring"),
            ),
            "tester": AgentConfig(
                project_id=project_id,
                agent_name="tester",
                model="claude-sonnet-4-5",
                timeout=600,
                requires_docker=True,
                makes_code_changes=False,
                mcp_servers=("artifact", "file"),
                capabilities=("testing", "validation"),
            ),
        }
        if agent_name in configs:
            return configs[agent_name]
        raise ValueError(f"Agent not found: {agent_name}")


class MockConfigurationService:
    """Mock configuration service for testing."""

    def __init__(self):
        self.config_store = MockConfigStore()


class TestProductionBootstrapStageConfig:
    """Tests for production bootstrap with stage-specific agent configuration."""

    @pytest.mark.asyncio
    async def test_wrapper_retrieves_agent_config(self):
        """Test that wrapper retrieves agent configuration from store."""
        service = MockConfigurationService()
        wrapper = ProductionProjectConfigurationWrapper(service, project_id="test-project")

        # Test getting analyzer config
        analyzer_config = await wrapper.get_agent_config("analyzer")
        assert analyzer_config.agent_name == "analyzer"
        assert analyzer_config.model == "claude-opus-4-6"
        assert analyzer_config.timeout == 600
        assert "artifact" in analyzer_config.mcp_servers

        # Test getting maker config
        maker_config = await wrapper.get_agent_config("maker")
        assert maker_config.agent_name == "maker"
        assert maker_config.model == "claude-opus-4-6"
        assert maker_config.timeout == 900
        assert maker_config.makes_code_changes is True

        # Test getting tester config
        tester_config = await wrapper.get_agent_config("tester")
        assert tester_config.agent_name == "tester"
        assert tester_config.model == "claude-sonnet-4-5"
        assert tester_config.timeout == 600
        assert tester_config.makes_code_changes is False

    @pytest.mark.asyncio
    async def test_wrapper_fallback_for_missing_config(self):
        """Test that wrapper returns sensible default when config not found."""
        service = MockConfigurationService()
        wrapper = ProductionProjectConfigurationWrapper(service, project_id="test-project")

        # Get config for non-existent agent
        config = await wrapper.get_agent_config("unknown-agent")
        assert config.agent_name == "unknown-agent"
        assert config.model == "claude-opus-4-6"  # Production default
        assert config.timeout == 300  # Production default
        assert config.requires_docker is True

    def test_pipeline_template_has_stage_configs(self):
        """Test that pipeline template includes stage-specific configurations."""
        template = create_codetoreum_pipeline_template()

        # Analysis column should have stage config
        analysis_col = template.get_column_config("Analysis")
        assert analysis_col is not None
        assert analysis_col.stage_agent_config is not None
        assert analysis_col.stage_agent_config.model == "claude-opus-4-6"
        assert analysis_col.stage_agent_config.timeout_seconds == 600
        assert analysis_col.stage_agent_config.permission_mode == "bypassPermissions"
        assert analysis_col.stage_agent_config.enable_mcp is True
        assert analysis_col.stage_agent_config.enable_tools is True

        # Implementation column should have stage config with tool permissions
        impl_col = template.get_column_config("Implementation")
        assert impl_col is not None
        assert impl_col.stage_agent_config is not None
        assert impl_col.stage_agent_config.model == "claude-opus-4-6"
        assert impl_col.stage_agent_config.timeout_seconds == 900
        assert "git" in dict(impl_col.stage_agent_config.tool_permissions)
        assert "files" in dict(impl_col.stage_agent_config.tool_permissions)

        # Testing column should have stage config with different model
        test_col = template.get_column_config("Testing")
        assert test_col is not None
        assert test_col.stage_agent_config is not None
        assert test_col.stage_agent_config.model == "claude-sonnet-4-5"
        assert test_col.stage_agent_config.timeout_seconds == 600
        assert "test_runners" in dict(test_col.stage_agent_config.tool_permissions)

        # Manual columns should not have stage config
        review_col = template.get_column_config("Review")
        assert review_col is not None
        assert review_col.stage_agent_config is None

        blocked_col = template.get_column_config("Blocked")
        assert blocked_col is not None
        assert blocked_col.stage_agent_config is None

        done_col = template.get_column_config("Done")
        assert done_col is not None
        assert done_col.stage_agent_config is None

    def test_stage_agent_config_immutability(self):
        """Test that stage agent configurations are immutable."""
        template = create_codetoreum_pipeline_template()
        analysis_col = template.get_column_config("Analysis")

        assert analysis_col is not None
        assert analysis_col.stage_agent_config is not None

        # Attempting to modify frozen dataclass should raise
        with pytest.raises(Exception):  # FrozenInstanceError
            analysis_col.stage_agent_config.model = "claude-sonnet-4-5"  # type: ignore

    def test_stage_config_per_stage_differences(self):
        """Test that different stages have appropriate CLI parameter differences."""
        template = create_codetoreum_pipeline_template()

        analysis_col = template.get_column_config("Analysis")
        impl_col = template.get_column_config("Implementation")
        test_col = template.get_column_config("Testing")

        assert analysis_col is not None
        assert impl_col is not None
        assert test_col is not None

        analysis_cfg = analysis_col.stage_agent_config
        impl_cfg = impl_col.stage_agent_config
        test_cfg = test_col.stage_agent_config

        assert analysis_cfg is not None
        assert impl_cfg is not None
        assert test_cfg is not None

        # Analysis: Opus, 600s timeout, no special tool permissions
        assert analysis_cfg.model == "claude-opus-4-6"
        assert analysis_cfg.timeout_seconds == 600
        assert analysis_cfg.tool_permissions == {}

        # Implementation: Opus, 900s timeout, git and file permissions
        assert impl_cfg.model == "claude-opus-4-6"
        assert impl_cfg.timeout_seconds == 900
        assert "git" in dict(impl_cfg.tool_permissions)
        assert "files" in dict(impl_cfg.tool_permissions)

        # Testing: Sonnet (faster), 600s timeout, test runner permissions
        assert test_cfg.model == "claude-sonnet-4-5"  # Different model
        assert test_cfg.timeout_seconds == 600
        assert "test_runners" in dict(test_cfg.tool_permissions)
        assert "files" in dict(test_cfg.tool_permissions)

        # Model differences are intentional
        assert analysis_cfg.model == impl_cfg.model  # Both use Opus
        assert test_cfg.model != impl_cfg.model  # Testing uses Sonnet
