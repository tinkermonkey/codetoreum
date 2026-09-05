"""Unit tests for BoardWorkflowTemplate domain entity."""

import pytest

from codetoreum.domain.board_workflow_template import (
    BoardReconciliationConfig,
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)


class TestColumnTypeEnum:
    """Test ColumnType enumeration."""

    def test_manual_type(self) -> None:
        """Test MANUAL column type."""
        assert ColumnType.MANUAL.value == "manual"

    def test_automated_type(self) -> None:
        """Test AUTOMATED column type."""
        assert ColumnType.AUTOMATED.value == "automated"


class TestColumnTemplate:
    """Test ColumnTemplate dataclass."""

    def test_create_manual_column(self):
        """Test creating a manual column template."""
        column = ColumnTemplate(
            name="Backlog",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
        )

        assert column.name == "Backlog"
        assert column.type == ColumnType.MANUAL
        assert column.agent_id is None
        assert column.is_pipeline_trigger is False
        assert column.is_exit_column is False
        assert column.position == 0
        assert column.auto_progress_on_completion is False

    def test_create_automated_column(self):
        """Test creating an automated column template."""
        column = ColumnTemplate(
            name="Development",
            type=ColumnType.AUTOMATED,
            agent_id="agent-dev",
            is_pipeline_trigger=True,
            is_exit_column=False,
            position=1,
            auto_progress_on_completion=True,
        )

        assert column.name == "Development"
        assert column.type == ColumnType.AUTOMATED
        assert column.agent_id == "agent-dev"
        assert column.is_pipeline_trigger is True
        assert column.is_exit_column is False
        assert column.position == 1
        assert column.auto_progress_on_completion is True

    def test_create_exit_column(self):
        """Test creating an exit column that releases locks."""
        column = ColumnTemplate(
            name="Done",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=True,
            position=4,
            auto_progress_on_completion=False,
        )

        assert column.name == "Done"
        assert column.is_exit_column is True
        assert column.is_pipeline_trigger is False


class TestColumnTemplateValidation:
    """Test ColumnTemplate validation."""

    def test_valid_manual_column(self) -> None:
        """Test creating a valid manual column."""
        column = ColumnTemplate(
            name="Backlog",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
        )

        assert column.name == "Backlog"
        assert column.type == ColumnType.MANUAL
        assert column.agent_id is None

    def test_valid_automated_column(self) -> None:
        """Test creating a valid automated column."""
        column = ColumnTemplate(
            name="Development",
            type=ColumnType.AUTOMATED,
            agent_id="agent-123",
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=1,
            auto_progress_on_completion=True,
        )

        assert column.name == "Development"
        assert column.type == ColumnType.AUTOMATED
        assert column.agent_id == "agent-123"

    def test_empty_column_name_invalid(self) -> None:
        """Test that empty column name raises ValueError."""
        with pytest.raises(ValueError, match="Column name cannot be empty"):
            ColumnTemplate(
                name="",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            )

    def test_negative_position_invalid(self) -> None:
        """Test that negative position raises ValueError."""
        with pytest.raises(ValueError, match="Position must be non-negative"):
            ColumnTemplate(
                name="Test",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=-1,
                auto_progress_on_completion=False,
            )

    def test_automated_column_without_agent_invalid(self) -> None:
        """Test that automated column without agent raises ValueError."""
        with pytest.raises(ValueError, match="Automated column.*must have an agent_id"):
            ColumnTemplate(
                name="Test",
                type=ColumnType.AUTOMATED,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            )

    def test_manual_column_with_agent_invalid(self) -> None:
        """Test that manual column with agent raises ValueError."""
        with pytest.raises(ValueError, match="Manual column.*cannot have an agent_id"):
            ColumnTemplate(
                name="Test",
                type=ColumnType.MANUAL,
                agent_id="agent-123",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            )

    def test_auto_progress_only_for_automated_columns(self) -> None:
        """Test that auto_progress_on_completion is only valid for automated columns."""
        with pytest.raises(ValueError, match="auto_progress_on_completion only valid for automated"):
            ColumnTemplate(
                name="Test",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=True,
            )

    def test_positive_sla_seconds(self) -> None:
        """Test that positive SLA seconds is valid."""
        column = ColumnTemplate(
            name="Review",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
            sla_seconds=3600,
        )

        assert column.sla_seconds == 3600

    def test_zero_sla_seconds_invalid(self) -> None:
        """Test that zero SLA seconds raises ValueError."""
        with pytest.raises(ValueError, match="SLA threshold must be positive"):
            ColumnTemplate(
                name="Test",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
                sla_seconds=0,
            )

    def test_invalid_execution_type(self) -> None:
        """Test that invalid execution type raises ValueError."""
        with pytest.raises(ValueError, match="execution_type must be one of"):
            ColumnTemplate(
                name="Test",
                type=ColumnType.AUTOMATED,
                agent_id="agent-123",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
                execution_type="invalid",
            )


class TestBoardWorkflowTemplateCreation:
    """Test BoardWorkflowTemplate creation and initialization."""

    def test_create_minimal_template(self):
        """Test creating a template with minimal columns."""
        columns = (
            ColumnTemplate(
                name="Backlog",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="Done",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=True,
                position=1,
                auto_progress_on_completion=False,
            ),
        )

        template = BoardWorkflowTemplate(
            id="template-1",
            name="Simple Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=columns,
        )

        assert template.id == "template-1"
        assert template.name == "Simple Workflow"
        assert len(template.columns) == 2
        assert template.pipeline_trigger_columns == ()
        assert template.exit_columns == ("Done",)

    def test_create_full_workflow_template(self):
        """Test creating a template with full SDLC workflow."""
        columns = (
            ColumnTemplate(
                name="Backlog",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="agent-dev",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="Review",
                type=ColumnType.AUTOMATED,
                agent_id="agent-reviewer",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="Done",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=True,
                position=3,
                auto_progress_on_completion=False,
            ),
        )

        template = BoardWorkflowTemplate(
            id="template-sdlc",
            name="Full SDLC Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=columns,
        )

        assert len(template.columns) == 4
        assert template.pipeline_trigger_columns == ("In Progress",)
        assert template.exit_columns == ("Done",)


class TestGetColumnConfig:
    """Test get_column_config method."""

    @pytest.fixture
    def template(self):
        """Fixture providing a complete workflow template."""
        columns = (
            ColumnTemplate(
                name="Backlog",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="agent-dev",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="Review",
                type=ColumnType.AUTOMATED,
                agent_id="agent-reviewer",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="Done",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=True,
                position=3,
                auto_progress_on_completion=False,
            ),
        )

        return BoardWorkflowTemplate(
            id="template-1",
            name="Test Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=columns,
        )

    def test_get_column_config_found(self) -> None:
        """Test getting a column config by name."""
        columns = (
            ColumnTemplate("Backlog", ColumnType.MANUAL, None, False, False, 0, False),
            ColumnTemplate("Dev", ColumnType.AUTOMATED, "agent-1", True, False, 1, True),
        )

        template = BoardWorkflowTemplate(
            id="template-1",
            name="Test",
            board_id="board-1",
            project_id="proj-1",
            columns=columns,
        )

        config = template.get_column_config("Dev")
        assert config is not None
        assert config.name == "Dev"
        assert config.agent_id == "agent-1"

    def test_get_column_config_not_found(self) -> None:
        """Test getting a column config for non-existent column."""
        columns = (ColumnTemplate("Backlog", ColumnType.MANUAL, None, False, False, 0, False),)

        template = BoardWorkflowTemplate(
            id="template-1",
            name="Test",
            board_id="board-1",
            project_id="proj-1",
            columns=columns,
        )

        config = template.get_column_config("NonExistent")
        assert config is None

    def test_get_column_by_name(self, template):
        """Test retrieving column configuration by name."""
        config = template.get_column_config("In Progress")

        assert config is not None
        assert config.name == "In Progress"
        assert config.type == ColumnType.AUTOMATED
        assert config.agent_id == "agent-dev"
        assert config.is_pipeline_trigger is True

    def test_get_column_manual(self, template):
        """Test retrieving a manual column."""
        config = template.get_column_config("Backlog")

        assert config is not None
        assert config.name == "Backlog"
        assert config.type == ColumnType.MANUAL
        assert config.agent_id is None
        assert config.is_pipeline_trigger is False

    def test_get_nonexistent_column(self, template):
        """Test that None is returned for nonexistent column."""
        config = template.get_column_config("Nonexistent")

        assert config is None

    def test_get_column_case_sensitive(self, template):
        """Test that column names are case-sensitive."""
        config = template.get_column_config("in progress")

        assert config is None

    def test_get_exit_column(self, template):
        """Test retrieving an exit column."""
        config = template.get_column_config("Done")

        assert config is not None
        assert config.is_exit_column is True


class TestGetNextColumn:
    """Test get_next_column method."""

    @pytest.fixture
    def template(self):
        """Fixture providing a complete workflow template."""
        columns = (
            ColumnTemplate(
                name="Backlog",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="agent-dev",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="Review",
                type=ColumnType.AUTOMATED,
                agent_id="agent-reviewer",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=True,
            ),
            ColumnTemplate(
                name="Done",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=True,
                position=3,
                auto_progress_on_completion=False,
            ),
        )

        return BoardWorkflowTemplate(
            id="template-1",
            name="Test Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=columns,
        )

    def test_get_next_column(self) -> None:
        """Test getting next column."""
        columns = (
            ColumnTemplate("Backlog", ColumnType.MANUAL, None, False, False, 0, False),
            ColumnTemplate("Dev", ColumnType.AUTOMATED, "agent-1", True, False, 1, True),
            ColumnTemplate("Done", ColumnType.MANUAL, None, False, True, 2, False),
        )

        template = BoardWorkflowTemplate(
            id="template-1",
            name="Test",
            board_id="board-1",
            project_id="proj-1",
            columns=columns,
        )

        assert template.get_next_column("Backlog") == "Dev"
        assert template.get_next_column("Dev") == "Done"
        assert template.get_next_column("Done") is None

    def test_get_next_column_from_backlog(self, template):
        """Test getting next column from Backlog."""
        next_col = template.get_next_column("Backlog")

        assert next_col == "In Progress"

    def test_get_next_column_from_in_progress(self, template):
        """Test getting next column from In Progress."""
        next_col = template.get_next_column("In Progress")

        assert next_col == "Review"

    def test_get_next_column_from_review(self, template):
        """Test getting next column from Review."""
        next_col = template.get_next_column("Review")

        assert next_col == "Done"

    def test_get_next_column_from_last(self, template):
        """Test that None is returned for last column."""
        next_col = template.get_next_column("Done")

        assert next_col is None

    def test_get_next_column_nonexistent(self, template):
        """Test that None is returned for nonexistent column."""
        next_col = template.get_next_column("Nonexistent")

        assert next_col is None

    def test_get_next_column_case_sensitive(self, template):
        """Test that column names are case-sensitive."""
        next_col = template.get_next_column("backlog")

        assert next_col is None

    def test_get_next_column_chain(self, template):
        """Test chaining get_next_column calls."""
        first = template.get_next_column("Backlog")
        second = template.get_next_column(first)
        third = template.get_next_column(second)
        fourth = template.get_next_column(third)

        assert first == "In Progress"
        assert second == "Review"
        assert third == "Done"
        assert fourth is None


class TestBoardWorkflowTemplateValidation:
    """Test BoardWorkflowTemplate validation."""

    def test_valid_workflow_template(self) -> None:
        """Test creating a valid workflow template."""
        columns = (
            ColumnTemplate("Backlog", ColumnType.MANUAL, None, False, False, 0, False),
            ColumnTemplate("Dev", ColumnType.AUTOMATED, "agent-1", True, False, 1, True),
            ColumnTemplate("Done", ColumnType.MANUAL, None, False, True, 2, False),
        )

        template = BoardWorkflowTemplate(
            id="template-1",
            name="SDLC Workflow",
            board_id="board-1",
            project_id="proj-1",
            columns=columns,
        )

        assert template.id == "template-1"
        assert len(template.columns) == 3

    def test_empty_id_invalid(self) -> None:
        """Test that empty ID raises ValueError."""
        columns = (ColumnTemplate("Col", ColumnType.MANUAL, None, False, False, 0, False),)

        with pytest.raises(ValueError, match="Template ID cannot be empty"):
            BoardWorkflowTemplate(
                id="",
                name="Test",
                board_id="board-1",
                project_id="proj-1",
                columns=columns,
            )

    def test_empty_name_invalid(self) -> None:
        """Test that empty name raises ValueError."""
        columns = (ColumnTemplate("Col", ColumnType.MANUAL, None, False, False, 0, False),)

        with pytest.raises(ValueError, match="Template name cannot be empty"):
            BoardWorkflowTemplate(
                id="template-1",
                name="",
                board_id="board-1",
                project_id="proj-1",
                columns=columns,
            )

    def test_empty_board_id_invalid(self) -> None:
        """Test that empty board_id raises ValueError."""
        columns = (ColumnTemplate("Col", ColumnType.MANUAL, None, False, False, 0, False),)

        with pytest.raises(ValueError, match="board_id cannot be empty"):
            BoardWorkflowTemplate(
                id="template-1",
                name="Test",
                board_id="",
                project_id="proj-1",
                columns=columns,
            )

    def test_no_columns_invalid(self) -> None:
        """Test that template with no columns raises ValueError."""
        with pytest.raises(ValueError, match="Workflow must have at least one column"):
            BoardWorkflowTemplate(
                id="template-1",
                name="Test",
                board_id="board-1",
                project_id="proj-1",
                columns=(),
            )

    def test_non_sequential_positions_invalid(self) -> None:
        """Test that non-sequential positions raise ValueError."""
        columns = (
            ColumnTemplate("Col1", ColumnType.MANUAL, None, False, False, 0, False),
            ColumnTemplate("Col2", ColumnType.MANUAL, None, False, False, 2, False),
        )

        with pytest.raises(ValueError, match="Column positions must be unique and sequential"):
            BoardWorkflowTemplate(
                id="template-1",
                name="Test",
                board_id="board-1",
                project_id="proj-1",
                columns=columns,
            )

    def test_duplicate_column_names_invalid(self) -> None:
        """Test that duplicate column names raise ValueError."""
        columns = (
            ColumnTemplate("Backlog", ColumnType.MANUAL, None, False, False, 0, False),
            ColumnTemplate("Backlog", ColumnType.MANUAL, None, False, False, 1, False),
        )

        with pytest.raises(ValueError, match="Column names must be unique"):
            BoardWorkflowTemplate(
                id="template-1",
                name="Test",
                board_id="board-1",
                project_id="proj-1",
                columns=columns,
            )

    def test_invalid_on_failure_column_reference(self) -> None:
        """Test that invalid on_failure_column reference raises ValueError."""
        columns = (
            ColumnTemplate(
                "Col1",
                ColumnType.MANUAL,
                None,
                False,
                False,
                0,
                False,
                on_failure_column="NonexistentColumn",
            ),
        )

        with pytest.raises(ValueError, match="references unknown on_failure_column"):
            BoardWorkflowTemplate(
                id="template-1",
                name="Test",
                board_id="board-1",
                project_id="proj-1",
                columns=columns,
            )


class TestBoardWorkflowTemplateProperties:
    """Test BoardWorkflowTemplate computed properties."""

    def test_pipeline_trigger_columns_property(self) -> None:
        """Test pipeline_trigger_columns computed property."""
        columns = (
            ColumnTemplate("Backlog", ColumnType.MANUAL, None, False, False, 0, False),
            ColumnTemplate("Dev", ColumnType.AUTOMATED, "agent-1", True, False, 1, True),
            ColumnTemplate("Done", ColumnType.MANUAL, None, False, False, 2, False),
        )

        template = BoardWorkflowTemplate(
            id="template-1",
            name="Test",
            board_id="board-1",
            project_id="proj-1",
            columns=columns,
        )

        assert template.pipeline_trigger_columns == ("Dev",)

    def test_exit_columns_property(self) -> None:
        """Test exit_columns computed property."""
        columns = (
            ColumnTemplate("Backlog", ColumnType.MANUAL, None, False, False, 0, False),
            ColumnTemplate("Dev", ColumnType.AUTOMATED, "agent-1", True, False, 1, True),
            ColumnTemplate("Done", ColumnType.MANUAL, None, False, True, 2, False),
        )

        template = BoardWorkflowTemplate(
            id="template-1",
            name="Test",
            board_id="board-1",
            project_id="proj-1",
            columns=columns,
        )

        assert template.exit_columns == ("Done",)


class TestBoardReconciliationConfig:
    """Test BoardReconciliationConfig validation."""

    def test_valid_config(self) -> None:
        """Test creating a valid reconciliation config."""
        config = BoardReconciliationConfig(
            workflow_template_id="template-1",
            board_id="board-1",
            project_id="proj-1",
        )

        assert config.workflow_template_id == "template-1"
        assert config.board_id == "board-1"
        assert config.project_id == "proj-1"

    def test_empty_workflow_template_id_invalid(self) -> None:
        """Test that empty workflow_template_id raises ValueError."""
        with pytest.raises(ValueError, match="workflow_template_id cannot be empty"):
            BoardReconciliationConfig(
                workflow_template_id="",
                board_id="board-1",
                project_id="proj-1",
            )

    def test_empty_board_id_invalid(self) -> None:
        """Test that empty board_id raises ValueError."""
        with pytest.raises(ValueError, match="board_id cannot be empty"):
            BoardReconciliationConfig(
                workflow_template_id="template-1",
                board_id="",
                project_id="proj-1",
            )

    def test_empty_project_id_invalid(self) -> None:
        """Test that empty project_id raises ValueError."""
        with pytest.raises(ValueError, match="project_id cannot be empty"):
            BoardReconciliationConfig(
                workflow_template_id="template-1",
                board_id="board-1",
                project_id="",
            )

    def test_create_board_reconciliation_config(self):
        """Test creating board reconciliation configuration."""
        config = BoardReconciliationConfig(
            workflow_template_id="template-1",
            board_id="board-123",
            project_id="proj-456",
        )

        assert config.workflow_template_id == "template-1"
        assert config.board_id == "board-123"
        assert config.project_id == "proj-456"


class TestBoardWorkflowTemplateEdgeCases:
    """Test edge cases and special scenarios."""

    def test_single_column_workflow(self):
        """Test workflow with single column."""
        columns = (
            ColumnTemplate(
                name="Work",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
        )

        template = BoardWorkflowTemplate(
            id="template-1",
            name="Single Column",
            board_id="board-1",
            project_id="test-project",
            columns=columns,
        )

        assert len(template.columns) == 1
        assert template.get_column_config("Work") is not None
        assert template.get_next_column("Work") is None

    def test_multiple_trigger_columns(self):
        """Test workflow with multiple pipeline trigger columns."""
        columns = (
            ColumnTemplate(
                name="Dev",
                type=ColumnType.AUTOMATED,
                agent_id="agent-1",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="QA",
                type=ColumnType.AUTOMATED,
                agent_id="agent-2",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=False,
            ),
        )

        template = BoardWorkflowTemplate(
            id="template-1",
            name="Multi Trigger",
            board_id="board-1",
            project_id="test-project",
            columns=columns,
        )

        assert len(template.pipeline_trigger_columns) == 2
        assert "Dev" in template.pipeline_trigger_columns
        assert "QA" in template.pipeline_trigger_columns

    def test_empty_columns_list(self):
        """Test template with empty columns list raises ValueError."""
        with pytest.raises(ValueError, match="Workflow must have at least one column"):
            BoardWorkflowTemplate(
                id="template-1",
                name="Empty Template",
                board_id="board-1",
                project_id="test-project",
                columns=(),
            )

    def test_column_type_enum(self):
        """Test ColumnType enum values."""
        assert ColumnType.MANUAL.value == "manual"
        assert ColumnType.AUTOMATED.value == "automated"
        assert len(ColumnType) == 2


class TestBoardWorkflowTemplatePositionValidation:
    """Test position validation in BoardWorkflowTemplate."""

    def test_valid_sequential_positions(self):
        """Test that sequential positions are accepted."""
        columns = (
            ColumnTemplate(
                name="Col0",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="Col1",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="Col2",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=False,
            ),
        )

        template = BoardWorkflowTemplate(
            id="template-1",
            name="Test",
            board_id="board-1",
            project_id="test-project",
            columns=columns,
        )

        assert len(template.columns) == 3

    def test_invalid_duplicate_positions(self):
        """Test that duplicate positions are rejected."""
        columns = (
            ColumnTemplate(
                name="Col0",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="Col1",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,  # Duplicate position
                auto_progress_on_completion=False,
            ),
        )

        with pytest.raises(ValueError, match="Column positions must be unique"):
            BoardWorkflowTemplate(
                id="template-1",
                name="Test",
                board_id="board-1",
                project_id="test-project",
                columns=columns,
            )

    def test_invalid_positions_not_starting_at_zero(self):
        """Test that positions not starting at 0 are rejected."""
        columns = (
            ColumnTemplate(
                name="Col1",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="Col2",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=False,
            ),
        )

        with pytest.raises(ValueError, match="Column positions must be unique"):
            BoardWorkflowTemplate(
                id="template-1",
                name="Test",
                board_id="board-1",
                project_id="test-project",
                columns=columns,
            )

    def test_invalid_positions_with_gaps(self):
        """Test that positions with gaps are rejected."""
        columns = (
            ColumnTemplate(
                name="Col0",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="Col2",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,  # Gap: missing position 1
                auto_progress_on_completion=False,
            ),
        )

        with pytest.raises(ValueError, match="Column positions must be unique"):
            BoardWorkflowTemplate(
                id="template-1",
                name="Test",
                board_id="board-1",
                project_id="test-project",
                columns=columns,
            )


class TestColumnTemplateReferenceValidation:
    """Tests for on_failure_column and sla_escalation_column validation."""

    def _make_col(self, name: str, position: int, **kwargs) -> ColumnTemplate:
        return ColumnTemplate(
            name=name,
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=position,
            auto_progress_on_completion=False,
            **kwargs,
        )

    def test_on_failure_column_self_reference_rejected(self):
        """ColumnTemplate rejects on_failure_column pointing to itself."""
        with pytest.raises(ValueError, match="on_failure_column cannot reference itself"):
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="agent-1",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
                on_failure_column="In Progress",
            )

    def test_sla_escalation_column_self_reference_rejected(self):
        """ColumnTemplate rejects sla_escalation_column pointing to itself."""
        with pytest.raises(ValueError, match="sla_escalation_column cannot reference itself"):
            ColumnTemplate(
                name="Waiting",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
                sla_escalation_column="Waiting",
            )

    def test_on_failure_column_unknown_reference_rejected(self):
        """BoardWorkflowTemplate rejects on_failure_column referencing a non-existent column."""
        columns = (
            self._make_col("Backlog", 0),
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="agent-1",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=False,
                on_failure_column="Nonexistent",
            ),
            self._make_col("Done", 2),
        )
        with pytest.raises(ValueError, match="references unknown on_failure_column 'Nonexistent'"):
            BoardWorkflowTemplate(
                id="t1",
                name="T",
                board_id="b1",
                project_id="p1",
                columns=columns,
            )

    def test_sla_escalation_column_unknown_reference_rejected(self):
        """BoardWorkflowTemplate rejects sla_escalation_column referencing a non-existent column."""
        columns = (
            self._make_col("Backlog", 0),
            ColumnTemplate(
                name="Review",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=False,
                sla_seconds=3600,
                sla_escalation_column="DoesNotExist",
            ),
            self._make_col("Done", 2),
        )
        with pytest.raises(ValueError, match="references unknown sla_escalation_column 'DoesNotExist'"):
            BoardWorkflowTemplate(
                id="t1",
                name="T",
                board_id="b1",
                project_id="p1",
                columns=columns,
            )

    def test_valid_on_failure_and_sla_escalation_columns_accepted(self):
        """BoardWorkflowTemplate accepts valid cross-column references."""
        columns = (
            ColumnTemplate(
                name="Backlog",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="agent-1",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=True,
                sla_seconds=3600,
                on_failure_column="Backlog",
                sla_escalation_column="Backlog",
            ),
            ColumnTemplate(
                name="Done",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=True,
                position=2,
                auto_progress_on_completion=False,
            ),
        )
        template = BoardWorkflowTemplate(
            id="t1",
            name="T",
            board_id="b1",
            project_id="p1",
            columns=columns,
        )
        col = template.get_column_config("In Progress")
        assert col is not None
        assert col.on_failure_column == "Backlog"
        assert col.sla_escalation_column == "Backlog"
