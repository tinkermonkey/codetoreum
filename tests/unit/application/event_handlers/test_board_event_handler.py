"""Unit tests for BoardColumnEventHandler."""

import logging
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

from codetoreum.application.event_handlers.board_event_handler import (
    BoardColumnEventHandler,
)
from codetoreum.application.pipeline_lock_service import (
    LockAcquisitionResult,
    LockReleaseResult,
    LockStatus,
)
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.domain.events import WorkItemColumnChanged
from codetoreum.ports.output.board_service import WorkItemPosition, MovedByType


@pytest.fixture
def mock_board_service():
    """Create mock board service."""
    service = AsyncMock()
    service.get_item_position = AsyncMock(
        return_value=WorkItemPosition(
            work_item_id="item-1",
            column_name="In Progress",
            position=0,
        )
    )
    service.move_item_to_column = AsyncMock()
    return service


@pytest.fixture
def mock_lock_service():
    """Create mock lock service."""
    service = AsyncMock()
    return service


@pytest.fixture
def mock_workflow_config():
    """Create mock workflow config service."""
    service = AsyncMock()
    return service


@pytest.fixture
def mock_agent_executor():
    """Create mock agent executor."""
    executor = AsyncMock()
    executor.execute = AsyncMock()
    return executor


@pytest.fixture
def mock_event_bus():
    """Create mock event bus."""
    from codetoreum.infrastructure.event_bus import EventBus
    return EventBus()


@pytest.fixture
def handler(
    mock_board_service,
    mock_lock_service,
    mock_workflow_config,
    mock_agent_executor,
    mock_event_bus,
):
    """Create handler with mocked dependencies."""
    return BoardColumnEventHandler(
        board_service=mock_board_service,
        lock_service=mock_lock_service,
        workflow_config=mock_workflow_config,
        agent_executor=mock_agent_executor,
        event_bus=mock_event_bus,
    )


@pytest.fixture
def sample_workflow_config():
    """Create sample workflow configuration."""
    return BoardWorkflowTemplate(
        id="workflow-1",
        name="SDLC Workflow",
        pipeline_trigger_columns=["In Development"],
        exit_columns=["Done"],
        columns=[
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
                name="In Development",
                type=ColumnType.AUTOMATED,
                agent_id="agent-dev",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="Review",
                type=ColumnType.AUTOMATED,
                agent_id="agent-review",
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
        ],
    )


def create_column_changed_event(
    work_item_id: str,
    board_id: str,
    project_id: str,
    from_column: str = "Backlog",
    to_column: str = "In Development",
    moved_by: str = "human",
) -> WorkItemColumnChanged:
    """Create WorkItemColumnChanged event."""
    return WorkItemColumnChanged(
        aggregate_id=work_item_id,
        payload={
            "work_item_id": work_item_id,
            "board_id": board_id,
            "project_id": project_id,
            "from_column": from_column,
            "to_column": to_column,
            "moved_by": moved_by,
        },
    )


class TestGetEventTypes:
    """Tests for get_event_types method."""

    def test_returns_workitem_column_changed(self, handler):
        """Should return WorkItemColumnChanged event type."""
        event_types = handler.get_event_types()
        assert "WorkItemColumnChanged" in event_types


class TestHandleColumnChangeWithPipelineTrigger:
    """Tests for handle_column_change with pipeline trigger columns."""

    @pytest.mark.asyncio
    async def test_acquires_lock_when_entering_trigger_column(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_agent_executor,
        sample_workflow_config,
    ):
        """Should acquire lock when work item enters trigger column."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_lock_service.try_acquire_lock.return_value = LockAcquisitionResult(
            status=LockStatus.ACQUIRED,
            work_item_id="item-1",
            queue_length=0,
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="In Development",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        mock_lock_service.try_acquire_lock.assert_called_once_with(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

    @pytest.mark.asyncio
    async def test_triggers_agent_when_lock_acquired(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_agent_executor,
        sample_workflow_config,
    ):
        """Should trigger agent when lock is acquired for trigger column."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_lock_service.try_acquire_lock.return_value = LockAcquisitionResult(
            status=LockStatus.ACQUIRED,
            work_item_id="item-1",
            queue_length=0,
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="In Development",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        mock_agent_executor.execute.assert_called_once_with(
            work_item_id="item-1", agent_id="agent-dev"
        )

    @pytest.mark.asyncio
    async def test_queues_when_lock_held(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        sample_workflow_config,
    ):
        """Should queue work item when lock is held."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_lock_service.try_acquire_lock.return_value = LockAcquisitionResult(
            status=LockStatus.QUEUED,
            work_item_id="item-1",
            queue_position=2,
            queue_length=3,
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="In Development",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert - handler should have called try_acquire_lock
        mock_lock_service.try_acquire_lock.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_trigger_agent_when_queued(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_agent_executor,
        sample_workflow_config,
    ):
        """Should not trigger agent when work item is queued."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_lock_service.try_acquire_lock.return_value = LockAcquisitionResult(
            status=LockStatus.QUEUED,
            work_item_id="item-1",
            queue_position=2,
            queue_length=3,
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="In Development",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        mock_agent_executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_already_held_status(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        sample_workflow_config,
        caplog,
    ):
        """Should log when work item already holds lock."""
        # Setup
        caplog.set_level(logging.INFO)
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_lock_service.try_acquire_lock.return_value = LockAcquisitionResult(
            status=LockStatus.ALREADY_HELD,
            work_item_id="item-1",
            queue_length=0,
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="In Development",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        assert "already holds lock" in caplog.text


class TestHandleColumnChangeWithExitColumn:
    """Tests for handle_column_change with exit columns."""

    @pytest.mark.asyncio
    async def test_releases_lock_when_entering_exit_column(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_event_bus,
        sample_workflow_config,
    ):
        """Should release lock when work item enters exit column."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_lock_service.release_lock.return_value = LockReleaseResult(
            released_work_item_id="item-1",
            next_work_item_id="item-2",
            queue_length_after_release=1,
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Review",
            to_column="Done",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        mock_lock_service.release_lock.assert_called_once_with(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
        )

    @pytest.mark.asyncio
    async def test_triggers_agent_for_next_queued_item(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_board_service,
        mock_agent_executor,
        sample_workflow_config,
    ):
        """Should trigger agent for next queued item when lock released."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_lock_service.release_lock.return_value = LockReleaseResult(
            released_work_item_id="item-1",
            next_work_item_id="item-2",
            queue_length_after_release=1,
        )
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-2",
            column_name="In Development",
            position=1,
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Review",
            to_column="Done",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        mock_agent_executor.execute.assert_called_once_with(
            work_item_id="item-2", agent_id="agent-dev"
        )

    @pytest.mark.asyncio
    async def test_does_not_trigger_agent_if_next_item_has_no_agent(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_board_service,
        mock_agent_executor,
        sample_workflow_config,
    ):
        """Should not trigger agent if next item's column has no agent."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_lock_service.release_lock.return_value = LockReleaseResult(
            released_work_item_id="item-1",
            next_work_item_id="item-2",
            queue_length_after_release=1,
        )
        # Next item is in Backlog (no agent)
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-2",
            column_name="Backlog",
            position=0,
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Review",
            to_column="Done",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        mock_agent_executor.execute.assert_not_called()


class TestHandleColumnChangeWithAutomatedColumn:
    """Tests for handle_column_change with automated columns."""

    @pytest.mark.asyncio
    async def test_triggers_agent_for_automated_column(
        self,
        handler,
        mock_workflow_config,
        mock_agent_executor,
        sample_workflow_config,
    ):
        """Should trigger agent when work item enters automated column."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="Review",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        mock_agent_executor.execute.assert_called_once_with(
            work_item_id="item-1", agent_id="agent-review"
        )


class TestHandleColumnChangeWithManualColumn:
    """Tests for handle_column_change with manual columns."""

    @pytest.mark.asyncio
    async def test_does_not_trigger_agent_for_manual_column(
        self,
        handler,
        mock_workflow_config,
        mock_agent_executor,
        sample_workflow_config,
    ):
        """Should not trigger agent for manual column."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="Backlog",
            to_column="Backlog",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        mock_agent_executor.execute.assert_not_called()


class TestTriggerAgent:
    """Tests for _trigger_agent method."""

    @pytest.mark.asyncio
    async def test_trigger_agent_with_none_agent_id(
        self,
        handler,
        mock_agent_executor,
        caplog,
    ):
        """Should log warning when column has no agent assigned."""
        # Setup
        column_config = ColumnTemplate(
            name="No Agent Column",
            type=ColumnType.MANUAL,
            agent_id=None,
            is_pipeline_trigger=False,
            is_exit_column=False,
            position=0,
            auto_progress_on_completion=False,
        )

        # Act
        await handler._trigger_agent("item-1", column_config)

        # Assert
        mock_agent_executor.execute.assert_not_called()
        assert "has no agent assigned" in caplog.text


class TestHandleAgentCompletion:
    """Tests for handle_agent_completion method."""

    @pytest.mark.asyncio
    async def test_auto_progresses_when_successful_and_enabled(
        self,
        handler,
        mock_workflow_config,
        mock_board_service,
        sample_workflow_config,
    ):
        """Should auto-progress to next column on successful completion."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-1",
            column_name="Review",  # Has auto_progress_on_completion=True
            position=2,
        )

        # Act
        await handler.handle_agent_completion(
            work_item_id="item-1",
            board_id="board-1",
            success=True,
        )

        # Assert
        mock_board_service.move_item_to_column.assert_called_once_with(
            "item-1",
            "Done",
            MovedByType.ORCHESTRATOR,
        )

    @pytest.mark.asyncio
    async def test_does_not_progress_when_failed(
        self,
        handler,
        mock_workflow_config,
        mock_board_service,
        sample_workflow_config,
        caplog,
    ):
        """Should not auto-progress when agent fails."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )

        # Act
        await handler.handle_agent_completion(
            work_item_id="item-1",
            board_id="board-1",
            success=False,
        )

        # Assert
        mock_board_service.move_item_to_column.assert_not_called()
        assert "skipping auto-progression" in caplog.text

    @pytest.mark.asyncio
    async def test_does_not_progress_when_disabled(
        self,
        handler,
        mock_workflow_config,
        mock_board_service,
        sample_workflow_config,
    ):
        """Should not auto-progress when column has auto_progress disabled."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-1",
            column_name="In Development",  # Has auto_progress_on_completion=False
            position=1,
        )

        # Act
        await handler.handle_agent_completion(
            work_item_id="item-1",
            board_id="board-1",
            success=True,
        )

        # Assert
        mock_board_service.move_item_to_column.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_no_next_column(
        self,
        handler,
        mock_workflow_config,
        mock_board_service,
        sample_workflow_config,
    ):
        """Should handle case where current column is last column."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-1",
            column_name="Done",  # Last column
            position=3,
        )

        # Act
        await handler.handle_agent_completion(
            work_item_id="item-1",
            board_id="board-1",
            success=True,
        )

        # Assert
        mock_board_service.move_item_to_column.assert_not_called()


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_handles_missing_workflow_config(
        self,
        handler,
        mock_workflow_config,
        caplog,
    ):
        """Should gracefully handle missing workflow config."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = None

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="In Development",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        assert "No workflow config found" in caplog.text

    @pytest.mark.asyncio
    async def test_handles_unknown_column(
        self,
        handler,
        mock_workflow_config,
        sample_workflow_config,
        caplog,
    ):
        """Should gracefully handle unknown column."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="Unknown Column",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        assert "Unknown column" in caplog.text

    @pytest.mark.asyncio
    async def test_handles_agent_execution_error(
        self,
        handler,
        mock_workflow_config,
        mock_agent_executor,
        sample_workflow_config,
        caplog,
    ):
        """Should log agent execution errors without raising."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = (
            sample_workflow_config
        )
        mock_agent_executor.execute.side_effect = RuntimeError("Agent failed")

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="Review",
        )

        # Act - should not raise
        await handler.handle_column_change(event)

        # Assert
        assert "Agent execution failed" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_method_logs_unexpected_event_type(
        self,
        handler,
        caplog,
    ):
        """Should log when receiving unexpected event type."""
        from codetoreum.domain.events import WorkItemCreated

        event = WorkItemCreated(
            aggregate_id="item-1",
            payload={"title": "Test"},
        )

        # Act
        await handler.handle(event)

        # Assert
        assert "unexpected event type" in caplog.text
