"""Integration tests for PR review cycle seeding.

Verifies that:
- Seeding properly maps pr_review_cycle_config from ScenarioColumnConfig to ColumnTemplate
- The resulting ColumnTemplate has the correct pr_review_cycle_config instance
- The domain conversion works correctly during seeding
"""

import pytest

from codetoreum.domain.board_workflow_template import ColumnTemplate
from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
from codetoreum.infrastructure.simulation.scenario_models import (
    PRReviewCycleConfigModel,
    ScenarioColumnConfig,
)
from codetoreum.infrastructure.simulation.seeding import SimulationDataSeeder


@pytest.mark.asyncio
class TestSeedingPRReviewCycle:
    """Test PR review cycle seeding integration."""

    async def test_register_workflow_template_with_pr_review_cycle_config(self, simulation_bootstrap) -> None:
        """Seeding maps pr_review_cycle_config to ColumnTemplate correctly."""
        seeder = SimulationDataSeeder(simulation_bootstrap)

        # Create a project context
        await seeder.create_project("test-project")
        project_id = seeder._current_project_id

        # Create a board
        await seeder.create_board(
            board_id="board-1",
            board_name="Test Board",
            column_names=["Backlog", "Review", "Done"],
            project_id=project_id,
        )

        # Create column configs with PR review cycle
        column_configs = [
            ScenarioColumnConfig(
                name="Backlog",
                type="manual",
            ),
            ScenarioColumnConfig(
                name="Review",
                type="manual",
                pr_review_cycle_config=PRReviewCycleConfigModel(
                    max_outer_cycles=2,
                    verifier_context_sources=["parent_issue", "ba_output"],
                ),
            ),
            ScenarioColumnConfig(
                name="Done",
                type="manual",
            ),
        ]

        # Register the workflow template from column configs
        await seeder.register_workflow_template_from_column_configs(
            board_id="board-1",
            column_configs=column_configs,
            project_id=project_id,
        )

        # Verify the template was created
        templates = await seeder.adapters.workflow_config.list_board_workflow_templates(project_id)
        assert len(templates) > 0

        # Find the template for board-1
        template = next((t for t in templates if t.board_id == "board-1"), None)
        assert template is not None

        # Verify the Review column has pr_review_cycle_config
        review_col = next((c for c in template.columns if c.name == "Review"), None)
        assert review_col is not None
        assert review_col.pr_review_cycle_config is not None
        assert isinstance(review_col.pr_review_cycle_config, PRReviewCycleConfig)
        assert review_col.pr_review_cycle_config.max_outer_cycles == 2
        assert review_col.pr_review_cycle_config.verifier_context_sources == ("parent_issue", "ba_output")

        # Verify other columns don't have pr_review_cycle_config
        backlog_col = next((c for c in template.columns if c.name == "Backlog"), None)
        assert backlog_col is not None
        assert backlog_col.pr_review_cycle_config is None

        done_col = next((c for c in template.columns if c.name == "Done"), None)
        assert done_col is not None
        assert done_col.pr_review_cycle_config is None

    async def test_seeding_without_pr_review_cycle_config_no_regression(self, simulation_bootstrap) -> None:
        """Seeding columns without pr_review_cycle_config works as before (no regression)."""
        seeder = SimulationDataSeeder(simulation_bootstrap)

        # Create a project context
        await seeder.create_project("test-project")
        project_id = seeder._current_project_id

        # Create a board
        await seeder.create_board(
            board_id="board-2",
            board_name="Test Board 2",
            column_names=["Backlog", "In Progress", "Done"],
            project_id=project_id,
        )

        # Create column configs WITHOUT PR review cycle
        column_configs = [
            ScenarioColumnConfig(
                name="Backlog",
                type="manual",
            ),
            ScenarioColumnConfig(
                name="In Progress",
                type="automated",
                agent_id="coder",
                is_pipeline_trigger=True,
            ),
            ScenarioColumnConfig(
                name="Done",
                type="manual",
                is_exit_column=True,
            ),
        ]

        # Register the workflow template
        await seeder.register_workflow_template_from_column_configs(
            board_id="board-2",
            column_configs=column_configs,
            project_id=project_id,
        )

        # Verify the template was created
        templates = await seeder.adapters.workflow_config.list_board_workflow_templates(project_id)
        template = next((t for t in templates if t.board_id == "board-2"), None)
        assert template is not None

        # Verify all columns have no pr_review_cycle_config
        for col in template.columns:
            assert col.pr_review_cycle_config is None

        # Verify other attributes are intact
        in_progress_col = next((c for c in template.columns if c.name == "In Progress"), None)
        assert in_progress_col is not None
        assert in_progress_col.agent_id == "coder"
        assert in_progress_col.is_pipeline_trigger is True

    async def test_seeding_with_complex_pr_review_config(self, simulation_bootstrap) -> None:
        """Seeding with all PR review cycle configuration fields works correctly."""
        seeder = SimulationDataSeeder(simulation_bootstrap)

        # Create a project context
        await seeder.create_project("test-project")
        project_id = seeder._current_project_id

        # Create a board
        await seeder.create_board(
            board_id="board-3",
            board_name="Complex Board",
            column_names=["Backlog", "PR Review", "Done"],
            project_id=project_id,
        )

        # Create column configs with complex PR review cycle config
        column_configs = [
            ScenarioColumnConfig(
                name="Backlog",
                type="manual",
            ),
            ScenarioColumnConfig(
                name="PR Review",
                type="manual",
                pr_review_cycle_config=PRReviewCycleConfigModel(
                    max_outer_cycles=3,
                    verifier_context_sources=["parent_issue", "ba_output", "arch_spec"],
                    code_review_timeout_seconds=1200,
                    verification_timeout_seconds=900,
                    ci_check_enabled=True,
                    ci_check_timeout_seconds=600,
                    consolidation_timeout_seconds=1500,
                ),
            ),
            ScenarioColumnConfig(
                name="Done",
                type="manual",
            ),
        ]

        # Register the workflow template
        await seeder.register_workflow_template_from_column_configs(
            board_id="board-3",
            column_configs=column_configs,
            project_id=project_id,
        )

        # Verify the template was created
        templates = await seeder.adapters.workflow_config.list_board_workflow_templates(project_id)
        template = next((t for t in templates if t.board_id == "board-3"), None)
        assert template is not None

        # Verify the Review column has all pr_review_cycle_config fields set correctly
        review_col = next((c for c in template.columns if c.name == "PR Review"), None)
        assert review_col is not None
        assert review_col.pr_review_cycle_config is not None

        config = review_col.pr_review_cycle_config
        assert config.max_outer_cycles == 3
        assert config.verifier_context_sources == ("parent_issue", "ba_output", "arch_spec")
        assert config.code_review_timeout_seconds == 1200
        assert config.verification_timeout_seconds == 900
        assert config.ci_check_enabled is True
        assert config.ci_check_timeout_seconds == 600
        assert config.consolidation_timeout_seconds == 1500
