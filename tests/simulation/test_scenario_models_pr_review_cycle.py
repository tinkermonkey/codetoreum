"""Tests for PRReviewCycleConfigModel and validation.

Verifies:
- PRReviewCycleConfigModel can be instantiated with all field combinations
- PRReviewCycleConfigModel.to_domain() produces valid domain objects
- ScenarioColumnConfig.pr_review_cycle_config field accepts PRReviewCycleConfigModel
- Mutual exclusivity validation in ColumnTemplate when both repair_cycle_agents and pr_review_cycle_config are set
- YAML with pr_review_cycle_config key is parsed without silently dropping it
- Backward compatibility: YAML without pr_review_cycle_config parses correctly
"""

import pytest
from pydantic import ValidationError

from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
from codetoreum.infrastructure.simulation.scenario_models import (
    PRReviewCycleConfigModel,
    ScenarioColumnConfig,
)


class TestPRReviewCycleConfigModel:
    """Test PRReviewCycleConfigModel instantiation and conversion."""

    def test_empty_pr_review_cycle_config(self) -> None:
        """All fields use defaults when not specified."""
        config = PRReviewCycleConfigModel()
        assert config.max_outer_cycles == 3
        assert config.verifier_context_sources == ["parent_issue"]
        assert config.code_review_timeout_seconds == 600
        assert config.verification_timeout_seconds == 300
        assert config.ci_check_enabled is True
        assert config.ci_check_timeout_seconds == 300
        assert config.consolidation_timeout_seconds == 600

    def test_partial_pr_review_cycle_config(self) -> None:
        """Some fields can be customized while others use defaults."""
        config = PRReviewCycleConfigModel(
            max_outer_cycles=3,
            code_review_timeout_seconds=1200,
        )
        assert config.max_outer_cycles == 3
        assert config.code_review_timeout_seconds == 1200
        # Defaults unchanged
        assert config.verifier_context_sources == ["parent_issue"]
        assert config.verification_timeout_seconds == 300
        assert config.ci_check_enabled is True
        assert config.ci_check_timeout_seconds == 300
        assert config.consolidation_timeout_seconds == 600

    def test_full_pr_review_cycle_config(self) -> None:
        """All fields can be set."""
        config = PRReviewCycleConfigModel(
            max_outer_cycles=5,
            verifier_context_sources=["parent_issue", "ba_output", "arch_spec"],
            code_review_timeout_seconds=900,
            verification_timeout_seconds=600,
            ci_check_enabled=False,
            ci_check_timeout_seconds=0,
            consolidation_timeout_seconds=1200,
        )
        assert config.max_outer_cycles == 5
        assert config.verifier_context_sources == ["parent_issue", "ba_output", "arch_spec"]
        assert config.code_review_timeout_seconds == 900
        assert config.verification_timeout_seconds == 600
        assert config.ci_check_enabled is False
        assert config.ci_check_timeout_seconds == 0
        assert config.consolidation_timeout_seconds == 1200

    def test_to_domain_empty(self) -> None:
        """to_domain() produces valid PRReviewCycleConfig with defaults."""
        config = PRReviewCycleConfigModel()
        domain = config.to_domain()

        assert isinstance(domain, PRReviewCycleConfig)
        assert domain.max_outer_cycles == 3
        assert domain.verifier_context_sources == ("parent_issue",)
        assert domain.code_review_timeout_seconds == 600
        assert domain.verification_timeout_seconds == 300
        assert domain.ci_check_enabled is True
        assert domain.ci_check_timeout_seconds == 300
        assert domain.consolidation_timeout_seconds == 600

    def test_to_domain_partial(self) -> None:
        """to_domain() preserves partial field values."""
        config = PRReviewCycleConfigModel(
            max_outer_cycles=2,
            code_review_timeout_seconds=1000,
        )
        domain = config.to_domain()

        assert isinstance(domain, PRReviewCycleConfig)
        assert domain.max_outer_cycles == 2
        assert domain.code_review_timeout_seconds == 1000
        # Verify tuple conversion for verifier_context_sources
        assert domain.verifier_context_sources == ("parent_issue",)
        assert isinstance(domain.verifier_context_sources, tuple)

    def test_to_domain_full(self) -> None:
        """to_domain() converts all fields correctly, including list-to-tuple conversion."""
        config = PRReviewCycleConfigModel(
            max_outer_cycles=5,
            verifier_context_sources=["parent_issue", "ba_output", "arch_spec"],
            code_review_timeout_seconds=900,
            verification_timeout_seconds=600,
            ci_check_enabled=False,
            ci_check_timeout_seconds=0,
            consolidation_timeout_seconds=1200,
        )
        domain = config.to_domain()

        assert isinstance(domain, PRReviewCycleConfig)
        assert domain.max_outer_cycles == 5
        # verifier_context_sources must be a tuple (immutable) in domain
        assert domain.verifier_context_sources == ("parent_issue", "ba_output", "arch_spec")
        assert isinstance(domain.verifier_context_sources, tuple)
        assert domain.code_review_timeout_seconds == 900
        assert domain.verification_timeout_seconds == 600
        assert domain.ci_check_enabled is False
        assert domain.ci_check_timeout_seconds == 0
        assert domain.consolidation_timeout_seconds == 1200

    def test_invalid_max_outer_cycles_zero(self) -> None:
        """ValidationError raised when max_outer_cycles < 1."""
        with pytest.raises(ValidationError) as exc_info:
            PRReviewCycleConfigModel(max_outer_cycles=0)

        error_str = str(exc_info.value)
        assert "max_outer_cycles" in error_str.lower() or "greater than or equal to 1" in error_str

    def test_invalid_max_outer_cycles_negative(self) -> None:
        """ValidationError raised when max_outer_cycles is negative."""
        with pytest.raises(ValidationError) as exc_info:
            PRReviewCycleConfigModel(max_outer_cycles=-1)

        error_str = str(exc_info.value)
        assert "max_outer_cycles" in error_str.lower() or "greater than or equal to 1" in error_str

    def test_invalid_empty_verifier_context_sources(self) -> None:
        """ValidationError raised when verifier_context_sources is empty."""
        with pytest.raises(ValidationError) as exc_info:
            PRReviewCycleConfigModel(verifier_context_sources=[])

        error_str = str(exc_info.value)
        assert "verifier_context_sources" in error_str.lower() or "min_length" in error_str

    def test_invalid_code_review_timeout_zero(self) -> None:
        """ValidationError raised when code_review_timeout_seconds <= 0."""
        with pytest.raises(ValidationError) as exc_info:
            PRReviewCycleConfigModel(code_review_timeout_seconds=0)

        error_str = str(exc_info.value)
        assert "code_review_timeout" in error_str.lower() or "greater than 0" in error_str

    def test_invalid_code_review_timeout_negative(self) -> None:
        """ValidationError raised when code_review_timeout_seconds is negative."""
        with pytest.raises(ValidationError) as exc_info:
            PRReviewCycleConfigModel(code_review_timeout_seconds=-100)

        error_str = str(exc_info.value)
        assert "code_review_timeout" in error_str.lower() or "greater than 0" in error_str

    def test_invalid_verification_timeout_zero(self) -> None:
        """ValidationError raised when verification_timeout_seconds <= 0."""
        with pytest.raises(ValidationError) as exc_info:
            PRReviewCycleConfigModel(verification_timeout_seconds=0)

        error_str = str(exc_info.value)
        assert "verification_timeout" in error_str.lower() or "greater than 0" in error_str

    def test_invalid_ci_check_timeout_positive_when_disabled(self) -> None:
        """ci_check_timeout_seconds can be any value (>= 0) when ci_check_enabled=False."""
        # When disabled, ci_check_timeout_seconds is not validated
        config = PRReviewCycleConfigModel(
            ci_check_enabled=False,
            ci_check_timeout_seconds=0,
        )
        assert config.ci_check_enabled is False
        assert config.ci_check_timeout_seconds == 0

    def test_invalid_ci_check_timeout_zero_when_enabled(self) -> None:
        """ValidationError raised when ci_check_timeout_seconds <= 0 and ci_check_enabled=True."""
        with pytest.raises(ValidationError) as exc_info:
            PRReviewCycleConfigModel(
                ci_check_enabled=True,
                ci_check_timeout_seconds=0,
            )

        error_str = str(exc_info.value)
        assert "ci_check_timeout" in error_str.lower() or "ci_check_enabled" in error_str.lower()

    def test_invalid_consolidation_timeout_zero(self) -> None:
        """ValidationError raised when consolidation_timeout_seconds <= 0."""
        with pytest.raises(ValidationError) as exc_info:
            PRReviewCycleConfigModel(consolidation_timeout_seconds=0)

        error_str = str(exc_info.value)
        assert "consolidation_timeout" in error_str.lower() or "greater than 0" in error_str


class TestScenarioColumnConfigPRReviewCycle:
    """Test ScenarioColumnConfig with pr_review_cycle_config field."""

    def test_column_config_without_pr_review_cycle_config(self) -> None:
        """pr_review_cycle_config defaults to None when not specified."""
        col = ScenarioColumnConfig(
            name="Review",
            type="manual",
        )
        assert col.pr_review_cycle_config is None

    def test_column_config_with_empty_pr_review_cycle_config(self) -> None:
        """pr_review_cycle_config can be explicitly set to empty config."""
        col = ScenarioColumnConfig(
            name="Review",
            type="manual",
            pr_review_cycle_config=PRReviewCycleConfigModel(),
        )
        assert col.pr_review_cycle_config is not None
        assert col.pr_review_cycle_config.max_outer_cycles == 3

    def test_column_config_with_pr_review_cycle_config(self) -> None:
        """pr_review_cycle_config can be set with specific values."""
        col = ScenarioColumnConfig(
            name="Review",
            type="manual",
            pr_review_cycle_config=PRReviewCycleConfigModel(
                max_outer_cycles=3,
                verifier_context_sources=["parent_issue", "ba_output"],
                code_review_timeout_seconds=900,
            ),
        )
        assert col.pr_review_cycle_config is not None
        assert col.pr_review_cycle_config.max_outer_cycles == 3
        assert col.pr_review_cycle_config.verifier_context_sources == ["parent_issue", "ba_output"]
        assert col.pr_review_cycle_config.code_review_timeout_seconds == 900

    def test_column_config_regression_no_pr_review_cycle_seeds_correctly(self) -> None:
        """Column with no pr_review_cycle_config key seeds as before (no regression)."""
        # This tests the backward compatibility — columns without pr_review_cycle_config
        # should work exactly as they did before this feature
        col = ScenarioColumnConfig(
            name="In Progress",
            type="automated",
            agent_id="coder",
            is_pipeline_trigger=True,
            is_exit_column=False,
            auto_progress_on_completion=True,
        )
        assert col.pr_review_cycle_config is None
        # All other fields should be intact
        assert col.name == "In Progress"
        assert col.type == "automated"
        assert col.agent_id == "coder"
        assert col.is_pipeline_trigger is True


class TestColumnTemplateMutualExclusivity:
    """Test mutual exclusivity validation in ColumnTemplate."""

    def test_column_template_with_pr_review_cycle_config_only(self) -> None:
        """ColumnTemplate accepts pr_review_cycle_config when repair_cycle_agents is None."""
        from codetoreum.domain.board_workflow_template import ColumnTemplate, ColumnType

        col = ColumnTemplate(
            name="Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=2,
            auto_progress_on_completion=False,
            pr_review_cycle_config=PRReviewCycleConfigModel().to_domain(),
        )
        assert col.pr_review_cycle_config is not None
        assert col.repair_cycle_agents is None

    def test_column_template_with_both_repair_and_pr_review_raises_error(self) -> None:
        """ColumnTemplate raises ValueError when both repair_cycle_agents and pr_review_cycle_config are set."""
        from codetoreum.domain.board_workflow_template import ColumnTemplate, ColumnType
        from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig

        with pytest.raises(ValueError) as exc_info:
            ColumnTemplate(
                name="Testing",
                type=ColumnType.AUTOMATED,
                agent_id="qa_engineer",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=True,
                repair_cycle_agents=RepairCycleAgentConfig(),
                pr_review_cycle_config=PRReviewCycleConfigModel().to_domain(),
            )

        error_str = str(exc_info.value)
        assert "mutually exclusive" in error_str.lower()
        assert "repair_cycle_agents" in error_str.lower() or "pr_review_cycle_config" in error_str.lower()


class TestYAMLParsingAndSeeding:
    """Test YAML parsing and seeding behavior."""

    def test_yaml_with_pr_review_cycle_config_is_recognized(self) -> None:
        """YAML with pr_review_cycle_config key is parsed without silently dropping it."""
        # Create a ScenarioColumnConfig from dict (simulating YAML parsing)
        col_dict = {
            "name": "Review",
            "type": "manual",
            "pr_review_cycle_config": {
                "max_outer_cycles": 2,
                "verifier_context_sources": ["parent_issue", "ba_output"],
            },
        }
        col = ScenarioColumnConfig(**col_dict)

        # Verify the field was not silently dropped
        assert col.pr_review_cycle_config is not None
        assert col.pr_review_cycle_config.max_outer_cycles == 2
        assert col.pr_review_cycle_config.verifier_context_sources == ["parent_issue", "ba_output"]

    def test_yaml_without_pr_review_cycle_config_parses_correctly(self) -> None:
        """YAML without pr_review_cycle_config key parses correctly (backward compatibility)."""
        col_dict = {
            "name": "In Progress",
            "type": "automated",
            "agent_id": "coder",
        }
        col = ScenarioColumnConfig(**col_dict)

        # Should parse without error and field should default to None
        assert col.pr_review_cycle_config is None
        assert col.name == "In Progress"
        assert col.agent_id == "coder"

    def test_to_domain_produces_valid_frozen_config(self) -> None:
        """PRReviewCycleConfigModel.to_domain() produces a valid frozen PRReviewCycleConfig."""
        config_model = PRReviewCycleConfigModel(
            max_outer_cycles=3,
            verifier_context_sources=["parent_issue", "ba_output", "arch_spec"],
        )
        domain_config = config_model.to_domain()

        # Verify it's a PRReviewCycleConfig instance
        assert isinstance(domain_config, PRReviewCycleConfig)

        # Verify all fields are populated correctly
        assert domain_config.max_outer_cycles == 3
        assert domain_config.verifier_context_sources == ("parent_issue", "ba_output", "arch_spec")
        assert isinstance(domain_config.verifier_context_sources, tuple)

        # Verify immutability (frozen dataclass) - attempting to modify should raise FrozenInstanceError
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            domain_config.max_outer_cycles = 5
