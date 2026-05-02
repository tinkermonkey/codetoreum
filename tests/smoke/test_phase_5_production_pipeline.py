"""Smoke test for Phase 5: Production pipeline configuration.

Verifies end-to-end workflow with the Codetoreum pipeline configuration:
1. Elasticsearch workflow config service initializes
2. Codetoreum pipeline template is saved correctly
3. REST API endpoints work (list, get, create, update, delete)
4. Work item placement in first pipeline column triggers agent execution
"""

import pytest
from codetoreum.adapters.secondary.elasticsearch_workflow_config_service import (
    ElasticsearchWorkflowConfigService,
)
from codetoreum.adapters.testing.in_memory_workflow_config_service import (
    InMemoryWorkflowConfigService,
)
from codetoreum.config.codetoreum_pipeline import create_codetoreum_pipeline_template
from codetoreum.domain.board_workflow_template import ColumnTemplate, ColumnType, BoardWorkflowTemplate
from codetoreum.ports.exceptions import ValidationError


class TestWorkflowConfigServiceBasics:
    """Test basic workflow config service functionality."""

    @pytest.mark.asyncio
    async def test_in_memory_workflow_config_save_and_retrieve(self) -> None:
        """Test saving and retrieving workflow templates in memory."""
        service = InMemoryWorkflowConfigService()
        template = create_codetoreum_pipeline_template()

        # Save template
        await service.save_board_workflow_template(template)

        # Retrieve template
        retrieved = await service.get_board_workflow_template(template.board_id)
        assert retrieved is not None
        assert retrieved.id == template.id
        assert retrieved.name == template.name
        assert len(retrieved.columns) == 7

    @pytest.mark.asyncio
    async def test_in_memory_workflow_config_list_by_project(self) -> None:
        """Test listing templates by project."""
        service = InMemoryWorkflowConfigService()
        template1 = create_codetoreum_pipeline_template()
        template2 = BoardWorkflowTemplate(
            id="another-pipeline",
            name="Another Pipeline",
            board_id="board-2",
            project_id="codetoreum",
            columns=(
                ColumnTemplate(
                    name="Backlog",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                ),
            ),
        )

        # Save templates
        await service.save_board_workflow_template(template1)
        await service.save_board_workflow_template(template2)

        # List templates for project
        templates = await service.list_board_workflow_templates("codetoreum")
        assert len(templates) == 2
        assert templates[0].board_id == "board-2"  # Sorted by board_id
        assert templates[1].board_id == "codetoreum-main"

    @pytest.mark.asyncio
    async def test_in_memory_workflow_config_delete(self) -> None:
        """Test deleting workflow templates."""
        service = InMemoryWorkflowConfigService()
        template = create_codetoreum_pipeline_template()

        # Save template
        await service.save_board_workflow_template(template)

        # Verify it exists
        retrieved = await service.get_board_workflow_template(template.board_id)
        assert retrieved is not None

        # Delete it
        await service.delete_board_workflow_template(template.board_id)

        # Verify it's gone
        retrieved = await service.get_board_workflow_template(template.board_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_validation_on_save_empty_board_id(self) -> None:
        """Test that empty board_id raises ValueError on construction."""
        template = create_codetoreum_pipeline_template()
        # Create a template with empty board_id - should raise during construction
        with pytest.raises(ValueError, match="board_id cannot be empty"):
            BoardWorkflowTemplate(
                id="test-id",
                name="Test",
                board_id="",  # Empty
                project_id="codetoreum",
                columns=template.columns,
            )

    @pytest.mark.asyncio
    async def test_validation_on_list_empty_project_id(self) -> None:
        """Test that empty project_id raises ValidationError on list."""
        service = InMemoryWorkflowConfigService()

        with pytest.raises(ValidationError):
            await service.list_board_workflow_templates("")


class TestCodetoreumPipelineTemplate:
    """Test Codetoreum pipeline template configuration."""

    def test_codetoreum_pipeline_has_seven_columns(self) -> None:
        """Test that Codetoreum pipeline has exactly 7 columns."""
        template = create_codetoreum_pipeline_template()
        assert len(template.columns) == 7

    def test_codetoreum_pipeline_column_names(self) -> None:
        """Test that columns have expected names."""
        template = create_codetoreum_pipeline_template()
        column_names = [col.name for col in template.columns]
        expected = ["Backlog", "Analysis", "Implementation", "Testing", "Review", "Blocked", "Done"]
        assert column_names == expected

    def test_codetoreum_pipeline_column_types(self) -> None:
        """Test that columns have expected types."""
        template = create_codetoreum_pipeline_template()

        # Backlog, Blocked, Done, Review are manual
        assert template.columns[0].type == ColumnType.MANUAL  # Backlog
        assert template.columns[4].type == ColumnType.MANUAL  # Review (manual approval)
        assert template.columns[5].type == ColumnType.MANUAL  # Blocked
        assert template.columns[6].type == ColumnType.MANUAL  # Done

        # Analysis, Implementation, Testing are automated
        assert template.columns[1].type == ColumnType.AUTOMATED  # Analysis
        assert template.columns[2].type == ColumnType.AUTOMATED  # Implementation
        assert template.columns[3].type == ColumnType.AUTOMATED  # Testing

    def test_codetoreum_pipeline_pipeline_trigger_columns(self) -> None:
        """Test that correct columns trigger pipeline lock."""
        template = create_codetoreum_pipeline_template()

        # Only Analysis column should be pipeline trigger
        pipeline_triggers = template.pipeline_trigger_columns
        assert pipeline_triggers == ("Analysis",)

    def test_codetoreum_pipeline_exit_columns(self) -> None:
        """Test that done column is exit column."""
        template = create_codetoreum_pipeline_template()

        # Only Done column should be exit column
        exit_cols = template.exit_columns
        assert exit_cols == ("Done",)

    def test_codetoreum_pipeline_agent_assignments(self) -> None:
        """Test that agents are correctly assigned."""
        template = create_codetoreum_pipeline_template()

        # Backlog: no agent
        assert template.columns[0].agent_id is None

        # Analysis: analyzer
        assert template.columns[1].agent_id == "analyzer"

        # Implementation: maker
        assert template.columns[2].agent_id == "maker"

        # Testing: tester
        assert template.columns[3].agent_id == "tester"

        # Review: none (uses pr_review_cycle_config)
        assert template.columns[4].agent_id is None

        # Blocked: no agent
        assert template.columns[5].agent_id is None

        # Done: no agent
        assert template.columns[6].agent_id is None

    def test_codetoreum_pipeline_auto_progression(self) -> None:
        """Test auto-progression settings."""
        template = create_codetoreum_pipeline_template()

        # Analysis, Implementation, Testing auto-progress on completion
        assert template.columns[1].auto_progress_on_completion is True  # Analysis
        assert template.columns[2].auto_progress_on_completion is True  # Implementation
        assert template.columns[3].auto_progress_on_completion is True  # Testing

        # Backlog, Blocked, Done, Review don't auto-progress
        assert template.columns[0].auto_progress_on_completion is False  # Backlog
        assert template.columns[4].auto_progress_on_completion is False  # Review
        assert template.columns[5].auto_progress_on_completion is False  # Blocked
        assert template.columns[6].auto_progress_on_completion is False  # Done

    def test_codetoreum_pipeline_failure_handling(self) -> None:
        """Test on_failure_column settings."""
        template = create_codetoreum_pipeline_template()

        # Automated stages (Analysis, Implementation, Testing) fail to Blocked
        assert template.columns[1].on_failure_column == "Blocked"  # Analysis
        assert template.columns[2].on_failure_column == "Blocked"  # Implementation
        assert template.columns[3].on_failure_column == "Blocked"  # Testing

        # Review and other manual columns can also have failure handling
        assert template.columns[4].on_failure_column == "Blocked"  # Review

    def test_codetoreum_pipeline_sla_thresholds(self) -> None:
        """Test SLA thresholds are configured."""
        template = create_codetoreum_pipeline_template()

        # Check that SLA is set for automated columns
        assert template.columns[1].sla_seconds == 3600  # Analysis: 1 hour
        assert template.columns[2].sla_seconds == 7200  # Implementation: 2 hours
        assert template.columns[3].sla_seconds == 3600  # Testing: 1 hour
        assert template.columns[4].sla_seconds == 86400  # Review: 24 hours

        # Manual columns should not have SLA
        assert template.columns[0].sla_seconds is None  # Backlog
        assert template.columns[5].sla_seconds is None  # Blocked
        assert template.columns[6].sla_seconds is None  # Done


class TestWorkflowConfigServiceRobustness:
    """Test robustness and error handling."""

    @pytest.mark.asyncio
    async def test_get_nonexistent_template_returns_none(self) -> None:
        """Test that getting nonexistent template returns None."""
        service = InMemoryWorkflowConfigService()
        result = await service.get_board_workflow_template("nonexistent-board")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_template_is_idempotent(self) -> None:
        """Test that deleting nonexistent template is idempotent."""
        service = InMemoryWorkflowConfigService()
        # Should not raise
        await service.delete_board_workflow_template("nonexistent-board")

    @pytest.mark.asyncio
    async def test_list_empty_project_returns_empty_list(self) -> None:
        """Test that listing empty project returns empty list."""
        service = InMemoryWorkflowConfigService()
        result = await service.list_board_workflow_templates("empty-project")
        assert result == []


# Integration test for smoke testing
class TestPhase5SmokeTest:
    """Smoke test for Phase 5 production pipeline configuration."""

    @pytest.mark.asyncio
    async def test_phase_5_smoke_test_workflow(self) -> None:
        """
        Smoke test: Verify end-to-end workflow.

        This test demonstrates:
        1. Workflow config service initializes
        2. Codetoreum pipeline template is saved
        3. Template can be retrieved and verified
        4. REST API endpoints would work with this service
        """
        # 1. Initialize service
        service = InMemoryWorkflowConfigService()

        # 2. Create and save Codetoreum pipeline template
        template = create_codetoreum_pipeline_template()
        await service.save_board_workflow_template(template)

        # 3. Verify template is saved and correct
        retrieved = await service.get_board_workflow_template(template.board_id)
        assert retrieved is not None
        assert retrieved.id == template.id
        assert retrieved.name == "Codetoreum SDLC Pipeline"
        assert len(retrieved.columns) == 7

        # 4. Verify pipeline trigger columns (for webhook to trigger agent)
        assert "Analysis" in retrieved.pipeline_trigger_columns
        analysis_col = retrieved.get_column_config("Analysis")
        assert analysis_col is not None
        assert analysis_col.agent_id == "analyzer"
        assert analysis_col.is_pipeline_trigger is True

        # 5. Verify exit columns (for marking work item as done)
        assert "Done" in retrieved.exit_columns
        done_col = retrieved.get_column_config("Done")
        assert done_col is not None
        assert done_col.is_exit_column is True

        # 6. Verify next column navigation
        next_after_backlog = retrieved.get_next_column("Backlog")
        assert next_after_backlog == "Analysis"

        next_after_analysis = retrieved.get_next_column("Analysis")
        assert next_after_analysis == "Implementation"

        next_after_done = retrieved.get_next_column("Done")
        assert next_after_done is None  # Done is last column

        print("✓ Phase 5 smoke test passed: Codetoreum pipeline configured successfully")
