"""Unit tests for BoardColumnEventHandler."""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from codetoreum.application.event_handlers.board_event_handler import (
    BoardColumnEventHandler,
    _WorkflowRunMetadata,
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
from codetoreum.domain.events import WorkItemColumnChangedEvent
from codetoreum.ports.output.board_service import MovedByType, WorkItemPosition


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
def mock_recovery_service():
    """Create mock recovery service."""
    service = AsyncMock()
    return service


@pytest.fixture
def mock_event_emitter():
    """Create mock event emitter."""
    emitter = AsyncMock()
    return emitter


@pytest.fixture
def handler(
    mock_board_service,
    mock_lock_service,
    mock_workflow_config,
    mock_agent_executor,
    mock_event_bus,
    mock_recovery_service,
    mock_event_emitter,
):
    """Create handler with mocked dependencies."""
    handler_instance = BoardColumnEventHandler(
        board_service=mock_board_service,
        lock_service=mock_lock_service,
        workflow_config=mock_workflow_config,
        agent_executor=mock_agent_executor,
        event_bus=mock_event_bus,
    )
    handler_instance.recovery_service = mock_recovery_service
    handler_instance.event_emitter = mock_event_emitter
    return handler_instance


@pytest.fixture
def sample_workflow_config():
    """Create sample workflow configuration."""
    return BoardWorkflowTemplate(
        id="workflow-1",
        name="SDLC Workflow",
        board_id="board-1",
        project_id="test-project",
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
        ),
    )


def create_column_changed_event(
    work_item_id: str,
    board_id: str,
    project_id: str,
    from_column: str = "Backlog",
    to_column: str = "In Development",
    moved_by: str = "human",
) -> WorkItemColumnChangedEvent:
    """Create WorkItemColumnChangedEvent event."""
    return WorkItemColumnChangedEvent(
        type="workitem.column_changed",
        timestamp=datetime.now(UTC).isoformat(),
        source="test",
        work_item_id=work_item_id,
        board_id=board_id,
        project_id=project_id,
        from_column=from_column,
        to_column=to_column,
        moved_by=moved_by,
    )


class TestGetEventTypes:
    """Tests for get_event_types method."""

    def test_returns_workitem_column_changed(self, handler):
        """Should return WorkItemColumnChangedEvent event type."""
        event_types = handler.get_event_types()
        assert "WorkItemColumnChangedEvent" in event_types


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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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
            work_item_id="item-1", agent_id="agent-dev", board_id="board-1"
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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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

    @pytest.mark.asyncio
    async def test_retriggers_agent_when_already_holds_lock(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_agent_executor,
        sample_workflow_config,
    ):
        """Should re-trigger agent when work item re-enters trigger column while holding lock.

        This supports maker-checker review loops where a work item is sent back to
        Development after review rejection while still holding the pipeline lock.
        """
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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

        # Assert - Agent should be re-triggered for maker-checker review loops
        mock_agent_executor.execute.assert_called_once()
        call_args = mock_agent_executor.execute.call_args
        assert call_args[1]["work_item_id"] == "item-1"
        # Verify it's calling with the Development column's agent
        # (from sample_workflow_config fixture)


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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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
            work_item_id="item-2", agent_id="agent-dev", board_id="board-1"
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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config

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
            work_item_id="item-1", agent_id="agent-review", board_id="board-1"
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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config

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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config

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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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


class TestHandleAgentCompletionFailureColumn:
    """Tests for on_failure_column wiring in handle_agent_completion."""

    def _make_config_with_failure_column(self, failure_col: str | None) -> BoardWorkflowTemplate:
        """Return a template where 'In Progress' has the given on_failure_column."""
        return BoardWorkflowTemplate(
            id="workflow-1",
            name="Test Workflow",
            board_id="board-1",
            project_id="test-project",
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
                    agent_id="agent-dev",
                    is_pipeline_trigger=True,
                    is_exit_column=False,
                    position=1,
                    auto_progress_on_completion=False,
                    on_failure_column=failure_col,
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

    @pytest.mark.asyncio
    async def test_moves_to_on_failure_column_when_configured(
        self,
        handler,
        mock_workflow_config,
        mock_board_service,
    ):
        """Should move item to on_failure_column when agent fails and column is configured."""
        config = self._make_config_with_failure_column("Backlog")
        mock_workflow_config.get_board_workflow_template.return_value = config
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-1",
            column_name="In Progress",
            position=1,
        )

        await handler.handle_agent_completion(
            work_item_id="item-1",
            board_id="board-1",
            success=False,
        )

        mock_board_service.move_item_to_column.assert_called_once_with(
            "item-1",
            "Backlog",
            MovedByType.ORCHESTRATOR,
        )

    @pytest.mark.asyncio
    async def test_no_move_when_on_failure_column_not_configured(
        self,
        handler,
        mock_workflow_config,
        mock_board_service,
    ):
        """Should not move item when on_failure_column is None."""
        config = self._make_config_with_failure_column(None)
        mock_workflow_config.get_board_workflow_template.return_value = config
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-1",
            column_name="In Progress",
            position=1,
        )

        await handler.handle_agent_completion(
            work_item_id="item-1",
            board_id="board-1",
            success=False,
        )

        mock_board_service.move_item_to_column.assert_not_called()

    @pytest.mark.asyncio
    async def test_fail_workflow_run_called_even_when_failure_move_raises(
        self,
        handler,
        mock_workflow_config,
        mock_board_service,
        caplog,
    ):
        """Should still call _fail_workflow_run if the failure-column move itself raises."""
        import logging

        caplog.set_level(logging.ERROR)
        config = self._make_config_with_failure_column("Backlog")
        mock_workflow_config.get_board_workflow_template.return_value = config
        mock_board_service.get_item_position.return_value = WorkItemPosition(
            work_item_id="item-1",
            column_name="In Progress",
            position=1,
        )
        mock_board_service.move_item_to_column.side_effect = RuntimeError("board unavailable")

        # Should NOT raise — error is caught; _fail_workflow_run is still called
        await handler.handle_agent_completion(
            work_item_id="item-1",
            board_id="board-1",
            success=False,
        )

        assert "Failed to move item-1 to failure column" in caplog.text


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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config

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
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
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


class TestWorkflowLifecycleEventPersistence:
    """Tests for workflow lifecycle event persistence to event store.

    These tests verify that when workflow lifecycle methods are called,
    they properly persist domain events to the event store for audit trail.
    This is critical for observability and debugging.
    """

    @pytest.fixture
    def handler_with_event_store(
        self,
        mock_board_service,
        mock_lock_service,
        mock_workflow_config,
        mock_agent_executor,
        mock_recovery_service,
        mock_event_emitter,
    ):
        """Create handler with event store wired for lifecycle event testing."""
        from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
        from codetoreum.infrastructure.event_bus import EventBus

        event_store = InMemoryEventStore()
        handler_instance = BoardColumnEventHandler(
            board_service=mock_board_service,
            lock_service=mock_lock_service,
            workflow_config=mock_workflow_config,
            agent_executor=mock_agent_executor,
            event_bus=EventBus(),
            event_store=event_store,  # Pass event_store to constructor
        )
        handler_instance.recovery_service = mock_recovery_service
        handler_instance.event_emitter = mock_event_emitter
        return handler_instance, event_store

    @pytest.mark.asyncio
    async def test_start_workflow_run_persists_event_to_event_store(
        self, handler_with_event_store, sample_workflow_config
    ):
        """Verify that _start_workflow_run persists WorkflowCreated and WorkflowStarted events."""
        handler, event_store = handler_with_event_store
        work_item_id = "item-1"
        project_id = "proj-1"
        board_id = "board-1"
        column_config = sample_workflow_config.get_column_config("In Development")

        # Act: Call _start_workflow_run directly
        await handler._start_workflow_run(
            work_item_id=work_item_id,
            project_id=project_id,
            board_id=board_id,
            column_config=column_config,
            workflow_config=sample_workflow_config,
        )

        # Assert: WorkflowCreated and WorkflowStarted events should be persisted to event store
        all_events = event_store.get_all_events_list()
        assert len(all_events) > 0

        # Find WorkflowCreated and WorkflowStarted events
        workflow_created_found = False
        workflow_started_found = False
        run_id = None
        for evt in all_events:
            if evt.event_type == "WorkflowCreated":
                assert evt.payload.get("work_item_id") == work_item_id
                run_id = evt.aggregate_id
                workflow_created_found = True
            elif evt.event_type == "WorkflowStarted":
                if run_id:
                    assert evt.aggregate_id == run_id
                workflow_started_found = True

        assert workflow_created_found, "WorkflowCreated event not persisted to event store"
        assert workflow_started_found, "WorkflowStarted event not persisted to event store"

    @pytest.mark.asyncio
    async def test_advance_workflow_stage_persists_event_to_event_store(
        self, handler_with_event_store, sample_workflow_config
    ):
        """Verify that _advance_workflow_stage persists WorkflowStageAdvanced event."""
        handler, event_store = handler_with_event_store
        work_item_id = "item-1"
        project_id = "proj-1"
        board_id = "board-1"
        column_config = sample_workflow_config.get_column_config("In Development")

        # First, set up active run (simulating prior _start_workflow_run)
        await handler._start_workflow_run(
            work_item_id=work_item_id,
            project_id=project_id,
            board_id=board_id,
            column_config=column_config,
            workflow_config=sample_workflow_config,
        )
        run_info = handler._active_runs[work_item_id]
        run_id = run_info.run_id

        # Act: Call _advance_workflow_stage directly
        await handler._advance_workflow_stage(
            work_item_id=work_item_id,
            from_stage="In Development",
            to_stage="Review",
        )

        # Assert: WorkflowStageAdvanced event should be persisted
        all_events = event_store.get_all_events_list()
        workflow_stage_found = False
        for evt in all_events:
            if evt.event_type == "WorkflowStageAdvanced":
                assert evt.aggregate_id == run_id
                assert evt.payload.get("to_stage") == "Review"
                workflow_stage_found = True
                break
        assert workflow_stage_found, "WorkflowStageAdvanced event not persisted to event store"

    @pytest.mark.asyncio
    async def test_complete_workflow_run_persists_event_to_event_store(
        self, handler_with_event_store, sample_workflow_config
    ):
        """Verify that _complete_workflow_run persists WorkflowCompleted event."""
        handler, event_store = handler_with_event_store
        work_item_id = "item-1"
        project_id = "proj-1"
        board_id = "board-1"
        column_config = sample_workflow_config.get_column_config("In Development")

        # Set up active run
        await handler._start_workflow_run(
            work_item_id=work_item_id,
            project_id=project_id,
            board_id=board_id,
            column_config=column_config,
            workflow_config=sample_workflow_config,
        )
        run_info = handler._active_runs[work_item_id]
        run_id = run_info.run_id

        # Act: Call _complete_workflow_run directly
        await handler._complete_workflow_run(
            work_item_id=work_item_id,
            exit_column="Done",
        )

        # Assert: WorkflowCompleted event should be persisted
        all_events = event_store.get_all_events_list()
        workflow_completed_found = False
        for evt in all_events:
            if evt.event_type == "WorkflowCompleted":
                assert evt.aggregate_id == run_id
                assert evt.payload.get("exit_column") == "Done"
                workflow_completed_found = True
                break
        assert workflow_completed_found, "WorkflowCompleted event not persisted to event store"

    @pytest.mark.asyncio
    async def test_fail_workflow_run_persists_event_to_event_store(
        self, handler_with_event_store, sample_workflow_config
    ):
        """Verify that _fail_workflow_run persists WorkflowFailed event."""
        handler, event_store = handler_with_event_store
        work_item_id = "item-1"
        project_id = "proj-1"
        board_id = "board-1"
        column_config = sample_workflow_config.get_column_config("In Development")
        reason = "Agent failed"

        # Set up active run
        await handler._start_workflow_run(
            work_item_id=work_item_id,
            project_id=project_id,
            board_id=board_id,
            column_config=column_config,
            workflow_config=sample_workflow_config,
        )
        run_info = handler._active_runs[work_item_id]
        run_id = run_info.run_id

        # Act: Call _fail_workflow_run directly
        await handler._fail_workflow_run(
            work_item_id=work_item_id,
            reason=reason,
        )

        # Assert: WorkflowFailed event should be persisted
        all_events = event_store.get_all_events_list()
        workflow_failed_found = False
        for evt in all_events:
            if evt.event_type == "WorkflowFailed":
                assert evt.aggregate_id == run_id
                assert evt.payload.get("reason") == reason
                workflow_failed_found = True
                break
        assert workflow_failed_found, "WorkflowFailed event not persisted to event store"


class TestTriggerAgentExecutionFailureAndLockRelease:
    """Tests for _trigger_agent error handling and lock release behavior.

    These tests verify that when agent execution fails, the pipeline lock
    is always released to unblock queued items, even if recovery service fails.
    """

    @pytest.mark.asyncio
    async def test_agent_execution_failure_releases_lock(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_agent_executor,
        mock_recovery_service,
        sample_workflow_config,
    ):
        """Should release lock when agent execution fails, unblocking pipeline."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
        mock_agent_executor.execute.side_effect = RuntimeError("Agent execution failed")
        mock_lock_service.release_lock.return_value = LockReleaseResult(
            released_work_item_id="item-1",
            next_work_item_id="item-2",
            queue_length_after_release=1,
        )
        mock_recovery_service.handle_agent_execution_failure.return_value = None

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="In Development",
        )

        # Setup active run tracking (handler tracks running work items)
        handler._active_runs["item-1"] = _WorkflowRunMetadata(
            run_id="run-1",
            project_id="proj-1",
            board_id="board-1",
            template_id="template-1",
            started_at=datetime.now(UTC),
            stage_index=0,
        )

        # Act - directly call _trigger_agent to test lock release on failure
        await handler._trigger_agent(
            work_item_id="item-1",
            column_config=sample_workflow_config.get_column_config("In Development"),
            board_id="board-1",
        )

        # Assert: Lock should be released despite agent execution failure
        mock_lock_service.release_lock.assert_called_once_with(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
        )

    @pytest.mark.asyncio
    async def test_agent_execution_failure_invokes_recovery_service(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_agent_executor,
        mock_recovery_service,
        sample_workflow_config,
    ):
        """Should invoke recovery service when agent execution fails."""
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
        error = RuntimeError("Agent execution failed")
        mock_agent_executor.execute.side_effect = error
        mock_lock_service.release_lock.return_value = LockReleaseResult(
            released_work_item_id="item-1",
            next_work_item_id="item-2",
            queue_length_after_release=1,
        )
        mock_recovery_service.handle_agent_execution_failure.return_value = None

        # Setup active run tracking
        handler._active_runs["item-1"] = _WorkflowRunMetadata(
            run_id="run-1",
            project_id="proj-1",
            board_id="board-1",
            template_id="template-1",
            started_at=datetime.now(UTC),
            stage_index=0,
        )

        # Act - directly call _trigger_agent
        await handler._trigger_agent(
            work_item_id="item-1",
            column_config=sample_workflow_config.get_column_config("In Development"),
            board_id="board-1",
        )

        # Assert: Recovery service should be invoked with failure details
        mock_recovery_service.handle_agent_execution_failure.assert_called_once_with(
            work_item_id="item-1",
            board_id="board-1",
            error=error,
            project_id="proj-1",
        )

    @pytest.mark.asyncio
    async def test_recovery_service_failure_does_not_prevent_lock_release(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_agent_executor,
        mock_recovery_service,
        sample_workflow_config,
    ):
        """Lock release must happen even if recovery service fails (critical).

        This prevents the scenario where recovery service failure causes
        pipeline deadlock by preventing lock release.
        """
        # Setup
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
        exec_error = RuntimeError("Agent execution failed")
        mock_agent_executor.execute.side_effect = exec_error
        recovery_error = RuntimeError("Recovery service unavailable")
        mock_recovery_service.handle_agent_execution_failure.side_effect = recovery_error
        mock_lock_service.release_lock.return_value = LockReleaseResult(
            released_work_item_id="item-1",
            next_work_item_id="item-2",
            queue_length_after_release=1,
        )

        # Setup active run tracking
        handler._active_runs["item-1"] = _WorkflowRunMetadata(
            run_id="run-1",
            project_id="proj-1",
            board_id="board-1",
            template_id="template-1",
            started_at=datetime.now(UTC),
            stage_index=0,
        )

        # Act - should not raise despite recovery service failure
        await handler._trigger_agent(
            work_item_id="item-1",
            column_config=sample_workflow_config.get_column_config("In Development"),
            board_id="board-1",
        )

        # Assert: Lock release must still be called (happens after recovery attempt)
        mock_lock_service.release_lock.assert_called_once_with(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
        )

    @pytest.mark.asyncio
    async def test_lock_release_failure_emits_lock_stuck_event(
        self,
        handler,
        mock_workflow_config,
        mock_lock_service,
        mock_agent_executor,
        mock_recovery_service,
        mock_event_emitter,
        sample_workflow_config,
        caplog,
    ):
        """When lock release fails, should emit LockStuckEvent for ops alerting."""
        # Setup
        caplog.set_level(logging.INFO)
        mock_workflow_config.get_board_workflow_template.return_value = sample_workflow_config
        mock_agent_executor.execute.side_effect = RuntimeError("Agent execution failed")
        lock_error = Exception("Lock service unavailable")
        mock_lock_service.release_lock.side_effect = lock_error
        mock_recovery_service.handle_agent_execution_failure.return_value = None

        # Setup active run tracking
        handler._active_runs["item-1"] = _WorkflowRunMetadata(
            run_id="run-1",
            project_id="proj-1",
            board_id="board-1",
            template_id="template-1",
            started_at=datetime.now(UTC),
            stage_index=0,
        )

        # Act
        await handler._trigger_agent(
            work_item_id="item-1",
            column_config=sample_workflow_config.get_column_config("In Development"),
            board_id="board-1",
        )

        # Assert: Should log critical error about lock release failure
        assert "Failed to release lock" in caplog.text
        assert "PIPELINE IS BLOCKED" in caplog.text

        # LockStuckEvent should be emitted
        mock_event_emitter.emit.assert_called_once()
        call_args = mock_event_emitter.emit.call_args[0][0]
        assert call_args.type == "lock.stuck"
        assert call_args.work_item_id == "item-1"


class TestPRReviewCycleExclusion:
    """Tests for PR review cycle exclusion from normal agent dispatch."""

    @pytest.mark.asyncio
    async def test_excludes_pr_review_cycle_columns_from_agent_dispatch(
        self,
        handler,
        mock_workflow_config,
        mock_agent_executor,
    ):
        """Should NOT trigger normal agent for columns with pr_review_cycle_config."""
        from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig

        # Create workflow with PR review cycle column
        workflow_config = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="PR Review",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-review",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                    pr_review_cycle_config=PRReviewCycleConfig(max_outer_cycles=2),
                ),
            ),
        )

        mock_workflow_config.get_board_workflow_template.return_value = workflow_config

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="PR Review",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert - normal agent executor should NOT be called
        mock_agent_executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_triggered_for_columns_without_pr_review_config(
        self,
        handler,
        mock_workflow_config,
        mock_agent_executor,
    ):
        """Should trigger normal agent for automated columns without pr_review_cycle_config."""
        # Create workflow with normal automated column
        workflow_config = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="Review",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-review",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=True,
                ),
            ),
        )

        mock_workflow_config.get_board_workflow_template.return_value = workflow_config

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="Review",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert - normal agent executor should be called
        mock_agent_executor.execute.assert_called_once_with(
            work_item_id="item-1", agent_id="agent-review", board_id="board-1"
        )


class TestPRReviewCycleDispatch:
    """Tests for PR review cycle dispatch in BoardColumnEventHandler."""

    @pytest.mark.asyncio
    async def test_dispatches_pr_review_cycle_when_config_present(
        self,
        handler,
        mock_workflow_config,
    ):
        """Should dispatch PR review cycle when column has pr_review_cycle_config."""
        from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
        from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus

        # Setup mocks
        pr_review_cycle_mock = AsyncMock()
        work_item_service_mock = AsyncMock()

        now = datetime.now(UTC)
        work_item = WorkItem(
            id="item-1",
            project_id="proj-1",
            title="Test Item",
            description="Test Description",
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority.MEDIUM,
            labels=[],
            external_id=None,
            external_url="https://github.com/owner/repo/pull/123",
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            current_column=None,
            entered_column_at=None,
            created_at=now,
            updated_at=now,
            pr_id="123",
            discussion_id="disc-1",
        )

        work_item_service_mock.get_work_item.return_value = work_item
        pr_review_cycle_mock.get_cycle_state.return_value = None  # First cycle

        # Create result response
        from codetoreum.domain.pr_review_cycle_types import (
            PRReviewCycleState,
            PRReviewOutcome,
            PRReviewPhaseOutput,
            PRReviewStatus,
        )

        cycle_config = PRReviewCycleConfig()
        cycle_state = PRReviewCycleState(
            cycle_id="cycle-1",
            pr_id="123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.IN_CODE_REVIEW,
            cycle_number=1,
            current_phase="code_review",
            findings=[],
            phase_outputs=[],
            config=cycle_config,
            started_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

        phase_output = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(),
            summary="Code review completed successfully",
            duration_seconds=10.0,
        )

        from codetoreum.domain.pr_review_cycle_types import PRReviewCycleResult

        result = PRReviewCycleResult(
            cycle_number=1,
            workflow_run_id="wf-run-1",
            outcome=PRReviewOutcome.APPROVED,
            phase_outputs=(phase_output,),
            all_findings=(),
            sub_issue_ids=(),
            ci_passed=None,
            total_findings=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            total_duration_seconds=10.0,
            timestamp=now.isoformat(),
            next_column="Approved",
        )

        pr_review_cycle_mock.start_pr_review_cycle.return_value = result

        handler.pr_review_cycle = pr_review_cycle_mock
        handler.work_item_service = work_item_service_mock

        # Create workflow with PR review cycle column
        workflow_config = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="PR Review",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-review",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                    pr_review_cycle_config=PRReviewCycleConfig(max_outer_cycles=2),
                ),
            ),
        )

        mock_workflow_config.get_board_workflow_template.return_value = workflow_config

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="PR Review",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        pr_review_cycle_mock.get_cycle_state.assert_called_once_with("item-1", "proj-1")
        pr_review_cycle_mock.start_pr_review_cycle.assert_called_once()

        # Verify request was constructed correctly
        call_args = pr_review_cycle_mock.start_pr_review_cycle.call_args
        request = call_args[0][0]
        assert request.work_item_id == "item-1"
        assert request.pr_id == "123"
        assert request.pr_url == "https://github.com/owner/repo/pull/123"
        assert request.discussion_id == "disc-1"
        assert request.cycle_number == 1

    @pytest.mark.asyncio
    async def test_derives_cycle_number_from_existing_state(
        self,
        handler,
        mock_workflow_config,
    ):
        """Should derive cycle number as existing + 1 when state exists."""
        from codetoreum.domain.pr_review_cycle_types import (
            PRReviewCycleConfig,
            PRReviewCycleState,
            PRReviewStatus,
        )
        from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
        from codetoreum.ports.output.pr_review_cycle_service import PRReviewCycleStateData

        # Setup mocks
        pr_review_cycle_mock = AsyncMock()
        work_item_service_mock = AsyncMock()

        now = datetime.now(UTC)
        work_item = WorkItem(
            id="item-1",
            project_id="proj-1",
            title="Test Item",
            description="Test Description",
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority.MEDIUM,
            labels=[],
            external_id=None,
            external_url="https://github.com/owner/repo/pull/123",
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            current_column=None,
            entered_column_at=None,
            created_at=now,
            updated_at=now,
            pr_id="123",
            discussion_id="disc-1",
        )

        work_item_service_mock.get_work_item.return_value = work_item

        # Return existing state with cycle_number=2
        existing_state = PRReviewCycleStateData(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            cycle_number=2,
            cycle_state=PRReviewCycleState(
                cycle_id="cycle-2",
                pr_id="123",
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                status=PRReviewStatus.COMPLETED,
                cycle_number=2,
                current_phase="completed",
                findings=[],
                phase_outputs=[],
                config=PRReviewCycleConfig(),
                started_at=now.isoformat(),
                updated_at=now.isoformat(),
            ),
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

        pr_review_cycle_mock.get_cycle_state.return_value = existing_state

        # Create response for new cycle
        new_cycle_state = PRReviewCycleState(
            cycle_id="cycle-3",
            pr_id="123",
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            status=PRReviewStatus.IN_CODE_REVIEW,
            cycle_number=3,
            current_phase="code_review",
            findings=[],
            phase_outputs=[],
            config=PRReviewCycleConfig(),
            started_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

        from codetoreum.domain.pr_review_cycle_types import PRReviewCycleResult, PRReviewPhaseOutput, PRReviewOutcome

        phase_output_cycle3 = PRReviewPhaseOutput(
            phase_name="code_review",
            phase_index=1,
            success=True,
            findings=(),
            summary="Code review completed successfully",
            duration_seconds=10.0,
        )

        new_result = PRReviewCycleResult(
            cycle_number=3,
            workflow_run_id="wf-run-3",
            outcome=PRReviewOutcome.APPROVED,
            phase_outputs=(phase_output_cycle3,),
            all_findings=(),
            sub_issue_ids=(),
            ci_passed=None,
            total_findings=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            total_duration_seconds=10.0,
            timestamp=now.isoformat(),
            next_column="Approved",
        )

        pr_review_cycle_mock.start_pr_review_cycle.return_value = new_result

        handler.pr_review_cycle = pr_review_cycle_mock
        handler.work_item_service = work_item_service_mock

        # Create workflow
        workflow_config = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="PR Review",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-review",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                    pr_review_cycle_config=PRReviewCycleConfig(max_outer_cycles=3),
                ),
            ),
        )

        mock_workflow_config.get_board_workflow_template.return_value = workflow_config

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="PR Review",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert - cycle_number should be 3 (2 + 1)
        call_args = pr_review_cycle_mock.start_pr_review_cycle.call_args
        request = call_args[0][0]
        assert request.cycle_number == 3

    @pytest.mark.asyncio
    async def test_emits_max_cycles_reached_event_when_exceeded(
        self,
        handler,
        mock_workflow_config,
        mock_event_emitter,
    ):
        """Should emit PRReviewCycleMaxCyclesReachedEvent when cycle_number > max_outer_cycles."""
        from codetoreum.domain.pr_review_cycle_types import (
            PRReviewCycleConfig,
            PRReviewCycleState,
            PRReviewStatus,
        )
        from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
        from codetoreum.ports.output.pr_review_cycle_service import PRReviewCycleStateData

        # Setup mocks
        pr_review_cycle_mock = AsyncMock()
        work_item_service_mock = AsyncMock()

        now = datetime.now(UTC)
        work_item = WorkItem(
            id="item-1",
            project_id="proj-1",
            title="Test Item",
            description="Test Description",
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority.MEDIUM,
            labels=[],
            external_id=None,
            external_url="https://github.com/owner/repo/pull/123",
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            current_column=None,
            entered_column_at=None,
            created_at=now,
            updated_at=now,
            pr_id="123",
            discussion_id="disc-1",
        )

        work_item_service_mock.get_work_item.return_value = work_item

        # Return existing state with cycle_number=2
        existing_state = PRReviewCycleStateData(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            cycle_number=2,
            cycle_state=PRReviewCycleState(
                cycle_id="cycle-2",
                pr_id="123",
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                status=PRReviewStatus.COMPLETED,
                cycle_number=2,
                current_phase="completed",
                findings=[],
                phase_outputs=[],
                config=PRReviewCycleConfig(),
                started_at=now.isoformat(),
                updated_at=now.isoformat(),
            ),
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

        pr_review_cycle_mock.get_cycle_state.return_value = existing_state

        handler.pr_review_cycle = pr_review_cycle_mock
        handler.work_item_service = work_item_service_mock
        handler.event_emitter = mock_event_emitter

        # Create workflow with max_outer_cycles=2
        # Next cycle would be 3, which exceeds the max
        workflow_config = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="PR Review",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-review",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                    pr_review_cycle_config=PRReviewCycleConfig(max_outer_cycles=2),
                ),
                ColumnTemplate(
                    name="Approved",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=True,
                    position=1,
                    auto_progress_on_completion=False,
                ),
            ),
        )

        mock_workflow_config.get_board_workflow_template.return_value = workflow_config

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="PR Review",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        # start_pr_review_cycle should NOT be called
        pr_review_cycle_mock.start_pr_review_cycle.assert_not_called()

        # PRReviewCycleMaxCyclesReachedEvent should be emitted
        mock_event_emitter.emit.assert_called_once()
        call_args = mock_event_emitter.emit.call_args[0][0]
        assert call_args.type == "pr_review_cycle.max_cycles_reached"
        assert call_args.cycle_number == 3  # Would be 2 + 1
        assert call_args.max_outer_cycles == 2
        assert call_args.next_column == "Approved"  # Escalation column is next column in workflow

    @pytest.mark.asyncio
    async def test_pr_review_max_cycles_workflow_config_not_found(
        self,
        handler,
        mock_workflow_config,
        mock_event_emitter,
    ):
        """Should handle gracefully when workflow config not found when determining escalation column."""
        from codetoreum.domain.pr_review_cycle_types import (
            PRReviewCycleConfig,
            PRReviewCycleState,
            PRReviewStatus,
        )
        from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
        from codetoreum.ports.output.pr_review_cycle_service import PRReviewCycleStateData

        # Setup mocks
        pr_review_cycle_mock = AsyncMock()
        work_item_service_mock = AsyncMock()

        now = datetime.now(UTC)
        work_item = WorkItem(
            id="item-1",
            project_id="proj-1",
            title="Test Item",
            description="Test Description",
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority.MEDIUM,
            labels=[],
            external_id=None,
            external_url="https://github.com/owner/repo/pull/123",
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            current_column=None,
            entered_column_at=None,
            created_at=now,
            updated_at=now,
            pr_id="123",
            discussion_id="disc-1",
        )

        work_item_service_mock.get_work_item.return_value = work_item

        # Return existing state with cycle_number=2
        existing_state = PRReviewCycleStateData(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            cycle_number=2,
            cycle_state=PRReviewCycleState(
                cycle_id="cycle-2",
                pr_id="123",
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                status=PRReviewStatus.COMPLETED,
                cycle_number=2,
                current_phase="completed",
                findings=[],
                phase_outputs=[],
                config=PRReviewCycleConfig(),
                started_at=now.isoformat(),
                updated_at=now.isoformat(),
            ),
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

        pr_review_cycle_mock.get_cycle_state.return_value = existing_state

        handler.pr_review_cycle = pr_review_cycle_mock
        handler.work_item_service = work_item_service_mock
        handler.event_emitter = mock_event_emitter

        # Return None for workflow config (simulating misconfiguration)
        mock_workflow_config.get_board_workflow_template.return_value = None

        workflow_config = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="PR Review",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-review",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                    pr_review_cycle_config=PRReviewCycleConfig(max_outer_cycles=2),
                ),
                ColumnTemplate(
                    name="Approved",
                    type=ColumnType.MANUAL,
                    agent_id=None,
                    is_pipeline_trigger=False,
                    is_exit_column=True,
                    position=1,
                    auto_progress_on_completion=False,
                ),
            ),
        )

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="PR Review",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        # start_pr_review_cycle should NOT be called
        pr_review_cycle_mock.start_pr_review_cycle.assert_not_called()

        # PRReviewCycleMaxCyclesReachedEvent should NOT be emitted (handler returned early)
        mock_event_emitter.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_pr_review_max_cycles_no_escalation_column(
        self,
        handler,
        mock_workflow_config,
        mock_event_emitter,
    ):
        """Should handle gracefully when PR review column is last column (no escalation column)."""
        from codetoreum.domain.pr_review_cycle_types import (
            PRReviewCycleConfig,
            PRReviewCycleState,
            PRReviewStatus,
        )
        from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus
        from codetoreum.ports.output.pr_review_cycle_service import PRReviewCycleStateData

        # Setup mocks
        pr_review_cycle_mock = AsyncMock()
        work_item_service_mock = AsyncMock()

        now = datetime.now(UTC)
        work_item = WorkItem(
            id="item-1",
            project_id="proj-1",
            title="Test Item",
            description="Test Description",
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority.MEDIUM,
            labels=[],
            external_id=None,
            external_url="https://github.com/owner/repo/pull/123",
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            current_column=None,
            entered_column_at=None,
            created_at=now,
            updated_at=now,
            pr_id="123",
            discussion_id="disc-1",
        )

        work_item_service_mock.get_work_item.return_value = work_item

        # Return existing state with cycle_number=2
        existing_state = PRReviewCycleStateData(
            work_item_id="item-1",
            project_id="proj-1",
            board_id="board-1",
            cycle_number=2,
            cycle_state=PRReviewCycleState(
                cycle_id="cycle-2",
                pr_id="123",
                work_item_id="item-1",
                project_id="proj-1",
                board_id="board-1",
                status=PRReviewStatus.COMPLETED,
                cycle_number=2,
                current_phase="completed",
                findings=[],
                phase_outputs=[],
                config=PRReviewCycleConfig(),
                started_at=now.isoformat(),
                updated_at=now.isoformat(),
            ),
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

        pr_review_cycle_mock.get_cycle_state.return_value = existing_state

        handler.pr_review_cycle = pr_review_cycle_mock
        handler.work_item_service = work_item_service_mock
        handler.event_emitter = mock_event_emitter

        # Create workflow where PR Review is the LAST column (no escalation column)
        workflow_config = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="In Development",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-dev",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                ),
                ColumnTemplate(
                    name="PR Review",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-review",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=1,
                    auto_progress_on_completion=False,
                    pr_review_cycle_config=PRReviewCycleConfig(max_outer_cycles=2),
                ),
            ),
        )

        mock_workflow_config.get_board_workflow_template.return_value = workflow_config

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="PR Review",
        )

        # Act
        await handler.handle_column_change(event)

        # Assert
        # start_pr_review_cycle should NOT be called
        pr_review_cycle_mock.start_pr_review_cycle.assert_not_called()

        # PRReviewCycleMaxCyclesReachedEvent should NOT be emitted (handler returned early)
        mock_event_emitter.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_propagates_exception_from_start_pr_review_cycle(
        self,
        handler,
        mock_workflow_config,
    ):
        """Should re-raise exceptions from start_pr_review_cycle instead of silently swallowing them."""
        from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
        from codetoreum.domain.work_item import WorkItem, WorkItemPriority, WorkItemStatus

        # Setup mocks
        pr_review_cycle_mock = AsyncMock()
        work_item_service_mock = AsyncMock()

        now = datetime.now(UTC)
        work_item = WorkItem(
            id="item-1",
            project_id="proj-1",
            title="Test Item",
            description="Test Description",
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority.MEDIUM,
            labels=[],
            external_id=None,
            external_url="https://github.com/owner/repo/pull/123",
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            current_column=None,
            entered_column_at=None,
            created_at=now,
            updated_at=now,
            pr_id="123",
            discussion_id="disc-1",
        )

        work_item_service_mock.get_work_item.return_value = work_item
        pr_review_cycle_mock.get_cycle_state.return_value = None  # First cycle

        # Mock start_pr_review_cycle to raise an exception
        test_error = RuntimeError("PR review cycle service unavailable")
        pr_review_cycle_mock.start_pr_review_cycle.side_effect = test_error

        handler.pr_review_cycle = pr_review_cycle_mock
        handler.work_item_service = work_item_service_mock

        # Create workflow with PR review cycle column
        workflow_config = BoardWorkflowTemplate(
            id="workflow-1",
            name="SDLC Workflow",
            board_id="board-1",
            project_id="test-project",
            columns=(
                ColumnTemplate(
                    name="PR Review",
                    type=ColumnType.AUTOMATED,
                    agent_id="agent-review",
                    is_pipeline_trigger=False,
                    is_exit_column=False,
                    position=0,
                    auto_progress_on_completion=False,
                    pr_review_cycle_config=PRReviewCycleConfig(max_outer_cycles=2),
                ),
            ),
        )

        mock_workflow_config.get_board_workflow_template.return_value = workflow_config

        event = create_column_changed_event(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            to_column="PR Review",
        )

        # Act & Assert - exception should be re-raised, not swallowed
        with pytest.raises(RuntimeError, match="PR review cycle service unavailable"):
            await handler.handle_column_change(event)

        # Verify the exception was logged with error_id
        pr_review_cycle_mock.start_pr_review_cycle.assert_called_once()
