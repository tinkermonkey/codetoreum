"""
End-to-end workflow stage configuration and execution

Tests the complete workflow stage lifecycle:
- Configure workflow template for automated stage
- Move work item to trigger column
- Verify event handler starts workflow run with template loaded
- Verify logging includes workflow configuration details
"""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.adapters.testing.in_memory_config_store import InMemoryConfigStore
from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.application.configuration_service import ConfigurationService
from codetoreum.application.event_handlers.board_event_handler import BoardColumnEventHandler
from codetoreum.application.pipeline_lock_service import LockStatus
from codetoreum.domain.board_workflow_template import BoardWorkflowTemplate, ColumnTemplate, ColumnType
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.input.config_command import UpdatePipelineConfigCommand
from codetoreum.ports.output.config_store import ProjectConfig
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService


@pytest.fixture
async def config_store():
    """Create in-memory config store."""
    store = InMemoryConfigStore()
    yield store
    store.clear()


@pytest.fixture
async def event_bus():
    """Create event bus."""
    return EventBus()


@pytest.fixture
async def config_service(config_store, event_bus):
    """Create configuration service."""
    return ConfigurationService(config_store, event_bus)


@pytest.fixture
async def sample_project(config_store):
    """Create sample project configuration."""
    project = ProjectConfig(
        id="codetoreum:codetoreum",
        name="codetoreum/codetoreum",
        github_org="codetoreum",
        github_repo="codetoreum",
        tech_stacks={},
        pipelines=[],
        testing={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await config_store.save_project_config(project)
    return project


@pytest.fixture
def mock_workflow_config_service():
    """Create mock workflow config service."""

    class MockWorkflowConfigService(IWorkflowConfigService):
        async def get_board_workflow_template(self, board_id: str):
            return BoardWorkflowTemplate(
                id="default-workflow",
                name="Default Workflow",
                board_id=board_id,
                project_id="codetoreum:codetoreum",
                columns=[
                    ColumnTemplate(
                        name="Backlog",
                        type=ColumnType.MANUAL,
                        agent_id=None,
                        is_exit_column=False,
                        is_pipeline_trigger=False,
                        auto_progress_on_completion=False,
                        position=0,
                    ),
                    ColumnTemplate(
                        name="In Progress",
                        type=ColumnType.AUTOMATED,
                        agent_id="coding-agent",
                        is_exit_column=False,
                        is_pipeline_trigger=True,
                        auto_progress_on_completion=False,
                        position=1,
                    ),
                    ColumnTemplate(
                        name="Done",
                        type=ColumnType.MANUAL,
                        agent_id=None,
                        is_exit_column=True,
                        is_pipeline_trigger=False,
                        auto_progress_on_completion=False,
                        position=2,
                    ),
                ],
            )

        async def save_board_workflow_template(self, template):
            pass

        async def delete_board_workflow_template(self, board_id: str):
            pass

        async def list_board_workflow_templates(self):
            return []

    return MockWorkflowConfigService()


class TestWorkflowStageE2E:
    """End-to-end tests for workflow stage configuration."""

    @pytest.mark.asyncio
    async def test_workflow_run_logs_template_on_column_entry(
        self, config_service, config_store, sample_project, mock_workflow_config_service, caplog
    ):
        """Test that entering automated stage column logs workflow run with template details.

        Verifies:
        - Pipeline config stored with stage configuration
        - Moving item to stage column triggers BoardColumnEventHandler
        - Handler logs "Starting workflow run" with template and stage details
        """
        # 1. Configure the pipeline with "In Progress" stage
        command = UpdatePipelineConfigCommand(
            project_name="codetoreum/codetoreum",
            pipeline_name="default",
            updates={
                "stages": [
                    {
                        "name": "In Progress",
                        "agent_type": "coding agent",
                        "model": "claude-sonnet-4-5",
                        "context_files": [
                            {"path": "/context/issue.md", "description": "Issue details"},
                            {"path": "/context/repo_summary.md", "description": "Repo structure"},
                            {"path": "/context/previous_stage.txt", "description": "Previous output"},
                        ],
                        "prompt_template": "Implement the issue",
                        "git_author_name": "Codetoreum Agent",
                        "git_author_email": "agent@codetoreum.dev",
                    }
                ]
            },
            user_id="test-user",
        )

        result = await config_service.update_pipeline_config(command)
        assert result.success

        # Verify config was stored
        pipeline = await config_store.get_pipeline_config(sample_project.id, "default")
        stage = dict(pipeline.stages[0])
        assert stage["name"] == "In Progress"
        assert stage["model"] == "claude-sonnet-4-5"
        assert stage["git_author_name"] == "Codetoreum Agent"

        # 2. Create mock board event handler with mocked dependencies
        mock_board_service = AsyncMock()
        mock_board_service.get_item_position.return_value = MagicMock(position=1, column_name="In Progress")

        mock_lock_service = AsyncMock()
        mock_lock_service.try_acquire_lock.return_value = MagicMock(
            status=LockStatus.ACQUIRED, queue_position=0, queue_length=0
        )

        mock_agent_executor = AsyncMock()
        event_store = InMemoryEventStore()
        event_bus = EventBus()

        handler = BoardColumnEventHandler(
            board_service=mock_board_service,
            lock_service=mock_lock_service,
            workflow_config=mock_workflow_config_service,
            agent_executor=mock_agent_executor,
            event_bus=event_bus,
            event_store=event_store,
            work_item_service=AsyncMock(),
        )

        # 3. Simulate work item moving to "In Progress"
        event = WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=datetime.now(UTC).isoformat(),
            source="test",
            work_item_id="issue-123",
            board_id="board-1",
            project_id=sample_project.id,
            from_column="Backlog",
            to_column="In Progress",
            moved_by="human",
        )

        # 4. Capture logs and handle the event
        with caplog.at_level(logging.INFO):
            await handler.handle_column_change(event)

        # 5. Verify logs contain workflow start information
        log_text = caplog.text
        assert "Starting workflow run" in log_text
        assert "issue-123" in log_text
        assert "In Progress" in log_text
        assert "board-1" in log_text
        assert "coding-agent" in log_text  # Agent ID from column template
