"""Tests for IssueIntakeService

Tests the application service that handles newly opened GitHub issues
and places them on boards for workflow orchestration.
"""

import pytest

from codetoreum.application.issue_intake_service import IssueIntakeService
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.ports.input.issue_intake import IssueOpenedCommand
from codetoreum.ports.output.board_service import BoardColumn


class MockBoardService:
    """Mock board service for testing."""

    def __init__(self):
        self.get_all_boards_called = False
        self.add_item_to_column_called = False
        self.last_add_item_call = None

    async def get_all_boards(self):
        """Return test boards."""
        self.get_all_boards_called = True
        return [
            type(
                "Board",
                (),
                {
                    "id": "board-1",
                    "project_id": "proj-1",
                    "name": "Test Board",
                    "columns": [
                        BoardColumn(id="col-1", name="Backlog", position=0, work_item_ids=()),
                        BoardColumn(id="col-2", name="In Progress", position=1, work_item_ids=()),
                    ],
                },
            )()
        ]

    async def add_item_to_column(self, work_item_id, target_column, moved_by):
        """Record the add_item_to_column call."""
        self.add_item_to_column_called = True
        self.last_add_item_call = {
            "work_item_id": work_item_id,
            "target_column": target_column,
            "moved_by": moved_by,
        }


class MockWorkflowConfigService:
    """Mock workflow config service for testing."""

    def __init__(self):
        self.get_board_workflow_template_called = False

    async def get_board_workflow_template(self, board_id):
        """Return test workflow template."""
        self.get_board_workflow_template_called = True
        return BoardWorkflowTemplate(
            id="template-1",
            name="Test Workflow",
            board_id=board_id,
            columns=[
                ColumnTemplate(
                    id="col-1",
                    name="Backlog",
                    position=0,
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-1",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                ),
                ColumnTemplate(
                    id="col-2",
                    name="In Progress",
                    position=1,
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-2",
                    is_pipeline_trigger=True,
                    is_exit_column=False,
                ),
            ],
        )


@pytest.mark.asyncio
async def test_on_issue_opened_success():
    """Test successful issue intake."""
    board_service = MockBoardService()
    config_service = MockWorkflowConfigService()
    service = IssueIntakeService(board_service, config_service)

    command = IssueOpenedCommand(
        project_id="proj-1",
        issue_number="42",
        issue_title="Test Issue",
        issue_url="https://github.com/org/repo/issues/42",
    )

    result = await service.on_issue_opened(command)

    assert result.success
    assert result.work_item_id == "42"
    assert "placed" in result.message.lower()
    assert board_service.get_all_boards_called
    assert config_service.get_board_workflow_template_called
    assert board_service.add_item_to_column_called
    assert board_service.last_add_item_call["work_item_id"] == "42"
    assert board_service.last_add_item_call["target_column"] == "Backlog"


@pytest.mark.asyncio
async def test_on_issue_opened_no_boards():
    """Test issue intake when no boards exist for project."""

    class EmptyBoardService:
        async def get_all_boards(self):
            return []

    board_service = EmptyBoardService()
    config_service = MockWorkflowConfigService()
    service = IssueIntakeService(board_service, config_service)

    command = IssueOpenedCommand(
        project_id="proj-1",
        issue_number="42",
    )

    result = await service.on_issue_opened(command)

    assert not result.success
    assert "no boards" in result.message.lower()
    assert result.errors


@pytest.mark.asyncio
async def test_on_issue_opened_no_template():
    """Test issue intake when no workflow template exists."""

    class NullTemplateConfigService:
        async def get_board_workflow_template(self, board_id):
            return None

    board_service = MockBoardService()
    config_service = NullTemplateConfigService()
    service = IssueIntakeService(board_service, config_service)

    command = IssueOpenedCommand(
        project_id="proj-1",
        issue_number="42",
    )

    result = await service.on_issue_opened(command)

    assert not result.success
    assert "no workflow template" in result.message.lower()
    assert result.errors


@pytest.mark.asyncio
async def test_on_issue_opened_no_initial_column():
    """Test issue intake when no initial column exists."""

    class NoInitialColumnConfigService:
        async def get_board_workflow_template(self, board_id):
            return BoardWorkflowTemplate(
                id="template-1",
                name="Test Workflow",
                board_id=board_id,
                columns=[
                    ColumnTemplate(
                        id="col-1",
                        name="In Progress",
                        position=1,  # No position 0!
                        type=ColumnType.AUTOMATED,
                        agent_id="agent-1",
                        is_pipeline_trigger=False,
                        is_exit_column=False,
                    ),
                ],
            )

    board_service = MockBoardService()
    config_service = NoInitialColumnConfigService()
    service = IssueIntakeService(board_service, config_service)

    command = IssueOpenedCommand(
        project_id="proj-1",
        issue_number="42",
    )

    result = await service.on_issue_opened(command)

    assert not result.success
    assert "no initial column" in result.message.lower()
    assert result.errors
