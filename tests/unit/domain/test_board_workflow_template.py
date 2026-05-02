"""Unit tests for BoardWorkflowTemplate domain model."""

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


class TestBoardWorkflowTemplateQueryHelpers:
    """Test BoardWorkflowTemplate query helper methods."""

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
