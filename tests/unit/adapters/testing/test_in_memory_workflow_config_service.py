"""Unit tests for InMemoryWorkflowConfigService."""

import pytest

from codetoreum.adapters.testing.in_memory_workflow_config_service import (
    InMemoryWorkflowConfigService,
)
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)


@pytest.fixture
def config_service():
    """Create an in-memory workflow configuration service."""
    return InMemoryWorkflowConfigService()


@pytest.fixture
def sample_workflow_template():
    """Create a sample workflow template for testing."""
    return BoardWorkflowTemplate(
        id="workflow-1",
        name="Standard Workflow",
        pipeline_trigger_columns=("In Progress",),
        exit_columns=("Done",),
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
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="agent-1",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=False,
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
        ),
    )


class TestRegisterTemplate:
    """Tests for register_template method."""

    def test_register_template_stores_template(self, config_service, sample_workflow_template):
        """Test that register_template stores the template."""
        config_service.register_template("board-1", sample_workflow_template)

        assert "board-1" in config_service._templates
        assert config_service._templates["board-1"] == sample_workflow_template

    def test_register_multiple_templates(self, config_service, sample_workflow_template):
        """Test registering multiple templates for different boards."""
        config_service.register_template("board-1", sample_workflow_template)
        config_service.register_template("board-2", sample_workflow_template)

        assert len(config_service._templates) == 2
        assert config_service._templates["board-1"] == sample_workflow_template
        assert config_service._templates["board-2"] == sample_workflow_template

    def test_register_overwrites_existing_template(self, config_service, sample_workflow_template):
        """Test that registering a template for an existing board overwrites it."""
        config_service.register_template("board-1", sample_workflow_template)

        new_template = BoardWorkflowTemplate(
            id="workflow-2",
            name="New Workflow",
            pipeline_trigger_columns=(),
            exit_columns=(),
            columns=(
                ColumnTemplate(
                    name="Todo",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                ),
            ),
        )

        config_service.register_template("board-1", new_template)

        assert config_service._templates["board-1"] == new_template
        assert config_service._templates["board-1"].id == "workflow-2"


class TestGetBoardWorkflowTemplate:
    """Tests for get_board_workflow_template method."""

    @pytest.mark.asyncio
    async def test_get_existing_template(self, config_service, sample_workflow_template):
        """Test retrieving an existing template."""
        config_service.register_template("board-1", sample_workflow_template)

        result = await config_service.get_board_workflow_template("board-1")

        assert result == sample_workflow_template
        assert result.id == "workflow-1"
        assert result.name == "Standard Workflow"

    @pytest.mark.asyncio
    async def test_get_non_existent_template(self, config_service):
        """Test retrieving a template that doesn't exist."""
        result = await config_service.get_board_workflow_template("board-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_after_multiple_registrations(self, config_service, sample_workflow_template):
        """Test retrieving templates after multiple registrations."""
        template1 = sample_workflow_template

        template2 = BoardWorkflowTemplate(
            id="workflow-2",
            name="Workflow 2",
            pipeline_trigger_columns=(),
            exit_columns=(),
            columns=(
                ColumnTemplate(
                    name="Open",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                ),
            ),
        )

        config_service.register_template("board-1", template1)
        config_service.register_template("board-2", template2)

        result1 = await config_service.get_board_workflow_template("board-1")
        result2 = await config_service.get_board_workflow_template("board-2")

        assert result1 == template1
        assert result2 == template2
        assert result1.id == "workflow-1"
        assert result2.id == "workflow-2"


class TestClear:
    """Tests for clear method."""

    def test_clear_removes_all_templates(self, config_service, sample_workflow_template):
        """Test that clear removes all registered templates."""
        config_service.register_template("board-1", sample_workflow_template)
        config_service.register_template("board-2", sample_workflow_template)

        assert len(config_service._templates) == 2

        config_service.clear()

        assert len(config_service._templates) == 0

    def test_clear_on_empty_service(self, config_service):
        """Test that clear on an empty service doesn't raise an error."""
        # Should not raise
        config_service.clear()

        assert len(config_service._templates) == 0

    def test_clear_allows_re_registration(self, config_service, sample_workflow_template):
        """Test that templates can be registered again after clear."""
        config_service.register_template("board-1", sample_workflow_template)
        config_service.clear()

        config_service.register_template("board-1", sample_workflow_template)

        result = config_service._templates.get("board-1")
        assert result == sample_workflow_template


class TestIntegration:
    """Integration tests for the service."""

    @pytest.mark.asyncio
    async def test_full_workflow_template_retrieval_flow(
        self, config_service, sample_workflow_template
    ):
        """Test complete workflow: register template and retrieve it."""
        # Register template
        config_service.register_template("board-1", sample_workflow_template)

        # Retrieve and verify
        retrieved = await config_service.get_board_workflow_template("board-1")

        assert retrieved is not None
        assert retrieved.id == "workflow-1"
        assert len(retrieved.columns) == 3
        assert retrieved.columns[0].name == "Backlog"
        assert retrieved.columns[1].agent_id == "agent-1"
        assert "In Progress" in retrieved.pipeline_trigger_columns

    @pytest.mark.asyncio
    async def test_multiple_boards_independent_templates(
        self, config_service, sample_workflow_template
    ):
        """Test that different boards can have different templates."""
        template1 = sample_workflow_template

        template2 = BoardWorkflowTemplate(
            id="workflow-alt",
            name="Alternative Workflow",
            pipeline_trigger_columns=("Backlog",),
            exit_columns=("Archived",),
            columns=(
                ColumnTemplate(
                    name="Backlog",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=True,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                ),
                ColumnTemplate(
                    name="Archived",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=True,
                    position=1,
                    auto_progress_on_completion=False,
                ),
            ),
        )

        # Register different templates for different boards
        config_service.register_template("board-1", template1)
        config_service.register_template("board-2", template2)

        # Verify templates are independent
        result1 = await config_service.get_board_workflow_template("board-1")
        result2 = await config_service.get_board_workflow_template("board-2")

        assert result1.id == "workflow-1"
        assert result2.id == "workflow-alt"
        assert len(result1.columns) == 3
        assert len(result2.columns) == 2
        assert "In Progress" in result1.pipeline_trigger_columns
        assert "Backlog" in result2.pipeline_trigger_columns
