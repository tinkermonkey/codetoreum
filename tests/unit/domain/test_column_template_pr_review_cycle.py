"""Unit tests for ColumnTemplate PR Review Cycle configuration.

Tests cover:
- Adding pr_review_cycle_config field to ColumnTemplate
- Mutual exclusivity between repair_cycle_agents and pr_review_cycle_config
- Default values
- Field access without errors
"""

import pytest
from codetoreum.domain.board_workflow_template import ColumnTemplate, ColumnType
from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig, RepairTestType


class TestColumnTemplatePRReviewCycleConfig:
    """Tests for PR Review Cycle configuration on ColumnTemplate."""

    def test_create_without_pr_review_config(self):
        """Test creating column without PR review config."""
        col = ColumnTemplate(
            name="In Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
        )
        assert col.pr_review_cycle_config is None

    def test_create_with_pr_review_config(self):
        """Test creating column with PR review config."""
        config = PRReviewCycleConfig(
            max_outer_cycles=2,
            verifier_context_sources=("parent_issue",),
        )
        col = ColumnTemplate(
            name="In Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
            pr_review_cycle_config=config,
        )
        assert col.pr_review_cycle_config == config
        assert col.pr_review_cycle_config.max_outer_cycles == 2

    def test_pr_review_config_default_none(self):
        """Test PR review config defaults to None."""
        col = ColumnTemplate(
            name="In Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
        )
        assert col.pr_review_cycle_config is None

    def test_mutual_exclusivity_with_repair_cycle_agents(self):
        """Test mutual exclusivity: cannot have both repair_cycle_agents and pr_review_cycle_config."""
        config = PRReviewCycleConfig()
        agents = RepairCycleAgentConfig()

        with pytest.raises(ValueError, match="cannot have both repair_cycle_agents and pr_review_cycle_config"):
            ColumnTemplate(
                name="In Review",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
                repair_cycle_agents=agents,
                pr_review_cycle_config=config,
            )

    def test_repair_cycle_agents_alone_valid(self):
        """Test repair_cycle_agents alone is valid."""
        agents = RepairCycleAgentConfig()
        col = ColumnTemplate(
            name="In Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
            repair_cycle_agents=agents,
            pr_review_cycle_config=None,
        )
        assert col.repair_cycle_agents == agents
        assert col.pr_review_cycle_config is None

    def test_pr_review_config_alone_valid(self):
        """Test pr_review_cycle_config alone is valid."""
        config = PRReviewCycleConfig()
        col = ColumnTemplate(
            name="In Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
            repair_cycle_agents=None,
            pr_review_cycle_config=config,
        )
        assert col.repair_cycle_agents is None
        assert col.pr_review_cycle_config == config

    def test_both_none_valid(self):
        """Test both None is valid."""
        col = ColumnTemplate(
            name="In Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
            repair_cycle_agents=None,
            pr_review_cycle_config=None,
        )
        assert col.repair_cycle_agents is None
        assert col.pr_review_cycle_config is None

    def test_mutual_exclusivity_error_message_includes_column_name(self):
        """Test mutual exclusivity error includes column name."""
        config = PRReviewCycleConfig()
        agents = RepairCycleAgentConfig()

        with pytest.raises(ValueError, match="Column 'In Review'"):
            ColumnTemplate(
                name="In Review",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
                repair_cycle_agents=agents,
                pr_review_cycle_config=config,
            )

    def test_pr_review_config_with_multiple_context_sources(self):
        """Test PR review config with multiple context sources."""
        config = PRReviewCycleConfig(
            max_outer_cycles=3,
            verifier_context_sources=("parent_issue", "ba_output", "arch_spec"),
        )
        col = ColumnTemplate(
            name="In Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
            pr_review_cycle_config=config,
        )
        assert len(col.pr_review_cycle_config.verifier_context_sources) == 3

    def test_pr_review_config_immutable(self):
        """Test that pr_review_cycle_config is part of immutable template."""
        config = PRReviewCycleConfig()
        col = ColumnTemplate(
            name="In Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
            pr_review_cycle_config=config,
        )
        # Column template is frozen, so attempting to modify should raise
        with pytest.raises(Exception):  # FrozenInstanceError
            col.pr_review_cycle_config = PRReviewCycleConfig(max_outer_cycles=2)

    def test_manual_column_with_pr_review_config(self):
        """Test manual column can have PR review config."""
        config = PRReviewCycleConfig()
        col = ColumnTemplate(
            name="In Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
            pr_review_cycle_config=config,
        )
        assert col.type == ColumnType.MANUAL
        assert col.pr_review_cycle_config == config

    def test_automated_column_with_pr_review_config(self):
        """Test automated column can have PR review config."""
        config = PRReviewCycleConfig()
        col = ColumnTemplate(
            name="In Review",
            type=ColumnType.AUTOMATED,
            agent_id="reviewer_agent",
            is_pipeline_trigger=True,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
            pr_review_cycle_config=config,
        )
        assert col.type == ColumnType.AUTOMATED
        assert col.pr_review_cycle_config == config
